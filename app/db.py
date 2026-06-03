from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.security import utc_now_iso


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
        conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


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
