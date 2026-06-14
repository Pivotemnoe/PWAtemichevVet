from __future__ import annotations

import json
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


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1", (table_name,))
    return cur.fetchone() is not None


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
            CREATE TABLE IF NOT EXISTS sync_tombstones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                external_id TEXT NOT NULL,
                local_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, provider, entity_type, external_id),
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sync_tombstones_lookup
            ON sync_tombstones(owner_id, provider, entity_type, external_id)
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
            CREATE TABLE IF NOT EXISTS review_login_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_login_tokens_hash ON review_login_tokens(token_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_login_tokens_expires ON review_login_tokens(expires_at, revoked_at)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                ip_hash TEXT,
                user_agent TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_admin_sessions_token ON admin_sessions(token_hash)")

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
        _ensure_column(cur, "pets", "external_source", "TEXT")
        _ensure_column(cur, "pets", "external_id", "TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets(owner_id)")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pets_external
            ON pets(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

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
        _ensure_column(cur, "pet_history", "external_source", "TEXT")
        _ensure_column(cur, "pet_history", "external_id", "TEXT")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pet_history_external
            ON pet_history(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

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
        _ensure_column(cur, "pet_observations", "external_source", "TEXT")
        _ensure_column(cur, "pet_observations", "external_id", "TEXT")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pet_observations_external
            ON pet_observations(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

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
        _ensure_column(cur, "pet_measurements", "external_source", "TEXT")
        _ensure_column(cur, "pet_measurements", "external_id", "TEXT")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pet_measurements_external
            ON pet_measurements(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

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
        _ensure_column(cur, "reminders", "external_source", "TEXT")
        _ensure_column(cur, "reminders", "external_id", "TEXT")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reminders_external
            ON reminders(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

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
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_payment_id TEXT NOT NULL,
                plan_code TEXT NOT NULL DEFAULT 'plus',
                amount_rub INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                confirmation_url TEXT,
                idempotence_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                paid_at TEXT,
                raw_payload TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        _ensure_column(cur, "payments", "confirmation_url", "TEXT")
        _ensure_column(cur, "payments", "idempotence_key", "TEXT")
        _ensure_column(cur, "payments", "paid_at", "TEXT")
        _ensure_column(cur, "payments", "raw_payload", "TEXT")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_provider_payment_id
            ON payments(provider, provider_payment_id)
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_created ON payments(user_id, created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_provider_status ON payments(provider, status)")

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
        _ensure_column(cur, "triage_logs", "external_source", "TEXT")
        _ensure_column(cur, "triage_logs", "external_id", "TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_triage_logs_user ON triage_logs(user_id, created_at)")
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_triage_logs_external
            ON triage_logs(external_source, external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                triage_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                pet_id INTEGER,
                urgency_level TEXT NOT NULL,
                scenario TEXT NOT NULL DEFAULT 'basic',
                scheduled_at TEXT NOT NULL,
                answered_at TEXT,
                status TEXT NOT NULL DEFAULT 'scheduled',
                answer TEXT,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(triage_id) REFERENCES triage_logs(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(pet_id) REFERENCES pets(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_triage_followups_user ON triage_followups(user_id, status, scheduled_at)")
        _ensure_column(cur, "triage_followups", "push_notified_at", "TEXT")
        _ensure_column(cur, "triage_followups", "push_last_error", "TEXT")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user
            ON push_subscriptions(user_id, revoked_at)
            """
        )

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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS security_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                provider TEXT,
                status TEXT NOT NULL,
                ip_hash TEXT,
                actor TEXT NOT NULL DEFAULT 'system',
                entity_type TEXT,
                entity_id TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_security_audit_type_created
            ON security_audit_events(event_type, created_at)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_security_audit_user_created
            ON security_audit_events(user_id, created_at)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_security_audit_status_created
            ON security_audit_events(status, created_at)
            """
        )
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _json_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_audit_metadata(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, (bool, int, float)):
            safe[str(key)[:80]] = item
            continue
        text = str(item)
        safe[str(key)[:80]] = text[:240]
    payload = _json_dump(safe)
    if payload and len(payload) > 1600:
        return payload[:1600]
    return payload


def create_security_audit_event(
    db_path: Path,
    *,
    event_type: str,
    user_id: int | None = None,
    provider: str | None = None,
    status: str = "ok",
    ip_hash: str | None = None,
    actor: str = "system",
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO security_audit_events (
                event_type, user_id, provider, status, ip_hash, actor,
                entity_type, entity_id, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type[:120],
                int(user_id) if user_id is not None else None,
                provider[:40] if provider else None,
                status[:40],
                ip_hash[:80] if ip_hash else None,
                actor[:40] if actor else "system",
                entity_type[:80] if entity_type else None,
                entity_id[:120] if entity_id else None,
                _safe_audit_metadata(metadata),
                now,
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM security_audit_events WHERE id = ?", (int(cur.lastrowid),))
        row = cur.fetchone()
        item = row_to_dict(row)
        if not item:
            raise RuntimeError("security_audit_event_not_created")
        item["metadata"] = _json_load(item.get("metadata"))
        return item


def list_security_audit_events(
    db_path: Path,
    *,
    limit: int = 100,
    event_type: str | None = None,
    user_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(int(user_id))
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM security_audit_events
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()
    items = rows_to_dicts(rows)
    for item in items:
        item["metadata"] = _json_load(item.get("metadata"))
    return items


def count_security_audit_events_since(
    db_path: Path,
    *,
    since: str,
    status: str | None = None,
    event_type_prefix: str | None = None,
) -> int:
    clauses = ["created_at >= ?"]
    params: list[Any] = [since]
    if status:
        clauses.append("status = ?")
        params.append(status)
    if event_type_prefix:
        clauses.append("event_type LIKE ?")
        params.append(f"{event_type_prefix}%")
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM security_audit_events
            WHERE {' AND '.join(clauses)}
            """,
            tuple(params),
        ).fetchone()
        return int((row or (0,))[0] or 0)


def upsert_push_subscription(
    db_path: Path,
    *,
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO push_subscriptions (
                user_id, endpoint, p256dh, auth, user_agent, created_at, updated_at, revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(endpoint) DO UPDATE SET
                user_id = excluded.user_id,
                p256dh = excluded.p256dh,
                auth = excluded.auth,
                user_agent = excluded.user_agent,
                updated_at = excluded.updated_at,
                revoked_at = NULL
            """,
            (
                int(user_id),
                endpoint[:2000],
                p256dh[:500],
                auth[:500],
                user_agent[:500] if user_agent else None,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM push_subscriptions WHERE endpoint = ?", (endpoint[:2000],)).fetchone()
    item = row_to_dict(row)
    if not item:
        raise RuntimeError("push_subscription_not_created")
    return item


def revoke_push_subscription(db_path: Path, *, user_id: int, endpoint: str) -> bool:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.execute(
            """
            UPDATE push_subscriptions
            SET revoked_at = ?, updated_at = ?
            WHERE user_id = ? AND endpoint = ? AND revoked_at IS NULL
            """,
            (now, now, int(user_id), endpoint[:2000]),
        )
        conn.commit()
        return bool(cur.rowcount)


def list_push_subscriptions(db_path: Path, *, user_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, endpoint, user_agent, created_at, updated_at
            FROM push_subscriptions
            WHERE user_id = ? AND revoked_at IS NULL
            ORDER BY updated_at DESC
            """,
            (int(user_id),),
        ).fetchall()
    return rows_to_dicts(rows)


def list_push_subscriptions_for_delivery(db_path: Path, *, user_id: int) -> list[dict[str, Any]]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, endpoint, p256dh, auth, user_agent, created_at, updated_at
            FROM push_subscriptions
            WHERE user_id = ? AND revoked_at IS NULL
            ORDER BY updated_at DESC
            """,
            (int(user_id),),
        ).fetchall()
    return rows_to_dicts(rows)


def list_due_triage_followups_for_push(db_path: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT f.*, p.pet_name, p.pet_type
            FROM triage_followups f
            LEFT JOIN pets p ON p.id = f.pet_id
            WHERE f.status = 'scheduled'
              AND f.scheduled_at <= ?
              AND f.push_notified_at IS NULL
            ORDER BY f.scheduled_at ASC, f.id ASC
            LIMIT ?
            """,
            (now, int(limit)),
        ).fetchall()
    return rows_to_dicts(rows)


def mark_triage_followup_push_result(
    db_path: Path,
    *,
    followup_id: int,
    sent: bool,
    error: str | None = None,
) -> None:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        if sent:
            conn.execute(
                """
                UPDATE triage_followups
                SET push_notified_at = ?, push_last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, now, int(followup_id)),
            )
        else:
            conn.execute(
                """
                UPDATE triage_followups
                SET push_last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                ((error or "unknown")[:240], now, int(followup_id)),
            )
        conn.commit()


def _payment_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["raw_payload"] = _json_load(item.get("raw_payload"))
    return item


def create_payment_record(
    db_path: Path,
    *,
    user_id: int,
    provider: str,
    provider_payment_id: str,
    amount_rub: int,
    status: str,
    plan_code: str = "plus",
    confirmation_url: str | None = None,
    idempotence_key: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO payments (
                user_id, provider, provider_payment_id, plan_code, amount_rub,
                status, confirmation_url, idempotence_key, created_at, updated_at,
                paid_at, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(provider, provider_payment_id) DO UPDATE SET
                user_id = excluded.user_id,
                plan_code = excluded.plan_code,
                amount_rub = excluded.amount_rub,
                status = excluded.status,
                confirmation_url = excluded.confirmation_url,
                idempotence_key = excluded.idempotence_key,
                updated_at = excluded.updated_at,
                raw_payload = excluded.raw_payload
            """,
            (
                int(user_id),
                provider,
                provider_payment_id,
                plan_code,
                int(amount_rub),
                status,
                confirmation_url,
                idempotence_key,
                now,
                now,
                _json_dump(raw_payload),
            ),
        )
        conn.commit()
        cur.execute(
            """
            SELECT *
            FROM payments
            WHERE provider = ? AND provider_payment_id = ?
            LIMIT 1
            """,
            (provider, provider_payment_id),
        )
        row = cur.fetchone()
        result = _payment_public(row)
        if result is None:
            raise RuntimeError("payment_record_not_created")
        return result


def update_payment_status(
    db_path: Path,
    *,
    provider: str,
    provider_payment_id: str,
    status: str,
    paid_at: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        if raw_payload is None:
            cur.execute(
                """
                UPDATE payments
                SET status = ?, paid_at = COALESCE(?, paid_at), updated_at = ?
                WHERE provider = ? AND provider_payment_id = ?
                """,
                (status, paid_at, now, provider, provider_payment_id),
            )
        else:
            cur.execute(
                """
                UPDATE payments
                SET status = ?, paid_at = COALESCE(?, paid_at), updated_at = ?, raw_payload = ?
                WHERE provider = ? AND provider_payment_id = ?
                """,
                (status, paid_at, now, _json_dump(raw_payload), provider, provider_payment_id),
            )
        conn.commit()
        cur.execute(
            """
            SELECT *
            FROM payments
            WHERE provider = ? AND provider_payment_id = ?
            LIMIT 1
            """,
            (provider, provider_payment_id),
        )
        return _payment_public(cur.fetchone())


def get_payment_record(db_path: Path, *, provider: str, provider_payment_id: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE provider = ? AND provider_payment_id = ?
            LIMIT 1
            """,
            (provider, provider_payment_id),
        ).fetchone()
        return _payment_public(row)


def get_last_payment(db_path: Path, *, user_id: int, provider: str = "yookassa") -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE user_id = ? AND provider = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(user_id), provider),
        ).fetchone()
        return _payment_public(row)


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


def _subscription_rank(row: sqlite3.Row | None) -> tuple[int, str, int]:
    if not row:
        return (-1, "", 0)
    plan = str(row["plan"] or "free").lower()
    rank = {"free": 0, "plus": 1, "pro": 2, "vip": 3}.get(plan, 0)
    period_end = str(row["period_end"] or "")
    quota_left = int(row["quota_total"] or 0) - int(row["quota_used"] or 0)
    return (rank, period_end, quota_left)


def merge_users(db_path: Path, *, source_user_id: int, target_user_id: int) -> dict[str, Any] | None:
    source_id = int(source_user_id)
    target_id = int(target_user_id)
    if source_id == target_id:
        with closing(connect(db_path)) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
            return row_to_dict(row)

    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (source_id,))
        source = cur.fetchone()
        cur.execute("SELECT * FROM users WHERE id = ?", (target_id,))
        target = cur.fetchone()
        if not source or not target:
            return None

        source_email = str(source["email"] or "").strip() or None
        source_name = str(source["name"] or "").strip() or None
        source_phone = str(source["phone"] or "").strip() or None

        updates: dict[str, Any] = {"updated_at": now}
        if source_email and not target["email"]:
            cur.execute("UPDATE users SET email = NULL, updated_at = ? WHERE id = ?", (now, source_id))
            updates["email"] = source_email
        if source_name and not target["name"]:
            updates["name"] = source_name
        if source_phone and not target["phone"]:
            updates["phone"] = source_phone

        if updates:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            cur.execute(
                f"UPDATE users SET {assignments} WHERE id = ?",
                (*updates.values(), target_id),
            )

        for table, column in (
            ("sessions", "user_id"),
            ("pets", "owner_id"),
            ("pet_observations", "user_id"),
            ("reminders", "user_id"),
            ("triage_logs", "user_id"),
            ("triage_followups", "user_id"),
            ("feedback", "user_id"),
            ("payments", "user_id"),
        ):
            if _table_exists(cur, table):
                cur.execute(f"UPDATE {table} SET {column} = ? WHERE {column} = ?", (target_id, source_id))

        if _table_exists(cur, "subscriptions"):
            cur.execute("SELECT * FROM subscriptions WHERE user_id = ? LIMIT 1", (source_id,))
            source_sub = cur.fetchone()
            cur.execute("SELECT * FROM subscriptions WHERE user_id = ? LIMIT 1", (target_id,))
            target_sub = cur.fetchone()
            if source_sub and not target_sub:
                cur.execute("UPDATE subscriptions SET user_id = ?, updated_at = ? WHERE user_id = ?", (target_id, now, source_id))
            elif source_sub and target_sub:
                if _subscription_rank(source_sub) > _subscription_rank(target_sub):
                    cur.execute(
                        """
                        UPDATE subscriptions
                        SET plan = ?, quota_total = ?, quota_used = ?, period_start = ?,
                            period_end = ?, source = ?, updated_at = ?
                        WHERE user_id = ?
                        """,
                        (
                            source_sub["plan"],
                            int(source_sub["quota_total"] or 0),
                            int(source_sub["quota_used"] or 0),
                            source_sub["period_start"],
                            source_sub["period_end"],
                            source_sub["source"],
                            now,
                            target_id,
                        ),
                    )
                cur.execute("DELETE FROM subscriptions WHERE user_id = ?", (source_id,))

        cur.execute(
            "SELECT id, provider, provider_user_id FROM external_accounts WHERE user_id = ?",
            (source_id,),
        )
        source_accounts = cur.fetchall()
        for account in source_accounts:
            cur.execute(
                """
                SELECT id
                FROM external_accounts
                WHERE user_id = ? AND provider = ? AND provider_user_id = ?
                LIMIT 1
                """,
                (target_id, account["provider"], account["provider_user_id"]),
            )
            if cur.fetchone():
                cur.execute("DELETE FROM external_accounts WHERE id = ?", (int(account["id"]),))
            else:
                cur.execute("UPDATE external_accounts SET user_id = ? WHERE id = ?", (target_id, int(account["id"])))

        cur.execute("DELETE FROM users WHERE id = ?", (source_id,))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (target_id,))
        return dict(cur.fetchone())


def link_or_merge_external_account(
    db_path: Path,
    *,
    user_id: int,
    provider: str,
    provider_user_id: str,
    display_name: str | None = None,
) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
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
        target_user_id = int(existing["user_id"])
        merged = merge_users(db_path, source_user_id=int(user_id), target_user_id=target_user_id)
        if merged:
            link_external_account(
                db_path,
                user_id=target_user_id,
                provider=provider,
                provider_user_id=provider_user_id,
                display_name=display_name,
            )
        return merged

    return link_external_account(
        db_path,
        user_id=int(user_id),
        provider=provider,
        provider_user_id=provider_user_id,
        display_name=display_name,
    )


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


def get_active_review_login_token(db_path: Path, *, token_hash: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM review_login_tokens
            WHERE token_hash = ?
              AND revoked_at IS NULL
              AND expires_at > ?
            LIMIT 1
            """,
            (token_hash, utc_now_iso()),
        ).fetchone()
        return row_to_dict(row)


def mark_review_login_token_used(db_path: Path, *, token_hash: str) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            UPDATE review_login_tokens
            SET last_used_at = ?
            WHERE token_hash = ?
              AND revoked_at IS NULL
            """,
            (utc_now_iso(), token_hash),
        )
        conn.commit()


def revoke_session(db_path: Path, *, token_hash: str) -> bool:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE token_hash = ?
              AND revoked_at IS NULL
            """,
            (utc_now_iso(), token_hash),
        )
        revoked = cur.rowcount > 0
        conn.commit()
        return revoked


def revoke_user_sessions(db_path: Path, *, user_id: int) -> int:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE user_id = ?
              AND revoked_at IS NULL
            """,
            (utc_now_iso(), int(user_id)),
        )
        revoked = int(cur.rowcount or 0)
        conn.commit()
        return revoked


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


def create_admin_session(
    db_path: Path,
    *,
    token_hash: str,
    expires_at: str,
    ip_hash: str | None = None,
    user_agent: str | None = None,
) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO admin_sessions (token_hash, created_at, expires_at, ip_hash, user_agent)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                utc_now_iso(),
                expires_at,
                ip_hash[:80] if ip_hash else None,
                user_agent[:240] if user_agent else None,
            ),
        )
        conn.commit()


def get_admin_session(db_path: Path, *, token_hash: str) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM admin_sessions
            WHERE token_hash = ?
              AND revoked_at IS NULL
              AND expires_at > ?
            LIMIT 1
            """,
            (token_hash, utc_now_iso()),
        ).fetchone()
        return row_to_dict(row)


def revoke_admin_session(db_path: Path, *, token_hash: str) -> bool:
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE admin_sessions
            SET revoked_at = ?
            WHERE token_hash = ?
              AND revoked_at IS NULL
            """,
            (utc_now_iso(), token_hash),
        )
        revoked = cur.rowcount > 0
        conn.commit()
        return revoked


def get_user_by_id(db_path: Path, *, user_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (int(user_id),)).fetchone()
        return row_to_dict(row)


def export_user_data(db_path: Path, *, user_id: int) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (int(user_id),)).fetchone())
        if not user:
            return None

        def select_all(query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
            return rows_to_dicts(conn.execute(query, params).fetchall())

        pets = select_all(
            """
            SELECT *
            FROM pets
            WHERE owner_id = ?
            ORDER BY is_main DESC, id DESC
            """,
            (int(user_id),),
        )
        pet_ids = [int(item["id"]) for item in pets]
        placeholders = ",".join("?" for _ in pet_ids) or "NULL"

        return {
            "user": user,
            "external_accounts": select_all(
                """
                SELECT provider, provider_user_id, display_name, created_at
                FROM external_accounts
                WHERE user_id = ?
                ORDER BY provider
                """,
                (int(user_id),),
            ),
            "subscription": row_to_dict(
                conn.execute("SELECT * FROM subscriptions WHERE user_id = ? LIMIT 1", (int(user_id),)).fetchone()
            ),
            "pets": pets,
            "pet_history": select_all(
                f"""
                SELECT *
                FROM pet_history
                WHERE pet_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                """,
                tuple(pet_ids),
            )
            if pet_ids
            else [],
            "observations": select_all(
                """
                SELECT *
                FROM pet_observations
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ),
            "measurements": select_all(
                f"""
                SELECT *
                FROM pet_measurements
                WHERE pet_id IN ({placeholders})
                ORDER BY created_at DESC, id DESC
                """,
                tuple(pet_ids),
            )
            if pet_ids
            else [],
            "reminders": select_all(
                """
                SELECT *
                FROM reminders
                WHERE user_id = ?
                ORDER BY due_date ASC, COALESCE(due_time, '99:99') ASC, id ASC
                """,
                (int(user_id),),
            ),
            "triage_logs": select_all(
                """
                SELECT *
                FROM triage_logs
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ),
            "triage_followups": select_all(
                """
                SELECT *
                FROM triage_followups
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ),
            "payments": select_all(
                """
                SELECT id, provider, provider_payment_id, plan_code, amount_rub, status,
                       confirmation_url, created_at, updated_at, paid_at
                FROM payments
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ),
            "feedback": select_all(
                """
                SELECT *
                FROM feedback
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ),
        }


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


def create_sync_tombstone(
    db_path: Path,
    *,
    owner_id: int,
    provider: str,
    entity_type: str,
    external_id: str,
    local_id: int | None = None,
) -> bool:
    external_id = str(external_id or "").strip()
    if not external_id:
        return False
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO sync_tombstones (
                owner_id, provider, entity_type, external_id, local_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(owner_id),
                str(provider),
                str(entity_type),
                external_id,
                int(local_id) if local_id is not None else None,
                utc_now_iso(),
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def sync_tombstone_exists(
    db_path: Path,
    *,
    owner_id: int,
    provider: str,
    entity_type: str,
    external_id: str,
) -> bool:
    external_id = str(external_id or "").strip()
    if not external_id:
        return False
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sync_tombstones
            WHERE owner_id = ?
              AND provider = ?
              AND entity_type = ?
              AND external_id = ?
            LIMIT 1
            """,
            (int(owner_id), str(provider), str(entity_type), external_id),
        ).fetchone()
        return row is not None


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


def add_triage_followup(
    db_path: Path,
    *,
    owner_id: int,
    triage_id: int,
    pet_id: int | None,
    urgency_level: str,
    scenario: str,
    scheduled_at: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if pet_id is not None and not get_pet(db_path, owner_id=owner_id, pet_id=pet_id):
        return None
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO triage_followups (
                    triage_id, user_id, pet_id, urgency_level, scenario,
                    scheduled_at, status, payload, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
                """,
                (
                    int(triage_id),
                    int(owner_id),
                    pet_id,
                    urgency_level,
                    scenario,
                    scheduled_at,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            return None
        followup_id = int(cur.lastrowid)
        conn.commit()
        cur.execute("SELECT * FROM triage_followups WHERE id = ?", (followup_id,))
        return dict(cur.fetchone())


def list_due_triage_followups(db_path: Path, *, owner_id: int, limit: int = 10) -> list[dict[str, Any]]:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT f.*, p.pet_name, p.pet_type
            FROM triage_followups f
            LEFT JOIN pets p ON p.id = f.pet_id
            WHERE f.user_id = ?
              AND f.status = 'scheduled'
              AND f.scheduled_at <= ?
            ORDER BY f.scheduled_at ASC, f.id ASC
            LIMIT ?
            """,
            (int(owner_id), now, int(limit)),
        )
        return rows_to_dicts(cur.fetchall())


def mark_triage_followup_answered(db_path: Path, *, owner_id: int, followup_id: int, answer: str) -> bool:
    now = utc_now_iso()
    with closing(connect(db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE triage_followups
            SET status = 'answered', answer = ?, answered_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ? AND status = 'scheduled'
            """,
            (answer, now, now, int(followup_id), int(owner_id)),
        )
        ok = cur.rowcount > 0
        conn.commit()
        return ok


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
