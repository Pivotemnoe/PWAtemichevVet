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
            cur.execute(
                """
                INSERT INTO pet_observations (user_id, pet_id, obs_type, payload, source, created_at)
                VALUES (?, ?, 'triage', ?, 'pwa', ?)
                """,
                (bot_user_id, bot_pet_id, json.dumps(metadata, ensure_ascii=False), now),
            )

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
            "telegram_followup_id": followup_id,
        }

