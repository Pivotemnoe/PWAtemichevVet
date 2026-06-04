from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.security import utc_now_iso


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(cur: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cur.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cur.fetchall())


def _ensure_column(cur: sqlite3.Cursor, table_name: str, column_name: str, ddl: str) -> None:
    if not _column_exists(cur, table_name, column_name):
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")


def init_db(db_path: Path) -> None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                name TEXT,
                phone TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS external_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(provider, provider_user_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT
            )
            """
        )
        _ensure_column(cur, "auth_challenges", "failed_attempts", "INTEGER NOT NULL DEFAULT 0")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_target ON auth_challenges(channel, target, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                pet_type TEXT NOT NULL,
                pet_name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                birth_year INTEGER,
                birth_month INTEGER,
                birth_day INTEGER,
                birth_precision TEXT,
                sex TEXT,
                weight_kg REAL,
                breed TEXT,
                is_main INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        _ensure_column(cur, "pets", "birth_year", "INTEGER")
        _ensure_column(cur, "pets", "birth_month", "INTEGER")
        _ensure_column(cur, "pets", "birth_day", "INTEGER")
        _ensure_column(cur, "pets", "birth_precision", "TEXT")
        _ensure_column(cur, "pets", "sex", "TEXT")
        _ensure_column(cur, "pets", "weight_kg", "REAL")
        _ensure_column(cur, "pets", "breed", "TEXT")
        _ensure_column(cur, "pets", "is_main", "INTEGER NOT NULL DEFAULT 0")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets(owner_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT,
                triage_id INTEGER,
                reminder_id INTEGER,
                metadata TEXT,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pet_history_pet ON pet_history(pet_id, created_at)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER NOT NULL,
                obs_type TEXT NOT NULL,
                payload TEXT,
                source TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pet_observations_pet ON pet_observations(pet_id, created_at)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                note TEXT,
                metadata TEXT,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pet_measurements_pet ON pet_measurements(pet_id, created_at)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER,
                reminder_type TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                due_time TEXT,
                periodicity TEXT NOT NULL DEFAULT 'once',
                notes TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id, is_active, due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_pet ON reminders(pet_id, is_active, due_date)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                plan TEXT NOT NULL,
                quota_total INTEGER NOT NULL,
                quota_used INTEGER NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT,
                source TEXT NOT NULL DEFAULT 'pwa',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        _ensure_column(cur, "subscriptions", "source", "TEXT NOT NULL DEFAULT 'pwa'")
        _ensure_column(cur, "subscriptions", "updated_at", "TEXT NOT NULL DEFAULT ''")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pet_id INTEGER,
                complaint_text TEXT NOT NULL,
                response_text TEXT,
                urgency_level TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE SET NULL
            )
            """
        )
        _ensure_column(cur, "triage_logs", "quota_before", "INTEGER")
        _ensure_column(cur, "triage_logs", "quota_after", "INTEGER")
        _ensure_column(cur, "triage_logs", "prompt_tokens", "INTEGER DEFAULT 0")
        _ensure_column(cur, "triage_logs", "completion_tokens", "INTEGER DEFAULT 0")
        _ensure_column(cur, "triage_logs", "total_tokens", "INTEGER DEFAULT 0")
        _ensure_column(cur, "triage_logs", "model", "TEXT")
        _ensure_column(cur, "triage_logs", "subscription_source", "TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_triage_logs_user ON triage_logs(user_id, created_at)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, created_at)")
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def create_auth_challenge(
    db_path: Path,
    *,
    channel: str,
    target: str,
    code_hash: str,
    expires_at: str,
    payload: str | None = None,
) -> int:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO auth_challenges (channel, target, code_hash, payload, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (channel, target, code_hash, payload, utc_now_iso(), expires_at),
        )
        conn.commit()
        return int(cur.lastrowid)


def find_active_challenge(db_path: Path, *, channel: str, target: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM auth_challenges
            WHERE channel = ?
              AND target = ?
              AND consumed_at IS NULL
              AND expires_at > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (channel, target, utc_now_iso()),
        )
        return row_to_dict(cur.fetchone())


def count_auth_challenges_since(db_path: Path, *, channel: str, target: str, since: str) -> int:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM auth_challenges
            WHERE channel = ?
              AND target = ?
              AND created_at >= ?
            """,
            (channel, target, since),
        )
        return int((cur.fetchone() or (0,))[0] or 0)


def get_last_auth_challenge(db_path: Path, *, channel: str, target: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM auth_challenges
            WHERE channel = ?
              AND target = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (channel, target),
        )
        return row_to_dict(cur.fetchone())


def increment_challenge_failed_attempts(db_path: Path, challenge_id: int) -> int:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE auth_challenges
            SET failed_attempts = COALESCE(failed_attempts, 0) + 1
            WHERE id = ? AND consumed_at IS NULL
            """,
            (int(challenge_id),),
        )
        cur.execute("SELECT COALESCE(failed_attempts, 0) FROM auth_challenges WHERE id = ?", (int(challenge_id),))
        row = cur.fetchone()
        conn.commit()
        return int((row or (0,))[0] or 0)


def consume_challenge(db_path: Path, challenge_id: int) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            "UPDATE auth_challenges SET consumed_at = ? WHERE id = ?",
            (utc_now_iso(), int(challenge_id)),
        )
        conn.commit()


def update_challenge_payload(db_path: Path, challenge_id: int, payload: str) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            "UPDATE auth_challenges SET payload = ? WHERE id = ? AND consumed_at IS NULL",
            (payload, int(challenge_id)),
        )
        conn.commit()


def get_or_create_user_by_email(db_path: Path, email: str) -> dict[str, Any]:
    email = email.strip().lower()
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(
            """
            INSERT INTO users (email, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (email, now, now),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (int(cur.lastrowid),))
        return dict(cur.fetchone())


def get_or_create_user_by_external_account(
    db_path: Path,
    *,
    provider: str,
    provider_user_id: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.*
            FROM external_accounts a
            JOIN users u ON u.id = a.user_id
            WHERE a.provider = ? AND a.provider_user_id = ?
            LIMIT 1
            """,
            (provider, provider_user_id),
        )
        row = cur.fetchone()
        if row:
            return dict(row)

        cur.execute(
            """
            INSERT INTO users (name, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (display_name, now, now),
        )
        user_id = int(cur.lastrowid)
        cur.execute(
            """
            INSERT INTO external_accounts (user_id, provider, provider_user_id, display_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, provider, provider_user_id, display_name, now),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(cur.fetchone())


def list_external_accounts(db_path: Path, *, user_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT provider, provider_user_id, display_name, created_at
            FROM external_accounts
            WHERE user_id = ?
            ORDER BY provider
            """,
            (int(user_id),),
        )
        return rows_to_dicts(cur.fetchall())


def get_external_account(db_path: Path, *, user_id: int, provider: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT provider, provider_user_id, display_name, created_at
            FROM external_accounts
            WHERE user_id = ? AND provider = ?
            LIMIT 1
            """,
            (int(user_id), provider),
        )
        return row_to_dict(cur.fetchone())


def link_external_account(
    db_path: Path,
    *,
    user_id: int,
    provider: str,
    provider_user_id: str,
    display_name: str | None = None,
) -> dict[str, Any] | None:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
        user = cur.fetchone()
        if not user:
            return None

        cur.execute(
            """
            SELECT user_id
            FROM external_accounts
            WHERE provider = ? AND provider_user_id = ?
            LIMIT 1
            """,
            (provider, provider_user_id),
        )
        existing = cur.fetchone()
        if existing and int(existing["user_id"]) != int(user_id):
            return None
        if existing:
            cur.execute(
                """
                UPDATE external_accounts
                SET display_name = ?
                WHERE provider = ? AND provider_user_id = ? AND user_id = ?
                """,
                (display_name, provider, provider_user_id, int(user_id)),
            )
        else:
            cur.execute(
                """
                INSERT INTO external_accounts (user_id, provider, provider_user_id, display_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), provider, provider_user_id, display_name, now),
            )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
        return dict(cur.fetchone())


def create_session(db_path: Path, *, user_id: int, token_hash: str, expires_at: str) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO sessions (user_id, token_hash, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(user_id), token_hash, utc_now_iso(), expires_at),
        )
        conn.commit()


def get_user_by_session(db_path: Path, *, token_hash: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.*
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
            LIMIT 1
            """,
            (token_hash, utc_now_iso()),
        )
        return row_to_dict(cur.fetchone())


def list_pets(db_path: Path, *, owner_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM pets
            WHERE owner_id = ?
            ORDER BY is_main DESC, id DESC
            """,
            (int(owner_id),),
        )
        return rows_to_dicts(cur.fetchall())


def get_pet(db_path: Path, *, owner_id: int, pet_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM pets WHERE id = ? AND owner_id = ? LIMIT 1",
            (int(pet_id), int(owner_id)),
        )
        return row_to_dict(cur.fetchone())


def _user_has_pets(cur: sqlite3.Cursor, owner_id: int) -> bool:
    cur.execute("SELECT 1 FROM pets WHERE owner_id = ? LIMIT 1", (int(owner_id),))
    return cur.fetchone() is not None


def create_pet(
    db_path: Path,
    *,
    owner_id: int,
    pet_type: str,
    pet_name: str,
    birth_year: int | None = None,
    birth_month: int | None = None,
    birth_day: int | None = None,
    birth_precision: str | None = None,
    sex: str | None = None,
    weight_kg: float | None = None,
    breed: str | None = None,
    is_main: bool | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        has_pets = _user_has_pets(cur, owner_id)
        make_main = (not has_pets) or bool(is_main)
        if make_main:
            cur.execute("UPDATE pets SET is_main = 0 WHERE owner_id = ?", (int(owner_id),))
        cur.execute(
            """
            INSERT INTO pets (
                owner_id, pet_type, pet_name, added_at, birth_year, birth_month,
                birth_day, birth_precision, sex, weight_kg, breed, is_main
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(owner_id),
                pet_type,
                pet_name,
                now,
                birth_year,
                birth_month,
                birth_day,
                birth_precision,
                sex,
                weight_kg,
                breed,
                1 if make_main else 0,
            ),
        )
        pet_id = int(cur.lastrowid)
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details)
            VALUES (?, 'profile', ?, 'Карточка создана', ?)
            """,
            (pet_id, now, f"{pet_type} — {pet_name}"),
        )
        conn.commit()
        cur.execute("SELECT * FROM pets WHERE id = ?", (pet_id,))
        return dict(cur.fetchone())


def update_pet(db_path: Path, *, owner_id: int, pet_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "pet_type",
        "pet_name",
        "birth_year",
        "birth_month",
        "birth_day",
        "birth_precision",
        "sex",
        "weight_kg",
        "breed",
    }
    clean = {k: v for k, v in values.items() if k in allowed}
    if not clean:
        return get_pet(db_path, owner_id=owner_id, pet_id=pet_id)

    assignments = ", ".join(f"{key} = ?" for key in clean)
    params = list(clean.values()) + [int(pet_id), int(owner_id)]
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE pets SET {assignments} WHERE id = ? AND owner_id = ?", params)
        if cur.rowcount == 0:
            return None
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details)
            VALUES (?, 'profile', ?, 'Карточка обновлена', NULL)
            """,
            (int(pet_id), utc_now_iso()),
        )
        conn.commit()
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_id = ?", (int(pet_id), int(owner_id)))
        return row_to_dict(cur.fetchone())


def set_main_pet(db_path: Path, *, owner_id: int, pet_id: int, is_main: bool) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM pets WHERE id = ? AND owner_id = ?", (int(pet_id), int(owner_id)))
        if not cur.fetchone():
            return None
        if is_main:
            cur.execute("UPDATE pets SET is_main = 0 WHERE owner_id = ?", (int(owner_id),))
        cur.execute("UPDATE pets SET is_main = ? WHERE id = ? AND owner_id = ?", (1 if is_main else 0, int(pet_id), int(owner_id)))
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details)
            VALUES (?, 'profile', ?, ?, NULL)
            """,
            (int(pet_id), utc_now_iso(), "Питомец выбран основным" if is_main else "Основной статус снят"),
        )
        conn.commit()
        cur.execute("SELECT * FROM pets WHERE id = ? AND owner_id = ?", (int(pet_id), int(owner_id)))
        return row_to_dict(cur.fetchone())


def delete_pet(db_path: Path, *, owner_id: int, pet_id: int) -> bool:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pets WHERE id = ? AND owner_id = ?", (int(pet_id), int(owner_id)))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def add_history(
    db_path: Path,
    *,
    pet_id: int,
    event_type: str,
    title: str,
    details: str | None = None,
    triage_id: int | None = None,
    reminder_id: int | None = None,
    metadata: str | None = None,
) -> int:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_history (
                pet_id, event_type, created_at, title, details, triage_id, reminder_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (int(pet_id), event_type, utc_now_iso(), title, details, triage_id, reminder_id, metadata),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_history(db_path: Path, *, owner_id: int, pet_id: int, limit: int = 30) -> list[dict[str, Any]] | None:
    if not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM pet_history
            WHERE pet_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (int(pet_id), int(limit)),
        )
        return rows_to_dicts(cur.fetchall())


def create_measurement(
    db_path: Path,
    *,
    owner_id: int,
    pet_id: int,
    weight_kg: float,
    note: str | None = None,
) -> dict[str, Any] | None:
    if not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pet_measurements (pet_id, created_at, weight_kg, note) VALUES (?, ?, ?, ?)",
            (int(pet_id), now, float(weight_kg), note),
        )
        measurement_id = int(cur.lastrowid)
        cur.execute("UPDATE pets SET weight_kg = ? WHERE id = ?", (float(weight_kg), int(pet_id)))
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details)
            VALUES (?, 'weight', ?, 'Вес обновлён', ?)
            """,
            (int(pet_id), now, f"{weight_kg:g} кг" + (f" — {note}" if note else "")),
        )
        conn.commit()
        cur.execute("SELECT * FROM pet_measurements WHERE id = ?", (measurement_id,))
        return dict(cur.fetchone())


def list_measurements(db_path: Path, *, owner_id: int, pet_id: int, limit: int = 20) -> list[dict[str, Any]] | None:
    if not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM pet_measurements WHERE pet_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(pet_id), int(limit)),
        )
        return rows_to_dicts(cur.fetchall())


def create_observation(
    db_path: Path,
    *,
    owner_id: int,
    pet_id: int,
    obs_type: str,
    payload: str,
    source: str = "pwa",
) -> dict[str, Any] | None:
    if not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pet_observations (user_id, pet_id, obs_type, payload, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(owner_id), int(pet_id), obs_type, payload, source, now),
        )
        observation_id = int(cur.lastrowid)
        cur.execute(
            """
            INSERT INTO pet_history (pet_id, event_type, created_at, title, details)
            VALUES (?, 'observation', ?, 'Наблюдение добавлено', ?)
            """,
            (int(pet_id), now, payload),
        )
        conn.commit()
        cur.execute("SELECT * FROM pet_observations WHERE id = ?", (observation_id,))
        return dict(cur.fetchone())


def list_observations(db_path: Path, *, owner_id: int, pet_id: int, limit: int = 20) -> list[dict[str, Any]] | None:
    if not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM pet_observations WHERE pet_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(pet_id), int(limit)),
        )
        return rows_to_dicts(cur.fetchall())


def create_reminder(
    db_path: Path,
    *,
    owner_id: int,
    pet_id: int | None,
    reminder_type: str,
    title: str,
    due_date: str,
    due_time: str | None = None,
    periodicity: str = "once",
    notes: str | None = None,
) -> dict[str, Any] | None:
    if pet_id is not None and not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO reminders (
                user_id, pet_id, reminder_type, title, due_date, due_time,
                periodicity, notes, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (int(owner_id), pet_id, reminder_type, title, due_date, due_time, periodicity, notes, now, now),
        )
        reminder_id = int(cur.lastrowid)
        if pet_id is not None:
            cur.execute(
                """
                INSERT INTO pet_history (pet_id, event_type, created_at, title, details, reminder_id)
                VALUES (?, 'reminder', ?, 'Напоминание добавлено', ?, ?)
                """,
                (int(pet_id), now, f"{due_date} {due_time or ''} — {title}".strip(), reminder_id),
            )
        conn.commit()
        cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        return dict(cur.fetchone())


def list_reminders(
    db_path: Path,
    *,
    owner_id: int,
    pet_id: int | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]] | None:
    if pet_id is not None and not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    clauses = ["r.user_id = ?"]
    params: list[Any] = [int(owner_id)]
    if pet_id is not None:
        clauses.append("r.pet_id = ?")
        params.append(int(pet_id))
    if active_only:
        clauses.append("r.is_active = 1")
    where = " AND ".join(clauses)
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT r.*, p.pet_name, p.pet_type
            FROM reminders r
            LEFT JOIN pets p ON p.id = r.pet_id
            WHERE {where}
            ORDER BY r.due_date ASC, COALESCE(r.due_time, '99:99') ASC, r.id ASC
            """,
            params,
        )
        return rows_to_dicts(cur.fetchall())


def deactivate_reminder(db_path: Path, *, owner_id: int, reminder_id: int) -> bool:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE reminders
            SET is_active = 0, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (utc_now_iso(), int(reminder_id), int(owner_id)),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def create_triage_log(
    db_path: Path,
    *,
    owner_id: int,
    pet_id: int | None,
    complaint_text: str,
    response_text: str,
    urgency_level: str,
    quota_before: int | None = None,
    quota_after: int | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    model: str | None = None,
    subscription_source: str | None = None,
) -> dict[str, Any] | None:
    if pet_id is not None and not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO triage_logs (
                user_id, pet_id, complaint_text, response_text, urgency_level, created_at,
                quota_before, quota_after, prompt_tokens, completion_tokens, total_tokens,
                model, subscription_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(owner_id),
                pet_id,
                complaint_text,
                response_text,
                urgency_level,
                now,
                quota_before,
                quota_after,
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                int(total_tokens or 0),
                model,
                subscription_source,
            ),
        )
        triage_id = int(cur.lastrowid)
        if pet_id is not None:
            cur.execute(
                """
                INSERT INTO pet_history (pet_id, event_type, created_at, title, details, triage_id)
                VALUES (?, 'triage', ?, ?, ?, ?)
                """,
                (
                    int(pet_id),
                    now,
                    "Разбор жалобы: срочно" if urgency_level == "red" else "Разбор жалобы",
                    complaint_text,
                    triage_id,
                ),
            )
        conn.commit()
        cur.execute("SELECT * FROM triage_logs WHERE id = ?", (triage_id,))
        return dict(cur.fetchone())


def create_feedback(db_path: Path, *, owner_id: int, text: str, category: str | None = None) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO feedback (user_id, created_at, text, category)
            VALUES (?, ?, ?, ?)
            """,
            (int(owner_id), utc_now_iso(), text, category),
        )
        conn.commit()
        cur.execute("SELECT * FROM feedback WHERE id = ?", (int(cur.lastrowid),))
        return dict(cur.fetchone())
