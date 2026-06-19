from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Any

from app import db
from app.config import Settings
from app.security import constant_time_equal, expires_in, hash_value, make_token, utc_now

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


MAX_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{12,80}$")
MAX_WEBHOOK_UPDATE_TYPES = ("bot_started", "message_created", "message_callback")
MAX_INIT_DATA_MAX_AGE_SECONDS = 60 * 60
logger = logging.getLogger(__name__)


def make_max_state() -> str:
    return f"pwa_{make_token()[:28]}"


def max_deep_link(settings: Settings, state: str) -> str:
    username = settings.max_bot_username.strip().lstrip("@")
    return f"https://max.ru/{username}?start={urllib.parse.quote(state)}"


def create_max_login_challenge(settings: Settings, *, link_user_id: int | None = None) -> tuple[str, str]:
    state = make_max_state()
    payload_data: dict[str, Any] = {"status": "pending"}
    if link_user_id:
        payload_data["link_user_id"] = int(link_user_id)
    payload = json.dumps(payload_data, ensure_ascii=False)
    db.create_auth_challenge(
        settings.database_path,
        channel="max",
        target=state,
        code_hash=hash_value(state, settings.session_secret),
        payload=payload,
        expires_at=expires_in(10),
    )
    return state, max_deep_link(settings, state)


def parse_challenge_payload(raw_payload: str | None) -> dict[str, Any]:
    if not raw_payload:
        return {"status": "pending"}
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {"status": "pending"}
    return data if isinstance(data, dict) else {"status": "pending"}


def _display_name_from_max_user(user: dict[str, Any]) -> str | None:
    parts = [
        str(user.get("first_name") or "").strip(),
        str(user.get("last_name") or "").strip(),
    ]
    display_name = " ".join(part for part in parts if part).strip()
    if display_name:
        return display_name
    username = str(user.get("username") or "").strip()
    return username or None


def validate_max_init_data(
    settings: Settings,
    init_data: str,
    *,
    max_age_seconds: int = MAX_INIT_DATA_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    if not settings.max_bot_token:
        return {"ok": False, "reason": "max_not_configured"}
    raw_init_data = (init_data or "").strip()
    if not raw_init_data:
        return {"ok": False, "reason": "init_data_missing"}

    try:
        params = urllib.parse.parse_qsl(raw_init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return {"ok": False, "reason": "init_data_invalid"}
    if not params:
        return {"ok": False, "reason": "init_data_empty"}

    keys = [key for key, _value in params]
    if len(set(keys)) != len(keys):
        return {"ok": False, "reason": "duplicate_init_data_key"}
    hash_values = [value for key, value in params if key == "hash"]
    if len(hash_values) != 1 or not hash_values[0]:
        return {"ok": False, "reason": "hash_missing"}

    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params) if key != "hash")
    secret_key = hmac.new(
        b"WebAppData",
        settings.max_bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(secret_key, launch_params.encode("utf-8"), hashlib.sha256).hexdigest()
    if not constant_time_equal(expected_hash, hash_values[0]):
        return {"ok": False, "reason": "hash_mismatch"}

    param_map = dict(params)
    try:
        auth_date = int(str(param_map.get("auth_date") or "0"))
    except ValueError:
        return {"ok": False, "reason": "auth_date_invalid"}
    now_ts = int(utc_now().timestamp())
    if auth_date <= 0:
        return {"ok": False, "reason": "auth_date_missing"}
    if auth_date > now_ts + 300:
        return {"ok": False, "reason": "auth_date_in_future"}
    if max_age_seconds > 0 and now_ts - auth_date > max_age_seconds:
        return {"ok": False, "reason": "auth_date_expired"}

    try:
        user = json.loads(str(param_map.get("user") or ""))
    except json.JSONDecodeError:
        return {"ok": False, "reason": "user_invalid"}
    if not isinstance(user, dict):
        return {"ok": False, "reason": "user_invalid"}
    provider_user_id = str(user.get("id") or "").strip()
    if not provider_user_id:
        return {"ok": False, "reason": "user_id_missing"}

    return {
        "ok": True,
        "provider_user_id": provider_user_id,
        "display_name": _display_name_from_max_user(user),
        "username": str(user.get("username") or "").strip() or None,
        "auth_date": auth_date,
    }


def complete_max_init_login(settings: Settings, init_data: str) -> dict[str, Any]:
    validation = validate_max_init_data(settings, init_data)
    if not validation.get("ok"):
        return {
            "status": "expired",
            "message": "MAX не подтвердил запуск мини-приложения. Откройте кабинет из MAX ещё раз.",
            "reason": validation.get("reason") or "init_data_invalid",
        }

    user = db.get_or_create_user_by_external_account(
        settings.database_path,
        provider="max",
        provider_user_id=str(validation["provider_user_id"]),
        display_name=validation.get("display_name"),
    )
    token = make_token()
    db.create_session(
        settings.database_path,
        user_id=int(user["id"]),
        token_hash=hash_value(token, settings.session_secret),
        expires_at=(utc_now() + timedelta(days=30)).isoformat(),
    )
    return {"status": "complete", "token": token, "user": user}


def _max_request(
    settings: Settings,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.max_bot_token:
        raise RuntimeError("MAX_BOT_TOKEN is not configured")
    url = f"{settings.max_api_base_url}{path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        url = f"{url}?{urllib.parse.urlencode(clean_query)}"
    data = None
    headers = {"Authorization": settings.max_bot_token}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MAX API HTTP {exc.code}: {details}") from exc
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _app_url(settings: Settings) -> str:
    url = (settings.app_base_url or "").strip()
    if url:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme in {"http", "https"} and host not in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
            return url.rstrip("/")
    return "https://temichevvet.ru"


def _app_action_url(settings: Settings, action: str | None = None) -> str:
    url = _app_url(settings)
    if not action:
        return url
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "action"]
    query.append(("action", action))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


def _max_mini_app_url(settings: Settings, action: str = "home") -> str:
    username = settings.max_bot_username.strip().lstrip("@")
    if not username:
        return _app_action_url(settings, None if action == "home" else action)
    query = urllib.parse.urlencode({"startapp": action})
    return f"https://max.ru/{username}?{query}"


def _open_app_keyboard(settings: Settings) -> list[dict[str, Any]]:
    buttons = [
        [{"type": "link", "text": "Открыть кабинет", "url": _max_mini_app_url(settings, "home")}],
        [
            {"type": "link", "text": "Разобрать жалобу", "url": _max_mini_app_url(settings, "triage")},
            {"type": "link", "text": "Питомцы", "url": _max_mini_app_url(settings, "pets")},
        ],
        [
            {"type": "link", "text": "Напоминания", "url": _max_mini_app_url(settings, "reminders")},
            {"type": "link", "text": "Подписка", "url": _max_mini_app_url(settings, "subscription")},
        ],
        [{"type": "link", "text": "Помощь", "url": _max_mini_app_url(settings, "more")}],
    ]
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": buttons
            },
        }
    ]


def send_max_text(
    settings: Settings,
    *,
    user_id: str,
    text: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    try:
        body: dict[str, Any] = {"text": text}
        if attachments is not None:
            body["attachments"] = attachments
        _max_request(settings, "POST", "/messages", body, query={"user_id": int(user_id)})
    except Exception as exc:
        # Login should not fail only because the confirmation message was not delivered.
        logger.warning("MAX message delivery failed for user_id=%s: %s", user_id, type(exc).__name__)
        return


def send_max_welcome(settings: Settings, *, user_id: str) -> None:
    send_max_text(
        settings,
        user_id=user_id,
        text=(
            "TemichevVet в MAX: выберите раздел личного кабинета.\n\n"
            "Открыть кабинет — главная PWA.\n"
            "Разобрать жалобу — проверка симптомов питомца.\n"
            "Питомцы — карточки и история.\n"
            "Напоминания — процедуры и задачи.\n"
            "Подписка — тариф и лимиты.\n"
            "Помощь — справка, питание, FAQ и настройки."
        ),
        attachments=_open_app_keyboard(settings),
    )


def get_max_updates(settings: Settings, *, marker: int | None = None, limit: int = 10, timeout: int = 30) -> dict[str, Any]:
    return _max_request(
        settings,
        "GET",
        "/updates",
        query={
            "marker": marker,
            "limit": limit,
            "timeout": timeout,
            "types": ",".join(MAX_WEBHOOK_UPDATE_TYPES),
        },
    )


def create_max_webhook_subscription(
    settings: Settings,
    *,
    url: str | None = None,
    update_types: tuple[str, ...] = MAX_WEBHOOK_UPDATE_TYPES,
) -> dict[str, Any]:
    webhook_url = (url or f"{_app_url(settings)}/api/webhooks/max").strip()
    body: dict[str, Any] = {
        "url": webhook_url,
        "update_types": list(update_types),
    }
    if settings.max_webhook_secret:
        body["secret"] = settings.max_webhook_secret
    return _max_request(settings, "POST", "/subscriptions", body)


def _extract_user(update: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("user", "sender", "from"):
        value = update.get(key)
        if isinstance(value, dict):
            user_id = value.get("user_id") or value.get("id")
            name = value.get("name") or value.get("display_name") or value.get("first_name")
            if user_id:
                return str(user_id), str(name) if name else None
    message = update.get("message")
    if isinstance(message, dict):
        sender = message.get("sender")
        if isinstance(sender, dict):
            user_id = sender.get("user_id") or sender.get("id")
            name = sender.get("name") or sender.get("display_name") or sender.get("first_name")
            if user_id:
                return str(user_id), str(name) if name else None
    user_id = update.get("user_id")
    if user_id:
        return str(user_id), None
    return None, None


def _extract_start_payload(update: dict[str, Any]) -> str:
    for key in ("payload", "start_payload", "start"):
        value = update.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _extract_message_text(update: dict[str, Any]) -> str:
    message = update.get("message")
    if isinstance(message, dict):
        body = message.get("body")
        if isinstance(body, dict) and isinstance(body.get("text"), str):
            return body["text"].strip()
    body = update.get("body")
    if isinstance(body, dict) and isinstance(body.get("text"), str):
        return body["text"].strip()
    text = update.get("text")
    return text.strip() if isinstance(text, str) else ""


def process_max_update(settings: Settings, update: dict[str, Any]) -> dict[str, Any]:
    update_type = str(update.get("update_type") or update.get("type") or "")
    if update_type in {"", "bot_started"}:
        state = _extract_start_payload(update)
        provider_user_id, display_name = _extract_user(update)
        if MAX_STATE_RE.match(state):
            challenge = db.find_active_challenge(settings.database_path, channel="max", target=state)
            if not challenge:
                return {"handled": False, "reason": "challenge_not_found"}

            if not provider_user_id:
                return {"handled": False, "reason": "user_not_found"}

            existing_payload = parse_challenge_payload(challenge.get("payload"))
            payload = {
                **existing_payload,
                "status": "confirmed",
                "provider_user_id": provider_user_id,
                "display_name": display_name,
                "confirmed_at": utc_now().isoformat(),
            }
            db.update_challenge_payload(
                settings.database_path,
                int(challenge["id"]),
                json.dumps(payload, ensure_ascii=False),
            )
            send_max_text(
                settings,
                user_id=provider_user_id,
                text=(
                    "Вход в TemichevVet подтвержден. MAX использован только для подтверждения личности. "
                    "Вернитесь на сайт или в PWA, кабинет откроется автоматически."
                ),
                attachments=_open_app_keyboard(settings),
            )
            return {"handled": True, "state": state, "action": "auth_confirmed"}

        if provider_user_id:
            send_max_welcome(settings, user_id=provider_user_id)
            return {"handled": True, "action": "welcome"}

        return {"handled": False, "reason": "user_not_found"}

    if update_type == "message_created":
        provider_user_id, _display_name = _extract_user(update)
        if not provider_user_id:
            return {"handled": False, "reason": "user_not_found"}
        message_text = _extract_message_text(update)
        send_max_welcome(settings, user_id=provider_user_id)
        return {"handled": True, "action": "message_menu", "message_text_present": bool(message_text)}

    if update_type == "message_callback":
        provider_user_id, _display_name = _extract_user(update)
        if not provider_user_id:
            return {"handled": False, "reason": "user_not_found"}
        send_max_welcome(settings, user_id=provider_user_id)
        return {"handled": True, "action": "callback_menu"}

    return {"handled": False, "reason": "unsupported_update_type"}


def complete_max_login(settings: Settings, state: str) -> dict[str, Any]:
    if not MAX_STATE_RE.match(state):
        return {"status": "expired", "message": "Некорректный код входа."}
    challenge = db.find_active_challenge(settings.database_path, channel="max", target=state)
    if not challenge:
        return {"status": "expired", "message": "Код входа истек или уже использован."}
    payload = parse_challenge_payload(challenge.get("payload"))
    if payload.get("status") != "confirmed":
        return {"status": "pending", "message": "Ожидаем подтверждение в MAX."}

    provider_user_id = str(payload.get("provider_user_id") or "")
    if not provider_user_id:
        return {"status": "expired", "message": "MAX не передал пользователя."}

    link_user_id = payload.get("link_user_id")
    if link_user_id:
        user = db.link_or_merge_external_account(
            settings.database_path,
            user_id=int(link_user_id),
            provider="max",
            provider_user_id=provider_user_id,
            display_name=payload.get("display_name"),
        )
        if not user:
            return {"status": "expired", "message": "Не удалось подключить MAX к кабинету."}
    else:
        user = db.get_or_create_user_by_external_account(
            settings.database_path,
            provider="max",
            provider_user_id=provider_user_id,
            display_name=payload.get("display_name"),
        )
    db.consume_challenge(settings.database_path, int(challenge["id"]))
    token = make_token()
    db.create_session(
        settings.database_path,
        user_id=int(user["id"]),
        token_hash=hash_value(token, settings.session_secret),
        expires_at=(utc_now() + timedelta(days=30)).isoformat(),
    )
    return {"status": "complete", "token": token, "user": user}
