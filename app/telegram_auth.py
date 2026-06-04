from __future__ import annotations

import json
import re
import urllib.parse
from datetime import timedelta
from typing import Any

from app import db
from app.config import Settings
from app.security import expires_in, hash_value, make_token, utc_now


TELEGRAM_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{12,80}$")


def make_telegram_state() -> str:
    return f"pwa_{make_token()[:28]}"


def telegram_deep_link(settings: Settings, state: str) -> str:
    username = settings.telegram_bot_username.strip().lstrip("@")
    return f"https://t.me/{username}?start=web_auth_{urllib.parse.quote(state)}"


def create_telegram_login_challenge(settings: Settings, *, link_user_id: int | None = None) -> tuple[str, str]:
    state = make_telegram_state()
    payload_data: dict[str, Any] = {"status": "pending"}
    if link_user_id:
        payload_data["link_user_id"] = int(link_user_id)
    payload = json.dumps(payload_data, ensure_ascii=False)
    db.create_auth_challenge(
        settings.database_path,
        channel="telegram",
        target=state,
        code_hash=hash_value(state, settings.session_secret),
        payload=payload,
        expires_at=expires_in(10),
    )
    return state, telegram_deep_link(settings, state)


def parse_challenge_payload(raw_payload: str | None) -> dict[str, Any]:
    if not raw_payload:
        return {"status": "pending"}
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {"status": "pending"}
    return data if isinstance(data, dict) else {"status": "pending"}


def confirm_telegram_login(
    settings: Settings,
    *,
    state: str,
    telegram_id: str,
    display_name: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    if not TELEGRAM_STATE_RE.match(state):
        return {"handled": False, "reason": "invalid_or_missing_payload"}

    challenge = db.find_active_challenge(settings.database_path, channel="telegram", target=state)
    if not challenge:
        return {"handled": False, "reason": "challenge_not_found"}

    provider_user_id = str(telegram_id or "").strip()
    if not provider_user_id:
        return {"handled": False, "reason": "user_not_found"}

    existing_payload = parse_challenge_payload(challenge.get("payload"))
    payload = {
        **existing_payload,
        "status": "confirmed",
        "provider_user_id": provider_user_id,
        "display_name": display_name,
        "username": username,
        "confirmed_at": utc_now().isoformat(),
    }
    db.update_challenge_payload(
        settings.database_path,
        int(challenge["id"]),
        json.dumps(payload, ensure_ascii=False),
    )
    return {"handled": True, "state": state}


def complete_telegram_login(settings: Settings, state: str) -> dict[str, Any]:
    if not TELEGRAM_STATE_RE.match(state):
        return {"status": "expired", "message": "Некорректный код входа."}
    challenge = db.find_active_challenge(settings.database_path, channel="telegram", target=state)
    if not challenge:
        return {"status": "expired", "message": "Код входа истек или уже использован."}

    payload = parse_challenge_payload(challenge.get("payload"))
    if payload.get("status") != "confirmed":
        return {"status": "pending", "message": "Ожидаем подтверждение в Telegram."}

    provider_user_id = str(payload.get("provider_user_id") or "")
    if not provider_user_id:
        return {"status": "expired", "message": "Telegram не передал пользователя."}

    display_name = payload.get("display_name") or payload.get("username")
    link_user_id = payload.get("link_user_id")
    if link_user_id:
        user = db.link_or_merge_external_account(
            settings.database_path,
            user_id=int(link_user_id),
            provider="telegram",
            provider_user_id=provider_user_id,
            display_name=display_name,
        )
        if not user:
            return {"status": "expired", "message": "Не удалось подключить Telegram к кабинету."}
    else:
        user = db.get_or_create_user_by_external_account(
            settings.database_path,
            provider="telegram",
            provider_user_id=provider_user_id,
            display_name=display_name,
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
