from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import defaultdict, deque
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from app import db
from app.config import Settings, get_settings
from app.emailer import send_login_code
from app.followups import detect_followup_scenario, followup_due_at, followup_payload
from app.knowledge import check_food, find_care, find_faq, find_food, food_to_public
from app.llm_triage import call_triage_llm, extract_urgency, short_summary
from app.max_auth import complete_max_login, create_max_login_challenge, process_max_update
from app.medical_safety import detect_red_flags, render_red_flag_response
from app.payments.yookassa import (
    PLUS_DAYS,
    PROVIDER as YOOKASSA_PROVIDER,
    YooKassaConfigError,
    YooKassaPaymentError,
    YooKassaPaymentValidationError,
    confirmation_url as yookassa_confirmation_url,
    create_plus_payment as create_yookassa_plus_payment,
    get_payment as get_yookassa_payment,
    payment_status as yookassa_payment_status,
    validate_plus_payment as validate_yookassa_plus_payment,
)
from app.security import constant_time_equal, expires_in, hash_value, make_code, make_token, utc_now
from app.subscriptions import activate_paid_subscription, get_effective_subscription, refund_quota, try_consume_quota
from app.telegram_auth import complete_telegram_login, confirm_telegram_login, create_telegram_login_challenge
from app.telegram_sync import (
    sync_pwa_measurement_to_telegram,
    sync_pwa_observation_to_telegram,
    sync_pwa_pet_to_telegram,
    sync_pwa_reminder_deactivation,
    sync_pwa_reminder_to_telegram,
    sync_telegram_profile_to_pwa,
    sync_triage_to_telegram,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"

settings = get_settings()


def _validate_production_settings() -> None:
    if settings.app_env != "production":
        return
    errors: list[str] = []
    if not settings.session_secret or settings.session_secret == "change-me-long-random-secret":
        errors.append("SESSION_SECRET must be set in production")
    if len(settings.session_secret) < 32:
        errors.append("SESSION_SECRET must be at least 32 characters")
    if settings.dev_auth_code_log:
        errors.append("DEV_AUTH_CODE_LOG must be disabled in production")
    if bool(settings.yookassa_shop_id) != bool(settings.yookassa_secret_key):
        errors.append("YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY must be configured together")
    if errors:
        raise RuntimeError("; ".join(errors))


_validate_production_settings()

app = FastAPI(title="TemichevVet PWA API", version="0.1.0")
db.init_db(settings.database_path)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")
logger = logging.getLogger(__name__)

EMAIL_CODE_COOLDOWN_SECONDS = 60
EMAIL_CODE_MAX_PER_HOUR = 5
EMAIL_CODE_MAX_VERIFY_ATTEMPTS = 5


RATE_LIMIT_RULES: tuple[tuple[str, set[str], tuple[str, ...], int, int], ...] = (
    ("auth_email_start", {"POST"}, ("/api/auth/email/start",), 20, 3600),
    ("auth_email_verify", {"POST"}, ("/api/auth/email/verify",), 40, 3600),
    ("auth_provider_start", {"POST"}, ("/api/auth/telegram/start", "/api/auth/max/start"), 30, 3600),
    ("account_provider_start", {"POST"}, ("/api/account/telegram/start", "/api/account/max/start"), 30, 3600),
    ("auth_provider_status", {"GET"}, ("/api/auth/telegram/status", "/api/auth/max/status"), 150, 600),
    ("payment", {"GET", "POST"}, ("/api/payments",), 60, 3600),
    ("feedback", {"POST"}, ("/api/feedback",), 10, 3600),
    ("triage", {"POST"}, ("/api/triage",), 30, 3600),
    ("account_export", {"GET"}, ("/api/account/export",), 5, 3600),
    ("account_deletion", {"POST"}, ("/api/account/deletion-request",), 3, 86400),
    ("account_sessions", {"POST"}, ("/api/account/sessions/revoke-all", "/api/auth/logout"), 20, 3600),
)

_rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _rate_limit_identity(request: Request, name: str) -> str:
    authorization = request.headers.get("authorization", "")
    match = re.match(r"^Bearer\s+(.+)$", authorization.strip(), flags=re.IGNORECASE)
    if match:
        token_hash = hash_value(match.group(1).strip(), settings.session_secret)
        return f"{name}:token:{token_hash[:24]}"
    return f"{name}:ip:{_client_ip(request)}"


def _rate_limit_retry_after(key: str, *, limit: int, window_seconds: int) -> int | None:
    now = monotonic()
    bucket = _rate_limit_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return max(1, int(window_seconds - (now - bucket[0])))
    bucket.append(now)
    return None


def _request_rate_limit_retry_after(request: Request) -> int | None:
    path = request.url.path
    method = request.method.upper()
    for name, methods, prefixes, limit, window_seconds in RATE_LIMIT_RULES:
        if method not in methods:
            continue
        if not any(path.startswith(prefix) for prefix in prefixes):
            continue
        key = _rate_limit_identity(request, name)
        return _rate_limit_retry_after(key, limit=limit, window_seconds=window_seconds)
    return None


def _apply_security_headers(request: Request, response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "; ".join(
            (
                "default-src 'self'",
                "base-uri 'self'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                "script-src 'self'",
                "style-src 'self'",
                "img-src 'self' data:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "worker-src 'self'",
                "form-action 'self' https://*.yookassa.ru https://yookassa.ru https://*.yoomoney.ru https://yoomoney.ru",
            )
        ),
    )
    if settings.app_env == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    retry_after = _request_rate_limit_retry_after(request)
    if retry_after is not None:
        response = JSONResponse(
            status_code=429,
            content={"detail": "rate_limited", "retry_after": retry_after},
        )
        response.headers["Retry-After"] = str(retry_after)
        _apply_security_headers(request, response)
        return response
    response = await call_next(request)
    _apply_security_headers(request, response)
    return response


class EmailStartRequest(BaseModel):
    email: EmailStr


class EmailStartResponse(BaseModel):
    ok: bool
    message: str
    debug_code: str | None = None


class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class SessionResponse(BaseModel):
    token: str
    user: dict


class ProviderStartResponse(BaseModel):
    enabled: bool
    provider: str
    url: str | None = None
    state: str | None = None
    message: str


class ProviderStatusResponse(BaseModel):
    status: str
    message: str | None = None
    token: str | None = None
    user: dict | None = None


class TelegramCompleteRequest(BaseModel):
    state: str = Field(min_length=8, max_length=100)
    telegram_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, max_length=80)


class TriageRequest(BaseModel):
    pet_id: int | None = None
    text: str = Field(min_length=3, max_length=2000)


class PetPayload(BaseModel):
    pet_type: str = Field(min_length=2, max_length=30)
    pet_name: str = Field(min_length=1, max_length=80)
    birth_year: int | None = Field(default=None, ge=1980, le=2100)
    birth_month: int | None = Field(default=None, ge=1, le=12)
    birth_day: int | None = Field(default=None, ge=1, le=31)
    birth_precision: str | None = Field(default=None, max_length=20)
    sex: str | None = Field(default=None, max_length=20)
    weight_kg: float | None = Field(default=None, ge=0.05, le=200)
    breed: str | None = Field(default=None, max_length=80)
    is_main: bool | None = None


class PetPatchPayload(BaseModel):
    pet_type: str | None = Field(default=None, min_length=2, max_length=30)
    pet_name: str | None = Field(default=None, min_length=1, max_length=80)
    birth_year: int | None = Field(default=None, ge=1980, le=2100)
    birth_month: int | None = Field(default=None, ge=1, le=12)
    birth_day: int | None = Field(default=None, ge=1, le=31)
    birth_precision: str | None = Field(default=None, max_length=20)
    sex: str | None = Field(default=None, max_length=20)
    weight_kg: float | None = Field(default=None, ge=0.05, le=200)
    breed: str | None = Field(default=None, max_length=80)


class MainPetPayload(BaseModel):
    is_main: bool = True


class MeasurementPayload(BaseModel):
    weight_kg: float = Field(ge=0.05, le=200)
    note: str | None = Field(default=None, max_length=300)


class ObservationPayload(BaseModel):
    obs_type: str = Field(default="note", max_length=40)
    text: str = Field(min_length=2, max_length=2000)


class ReminderPayload(BaseModel):
    pet_id: int | None = None
    reminder_type: str = Field(default="custom", max_length=40)
    title: str = Field(min_length=2, max_length=120)
    due_date: str = Field(min_length=8, max_length=20)
    due_time: str | None = Field(default=None, max_length=10)
    periodicity: str = Field(default="once", max_length=30)
    notes: str | None = Field(default=None, max_length=500)


class FoodCheckPayload(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    ingredients: str | None = Field(default=None, max_length=1000)


class FeedbackPayload(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    category: str | None = Field(default=None, max_length=80)


class DataDeletionRequest(BaseModel):
    confirm: str = Field(min_length=3, max_length=40)
    comment: str | None = Field(default=None, max_length=500)


class FollowupAnswerPayload(BaseModel):
    answer: str = Field(min_length=2, max_length=20)


class PaymentCreateResponse(BaseModel):
    ok: bool
    status: str
    payment_id: str | None = None
    confirmation_url: str | None = None
    message: str
    subscription: dict | None = None


class PaymentStatusResponse(BaseModel):
    ok: bool
    status: str
    payment_id: str | None = None
    message: str
    subscription: dict | None = None


class TelegramCoreSyncEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=80)
    table_name: str = Field(min_length=1, max_length=80)
    row_id: int | None = None
    operation: str = Field(pattern="^(upsert|delete)$")
    row: dict[str, Any] | None = None
    created_at: str | None = Field(default=None, max_length=80)


class TelegramCoreSyncBatch(BaseModel):
    source: str = Field(default="telegram-nl", max_length=80)
    events: list[TelegramCoreSyncEvent] = Field(default_factory=list, max_length=500)


class TelegramCoreOutboundAck(BaseModel):
    event_ids: list[int] = Field(default_factory=list, max_length=500)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_delivery_enabled() -> bool:
    if settings.dev_auth_code_log and settings.app_env != "production":
        return True
    return bool(
        settings.smtp_host
        and settings.smtp_username
        and settings.smtp_password
        and settings.smtp_from_email
    )


def _parse_iso_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _clean_text(value: str | None, default: str = "") -> str:
    text = " ".join(str(value or "").split())
    return text or default


def _clean_optional_text(value: str | None) -> str | None:
    text = _clean_text(value)
    return text or None


def _normalize_pet_type(value: str) -> str:
    text = _clean_text(value).casefold()
    if text in {"кот", "кошка", "кот/кошка", "cat"}:
        return "кошка"
    if text in {"пёс", "пес", "собака", "dog"}:
        return "собака"
    return _clean_text(value)


def _normalize_birth_precision(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value if value in {"year", "month", "day"} else None


def _pet_age_text(pet: dict) -> str | None:
    year = pet.get("birth_year")
    if not year:
        return None
    precision = pet.get("birth_precision") or "year"
    try:
        birth = date(
            int(year),
            int(pet.get("birth_month") or 1),
            int(pet.get("birth_day") or 1),
        )
    except (TypeError, ValueError):
        return None
    today = date.today()
    months = max(0, (today.year - birth.year) * 12 + today.month - birth.month - (1 if today.day < birth.day else 0))
    years, rest_months = divmod(months, 12)
    if precision == "year":
        return f"{years} г."
    if precision == "month":
        return f"{years} г. {rest_months} мес." if years else f"{max(1, rest_months)} мес."
    if years <= 0:
        return f"{max(1, rest_months)} мес."
    if rest_months:
        return f"{years} г. {rest_months} мес."
    return f"{years} г."


def _schedule_pwa_followup(
    *,
    user_id: int,
    pet_id: int | None,
    triage_id: int | None,
    urgency: str,
    complaint_text: str,
    summary: str | None,
) -> dict | None:
    if not triage_id:
        return None
    scheduled_at = followup_due_at(urgency)
    if not scheduled_at:
        return None
    return db.add_triage_followup(
        settings.database_path,
        owner_id=int(user_id),
        pet_id=pet_id,
        triage_id=int(triage_id),
        urgency_level=urgency,
        scenario=detect_followup_scenario(complaint_text),
        scheduled_at=scheduled_at,
        payload=followup_payload(complaint_text=complaint_text, summary=summary),
    )


def _safe_sync_triage_to_telegram(**kwargs) -> dict:
    try:
        return sync_triage_to_telegram(settings, **kwargs)
    except Exception as exc:
        logger.warning("PWA triage Telegram sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_telegram_profile_to_pwa(user: dict) -> dict:
    try:
        return sync_telegram_profile_to_pwa(settings, user)
    except Exception as exc:
        logger.warning("Telegram to PWA profile sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_pwa_pet_to_telegram(user: dict, pet: dict) -> dict:
    try:
        return sync_pwa_pet_to_telegram(settings, pwa_user=user, pet=pet)
    except Exception as exc:
        logger.warning("PWA pet Telegram sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_pwa_reminder_to_telegram(user: dict, reminder: dict) -> dict:
    try:
        return sync_pwa_reminder_to_telegram(settings, pwa_user=user, reminder=reminder)
    except Exception as exc:
        logger.warning("PWA reminder Telegram sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_pwa_reminder_deactivation(user: dict, reminder_id: int) -> dict:
    try:
        return sync_pwa_reminder_deactivation(settings, pwa_user=user, reminder_id=reminder_id)
    except Exception as exc:
        logger.warning("PWA reminder Telegram deactivation failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_pwa_observation_to_telegram(user: dict, observation: dict) -> dict:
    try:
        return sync_pwa_observation_to_telegram(settings, pwa_user=user, observation=observation)
    except Exception as exc:
        logger.warning("PWA observation Telegram sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


def _safe_sync_pwa_measurement_to_telegram(user: dict, measurement: dict) -> dict:
    try:
        return sync_pwa_measurement_to_telegram(settings, pwa_user=user, measurement=measurement)
    except Exception as exc:
        logger.warning("PWA measurement Telegram sync failed: %s", exc)
        return {"synced": False, "reason": "sync_error"}


TELEGRAM_CORE_SYNC_TABLES = {
    "users",
    "pets",
    "subscriptions",
    "payments",
    "triage_logs",
    "reminders",
    "feedback",
    "admin_audit_log",
    "pet_history",
    "pet_measurements",
    "pet_vaccinations",
    "pet_observations",
    "user_events",
    "subscription_offer_logs",
    "triage_followups",
}


def _require_core_api_secret(authorization: Annotated[str | None, Header()] = None) -> None:
    if not settings.core_api_secret:
        raise HTTPException(status_code=503, detail="core_api_not_configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="authorization_required")
    match = re.match(r"^Bearer\s+(.+)$", authorization.strip(), flags=re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=401, detail="invalid_authorization_header")
    if not constant_time_equal(match.group(1).strip(), settings.core_api_secret):
        raise HTTPException(status_code=403, detail="invalid_core_api_secret")


def _core_mirror_db_path() -> Path:
    if not settings.bot_database_path:
        raise HTTPException(status_code=503, detail="bot_mirror_db_not_configured")
    path = Path(settings.bot_database_path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=503, detail="bot_mirror_db_not_found")
    return path


def _ensure_core_sync_log(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS core_sync_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_id INTEGER,
            operation TEXT NOT NULL,
            payload TEXT,
            received_at TEXT NOT NULL,
            UNIQUE(source, event_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_core_sync_events_received
        ON core_sync_events(received_at)
        """
    )


def _ensure_core_outbound_log(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS core_outbound_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            row_id INTEGER,
            operation TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL,
            delivered_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_core_outbound_events_pending
        ON core_outbound_events(delivered_at, id)
        """
    )


def _mirror_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _apply_core_sync_event(conn: sqlite3.Connection, event: TelegramCoreSyncEvent) -> None:
    table_name = event.table_name
    if table_name not in TELEGRAM_CORE_SYNC_TABLES:
        raise HTTPException(status_code=400, detail=f"sync_table_not_allowed:{table_name}")

    if event.operation == "delete":
        if event.row_id is None:
            raise HTTPException(status_code=400, detail="delete_requires_row_id")
        conn.execute(f"DELETE FROM {table_name} WHERE id = ?", (int(event.row_id),))
        return

    row = event.row or {}
    if "id" not in row:
        raise HTTPException(status_code=400, detail="upsert_requires_row_id")

    allowed_columns = _mirror_table_columns(conn, table_name)
    if not allowed_columns:
        raise HTTPException(status_code=500, detail=f"sync_table_missing:{table_name}")
    columns = [key for key in row.keys() if key in allowed_columns]
    if "id" not in columns:
        columns.insert(0, "id")
    values = [row.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    update_columns = [column for column in columns if column != "id"]
    if update_columns:
        update_sql = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        sql = (
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_sql}"
        )
    else:
        sql = f"INSERT OR IGNORE INTO {table_name} ({column_sql}) VALUES ({placeholders})"
    conn.execute(sql, values)


def _save_core_sync_log(
    conn: sqlite3.Connection,
    *,
    source: str,
    event: TelegramCoreSyncEvent,
) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO core_sync_events (
            source, event_id, table_name, row_id, operation, payload, received_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            event.event_id,
            event.table_name,
            event.row_id,
            event.operation,
            json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True),
            utc_now().isoformat(),
        ),
    )
    return cur.rowcount > 0


def _mirror_row_payload(
    mirror_conn: sqlite3.Connection,
    *,
    table_name: str,
    row_id: int,
    operation: str = "upsert",
) -> dict[str, Any] | None:
    if table_name not in TELEGRAM_CORE_SYNC_TABLES:
        return None
    if operation == "delete":
        return {
            "table_name": table_name,
            "row_id": int(row_id),
            "operation": "delete",
            "row": None,
            "created_at": utc_now().isoformat(),
        }

    mirror_conn.row_factory = sqlite3.Row
    allowed_columns = _mirror_table_columns(mirror_conn, table_name)
    if not allowed_columns:
        return None
    row = mirror_conn.execute(f"SELECT * FROM {table_name} WHERE id = ? LIMIT 1", (int(row_id),)).fetchone()
    if row is None:
        return None
    return {
        "table_name": table_name,
        "row_id": int(row_id),
        "operation": "upsert",
        "row": {key: row[key] for key in row.keys()},
        "created_at": utc_now().isoformat(),
    }


def _enqueue_core_outbound_event(table_name: str, row_id: int | None, operation: str = "upsert") -> bool:
    if row_id is None:
        return False
    mirror_path = _core_mirror_db_path()
    with closing(sqlite3.connect(mirror_path)) as mirror_conn:
        payload = _mirror_row_payload(
            mirror_conn,
            table_name=table_name,
            row_id=int(row_id),
            operation=operation,
        )
    if payload is None:
        return False

    with closing(db.connect(settings.database_path)) as conn:
        _ensure_core_outbound_log(conn)
        conn.execute(
            """
            INSERT INTO core_outbound_events (table_name, row_id, operation, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                table_name,
                int(row_id),
                operation,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                utc_now().isoformat(),
            ),
        )
        conn.commit()
    return True


def _enqueue_core_outbound_subscription_for_bot_user(bot_user_id: int | None) -> bool:
    if bot_user_id is None:
        return False
    mirror_path = _core_mirror_db_path()
    with closing(sqlite3.connect(mirror_path)) as mirror_conn:
        row = mirror_conn.execute(
            "SELECT id FROM subscriptions WHERE user_id = ? LIMIT 1",
            (int(bot_user_id),),
        ).fetchone()
    if not row:
        return False
    return _enqueue_core_outbound_event("subscriptions", int(row[0]))


def _enqueue_core_outbound_from_sync(sync_result: dict, rows: tuple[tuple[str, str], ...]) -> dict[str, int]:
    result = {"queued": 0, "skipped": 0}
    if not sync_result.get("synced"):
        result["skipped"] = len(rows)
        return result

    seen: set[tuple[str, int]] = set()
    for key, table_name in rows:
        row_id = sync_result.get(key)
        if row_id is None:
            result["skipped"] += 1
            continue
        try:
            row_id_int = int(row_id)
        except (TypeError, ValueError):
            result["skipped"] += 1
            continue
        marker = (table_name, row_id_int)
        if marker in seen:
            result["skipped"] += 1
            continue
        seen.add(marker)
        if _enqueue_core_outbound_event(table_name, row_id_int):
            result["queued"] += 1
        else:
            result["skipped"] += 1
    return result


def _core_event_bot_user_id(
    mirror_conn: sqlite3.Connection,
    event: TelegramCoreSyncEvent,
) -> int | None:
    row = event.row or {}
    table_name = event.table_name

    if table_name == "users":
        value = row.get("id") if row else event.row_id
    elif table_name == "pets":
        value = row.get("owner_id")
    elif table_name in {
        "subscriptions",
        "payments",
        "triage_logs",
        "reminders",
        "feedback",
        "user_events",
        "subscription_offer_logs",
        "triage_followups",
        "pet_observations",
    }:
        value = row.get("user_id")
    else:
        value = None

    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    if table_name in {"pet_history", "pet_measurements", "pet_vaccinations"}:
        pet_id = row.get("pet_id")
        if pet_id is None:
            return None
        try:
            pet_id_int = int(pet_id)
        except (TypeError, ValueError):
            return None
        found = mirror_conn.execute(
            "SELECT owner_id FROM pets WHERE id = ? LIMIT 1",
            (pet_id_int,),
        ).fetchone()
        if found and found[0] is not None:
            return int(found[0])

    return None


def _pwa_users_linked_to_bot_users(bot_user_ids: set[int]) -> list[dict[str, Any]]:
    if not bot_user_ids:
        return []

    mirror_path = _core_mirror_db_path()
    with closing(sqlite3.connect(mirror_path)) as mirror_conn:
        mirror_conn.row_factory = sqlite3.Row
        placeholders = ", ".join("?" for _ in bot_user_ids)
        rows = mirror_conn.execute(
            f"SELECT telegram_id FROM users WHERE id IN ({placeholders})",
            tuple(int(user_id) for user_id in bot_user_ids),
        ).fetchall()

    telegram_ids = [str(row["telegram_id"]) for row in rows if row["telegram_id"] is not None]
    if not telegram_ids:
        return []

    with closing(db.connect(settings.database_path)) as pwa_conn:
        placeholders = ", ".join("?" for _ in telegram_ids)
        linked = pwa_conn.execute(
            f"""
            SELECT DISTINCT u.*
            FROM external_accounts a
            JOIN users u ON u.id = a.user_id
            WHERE a.provider = 'telegram'
              AND a.provider_user_id IN ({placeholders})
            """,
            tuple(telegram_ids),
        ).fetchall()
        return [dict(row) for row in linked]


def _sync_linked_pwa_profiles_from_telegram(bot_user_ids: set[int]) -> dict[str, int]:
    users = _pwa_users_linked_to_bot_users(bot_user_ids)
    result = {"users": len(users), "synced": 0, "failed": 0}
    for user in users:
        try:
            sync_result = sync_telegram_profile_to_pwa(settings, user)
            if sync_result.get("synced"):
                result["synced"] += 1
            else:
                result["failed"] += 1
                logger.warning(
                    "Telegram profile sync skipped for PWA user %s: %s",
                    user.get("id"),
                    sync_result,
                )
        except Exception as exc:
            result["failed"] += 1
            logger.warning("Telegram profile sync failed for PWA user %s: %s", user.get("id"), exc)
    return result


def _pet_public(pet: dict) -> dict:
    result = dict(pet)
    result["is_main"] = bool(result.get("is_main"))
    result["age_text"] = _pet_age_text(result)
    return result


def _parse_json_payload(row: dict) -> dict:
    item = dict(row)
    payload = item.get("payload")
    if isinstance(payload, str) and payload:
        try:
            item["payload"] = json.loads(payload)
        except json.JSONDecodeError:
            item["payload"] = {"text": payload}
    return item


def _require_bearer(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="authorization_required")
    match = re.match(r"^Bearer\s+(.+)$", authorization.strip(), flags=re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=401, detail="invalid_authorization_header")
    return match.group(1).strip()


def current_user(token: str = Depends(_require_bearer)) -> dict:
    token_hash = hash_value(token, settings.session_secret)
    user = db.get_user_by_session(settings.database_path, token_hash=token_hash)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_session")
    return user


def _payment_message(status: str) -> str:
    messages = {
        "pending": "Платёж создан. Перейдите к оплате и затем вернитесь проверить статус.",
        "waiting_for_capture": "Платёж ожидает подтверждения. Если деньги списались, проверьте статус через минуту.",
        "succeeded": "Plus подключён на 30 дней.",
        "canceled": "Платёж отменён или не завершён.",
        "invalid": "Платёж не прошёл серверную проверку. Напишите в поддержку.",
    }
    return messages.get(status, "Статус платежа обновлён.")


def _safe_enqueue_subscription_after_payment(sub: dict | None) -> bool:
    if not sub or sub.get("source") != "telegram":
        return False
    try:
        return _enqueue_core_outbound_subscription_for_bot_user(int(sub["user_id"]))
    except Exception as exc:
        logger.warning("PWA payment subscription outbound sync skipped: %s", exc)
        return False


def _activate_plus_from_valid_payment(*, user: dict, payment: dict[str, Any], record: dict[str, Any]) -> PaymentStatusResponse:
    validate_yookassa_plus_payment(
        payment,
        expected_user_id=int(record["user_id"]),
        expected_amount_rub=int(record["amount_rub"]),
    )
    paid_at = str(payment.get("captured_at") or utc_now().isoformat())
    db.update_payment_status(
        settings.database_path,
        provider=YOOKASSA_PROVIDER,
        provider_payment_id=str(record["provider_payment_id"]),
        status="succeeded",
        paid_at=paid_at,
        raw_payload=payment,
    )
    activate_paid_subscription(settings, user_id=int(user["id"]), plan_code="plus", days=PLUS_DAYS)
    effective = get_effective_subscription(settings, user).to_public()
    _safe_enqueue_subscription_after_payment(effective)
    return PaymentStatusResponse(
        ok=True,
        status="succeeded",
        payment_id=str(record["provider_payment_id"]),
        message=_payment_message("succeeded"),
        subscription=effective,
    )


def _refresh_yookassa_payment_for_user(*, record: dict[str, Any], user: dict) -> PaymentStatusResponse:
    if int(record["user_id"]) != int(user["id"]):
        raise HTTPException(status_code=404, detail="payment_not_found")
    try:
        payment = get_yookassa_payment(settings, str(record["provider_payment_id"]))
    except YooKassaConfigError as exc:
        raise HTTPException(status_code=503, detail="payment_provider_not_configured") from exc
    except YooKassaPaymentError as exc:
        logger.warning("YooKassa payment status failed: %s", exc)
        raise HTTPException(status_code=502, detail="payment_provider_error") from exc

    status = yookassa_payment_status(payment)
    if status == "succeeded":
        try:
            return _activate_plus_from_valid_payment(user=user, payment=payment, record=record)
        except YooKassaPaymentValidationError as exc:
            logger.warning("YooKassa payment validation failed for %s: %s", record.get("provider_payment_id"), exc)
            db.update_payment_status(
                settings.database_path,
                provider=YOOKASSA_PROVIDER,
                provider_payment_id=str(record["provider_payment_id"]),
                status="invalid",
                raw_payload=payment,
            )
            raise HTTPException(status_code=409, detail="payment_verification_failed") from exc

    db.update_payment_status(
        settings.database_path,
        provider=YOOKASSA_PROVIDER,
        provider_payment_id=str(record["provider_payment_id"]),
        status=status,
        raw_payload=payment,
    )
    return PaymentStatusResponse(
        ok=status not in {"canceled", "invalid"},
        status=status,
        payment_id=str(record["provider_payment_id"]),
        message=_payment_message(status),
        subscription=get_effective_subscription(settings, user).to_public(),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "temichevvet-pwa", "env": settings.app_env}


@app.get("/api/internal/telegram-sync/ping")
def telegram_core_sync_ping(_: None = Depends(_require_core_api_secret)) -> dict:
    mirror_path = _core_mirror_db_path()
    return {
        "ok": True,
        "service": "temichevvet-core-api",
        "mirror_db": str(mirror_path),
    }


@app.post("/api/internal/telegram-sync/batch")
def telegram_core_sync_batch(
    payload: TelegramCoreSyncBatch,
    _: None = Depends(_require_core_api_secret),
) -> dict:
    mirror_path = _core_mirror_db_path()
    applied = 0
    duplicates = 0
    affected_bot_user_ids: set[int] = set()
    with closing(db.connect(settings.database_path)) as pwa_conn, closing(sqlite3.connect(mirror_path)) as mirror_conn:
        try:
            _ensure_core_sync_log(pwa_conn)
            for event in payload.events:
                inserted = _save_core_sync_log(pwa_conn, source=payload.source, event=event)
                if not inserted:
                    duplicates += 1
                    continue
                _apply_core_sync_event(mirror_conn, event)
                bot_user_id = _core_event_bot_user_id(mirror_conn, event)
                if bot_user_id is not None:
                    affected_bot_user_ids.add(bot_user_id)
                applied += 1
            pwa_conn.commit()
            mirror_conn.commit()
        except HTTPException:
            pwa_conn.rollback()
            mirror_conn.rollback()
            raise
        except Exception as exc:
            pwa_conn.rollback()
            mirror_conn.rollback()
            logger.exception("Telegram core sync batch failed: %s", exc)
            raise HTTPException(status_code=500, detail="telegram_core_sync_failed") from exc
    profile_sync = _sync_linked_pwa_profiles_from_telegram(affected_bot_user_ids)
    return {
        "ok": True,
        "received": len(payload.events),
        "applied": applied,
        "duplicates": duplicates,
        "profile_sync": profile_sync,
    }


@app.get("/api/internal/telegram-sync/outbound")
def telegram_core_sync_outbound(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    _: None = Depends(_require_core_api_secret),
) -> dict:
    with closing(db.connect(settings.database_path)) as conn:
        _ensure_core_outbound_log(conn)
        rows = conn.execute(
            """
            SELECT id, table_name, row_id, operation, payload, created_at
            FROM core_outbound_events
            WHERE delivered_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    events = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        events.append(
            {
                "outbox_id": int(row["id"]),
                "event_id": str(row["id"]),
                "table_name": payload.get("table_name") or row["table_name"],
                "row_id": payload.get("row_id") if payload.get("row_id") is not None else row["row_id"],
                "operation": payload.get("operation") or row["operation"],
                "row": payload.get("row"),
                "created_at": payload.get("created_at") or row["created_at"],
            }
        )
    return {"ok": True, "source": "ru-core", "events": events}


@app.post("/api/internal/telegram-sync/outbound/ack")
def telegram_core_sync_outbound_ack(
    payload: TelegramCoreOutboundAck,
    _: None = Depends(_require_core_api_secret),
) -> dict:
    event_ids = sorted({int(event_id) for event_id in payload.event_ids if int(event_id) > 0})
    if not event_ids:
        return {"ok": True, "acked": 0}

    placeholders = ", ".join("?" for _ in event_ids)
    with closing(db.connect(settings.database_path)) as conn:
        _ensure_core_outbound_log(conn)
        cur = conn.execute(
            f"""
            UPDATE core_outbound_events
            SET delivered_at = COALESCE(delivered_at, ?)
            WHERE id IN ({placeholders})
            """,
            (utc_now().isoformat(), *event_ids),
        )
        conn.commit()
    return {"ok": True, "acked": int(cur.rowcount or 0)}


@app.get("/api/config")
def public_config() -> dict:
    return {
        "telegram_enabled": bool(settings.telegram_bot_username),
        "max_enabled": bool(settings.max_bot_username and settings.max_bot_token),
        "email_enabled": _email_delivery_enabled(),
    }


@app.post("/api/auth/email/start", response_model=EmailStartResponse)
def auth_email_start(payload: EmailStartRequest) -> EmailStartResponse:
    if not _email_delivery_enabled():
        raise HTTPException(status_code=503, detail="email_not_configured")

    email = _normalize_email(str(payload.email))
    last_challenge = db.get_last_auth_challenge(settings.database_path, channel="email", target=email)
    last_created_at = _parse_iso_dt(last_challenge.get("created_at") if last_challenge else None)
    if last_created_at and utc_now() - last_created_at < timedelta(seconds=EMAIL_CODE_COOLDOWN_SECONDS):
        raise HTTPException(status_code=429, detail="email_code_too_many_requests")

    recent_count = db.count_auth_challenges_since(
        settings.database_path,
        channel="email",
        target=email,
        since=(utc_now() - timedelta(hours=1)).isoformat(),
    )
    if recent_count >= EMAIL_CODE_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="email_code_hour_limit")

    code = make_code()
    db.create_auth_challenge(
        settings.database_path,
        channel="email",
        target=email,
        code_hash=hash_value(code, settings.session_secret),
        expires_at=expires_in(10),
    )
    if settings.smtp_host:
        try:
            send_login_code(settings, email=email, code=code)
        except Exception:
            logger.exception("Failed to send email login code")
            raise HTTPException(status_code=503, detail="email_delivery_failed") from None
    return EmailStartResponse(
        ok=True,
        message="Код отправлен на email.",
        debug_code=code if settings.dev_auth_code_log and settings.app_env != "production" else None,
    )


@app.post("/api/auth/email/verify", response_model=SessionResponse)
def auth_email_verify(payload: EmailVerifyRequest) -> SessionResponse:
    email = _normalize_email(str(payload.email))
    challenge = db.find_active_challenge(settings.database_path, channel="email", target=email)
    if not challenge:
        raise HTTPException(status_code=400, detail="code_expired_or_not_found")

    code_hash = hash_value(payload.code.strip(), settings.session_secret)
    if not constant_time_equal(code_hash, str(challenge["code_hash"])):
        failed_attempts = db.increment_challenge_failed_attempts(settings.database_path, int(challenge["id"]))
        if failed_attempts >= EMAIL_CODE_MAX_VERIFY_ATTEMPTS:
            db.consume_challenge(settings.database_path, int(challenge["id"]))
            raise HTTPException(status_code=400, detail="code_attempts_exceeded")
        raise HTTPException(status_code=400, detail="invalid_code")

    db.consume_challenge(settings.database_path, int(challenge["id"]))
    user = db.get_or_create_user_by_email(settings.database_path, email)
    token = make_token()
    db.create_session(
        settings.database_path,
        user_id=int(user["id"]),
        token_hash=hash_value(token, settings.session_secret),
        expires_at=(utc_now() + timedelta(days=30)).isoformat(),
    )
    return SessionResponse(token=token, user=user)


@app.post("/api/auth/telegram/start", response_model=ProviderStartResponse)
def auth_telegram_start() -> ProviderStartResponse:
    if not settings.telegram_bot_username:
        return ProviderStartResponse(
            enabled=False,
            provider="telegram",
            message="Вход через Telegram будет доступен после настройки бота.",
        )
    if not settings.telegram_auth_secret:
        return ProviderStartResponse(
            enabled=False,
            provider="telegram",
            message="Вход через Telegram настраивается. Пока используйте email.",
        )
    state, url = create_telegram_login_challenge(settings)
    return ProviderStartResponse(
        enabled=True,
        provider="telegram",
        url=url,
        state=state,
        message="Откройте Telegram только для подтверждения входа, затем вернитесь на сайт.",
    )


@app.get("/api/auth/telegram/status", response_model=ProviderStatusResponse)
def auth_telegram_status(state: str) -> ProviderStatusResponse:
    result = complete_telegram_login(settings, state)
    return ProviderStatusResponse(**result)


@app.post("/api/account/telegram/start", response_model=ProviderStartResponse)
def account_telegram_start(user: dict = Depends(current_user)) -> ProviderStartResponse:
    if not settings.telegram_bot_username:
        return ProviderStartResponse(
            enabled=False,
            provider="telegram",
            message="Подключение Telegram будет доступно после настройки бота.",
        )
    if not settings.telegram_auth_secret:
        return ProviderStartResponse(
            enabled=False,
            provider="telegram",
            message="Подключение Telegram настраивается.",
        )
    state, url = create_telegram_login_challenge(settings, link_user_id=int(user["id"]))
    return ProviderStartResponse(
        enabled=True,
        provider="telegram",
        url=url,
        state=state,
        message="Откройте Telegram только для подтверждения привязки, затем вернитесь на сайт.",
    )


@app.post("/api/auth/telegram/complete")
def auth_telegram_complete(
    payload: TelegramCompleteRequest,
    x_temichevvet_telegram_secret: Annotated[str | None, Header()] = None,
) -> dict:
    if not settings.telegram_auth_secret:
        raise HTTPException(status_code=503, detail="telegram_auth_not_configured")
    if not x_temichevvet_telegram_secret or not constant_time_equal(
        x_temichevvet_telegram_secret,
        settings.telegram_auth_secret,
    ):
        raise HTTPException(status_code=403, detail="invalid_telegram_auth_secret")
    result = confirm_telegram_login(
        settings,
        state=payload.state.strip(),
        telegram_id=payload.telegram_id.strip(),
        display_name=_clean_optional_text(payload.display_name),
        username=_clean_optional_text(payload.username),
    )
    if not result.get("handled"):
        raise HTTPException(status_code=404, detail=result.get("reason") or "telegram_challenge_not_found")
    return {"ok": True, "state": result.get("state")}


@app.post("/api/auth/max/start", response_model=ProviderStartResponse)
def auth_max_start() -> ProviderStartResponse:
    if not settings.max_bot_username or not settings.max_bot_token:
        return ProviderStartResponse(
            enabled=False,
            provider="max",
            message="Вход через MAX будет доступен после настройки имени и токена бота.",
        )
    state, url = create_max_login_challenge(settings)
    return ProviderStartResponse(
        enabled=True,
        provider="max",
        url=url,
        state=state,
        message="Откройте MAX только для подтверждения входа, затем вернитесь на сайт.",
    )


@app.get("/api/auth/max/status", response_model=ProviderStatusResponse)
def auth_max_status(state: str) -> ProviderStatusResponse:
    result = complete_max_login(settings, state)
    return ProviderStatusResponse(**result)


@app.post("/api/account/max/start", response_model=ProviderStartResponse)
def account_max_start(user: dict = Depends(current_user)) -> ProviderStartResponse:
    if not settings.max_bot_username or not settings.max_bot_token:
        return ProviderStartResponse(
            enabled=False,
            provider="max",
            message="Подключение MAX будет доступно после настройки имени и токена бота.",
        )
    state, url = create_max_login_challenge(settings, link_user_id=int(user["id"]))
    return ProviderStartResponse(
        enabled=True,
        provider="max",
        url=url,
        state=state,
        message="Откройте MAX только для подтверждения привязки, затем вернитесь на сайт.",
    )


@app.post("/api/webhooks/max")
async def max_webhook(
    request: Request,
    x_max_bot_api_secret: Annotated[str | None, Header()] = None,
) -> dict:
    if settings.max_webhook_secret and x_max_bot_api_secret != settings.max_webhook_secret:
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")
    update = await request.json()
    result = process_max_update(settings, update)
    return {"ok": True, **result}


@app.get("/api/me")
def me(user: dict = Depends(current_user)) -> dict:
    telegram_profile_sync = _safe_sync_telegram_profile_to_pwa(user)
    return {
        "user": user,
        "external_accounts": db.list_external_accounts(settings.database_path, user_id=int(user["id"])),
        "subscription": get_effective_subscription(settings, user).to_public(),
        "telegram_profile_sync": telegram_profile_sync,
    }


@app.post("/api/auth/logout")
def auth_logout(token: str = Depends(_require_bearer)) -> dict:
    db.revoke_session(
        settings.database_path,
        token_hash=hash_value(token, settings.session_secret),
    )
    return {"ok": True, "message": "Сессия завершена."}


@app.post("/api/account/sessions/revoke-all")
def account_revoke_sessions(user: dict = Depends(current_user)) -> dict:
    revoked = db.revoke_user_sessions(settings.database_path, user_id=int(user["id"]))
    return {"ok": True, "revoked": revoked, "message": "Все активные сессии завершены."}


@app.get("/api/account/export")
def account_export(user: dict = Depends(current_user)) -> dict:
    data = db.export_user_data(settings.database_path, user_id=int(user["id"]))
    if not data:
        raise HTTPException(status_code=404, detail="user_not_found")
    return {
        "exported_at": utc_now().isoformat(),
        "format": "temichevvet_user_export_v1",
        "data": data,
    }


@app.post("/api/account/deletion-request")
def account_deletion_request(payload: DataDeletionRequest, user: dict = Depends(current_user)) -> dict:
    if payload.confirm.strip().upper() != "УДАЛИТЬ":
        raise HTTPException(status_code=400, detail="invalid_deletion_confirmation")
    comment = _clean_optional_text(payload.comment) or "Без комментария."
    text = (
        "Запрос удаления персональных данных из PWA и связанных мессенджеров.\n"
        f"Пользователь: #{int(user['id'])}, email: {user.get('email') or 'не указан'}.\n"
        f"Комментарий: {comment}"
    )
    item = db.create_feedback(
        settings.database_path,
        owner_id=int(user["id"]),
        text=text,
        category="data_deletion_request",
    )
    return {
        "ok": True,
        "item": item,
        "message": "Запрос на удаление данных создан. Команда TemichevVet проверит связанные входы и свяжется с вами.",
    }


@app.post("/api/payments/plus/create", response_model=PaymentCreateResponse)
def payment_plus_create(user: dict = Depends(current_user)) -> PaymentCreateResponse:
    sub = get_effective_subscription(settings, user)
    if sub.plan != "free":
        return PaymentCreateResponse(
            ok=True,
            status="already_active",
            message="Plus уже активен. Повторная оплата сейчас не нужна.",
            subscription=sub.to_public(),
        )

    try:
        payment = create_yookassa_plus_payment(
            settings,
            user_id=int(user["id"]),
            user_email=str(user.get("email") or "") or None,
        )
    except YooKassaConfigError as exc:
        raise HTTPException(status_code=503, detail="payment_provider_not_configured") from exc
    except YooKassaPaymentError as exc:
        logger.warning("YooKassa create payment failed: %s", exc)
        raise HTTPException(status_code=502, detail="payment_provider_error") from exc

    payment_id = str(payment.get("id") or "").strip()
    pay_url = yookassa_confirmation_url(payment)
    if not payment_id or not pay_url:
        raise HTTPException(status_code=502, detail="payment_confirmation_missing")

    status = yookassa_payment_status(payment)
    db.create_payment_record(
        settings.database_path,
        user_id=int(user["id"]),
        provider=YOOKASSA_PROVIDER,
        provider_payment_id=payment_id,
        amount_rub=200,
        status=status,
        plan_code="plus",
        confirmation_url=pay_url,
        idempotence_key=str(payment.get("idempotence_key") or ""),
        raw_payload=payment,
    )
    return PaymentCreateResponse(
        ok=True,
        status=status,
        payment_id=payment_id,
        confirmation_url=pay_url,
        message=_payment_message(status),
        subscription=sub.to_public(),
    )


@app.get("/api/payments/plus/status", response_model=PaymentStatusResponse)
def payment_plus_last_status(user: dict = Depends(current_user)) -> PaymentStatusResponse:
    record = db.get_last_payment(settings.database_path, user_id=int(user["id"]), provider=YOOKASSA_PROVIDER)
    if not record:
        return PaymentStatusResponse(
            ok=False,
            status="not_found",
            message="Платёж не найден. Сначала нажмите «Оплатить Plus».",
            subscription=get_effective_subscription(settings, user).to_public(),
        )
    return _refresh_yookassa_payment_for_user(record=record, user=user)


@app.get("/api/payments/{payment_id}/status", response_model=PaymentStatusResponse)
def payment_status(payment_id: str, user: dict = Depends(current_user)) -> PaymentStatusResponse:
    record = db.get_payment_record(
        settings.database_path,
        provider=YOOKASSA_PROVIDER,
        provider_payment_id=str(payment_id),
    )
    if not record:
        raise HTTPException(status_code=404, detail="payment_not_found")
    return _refresh_yookassa_payment_for_user(record=record, user=user)


@app.post("/api/webhooks/yookassa")
async def yookassa_webhook(request: Request, secret: str | None = Query(default=None)) -> dict:
    if settings.yookassa_webhook_secret and not constant_time_equal(secret or "", settings.yookassa_webhook_secret):
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")

    payload = await request.json()
    event = str(payload.get("event") or "")
    obj = payload.get("object") or {}
    if not isinstance(obj, dict):
        return {"ok": True, "ignored": "missing_object"}
    payment_id = str(obj.get("id") or "").strip()
    if not payment_id:
        return {"ok": True, "ignored": "missing_payment_id"}
    if event and event not in {"payment.succeeded", "payment.canceled", "payment.waiting_for_capture"}:
        return {"ok": True, "ignored": event}

    record = db.get_payment_record(settings.database_path, provider=YOOKASSA_PROVIDER, provider_payment_id=payment_id)
    if not record:
        logger.warning("YooKassa webhook for unknown payment %s", payment_id)
        return {"ok": True, "ignored": "unknown_payment"}
    user = db.get_user_by_id(settings.database_path, user_id=int(record["user_id"]))
    if not user:
        logger.warning("YooKassa webhook payment %s has missing user %s", payment_id, record.get("user_id"))
        return {"ok": True, "ignored": "missing_user"}

    try:
        result = _refresh_yookassa_payment_for_user(record=record, user=user)
    except HTTPException as exc:
        logger.warning("YooKassa webhook processing failed for %s: %s", payment_id, exc.detail)
        return {"ok": True, "status": "failed", "detail": exc.detail}
    return {"ok": True, "status": result.status, "payment_id": result.payment_id}


@app.get("/api/pets")
def pets(user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    items = [_pet_public(pet) for pet in db.list_pets(settings.database_path, owner_id=int(user["id"]))]
    return {"items": items}


@app.post("/api/pets")
def create_pet(payload: PetPayload, user: dict = Depends(current_user)) -> dict:
    pet = db.create_pet(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_type=_normalize_pet_type(payload.pet_type),
        pet_name=_clean_text(payload.pet_name, "Питомец"),
        birth_year=payload.birth_year,
        birth_month=payload.birth_month,
        birth_day=payload.birth_day,
        birth_precision=_normalize_birth_precision(payload.birth_precision),
        sex=_clean_optional_text(payload.sex),
        weight_kg=payload.weight_kg,
        breed=_clean_optional_text(payload.breed),
        is_main=payload.is_main,
    )
    sync_result = _safe_sync_pwa_pet_to_telegram(user, pet)
    _enqueue_core_outbound_from_sync(sync_result, (("telegram_pet_id", "pets"),))
    pet = db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=int(pet["id"])) or pet
    return {"item": _pet_public(pet)}


@app.get("/api/pets/{pet_id}")
def get_pet(pet_id: int, user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    pet = db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id)
    if not pet:
        raise HTTPException(status_code=404, detail="pet_not_found")
    reminders = db.list_reminders(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id) or []
    observations = db.list_observations(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=5) or []
    weights = db.list_measurements(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=5) or []
    history = db.list_history(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=10) or []
    return {
        "item": _pet_public(pet),
        "summary": {
            "reminders": len(reminders),
            "observations": len(observations),
            "weights": len(weights),
            "history": len(history),
            "what_now": _pet_what_now(reminders, observations, weights),
        },
        "reminders": reminders,
        "observations": [_parse_json_payload(row) for row in observations],
        "weights": weights,
        "history": history,
    }


def _pet_what_now(reminders: list[dict], observations: list[dict], weights: list[dict]) -> str:
    if reminders:
        next_reminder = reminders[0]
        return f"Ближайшее напоминание: {next_reminder['due_date']} {next_reminder.get('due_time') or ''} — {next_reminder['title']}".strip()
    if observations:
        return "Есть свежие наблюдения. Следите за динамикой и добавляйте изменения в карточку."
    if weights:
        return "Вес сохранён. Обновляйте его регулярно, чтобы видеть динамику."
    return "Добавьте вес, наблюдение или напоминание, чтобы карточка стала полезнее."


@app.patch("/api/pets/{pet_id}")
def update_pet(pet_id: int, payload: PetPatchPayload, user: dict = Depends(current_user)) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if "pet_type" in values and values["pet_type"] is not None:
        values["pet_type"] = _normalize_pet_type(values["pet_type"])
    if "pet_name" in values and values["pet_name"] is not None:
        values["pet_name"] = _clean_text(values["pet_name"], "Питомец")
    if "birth_precision" in values:
        values["birth_precision"] = _normalize_birth_precision(values["birth_precision"])
    for key in ("sex", "breed"):
        if key in values:
            values[key] = _clean_optional_text(values[key])
    pet = db.update_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, values=values)
    if not pet:
        raise HTTPException(status_code=404, detail="pet_not_found")
    sync_result = _safe_sync_pwa_pet_to_telegram(user, pet)
    _enqueue_core_outbound_from_sync(sync_result, (("telegram_pet_id", "pets"),))
    pet = db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id) or pet
    return {"item": _pet_public(pet)}


@app.post("/api/pets/{pet_id}/main")
def set_main_pet(pet_id: int, payload: MainPetPayload, user: dict = Depends(current_user)) -> dict:
    pet = db.set_main_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, is_main=payload.is_main)
    if not pet:
        raise HTTPException(status_code=404, detail="pet_not_found")
    sync_result = _safe_sync_pwa_pet_to_telegram(user, pet)
    _enqueue_core_outbound_from_sync(sync_result, (("telegram_pet_id", "pets"),))
    return {"item": _pet_public(pet)}


@app.delete("/api/pets/{pet_id}")
def delete_pet(pet_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.delete_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id):
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"ok": True}


@app.get("/api/pets/{pet_id}/history")
def pet_history(pet_id: int, user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    items = db.list_history(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=50)
    if items is None:
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"items": items}


@app.get("/api/pets/{pet_id}/weights")
def pet_weights(pet_id: int, user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    items = db.list_measurements(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=50)
    if items is None:
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"items": items}


@app.post("/api/pets/{pet_id}/weights")
def add_pet_weight(pet_id: int, payload: MeasurementPayload, user: dict = Depends(current_user)) -> dict:
    item = db.create_measurement(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_id=pet_id,
        weight_kg=payload.weight_kg,
        note=_clean_optional_text(payload.note),
    )
    if not item:
        raise HTTPException(status_code=404, detail="pet_not_found")
    sync_result = _safe_sync_pwa_measurement_to_telegram(user, item)
    _enqueue_core_outbound_from_sync(
        sync_result,
        (("telegram_pet_id", "pets"), ("telegram_measurement_id", "pet_measurements")),
    )
    return {"item": item}


@app.get("/api/pets/{pet_id}/observations")
def pet_observations(pet_id: int, user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    items = db.list_observations(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=50)
    if items is None:
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"items": [_parse_json_payload(row) for row in items]}


@app.post("/api/pets/{pet_id}/observations")
def add_pet_observation(pet_id: int, payload: ObservationPayload, user: dict = Depends(current_user)) -> dict:
    body = json.dumps({"text": _clean_text(payload.text)}, ensure_ascii=False)
    item = db.create_observation(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_id=pet_id,
        obs_type=_clean_text(payload.obs_type, "note"),
        payload=body,
    )
    if not item:
        raise HTTPException(status_code=404, detail="pet_not_found")
    sync_result = _safe_sync_pwa_observation_to_telegram(user, item)
    _enqueue_core_outbound_from_sync(
        sync_result,
        (("telegram_pet_id", "pets"), ("telegram_observation_id", "pet_observations")),
    )
    return {"item": _parse_json_payload(item)}


@app.get("/api/reminders")
def reminders(user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    return {"items": db.list_reminders(settings.database_path, owner_id=int(user["id"])) or []}


@app.post("/api/reminders")
def add_reminder(payload: ReminderPayload, user: dict = Depends(current_user)) -> dict:
    item = db.create_reminder(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_id=payload.pet_id,
        reminder_type=_clean_text(payload.reminder_type, "custom"),
        title=_clean_text(payload.title),
        due_date=_clean_text(payload.due_date),
        due_time=_clean_optional_text(payload.due_time),
        periodicity=_clean_text(payload.periodicity, "once"),
        notes=_clean_optional_text(payload.notes),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="pet_not_found")
    sync_result = _safe_sync_pwa_reminder_to_telegram(user, item)
    _enqueue_core_outbound_from_sync(
        sync_result,
        (("telegram_pet_id", "pets"), ("telegram_reminder_id", "reminders")),
    )
    return {"item": item}


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user: dict = Depends(current_user)) -> dict:
    sync_result = _safe_sync_pwa_reminder_deactivation(user, reminder_id)
    _enqueue_core_outbound_from_sync(sync_result, (("telegram_reminder_id", "reminders"),))
    if not db.deactivate_reminder(settings.database_path, owner_id=int(user["id"]), reminder_id=reminder_id):
        raise HTTPException(status_code=404, detail="reminder_not_found")
    return {"ok": True}


@app.get("/api/food/search")
def food_search(q: str) -> dict:
    return {"items": [food_to_public(item) for item in find_food(q, limit=5)]}


@app.post("/api/food/check")
def food_check(payload: FoodCheckPayload) -> dict:
    return check_food(payload.query, payload.ingredients)


@app.get("/api/faq")
def faq_list(
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=6, ge=1, le=20),
    user: dict = Depends(current_user),
) -> dict:
    subscription = get_effective_subscription(settings, user)
    return {"items": find_faq(q, plan=subscription.plan, limit=limit)}


@app.get("/api/care")
def care_list(
    q: str = Query(default="", max_length=160),
    limit: int = Query(default=6, ge=1, le=20),
    user: dict = Depends(current_user),
) -> dict:
    subscription = get_effective_subscription(settings, user)
    return {"items": find_care(q, plan=subscription.plan, limit=limit)}


@app.post("/api/feedback")
def create_feedback(payload: FeedbackPayload, user: dict = Depends(current_user)) -> dict:
    item = db.create_feedback(
        settings.database_path,
        owner_id=int(user["id"]),
        text=_clean_text(payload.text),
        category=_clean_optional_text(payload.category),
    )
    return {
        "item": item,
        "message": "Сообщение отправлено команде TemichevVet. Это не связь с ветеринарным врачом.",
    }


@app.get("/api/followups/due")
def due_followups(user: dict = Depends(current_user)) -> dict:
    return {"items": db.list_due_triage_followups(settings.database_path, owner_id=int(user["id"]))}


@app.post("/api/followups/{followup_id}/answer")
def answer_followup(followup_id: int, payload: FollowupAnswerPayload, user: dict = Depends(current_user)) -> dict:
    answer = payload.answer.strip().lower()
    if answer not in {"better", "same", "worse", "retry"}:
        raise HTTPException(status_code=400, detail="invalid_followup_answer")
    if not db.mark_triage_followup_answered(
        settings.database_path,
        owner_id=int(user["id"]),
        followup_id=followup_id,
        answer=answer,
    ):
        raise HTTPException(status_code=404, detail="followup_not_found")
    messages = {
        "better": "Хорошо. Продолжайте наблюдение и следуйте рекомендациям врача, если они были даны.",
        "same": "Продолжайте внимательно наблюдать. Если состояние не улучшается или есть сомнения — лучше показать питомца врачу.",
        "worse": "Ухудшение состояния — повод для очного осмотра. Рекомендуется обратиться в клинику как можно скорее.",
        "retry": "Откройте новый разбор и добавьте свежие симптомы. Это будет отдельная проверка состояния.",
    }
    return {"ok": True, "message": messages[answer]}


@app.post("/api/triage")
def triage(payload: TriageRequest, user: dict = Depends(current_user)) -> dict:
    _safe_sync_telegram_profile_to_pwa(user)
    pet_id = payload.pet_id
    if pet_id is not None and not db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id):
        raise HTTPException(status_code=404, detail="pet_not_found")
    pets = db.list_pets(settings.database_path, owner_id=int(user["id"]))
    selected_pet = (
        db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=int(pet_id))
        if pet_id is not None
        else None
    )

    red_flags = detect_red_flags(payload.text)
    if red_flags.has_red_flags:
        sub = get_effective_subscription(settings, user)
        answer = render_red_flag_response(red_flags)
        summary = "Красные симптомы: " + ", ".join(red_flags.matched)
        log = db.create_triage_log(
            settings.database_path,
            owner_id=int(user["id"]),
            pet_id=pet_id,
            complaint_text=_clean_text(payload.text),
            response_text=answer,
            urgency_level="red",
            quota_before=sub.quota_used,
            quota_after=sub.quota_used,
            subscription_source=sub.source,
        )
        followup = _schedule_pwa_followup(
            user_id=int(user["id"]),
            pet_id=pet_id,
            triage_id=log["id"] if log else None,
            urgency="red",
            complaint_text=_clean_text(payload.text),
            summary=summary,
        )
        telegram_sync = _safe_sync_triage_to_telegram(
            pwa_user=user,
            selected_pet=selected_pet,
            pwa_triage_id=log["id"] if log else None,
            complaint_text=_clean_text(payload.text),
            response_text=answer,
            urgency_level="red",
            summary=summary,
            quota_before=sub.quota_used,
            quota_after=sub.quota_used,
        )
        _enqueue_core_outbound_from_sync(
            telegram_sync,
            (
                ("telegram_pet_id", "pets"),
                ("telegram_triage_id", "triage_logs"),
                ("telegram_history_id", "pet_history"),
                ("telegram_observation_id", "pet_observations"),
                ("telegram_followup_id", "triage_followups"),
            ),
        )
        return {
            "status": "red",
            "urgency": "red",
            "matched": list(red_flags.matched),
            "triage_id": log["id"] if log else None,
            "answer": answer,
            "subscription": sub.to_public(),
            "followup": followup,
            "telegram_sync": telegram_sync,
        }

    ok, sub = try_consume_quota(settings, user, amount=1)
    if not ok:
        raise HTTPException(
            status_code=402,
            detail=(
                "Лимит разборов по текущему тарифу закончился. "
                "Если Plus уже оплачен в Telegram, войдите на сайте через Telegram или подключите Telegram в разделе «Способы входа»."
            ),
        )
    quota_before = sub.quota_used - 1
    quota_after = sub.quota_used
    try:
        llm_result = call_triage_llm(
            user=user,
            pets=pets,
            selected_pet=selected_pet,
            complaint_text=_clean_text(payload.text),
            plan_code=sub.plan,
        )
    except Exception as exc:
        refund_quota(sub, amount=1)
        logger.exception("PWA triage LLM failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Не удалось получить разбор. Запрос не списан, попробуйте позже.",
        ) from exc

    urgency_emoji, urgency_label, urgency_level = extract_urgency(llm_result.text)
    urgency = urgency_level or "yellow"
    summary = short_summary(llm_result.text) or _clean_text(payload.text)
    log = db.create_triage_log(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_id=pet_id,
        complaint_text=_clean_text(payload.text),
        response_text=llm_result.text,
        urgency_level=urgency,
        quota_before=quota_before,
        quota_after=quota_after,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        total_tokens=llm_result.total_tokens,
        model=llm_result.model,
        subscription_source=sub.source,
    )
    followup = _schedule_pwa_followup(
        user_id=int(user["id"]),
        pet_id=pet_id,
        triage_id=log["id"] if log else None,
        urgency=urgency,
        complaint_text=_clean_text(payload.text),
        summary=summary,
    )
    telegram_sync = _safe_sync_triage_to_telegram(
        pwa_user=user,
        selected_pet=selected_pet,
        pwa_triage_id=log["id"] if log else None,
        complaint_text=_clean_text(payload.text),
        response_text=llm_result.text,
        urgency_level=urgency,
        summary=summary,
        quota_before=quota_before,
        quota_after=quota_after,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        total_tokens=llm_result.total_tokens,
    )
    if sub.source == "telegram":
        _enqueue_core_outbound_subscription_for_bot_user(sub.user_id)
    _enqueue_core_outbound_from_sync(
        telegram_sync,
        (
            ("telegram_pet_id", "pets"),
            ("telegram_triage_id", "triage_logs"),
            ("telegram_history_id", "pet_history"),
            ("telegram_observation_id", "pet_observations"),
            ("telegram_followup_id", "triage_followups"),
        ),
    )
    return {
        "status": "saved",
        "urgency": urgency,
        "urgency_emoji": urgency_emoji,
        "urgency_label": urgency_label,
        "summary": summary,
        "user_id": user["id"],
        "triage_id": log["id"] if log else None,
        "answer": llm_result.text,
        "subscription": sub.to_public(),
        "followup": followup,
        "telegram_sync": telegram_sync,
    }


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(WEB_ROOT / "index.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=False)
