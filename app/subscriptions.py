from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app import db
from app.config import Settings
from app.security import utc_now, utc_now_iso


FREE_HEALTH_TRIAL_DAYS = 30

SUBSCRIPTION_PLANS: dict[str, dict[str, Any]] = {
    "free": {"title": "Free — первый месяц", "quota_total": 5, "price": 0},
    "plus": {"title": "Plus — 200 ₽ / 30 дней", "quota_total": 10, "price": 200},
    "pro": {"title": "Pro — 300 ₽/мес", "quota_total": 30, "price": 300},
    "vip": {"title": "VIP — 2500 ₽/мес", "quota_total": 25, "price": 2500},
}

PLAN_RANK = {"free": 0, "plus": 1, "pro": 2, "vip": 3}


@dataclass(frozen=True)
class SubscriptionRef:
    source: str
    user_id: int
    plan: str
    quota_total: int
    quota_used: int
    period_start: str
    period_end: str | None
    db_path: Path

    @property
    def quota_left(self) -> int:
        return max(0, self.quota_total - self.quota_used)

    def to_public(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "user_id": self.user_id,
            "plan": self.plan,
            "title": SUBSCRIPTION_PLANS.get(self.plan, SUBSCRIPTION_PLANS["free"])["title"],
            "quota_total": self.quota_total,
            "quota_used": self.quota_used,
            "quota_left": self.quota_left,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_expired(plan: str, period_end: str | None) -> bool:
    if (plan or "free").lower() == "free" or not period_end:
        return False
    end_at = _parse_dt(period_end)
    return bool(end_at and end_at <= utc_now())


def _normalize_plan(plan: str | None) -> str:
    value = (plan or "free").strip().lower()
    return value if value in SUBSCRIPTION_PLANS else "free"


def _pwa_free_quota_state(conn: sqlite3.Connection, user_id: int) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM users WHERE id = ?", (int(user_id),))
    row = cur.fetchone()
    registered_at = _parse_dt(row["created_at"] if row else None)
    if registered_at is None:
        return 0, 0
    if utc_now() > registered_at + timedelta(days=FREE_HEALTH_TRIAL_DAYS):
        return 0, 0
    total = int(SUBSCRIPTION_PLANS["free"]["quota_total"])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM triage_logs
        WHERE user_id = ?
          AND COALESCE(NULLIF(urgency_level, ''), '') != 'red'
          AND COALESCE(NULLIF(subscription_source, ''), '') != 'public_preview'
          AND created_at >= ?
          AND created_at < ?
        """,
        (
            int(user_id),
            registered_at.isoformat(),
            (registered_at + timedelta(days=FREE_HEALTH_TRIAL_DAYS)).isoformat(),
        ),
    )
    used_from_logs = int((cur.fetchone() or (0,))[0] or 0)
    cur.execute("SELECT quota_used FROM subscriptions WHERE user_id = ? AND plan = 'free'", (int(user_id),))
    sub = cur.fetchone()
    used = max(used_from_logs, int(sub["quota_used"] if sub else 0))
    return total, min(total, used)


def _ensure_local_subscription(settings: Settings, user_id: int) -> SubscriptionRef:
    now = utc_now_iso()
    with closing(db.connect(settings.database_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, plan, quota_total, quota_used, period_start, period_end, source
            FROM subscriptions
            WHERE user_id = ?
            LIMIT 1
            """,
            (int(user_id),),
        )
        row = cur.fetchone()
        if row is None:
            quota_total, quota_used = _pwa_free_quota_state(conn, int(user_id))
            cur.execute(
                """
                INSERT INTO subscriptions (user_id, plan, quota_total, quota_used, period_start, period_end, source, updated_at)
                VALUES (?, 'free', ?, ?, ?, NULL, 'pwa', ?)
                """,
                (int(user_id), quota_total, quota_used, now, now),
            )
            conn.commit()
            return SubscriptionRef("pwa", int(user_id), "free", quota_total, quota_used, now, None, settings.database_path)

        plan = _normalize_plan(row["plan"])
        if _is_expired(plan, row["period_end"]):
            plan = "free"
        if plan == "free":
            quota_total, quota_used = _pwa_free_quota_state(conn, int(user_id))
            if (
                row["plan"] != plan
                or int(row["quota_total"] or 0) != quota_total
                or int(row["quota_used"] or 0) != quota_used
                or row["period_end"] is not None
            ):
                cur.execute(
                    """
                    UPDATE subscriptions
                    SET plan = 'free', quota_total = ?, quota_used = ?, period_end = NULL, source = 'pwa', updated_at = ?
                    WHERE user_id = ?
                    """,
                    (quota_total, quota_used, now, int(user_id)),
                )
                conn.commit()
            return SubscriptionRef("pwa", int(user_id), "free", quota_total, quota_used, row["period_start"], None, settings.database_path)

        return SubscriptionRef(
            "pwa",
            int(user_id),
            plan,
            int(row["quota_total"] or SUBSCRIPTION_PLANS[plan]["quota_total"]),
            int(row["quota_used"] or 0),
            row["period_start"],
            row["period_end"],
            settings.database_path,
        )


def _linked_telegram_id(settings: Settings, pwa_user_id: int) -> str | None:
    account = db.get_external_account(settings.database_path, user_id=int(pwa_user_id), provider="telegram")
    if not account:
        return None
    value = str(account.get("provider_user_id") or "").strip()
    return value or None


def _bot_db_path(settings: Settings) -> Path | None:
    if not settings.bot_database_path:
        return None
    path = Path(settings.bot_database_path).expanduser()
    return path if path.exists() else None


def _telegram_subscription(settings: Settings, telegram_id: str) -> SubscriptionRef | None:
    bot_path = _bot_db_path(settings)
    if bot_path is None:
        return None
    with closing(sqlite3.connect(bot_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = ? LIMIT 1", (int(telegram_id),))
        user_row = cur.fetchone()
        if not user_row:
            return None
        bot_user_id = int(user_row["id"])
        cur.execute(
            """
            SELECT user_id, plan, quota_total, quota_used, period_start, period_end
            FROM subscriptions
            WHERE user_id = ?
            LIMIT 1
            """,
            (bot_user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        plan = _normalize_plan(row["plan"])
        if _is_expired(plan, row["period_end"]):
            return SubscriptionRef(
                "telegram",
                bot_user_id,
                "free",
                0,
                0,
                row["period_start"],
                None,
                bot_path,
            )
        return SubscriptionRef(
            "telegram",
            bot_user_id,
            plan,
            int(row["quota_total"] or SUBSCRIPTION_PLANS[plan]["quota_total"]),
            int(row["quota_used"] or 0),
            row["period_start"],
            None if plan == "free" else row["period_end"],
            bot_path,
        )


def _sync_pwa_paid_subscription_to_telegram(
    settings: Settings,
    local: SubscriptionRef,
    telegram_id: str,
) -> SubscriptionRef | None:
    if local.plan == "free" or _is_expired(local.plan, local.period_end):
        return None
    bot_path = _bot_db_path(settings)
    if bot_path is None:
        return None
    try:
        telegram_id_int = int(telegram_id)
    except (TypeError, ValueError):
        return None

    with closing(sqlite3.connect(bot_path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = ? LIMIT 1", (telegram_id_int,))
        user_row = cur.fetchone()
        if not user_row:
            return None

        bot_user_id = int(user_row["id"])
        cur.execute("SELECT id FROM subscriptions WHERE user_id = ? LIMIT 1", (bot_user_id,))
        sub_row = cur.fetchone()
        if sub_row is None:
            cur.execute(
                """
                INSERT INTO subscriptions (user_id, plan, quota_total, quota_used, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_user_id,
                    local.plan,
                    int(local.quota_total),
                    int(local.quota_used),
                    local.period_start,
                    local.period_end,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE subscriptions
                SET plan = ?, quota_total = ?, quota_used = ?, period_start = ?, period_end = ?
                WHERE user_id = ?
                """,
                (
                    local.plan,
                    int(local.quota_total),
                    int(local.quota_used),
                    local.period_start,
                    local.period_end,
                    bot_user_id,
                ),
            )
        conn.commit()

    return SubscriptionRef(
        "telegram",
        bot_user_id,
        local.plan,
        int(local.quota_total),
        int(local.quota_used),
        local.period_start,
        local.period_end,
        bot_path,
    )


def get_effective_subscription(settings: Settings, user: dict[str, Any]) -> SubscriptionRef:
    local = _ensure_local_subscription(settings, int(user["id"]))
    telegram_id = _linked_telegram_id(settings, int(user["id"]))
    telegram = _telegram_subscription(settings, telegram_id) if telegram_id else None
    if telegram is None:
        if telegram_id:
            mirrored = _sync_pwa_paid_subscription_to_telegram(settings, local, telegram_id)
            if mirrored:
                return mirrored
        return local

    local_rank = PLAN_RANK.get(local.plan, 0)
    telegram_rank = PLAN_RANK.get(telegram.plan, 0)
    if local_rank > telegram_rank:
        mirrored = _sync_pwa_paid_subscription_to_telegram(settings, local, telegram_id or "")
        if mirrored:
            return mirrored
        return local
    if local_rank == telegram_rank and local.plan != "free":
        local_end = _parse_dt(local.period_end)
        telegram_end = _parse_dt(telegram.period_end)
        if local_end and (not telegram_end or local_end > telegram_end):
            mirrored = _sync_pwa_paid_subscription_to_telegram(settings, local, telegram_id or "")
            if mirrored:
                return mirrored
    if telegram_rank > local_rank:
        return telegram
    if telegram_rank == local_rank and telegram.source == "telegram":
        return telegram
    return local


def activate_paid_subscription(
    settings: Settings,
    *,
    user_id: int,
    plan_code: str = "plus",
    days: int = 30,
) -> SubscriptionRef:
    plan = _normalize_plan(plan_code)
    if plan == "free":
        raise ValueError("paid subscription plan must not be free")
    now = utc_now_iso()
    period_end = (utc_now() + timedelta(days=int(days))).isoformat()
    quota_total = int(SUBSCRIPTION_PLANS[plan]["quota_total"])
    with closing(db.connect(settings.database_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO subscriptions (user_id, plan, quota_total, quota_used, period_start, period_end, source, updated_at)
            VALUES (?, ?, ?, 0, ?, ?, 'pwa', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan = excluded.plan,
                quota_total = excluded.quota_total,
                quota_used = 0,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                source = 'pwa',
                updated_at = excluded.updated_at
            """,
            (int(user_id), plan, quota_total, now, period_end, now),
        )
        conn.commit()
    return SubscriptionRef("pwa", int(user_id), plan, quota_total, 0, now, period_end, settings.database_path)


def _update_quota(ref: SubscriptionRef, quota_used: int) -> None:
    with closing(sqlite3.connect(ref.db_path)) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE subscriptions SET quota_used = ? WHERE user_id = ?",
            (int(quota_used), int(ref.user_id)),
        )
        conn.commit()


def try_consume_quota(settings: Settings, user: dict[str, Any], amount: int = 1) -> tuple[bool, SubscriptionRef]:
    ref = get_effective_subscription(settings, user)
    if ref.quota_used + int(amount) > ref.quota_total:
        return False, ref
    new_used = ref.quota_used + int(amount)
    _update_quota(ref, new_used)
    return True, SubscriptionRef(
        ref.source,
        ref.user_id,
        ref.plan,
        ref.quota_total,
        new_used,
        ref.period_start,
        ref.period_end,
        ref.db_path,
    )


def refund_quota(ref: SubscriptionRef, amount: int = 1) -> SubscriptionRef:
    new_used = max(0, ref.quota_used - int(amount))
    _update_quota(ref, new_used)
    return SubscriptionRef(
        ref.source,
        ref.user_id,
        ref.plan,
        ref.quota_total,
        new_used,
        ref.period_start,
        ref.period_end,
        ref.db_path,
    )
