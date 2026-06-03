from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from app import db
from app.config import Settings, get_settings
from app.emailer import send_login_code
from app.max_auth import complete_max_login, create_max_login_challenge, process_max_update
from app.security import constant_time_equal, expires_in, hash_value, make_code, make_token, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"

app = FastAPI(title="TemichevVet PWA API", version="0.1.0")
settings = get_settings()
db.init_db(settings.database_path)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


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


class TriageRequest(BaseModel):
    pet_id: int | None = None
    text: str = Field(min_length=3, max_length=2000)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "temichevvet-pwa", "env": settings.app_env}


@app.get("/api/config")
def public_config() -> dict:
    return {
        "telegram_enabled": bool(settings.telegram_bot_username),
        "max_enabled": bool(settings.max_bot_username and settings.max_bot_token),
        "email_enabled": True,
    }


@app.post("/api/auth/email/start", response_model=EmailStartResponse)
def auth_email_start(payload: EmailStartRequest) -> EmailStartResponse:
    email = _normalize_email(str(payload.email))
    code = make_code()
    db.create_auth_challenge(
        settings.database_path,
        channel="email",
        target=email,
        code_hash=hash_value(code, settings.session_secret),
        expires_at=expires_in(10),
    )
    send_login_code(settings, email=email, code=code)
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
    token = make_token()[:24]
    return ProviderStartResponse(
        enabled=True,
        provider="telegram",
        url=f"https://t.me/{settings.telegram_bot_username}?start=web_auth_{token}",
        message="Откройте Telegram-бота и подтвердите вход.",
    )


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
        message="Откройте MAX-бота и нажмите старт, чтобы подтвердить вход.",
    )


@app.get("/api/auth/max/status", response_model=ProviderStatusResponse)
def auth_max_status(state: str) -> ProviderStatusResponse:
    result = complete_max_login(settings, state)
    return ProviderStatusResponse(**result)


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
    return {"user": user}


@app.get("/api/pets")
def pets(user: dict = Depends(current_user)) -> dict:
    return {
        "items": [],
        "message": "Карточки питомцев будут подключены следующим этапом.",
        "user_id": user["id"],
    }


@app.post("/api/triage")
def triage(payload: TriageRequest, user: dict = Depends(current_user)) -> dict:
    return {
        "status": "draft",
        "user_id": user["id"],
        "answer": (
            "PWA подключена. Медицинский разбор будет подключён к общей логике TemichevVet "
            "после утверждения API-слоя."
        ),
    }


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(WEB_ROOT / "index.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=False)
