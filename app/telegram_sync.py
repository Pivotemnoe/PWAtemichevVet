from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

from app import db
from app.config import Settings
from app.followups import detect_followup_scenario, followup_due_at, followup_payload
from app.security import utc_now, utc_now_iso


URGENCY_TITLES = {
    "green": ("🟢", "Можно наблюдать"),
    "yellow": ("🟡", "Нужна консультация"),
    "red": ("🟥", "Срочно в клинику"),
}

TELEGRAM_SOURCE = "telegram"
PWA_SOURCE = "pwa"


def _bot_db_path(settings: Settings) -> Path | None:
    if not settings.bot_database_path:
        return None
    path = Path(settings.bot_database_path).expanduser()
    return path if path.exists() else None


def _compact(value: str | None) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", str(value or "").casefold())


def _pet_type_key(value: str | None) -> str:
    text = str(value or "").casefold()
    if "кош" in text or "кот" in text or "cat" in text:
        return "cat"
    if "соб" in text or "пес" in text or "пёс" in text or "dog" in text:
        return "dog"
    return _compact(text)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source_id(value: Any) -> str:
    return str(value or "").strip()


def _linked_telegram_account(settings: Settings, pwa_user: dict[str, Any]) -> dict[str, Any] | None:
    return db.get_external_account(settings.database_path, user_id=int(pwa_user["id"]), provider="telegram")


def _linked_telegram_id(settings: Settings, pwa_user: dict[str, Any]) -> int | None:
    account = _linked_telegram_account(settings, pwa_user)
    if not account:
        return None
    try:
        return int(str(account.get("provider_user_id") or "").strip())
    except (TypeError, ValueError):
        return None


def _telegram_user_row(cur: sqlite3.Cursor, telegram_id: int) -> sqlite3.Row | None:
    cur.execute("SELECT id, telegram_id, name, registered_at FROM users WHERE telegram_id = ? LIMIT 1", (int(telegram_id),))
    return cur.fetchone()


def _find_telegram_pet(cur: sqlite3.Cursor, *, owner_id: int, selected_pet: dict[str, Any] | None) -> int | None:
    if not selected_pet:
        return None
    pet_type = _pet_type_key(selected_pet.get("pet_type"))
    pet_name = _compact(selected_pet.get("pet_name"))
    if not pet_name:
        return None

    cur.execute(
        """
        SELECT id, pet_type, pet_name, is_main
        FROM pets
        WHERE owner_id = ?
        ORDER BY is_main DESC, id ASC
        """,
        (int(owner_id),),
    )
    rows = cur.fetchall()
    exact = [
        row
        for row in rows
        if _compact(row["pet_name"]) == pet_name and _pet_type_key(row["pet_type"]) == pet_type
    ]
    if exact:
        return int(exact[0]["id"])

    same_name = [row for row in rows if _compact(row["pet_name"]) == pet_name]
    if len(same_name) == 1:
        return int(same_name[0]["id"])
    return None


def _ensure_bot_column(cur: sqlite3.Cursor, table_name: str, column_name: str, ddl: str) -> None:
    cur.execute(f"PRAGMA table_info({table_name})")
    if not any(row[1] == column_name for row in cur.fetchall()):
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def _ensure_bot_sync_columns(cur: sqlite3.Cursor) -> None:
    for table in ("pets", "reminders", "pet_observations", "pet_measurements"):
        _ensure_bot_column(cur, table, "external_source", "TEXT")
        _ensure_bot_column(cur, table, "external_id", "TEXT")


def _pwa_pet_by_external(cur: sqlite3.Cursor, *, owner_id: int, external_id: Any) -> sqlite3.Row | None:
    cur.execute(
        """
        SELECT *
        FROM pets
        WHERE owner_id = ?
          AND external_source = 'telegram'
          AND external_id = ?
        LIMIT 1
        """,
        (int(owner_id), _source_id(external_id)),
    )
    return cur.fetchone()


def _pwa_external_exists(cur: sqlite3.Cursor, table_name: str, external_id: Any) -> bool:
    cur.execute(
        f"""
        SELECT 1
        FROM {table_name}
        WHERE external_source = 'telegram'
          AND external_id = ?
        LIMIT 1
        """,
        (_source_id(external_id),),
    )
    return cur.fetchone() is not None


def _pwa_has_main_pet(cur: sqlite3.Cursor, owner_id: int) -> bool:
    cur.execute("SELECT 1 FROM pets WHERE owner_id = ? AND is_main = 1 LIMIT 1", (int(owner_id),))
    return cur.fetchone() is not None


def _pwa_find_matching_pet(cur: sqlite3.Cursor, *, owner_id: int, bot_pet: sqlite3.Row) -> sqlite3.Row | None:
    name = _compact(bot_pet["pet_name"])
    pet_type = _pet_type_key(bot_pet["pet_type"])
    if not name:
        return None
    cur.execute(
        """
        SELECT *
        FROM pets
        WHERE owner_id = ?
        ORDER BY is_main DESC, id ASC
        """,
        (int(owner_id),),
    )
    rows = cur.fetchall()
    exact = [
        row
        for row in rows
        if _compact(row["pet_name"]) == name and _pet_type_key(row["pet_type"]) == pet_type
    ]
    if exact:
        return exact[0]
    same_name = [row for row in rows if _compact(row["pet_name"]) == name]
    return same_name[0] if len(same_name) == 1 else None


def _link_or_insert_pwa_pet(
    cur: sqlite3.Cursor,
    *,
    owner_id: int,
    bot_pet: sqlite3.Row,
    counts: dict[str, int],
) -> int:
    bot_pet_id = int(bot_pet["id"])
    existing = _pwa_pet_by_external(cur, owner_id=owner_id, external_id=bot_pet_id)
    if existing:
        return int(existing["id"])

    matched = _pwa_find_matching_pet(cur, owner_id=owner_id, bot_pet=bot_pet)
    make_main = bool(int(bot_pet["is_main"] or 0)) and not _pwa_has_main_pet(cur, owner_id)
    if matched:
        updates: dict[str, Any] = {
            "external_source": TELEGRAM_SOURCE,
            "external_id": _source_id(bot_pet_id),
        }
        for field in ("birth_year", "birth_month", "birth_day", "birth_precision", "sex", "weight_kg", "breed"):
            if matched[field] in (None, "") and bot_pet[field] not in (None, ""):
                updates[field] = bot_pet[field]
        if make_main:
            cur.execute("UPDATE pets SET is_main = 0 WHERE owner_id = ?", (int(owner_id),))
            updates["is_main"] = 1
        assignments = ", ".join(f"{key} = ?" for key in updates)
        cur.execute(f"UPDATE pets SET {assignments} WHERE id = ?", (*updates.values(), int(matched["id"])))
        counts["pets_linked"] += 1
        return int(matched["id"])

    if make_main:
        cur.execute("UPDATE pets SET is_main = 0 WHERE owner_id = ?", (int(owner_id),))
    cur.execute(
        """
        INSERT INTO pets (
            owner_id, pet_type, pet_name, added_at, birth_year, birth_month,
            birth_day, birth_precision, sex, weight_kg, breed, is_main,
            external_source, external_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'telegram', ?)
        """,
        (
            int(owner_id),
            bot_pet["pet_type"] or "питомец",
            bot_pet["pet_name"] or "Питомец",
            bot_pet["added_at"] or utc_now_iso(),
            bot_pet["birth_year"],
            bot_pet["birth_month"],
            bot_pet["birth_day"],
            bot_pet["birth_precision"],
            bot_pet["sex"],
            bot_pet["weight_kg"],
            bot_pet["breed"],
            1 if make_main or not _pwa_has_main_pet(cur, owner_id) else 0,
            _source_id(bot_pet_id),
        ),
    )
    counts["pets_imported"] += 1
    return int(cur.lastrowid)


def _import_telegram_pets(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    bot_user_id: int,
    pwa_user_id: int,
    counts: dict[str, int],
) -> dict[int, int]:
    bot_cur.execute(
        """
        SELECT
            id, pet_type, pet_name, added_at, birth_year, birth_month, birth_day,
            birth_precision, sex, weight_kg, breed, is_main
        FROM pets
        WHERE owner_id = ?
        ORDER BY is_main DESC, id ASC
        """,
        (int(bot_user_id),),
    )
    mapping: dict[int, int] = {}
    for bot_pet in bot_cur.fetchall():
        mapping[int(bot_pet["id"])] = _link_or_insert_pwa_pet(
            pwa_cur,
            owner_id=pwa_user_id,
            bot_pet=bot_pet,
            counts=counts,
        )
    return mapping


def _import_telegram_reminders(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    bot_user_id: int,
    pwa_user_id: int,
    pet_map: dict[int, int],
    counts: dict[str, int],
) -> None:
    bot_cur.execute(
        """
        SELECT id, pet_id, reminder_type, title, due_date, due_time, periodicity,
               notes, is_active, created_at, updated_at
        FROM reminders
        WHERE user_id = ?
        ORDER BY id ASC
        LIMIT 500
        """,
        (int(bot_user_id),),
    )
    for item in bot_cur.fetchall():
        external_id = _source_id(item["id"])
        pet_id = pet_map.get(int(item["pet_id"])) if item["pet_id"] is not None else None
        pwa_cur.execute(
            "SELECT id FROM reminders WHERE external_source = 'telegram' AND external_id = ? LIMIT 1",
            (external_id,),
        )
        existing = pwa_cur.fetchone()
        if existing:
            pwa_cur.execute(
                """
                UPDATE reminders
                SET user_id = ?, pet_id = ?, reminder_type = ?, title = ?, due_date = ?,
                    due_time = ?, periodicity = ?, notes = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    int(pwa_user_id),
                    pet_id,
                    item["reminder_type"] or "custom",
                    item["title"] or "Напоминание",
                    item["due_date"] or "",
                    item["due_time"],
                    item["periodicity"] or "once",
                    item["notes"],
                    int(item["is_active"] or 0),
                    item["updated_at"] or utc_now_iso(),
                    int(existing["id"]),
                ),
            )
            continue
        pwa_cur.execute(
            """
            INSERT INTO reminders (
                user_id, pet_id, reminder_type, title, due_date, due_time, periodicity,
                notes, is_active, created_at, updated_at, external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'telegram', ?)
            """,
            (
                int(pwa_user_id),
                pet_id,
                item["reminder_type"] or "custom",
                item["title"] or "Напоминание",
                item["due_date"] or "",
                item["due_time"],
                item["periodicity"] or "once",
                item["notes"],
                int(item["is_active"] or 0),
                item["created_at"] or utc_now_iso(),
                item["updated_at"] or utc_now_iso(),
                external_id,
            ),
        )
        counts["reminders_imported"] += 1


def _import_telegram_observations(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    bot_user_id: int,
    pwa_user_id: int,
    pet_map: dict[int, int],
    counts: dict[str, int],
) -> None:
    bot_cur.execute(
        """
        SELECT id, pet_id, obs_type, payload, source, created_at
        FROM pet_observations
        WHERE user_id = ?
        ORDER BY id ASC
        LIMIT 500
        """,
        (int(bot_user_id),),
    )
    for item in bot_cur.fetchall():
        if item["pet_id"] is None or int(item["pet_id"]) not in pet_map:
            continue
        external_id = _source_id(item["id"])
        if _pwa_external_exists(pwa_cur, "pet_observations", external_id):
            continue
        pwa_cur.execute(
            """
            INSERT INTO pet_observations (
                user_id, pet_id, obs_type, payload, source, created_at, external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, ?, 'telegram', ?)
            """,
            (
                int(pwa_user_id),
                pet_map[int(item["pet_id"])],
                item["obs_type"] or "note",
                item["payload"],
                item["source"] or "telegram",
                item["created_at"] or utc_now_iso(),
                external_id,
            ),
        )
        counts["observations_imported"] += 1


def _import_telegram_measurements(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    pet_map: dict[int, int],
    counts: dict[str, int],
) -> None:
    if not pet_map:
        return
    placeholders = ",".join("?" for _ in pet_map)
    bot_cur.execute(
        f"""
        SELECT id, pet_id, created_at, weight_kg, note, metadata
        FROM pet_measurements
        WHERE pet_id IN ({placeholders})
        ORDER BY id ASC
        LIMIT 500
        """,
        tuple(pet_map.keys()),
    )
    for item in bot_cur.fetchall():
        if item["weight_kg"] is None:
            continue
        external_id = _source_id(item["id"])
        if _pwa_external_exists(pwa_cur, "pet_measurements", external_id):
            continue
        pwa_pet_id = pet_map[int(item["pet_id"])]
        pwa_cur.execute(
            """
            INSERT INTO pet_measurements (
                pet_id, created_at, weight_kg, note, metadata, external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, 'telegram', ?)
            """,
            (
                pwa_pet_id,
                item["created_at"] or utc_now_iso(),
                float(item["weight_kg"]),
                item["note"],
                item["metadata"],
                external_id,
            ),
        )
        pwa_cur.execute(
            "UPDATE pets SET weight_kg = COALESCE(weight_kg, ?) WHERE id = ?",
            (float(item["weight_kg"]), pwa_pet_id),
        )
        counts["measurements_imported"] += 1


def _import_telegram_history(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    pet_map: dict[int, int],
    counts: dict[str, int],
) -> None:
    if not pet_map:
        return
    placeholders = ",".join("?" for _ in pet_map)
    bot_cur.execute(
        f"""
        SELECT id, pet_id, event_type, created_at, title, details, metadata
        FROM pet_history
        WHERE pet_id IN ({placeholders})
        ORDER BY id ASC
        LIMIT 1000
        """,
        tuple(pet_map.keys()),
    )
    for item in bot_cur.fetchall():
        external_id = _source_id(item["id"])
        if _pwa_external_exists(pwa_cur, "pet_history", external_id):
            continue
        pwa_cur.execute(
            """
            INSERT INTO pet_history (
                pet_id, event_type, created_at, title, details, metadata,
                external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, ?, 'telegram', ?)
            """,
            (
                pet_map[int(item["pet_id"])],
                item["event_type"] or "telegram",
                item["created_at"] or utc_now_iso(),
                item["title"] or "Событие из Telegram",
                item["details"],
                item["metadata"],
                external_id,
            ),
        )
        counts["history_imported"] += 1


def _import_telegram_triage_logs(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    bot_user_id: int,
    pwa_user_id: int,
    pet_map: dict[int, int],
    counts: dict[str, int],
) -> None:
    bot_cur.execute(
        """
        SELECT id, pet_id, complaint_text, response_text, quota_before, quota_after,
               created_at, prompt_tokens, completion_tokens, total_tokens, urgency_level
        FROM triage_logs
        WHERE user_id = ?
        ORDER BY id ASC
        LIMIT 500
        """,
        (int(bot_user_id),),
    )
    for item in bot_cur.fetchall():
        external_id = _source_id(item["id"])
        if _pwa_external_exists(pwa_cur, "triage_logs", external_id):
            continue
        pwa_pet_id = pet_map.get(int(item["pet_id"])) if item["pet_id"] is not None else None
        pwa_cur.execute(
            """
            SELECT 1
            FROM triage_logs
            WHERE user_id = ?
              AND COALESCE(pet_id, 0) = COALESCE(?, 0)
              AND complaint_text = ?
              AND COALESCE(response_text, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (
                int(pwa_user_id),
                pwa_pet_id,
                item["complaint_text"] or "",
                item["response_text"],
            ),
        )
        if pwa_cur.fetchone():
            continue
        pwa_cur.execute(
            """
            INSERT INTO triage_logs (
                user_id, pet_id, complaint_text, response_text, urgency_level, created_at,
                quota_before, quota_after, prompt_tokens, completion_tokens, total_tokens,
                subscription_source, external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'telegram', 'telegram', ?)
            """,
            (
                int(pwa_user_id),
                pwa_pet_id,
                item["complaint_text"] or "",
                item["response_text"],
                item["urgency_level"] or "yellow",
                item["created_at"] or utc_now_iso(),
                item["quota_before"],
                item["quota_after"],
                int(item["prompt_tokens"] or 0),
                int(item["completion_tokens"] or 0),
                int(item["total_tokens"] or 0),
                external_id,
            ),
        )
        counts["triage_imported"] += 1


def sync_telegram_profile_to_pwa(settings: Settings, pwa_user: dict[str, Any]) -> dict[str, Any]:
    telegram_id = _linked_telegram_id(settings, pwa_user)
    if telegram_id is None:
        return {"synced": False, "reason": "telegram_not_linked"}

    bot_path = _bot_db_path(settings)
    if bot_path is None:
        return {"synced": False, "reason": "telegram_db_not_configured"}

    counts = {
        "pets_imported": 0,
        "pets_linked": 0,
        "reminders_imported": 0,
        "observations_imported": 0,
        "measurements_imported": 0,
        "history_imported": 0,
        "triage_imported": 0,
    }

    with closing(sqlite3.connect(bot_path)) as bot_conn, closing(db.connect(settings.database_path)) as pwa_conn:
        bot_conn.row_factory = sqlite3.Row
        bot_cur = bot_conn.cursor()
        pwa_cur = pwa_conn.cursor()
        bot_user = _telegram_user_row(bot_cur, telegram_id)
        if not bot_user:
            return {"synced": False, "reason": "telegram_user_not_found"}

        pwa_user_id = int(pwa_user["id"])
        bot_user_id = int(bot_user["id"])
        pet_map = _import_telegram_pets(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_user_id=pwa_user_id,
            counts=counts,
        )
        _import_telegram_reminders(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_user_id=pwa_user_id,
            pet_map=pet_map,
            counts=counts,
        )
        _import_telegram_observations(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_user_id=pwa_user_id,
            pet_map=pet_map,
            counts=counts,
        )
        _import_telegram_measurements(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            pet_map=pet_map,
            counts=counts,
        )
        _import_telegram_history(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            pet_map=pet_map,
            counts=counts,
        )
        _import_telegram_triage_logs(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_user_id=pwa_user_id,
            pet_map=pet_map,
            counts=counts,
        )
        pwa_conn.commit()
    return {"synced": True, **counts}


def _find_or_create_bot_pet(
    *,
    bot_cur: sqlite3.Cursor,
    pwa_cur: sqlite3.Cursor,
    bot_user_id: int,
    pwa_pet: dict[str, Any],
) -> int | None:
    external_id = _source_id(pwa_pet.get("external_id")) if pwa_pet.get("external_source") == TELEGRAM_SOURCE else ""
    if external_id:
        bot_cur.execute("SELECT id FROM pets WHERE id = ? AND owner_id = ? LIMIT 1", (external_id, int(bot_user_id)))
        row = bot_cur.fetchone()
        if row:
            return int(row["id"])

    bot_pet_id = _find_telegram_pet(bot_cur, owner_id=bot_user_id, selected_pet=pwa_pet)
    now = utc_now_iso()
    if bot_pet_id is None:
        bot_cur.execute(
            """
            INSERT INTO pets (
                owner_id, pet_type, pet_name, added_at, birth_year, birth_month,
                birth_day, birth_precision, sex, weight_kg, breed, is_main,
                external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pwa', ?)
            """,
            (
                int(bot_user_id),
                pwa_pet.get("pet_type") or "питомец",
                pwa_pet.get("pet_name") or "Питомец",
                pwa_pet.get("added_at") or now,
                pwa_pet.get("birth_year"),
                pwa_pet.get("birth_month"),
                pwa_pet.get("birth_day"),
                pwa_pet.get("birth_precision"),
                pwa_pet.get("sex"),
                pwa_pet.get("weight_kg"),
                pwa_pet.get("breed"),
                1 if pwa_pet.get("is_main") else 0,
                _source_id(pwa_pet.get("id")),
            ),
        )
        bot_pet_id = int(bot_cur.lastrowid)
    else:
        bot_cur.execute(
            """
            UPDATE pets
            SET pet_type = ?, pet_name = ?, birth_year = ?, birth_month = ?, birth_day = ?,
                birth_precision = ?, sex = ?, weight_kg = ?, breed = ?,
                external_source = COALESCE(external_source, 'pwa'),
                external_id = COALESCE(external_id, ?)
            WHERE id = ? AND owner_id = ?
            """,
            (
                pwa_pet.get("pet_type") or "питомец",
                pwa_pet.get("pet_name") or "Питомец",
                pwa_pet.get("birth_year"),
                pwa_pet.get("birth_month"),
                pwa_pet.get("birth_day"),
                pwa_pet.get("birth_precision"),
                pwa_pet.get("sex"),
                pwa_pet.get("weight_kg"),
                pwa_pet.get("breed"),
                _source_id(pwa_pet.get("id")),
                int(bot_pet_id),
                int(bot_user_id),
            ),
        )

    if pwa_pet.get("is_main"):
        bot_cur.execute("UPDATE pets SET is_main = 0 WHERE owner_id = ?", (int(bot_user_id),))
        bot_cur.execute("UPDATE pets SET is_main = 1 WHERE id = ? AND owner_id = ?", (int(bot_pet_id), int(bot_user_id)))

    pwa_cur.execute(
        "UPDATE pets SET external_source = 'telegram', external_id = ? WHERE id = ?",
        (_source_id(bot_pet_id), int(pwa_pet["id"])),
    )
    return int(bot_pet_id)


def _telegram_context(settings: Settings, pwa_user: dict[str, Any]) -> tuple[Path, int] | None:
    telegram_id = _linked_telegram_id(settings, pwa_user)
    bot_path = _bot_db_path(settings)
    if telegram_id is None or bot_path is None:
        return None
    with closing(sqlite3.connect(bot_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        row = _telegram_user_row(cur, telegram_id)
        if not row:
            return None
        return bot_path, int(row["id"])


def sync_pwa_pet_to_telegram(settings: Settings, *, pwa_user: dict[str, Any], pet: dict[str, Any]) -> dict[str, Any]:
    context = _telegram_context(settings, pwa_user)
    if context is None:
        return {"synced": False, "reason": "telegram_not_ready"}
    bot_path, bot_user_id = context
    with closing(sqlite3.connect(bot_path)) as bot_conn, closing(db.connect(settings.database_path)) as pwa_conn:
        bot_conn.row_factory = sqlite3.Row
        bot_cur = bot_conn.cursor()
        pwa_cur = pwa_conn.cursor()
        _ensure_bot_sync_columns(bot_cur)
        bot_pet_id = _find_or_create_bot_pet(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_pet=pet,
        )
        bot_conn.commit()
        pwa_conn.commit()
    return {"synced": bool(bot_pet_id), "telegram_pet_id": bot_pet_id}


def sync_pwa_reminder_to_telegram(
    settings: Settings,
    *,
    pwa_user: dict[str, Any],
    reminder: dict[str, Any],
) -> dict[str, Any]:
    context = _telegram_context(settings, pwa_user)
    if context is None:
        return {"synced": False, "reason": "telegram_not_ready"}
    bot_path, bot_user_id = context
    with closing(sqlite3.connect(bot_path)) as bot_conn, closing(db.connect(settings.database_path)) as pwa_conn:
        bot_conn.row_factory = sqlite3.Row
        bot_cur = bot_conn.cursor()
        pwa_cur = pwa_conn.cursor()
        _ensure_bot_sync_columns(bot_cur)
        bot_pet_id = None
        if reminder.get("pet_id"):
            pwa_cur.execute("SELECT * FROM pets WHERE id = ? AND owner_id = ? LIMIT 1", (int(reminder["pet_id"]), int(pwa_user["id"])))
            pwa_pet = pwa_cur.fetchone()
            if pwa_pet:
                bot_pet_id = _find_or_create_bot_pet(
                    bot_cur=bot_cur,
                    pwa_cur=pwa_cur,
                    bot_user_id=bot_user_id,
                    pwa_pet=dict(pwa_pet),
                )

        external_id = _source_id(reminder.get("external_id")) if reminder.get("external_source") == TELEGRAM_SOURCE else ""
        if external_id:
            bot_cur.execute("SELECT id FROM reminders WHERE id = ? AND user_id = ? LIMIT 1", (external_id, int(bot_user_id)))
            row = bot_cur.fetchone()
        else:
            row = None

        now = utc_now_iso()
        if row:
            bot_reminder_id = int(row["id"])
            bot_cur.execute(
                """
                UPDATE reminders
                SET pet_id = ?, reminder_type = ?, title = ?, due_date = ?, due_time = ?,
                    periodicity = ?, notes = ?, is_active = ?, updated_at = ?,
                    external_source = COALESCE(external_source, 'pwa'),
                    external_id = COALESCE(external_id, ?)
                WHERE id = ? AND user_id = ?
                """,
                (
                    bot_pet_id,
                    reminder.get("reminder_type") or "custom",
                    reminder.get("title") or "Напоминание",
                    reminder.get("due_date") or "",
                    reminder.get("due_time"),
                    reminder.get("periodicity") or "once",
                    reminder.get("notes"),
                    int(reminder.get("is_active", 1) or 0),
                    now,
                    _source_id(reminder.get("id")),
                    bot_reminder_id,
                    int(bot_user_id),
                ),
            )
        else:
            bot_cur.execute(
                """
                INSERT INTO reminders (
                    user_id, pet_id, reminder_type, title, due_date, due_time, periodicity,
                    notes, is_active, created_at, updated_at, external_source, external_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pwa', ?)
                """,
                (
                    int(bot_user_id),
                    bot_pet_id,
                    reminder.get("reminder_type") or "custom",
                    reminder.get("title") or "Напоминание",
                    reminder.get("due_date") or "",
                    reminder.get("due_time"),
                    reminder.get("periodicity") or "once",
                    reminder.get("notes"),
                    int(reminder.get("is_active", 1) or 0),
                    reminder.get("created_at") or now,
                    now,
                    _source_id(reminder.get("id")),
                ),
            )
            bot_reminder_id = int(bot_cur.lastrowid)

        pwa_cur.execute(
            "UPDATE reminders SET external_source = 'telegram', external_id = ?, updated_at = ? WHERE id = ?",
            (_source_id(bot_reminder_id), now, int(reminder["id"])),
        )
        bot_conn.commit()
        pwa_conn.commit()
    return {"synced": True, "telegram_pet_id": bot_pet_id, "telegram_reminder_id": bot_reminder_id}


def sync_pwa_reminder_deactivation(settings: Settings, *, pwa_user: dict[str, Any], reminder_id: int) -> dict[str, Any]:
    context = _telegram_context(settings, pwa_user)
    if context is None:
        return {"synced": False, "reason": "telegram_not_ready"}
    bot_path, bot_user_id = context
    with closing(db.connect(settings.database_path)) as pwa_conn:
        row = pwa_conn.execute(
            "SELECT external_source, external_id FROM reminders WHERE id = ? AND user_id = ? LIMIT 1",
            (int(reminder_id), int(pwa_user["id"])),
        ).fetchone()
    if not row or row["external_source"] != TELEGRAM_SOURCE or not row["external_id"]:
        return {"synced": False, "reason": "not_telegram_backed"}
    with closing(sqlite3.connect(bot_path)) as bot_conn:
        cur = bot_conn.cursor()
        cur.execute(
            "UPDATE reminders SET is_active = 0, updated_at = ? WHERE id = ? AND user_id = ?",
            (utc_now_iso(), int(row["external_id"]), int(bot_user_id)),
        )
        bot_conn.commit()
        return {
            "synced": cur.rowcount > 0,
            "telegram_reminder_id": int(row["external_id"]),
        }


def sync_pwa_observation_to_telegram(
    settings: Settings,
    *,
    pwa_user: dict[str, Any],
    observation: dict[str, Any],
) -> dict[str, Any]:
    if observation.get("external_source") == TELEGRAM_SOURCE and observation.get("external_id"):
        return {"synced": True, "reason": "already_linked"}
    context = _telegram_context(settings, pwa_user)
    if context is None:
        return {"synced": False, "reason": "telegram_not_ready"}
    bot_path, bot_user_id = context
    with closing(sqlite3.connect(bot_path)) as bot_conn, closing(db.connect(settings.database_path)) as pwa_conn:
        bot_conn.row_factory = sqlite3.Row
        bot_cur = bot_conn.cursor()
        pwa_cur = pwa_conn.cursor()
        _ensure_bot_sync_columns(bot_cur)
        pwa_cur.execute("SELECT * FROM pets WHERE id = ? AND owner_id = ? LIMIT 1", (int(observation["pet_id"]), int(pwa_user["id"])))
        pwa_pet = pwa_cur.fetchone()
        if not pwa_pet:
            return {"synced": False, "reason": "pet_not_found"}
        bot_pet_id = _find_or_create_bot_pet(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_pet=dict(pwa_pet),
        )
        bot_cur.execute(
            """
            INSERT INTO pet_observations (
                user_id, pet_id, obs_type, payload, source, created_at, external_source, external_id
            )
            VALUES (?, ?, ?, ?, 'pwa', ?, 'pwa', ?)
            """,
            (
                int(bot_user_id),
                int(bot_pet_id),
                observation.get("obs_type") or "note",
                observation.get("payload"),
                observation.get("created_at") or utc_now_iso(),
                _source_id(observation.get("id")),
            ),
        )
        bot_observation_id = int(bot_cur.lastrowid)
        pwa_cur.execute(
            "UPDATE pet_observations SET external_source = 'telegram', external_id = ? WHERE id = ?",
            (_source_id(bot_observation_id), int(observation["id"])),
        )
        bot_conn.commit()
        pwa_conn.commit()
    return {
        "synced": True,
        "telegram_pet_id": bot_pet_id,
        "telegram_observation_id": bot_observation_id,
    }


def sync_pwa_measurement_to_telegram(
    settings: Settings,
    *,
    pwa_user: dict[str, Any],
    measurement: dict[str, Any],
) -> dict[str, Any]:
    if measurement.get("external_source") == TELEGRAM_SOURCE and measurement.get("external_id"):
        return {"synced": True, "reason": "already_linked"}
    context = _telegram_context(settings, pwa_user)
    if context is None:
        return {"synced": False, "reason": "telegram_not_ready"}
    bot_path, bot_user_id = context
    with closing(sqlite3.connect(bot_path)) as bot_conn, closing(db.connect(settings.database_path)) as pwa_conn:
        bot_conn.row_factory = sqlite3.Row
        bot_cur = bot_conn.cursor()
        pwa_cur = pwa_conn.cursor()
        _ensure_bot_sync_columns(bot_cur)
        pwa_cur.execute("SELECT * FROM pets WHERE id = ? AND owner_id = ? LIMIT 1", (int(measurement["pet_id"]), int(pwa_user["id"])))
        pwa_pet = pwa_cur.fetchone()
        if not pwa_pet:
            return {"synced": False, "reason": "pet_not_found"}
        bot_pet_id = _find_or_create_bot_pet(
            bot_cur=bot_cur,
            pwa_cur=pwa_cur,
            bot_user_id=bot_user_id,
            pwa_pet=dict(pwa_pet),
        )
        metadata = measurement.get("metadata") or json.dumps({"source": "pwa"}, ensure_ascii=False)
        bot_cur.execute(
            """
            INSERT INTO pet_measurements (
                pet_id, created_at, weight_kg, note, metadata, external_source, external_id
            )
            VALUES (?, ?, ?, ?, ?, 'pwa', ?)
            """,
            (
                int(bot_pet_id),
                measurement.get("created_at") or utc_now_iso(),
                float(measurement["weight_kg"]),
                measurement.get("note"),
                metadata,
                _source_id(measurement.get("id")),
            ),
        )
        bot_measurement_id = int(bot_cur.lastrowid)
        pwa_cur.execute(
            "UPDATE pet_measurements SET external_source = 'telegram', external_id = ? WHERE id = ?",
            (_source_id(bot_measurement_id), int(measurement["id"])),
        )
        bot_conn.commit()
        pwa_conn.commit()
    return {
        "synced": True,
        "telegram_pet_id": bot_pet_id,
        "telegram_measurement_id": bot_measurement_id,
    }


def _recent_telegram_followup_exists(cur: sqlite3.Cursor, *, user_id: int) -> bool:
    since = (utc_now() - timedelta(hours=24)).isoformat()
    cur.execute(
        """
        SELECT 1
        FROM triage_followups
        WHERE user_id = ?
          AND created_at >= ?
          AND status IN ('scheduled', 'sent', 'answered')
        LIMIT 1
        """,
        (int(user_id), since),
    )
    return cur.fetchone() is not None


def sync_triage_to_telegram(
    settings: Settings,
    *,
    pwa_user: dict[str, Any],
    selected_pet: dict[str, Any] | None,
    pwa_triage_id: int | None,
    complaint_text: str,
    response_text: str,
    urgency_level: str,
    summary: str | None,
    quota_before: int | None,
    quota_after: int | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> dict[str, Any]:
    account = db.get_external_account(settings.database_path, user_id=int(pwa_user["id"]), provider="telegram")
    if not account:
        return {"synced": False, "reason": "telegram_not_linked"}

    bot_path = _bot_db_path(settings)
    if bot_path is None:
        return {"synced": False, "reason": "telegram_db_not_configured"}

    try:
        telegram_id = int(str(account.get("provider_user_id") or "").strip())
    except (TypeError, ValueError):
        return {"synced": False, "reason": "telegram_id_invalid"}

    now = utc_now_iso()
    urgency = (urgency_level or "yellow").strip().lower()
    urgency_emoji, urgency_label = URGENCY_TITLES.get(urgency, URGENCY_TITLES["yellow"])

    with closing(sqlite3.connect(bot_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = ? LIMIT 1", (telegram_id,))
        user_row = cur.fetchone()
        if not user_row:
            return {"synced": False, "reason": "telegram_user_not_found"}

        bot_user_id = int(user_row["id"])
        bot_pet_id = _find_telegram_pet(cur, owner_id=bot_user_id, selected_pet=selected_pet)
        cur.execute(
            """
            INSERT INTO triage_logs (
                user_id, pet_id, complaint_text, response_text,
                quota_before, quota_after, created_at,
                prompt_tokens, completion_tokens, total_tokens, urgency_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bot_user_id,
                bot_pet_id,
                complaint_text,
                response_text,
                quota_before,
                quota_after,
                now,
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                int(total_tokens or 0),
                urgency,
            ),
        )
        bot_triage_id = int(cur.lastrowid)

        metadata = {
            "source": "pwa",
            "pwa_user_id": int(pwa_user["id"]),
            "pwa_triage_id": pwa_triage_id,
            "complaint": complaint_text,
            "summary": summary,
            "urgency_emoji": urgency_emoji,
            "urgency_label": urgency_label,
            "urgency_level": urgency,
        }
        bot_history_id = None
        bot_observation_id = None
        if bot_pet_id is not None:
            cur.execute(
                """
                INSERT INTO pet_history (pet_id, event_type, created_at, title, details, triage_id, metadata)
                VALUES (?, 'triage', ?, ?, ?, ?, ?)
                """,
                (
                    bot_pet_id,
                    now,
                    f"{urgency_emoji} {urgency_label}",
                    summary or complaint_text,
                    bot_triage_id,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            bot_history_id = int(cur.lastrowid)
            cur.execute(
                """
                INSERT INTO pet_observations (user_id, pet_id, obs_type, payload, source, created_at)
                VALUES (?, ?, 'triage', ?, 'pwa', ?)
                """,
                (bot_user_id, bot_pet_id, json.dumps(metadata, ensure_ascii=False), now),
            )
            bot_observation_id = int(cur.lastrowid)

        scheduled_at = followup_due_at(urgency)
        followup_id = None
        if scheduled_at and not _recent_telegram_followup_exists(cur, user_id=bot_user_id):
            scenario = detect_followup_scenario(complaint_text)
            cur.execute(
                """
                INSERT INTO triage_followups (
                    triage_event_id, user_id, pet_id, urgency_level, scenario,
                    scheduled_at, status, payload, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
                """,
                (
                    bot_triage_id,
                    bot_user_id,
                    bot_pet_id,
                    urgency,
                    scenario,
                    scheduled_at,
                    json.dumps(followup_payload(complaint_text=complaint_text, summary=summary), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            followup_id = int(cur.lastrowid)

        conn.commit()
        return {
            "synced": True,
            "telegram_user_id": bot_user_id,
            "telegram_pet_id": bot_pet_id,
            "telegram_triage_id": bot_triage_id,
            "telegram_history_id": bot_history_id,
            "telegram_observation_id": bot_observation_id,
            "telegram_followup_id": followup_id,
        }
