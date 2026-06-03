from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Any

from app import db
from app.config import Settings
from app.security import expires_in, hash_value, make_token, utc_now

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


MAX_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{12,80}$")


def make_max_state() -> str:
    return f"pwa_{make_token()[:28]}"


def max_deep_link(settings: Settings, state: str) -> str:
    username = settings.max_bot_username.strip().lstrip("@")
    return f"https://max.ru/{username}?start={urllib.parse.quote(state)}"


def create_max_login_challenge(settings: Settings) -> tuple[str, str]:
    state = make_max_state()
    payload = json.dumps({"status": "pending"}, ensure_ascii=False)
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
    headers = {"Authorization": f"Bearer {settings.max_bot_token}"}
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


def send_max_text(settings: Settings, *, user_id: str, text: str) -> None:
    try:
        _max_request(settings, "POST", "/messages", {"user_id": int(user_id), "text": text})
    except Exception:
        # Login should not fail only because the confirmation message was not delivered.
        return


def get_max_updates(settings: Settings, *, marker: int | None = None, limit: int = 10, timeout: int = 30) -> dict[str, Any]:
    return _max_request(
        settings,
        "GET",
        "/updates",
        query={
            "marker": marker,
            "limit": limit,
            "timeout": timeout,
            "types": "bot_started",
        },
    )


def _extract_user(update: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("user", "sender", "from"):
        value = update.get(key)
        if isinstance(value, dict):
            user_id = value.get("user_id") or value.get("id")
            name = value.get("name") or value.get("display_name") or value.get("first_name")
            if user_id:
                return str(user_id), str(name) if name else None
    user_id = update.get("user_id")
    if user_id:
        return str(user_id), None
    return None, None


def process_max_update(settings: Settings, update: dict[str, Any]) -> dict[str, Any]:
    update_type = str(update.get("update_type") or update.get("type") or "")
    if update_type and update_type != "bot_started":
        return {"handled": False, "reason": "unsupported_update_type"}

    state = str(update.get("payload") or "")
    if not MAX_STATE_RE.match(state):
        return {"handled": False, "reason": "invalid_or_missing_payload"}

    challenge = db.find_active_challenge(settings.database_path, channel="max", target=state)
    if not challenge:
        return {"handled": False, "reason": "challenge_not_found"}

    provider_user_id, display_name = _extract_user(update)
    if not provider_user_id:
        return {"handled": False, "reason": "user_not_found"}

    payload = {
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
        text="Вход в TemichevVet подтвержден. Вернитесь в PWA, она завершит вход автоматически.",
    )
    return {"handled": True, "state": state}


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
