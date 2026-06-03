from __future__ import annotations

import json
import re
from datetime import date, timedelta
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
from app.knowledge import check_food, find_food, food_to_public
from app.max_auth import complete_max_login, create_max_login_challenge, process_max_update
from app.medical_safety import detect_red_flags, render_red_flag_response
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


def _normalize_email(email: str) -> str:
    return email.strip().lower()


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
    return {"item": _pet_public(pet)}


@app.get("/api/pets/{pet_id}")
def get_pet(pet_id: int, user: dict = Depends(current_user)) -> dict:
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
    return {"item": _pet_public(pet)}


@app.post("/api/pets/{pet_id}/main")
def set_main_pet(pet_id: int, payload: MainPetPayload, user: dict = Depends(current_user)) -> dict:
    pet = db.set_main_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, is_main=payload.is_main)
    if not pet:
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"item": _pet_public(pet)}


@app.delete("/api/pets/{pet_id}")
def delete_pet(pet_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.delete_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id):
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"ok": True}


@app.get("/api/pets/{pet_id}/history")
def pet_history(pet_id: int, user: dict = Depends(current_user)) -> dict:
    items = db.list_history(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id, limit=50)
    if items is None:
        raise HTTPException(status_code=404, detail="pet_not_found")
    return {"items": items}


@app.get("/api/pets/{pet_id}/weights")
def pet_weights(pet_id: int, user: dict = Depends(current_user)) -> dict:
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
    return {"item": item}


@app.get("/api/pets/{pet_id}/observations")
def pet_observations(pet_id: int, user: dict = Depends(current_user)) -> dict:
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
    return {"item": _parse_json_payload(item)}


@app.get("/api/reminders")
def reminders(user: dict = Depends(current_user)) -> dict:
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
    return {"item": item}


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.deactivate_reminder(settings.database_path, owner_id=int(user["id"]), reminder_id=reminder_id):
        raise HTTPException(status_code=404, detail="reminder_not_found")
    return {"ok": True}


@app.get("/api/food/search")
def food_search(q: str) -> dict:
    return {"items": [food_to_public(item) for item in find_food(q, limit=5)]}


@app.post("/api/food/check")
def food_check(payload: FoodCheckPayload) -> dict:
    return check_food(payload.query, payload.ingredients)


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


@app.post("/api/triage")
def triage(payload: TriageRequest, user: dict = Depends(current_user)) -> dict:
    pet_id = payload.pet_id
    if pet_id is not None and not db.get_pet(settings.database_path, owner_id=int(user["id"]), pet_id=pet_id):
        raise HTTPException(status_code=404, detail="pet_not_found")

    red_flags = detect_red_flags(payload.text)
    if red_flags.has_red_flags:
        answer = render_red_flag_response(red_flags)
        log = db.create_triage_log(
            settings.database_path,
            owner_id=int(user["id"]),
            pet_id=pet_id,
            complaint_text=_clean_text(payload.text),
            response_text=answer,
            urgency_level="red",
        )
        return {
            "status": "red",
            "urgency": "red",
            "matched": list(red_flags.matched),
            "triage_id": log["id"] if log else None,
            "answer": answer,
        }

    answer = (
        "🟡 Нужна консультация\n\n"
        "В веб-версии уже работает проверка красных симптомов и сохранение обращения в историю питомца. "
        "Полный LLM-разбор с лимитами и оплатой будет подключён следующим переносом из Telegram-бота.\n\n"
        "Пока используйте этот раздел для фиксации жалобы. Если состояние ухудшается, не ждите онлайн-ответа и обратитесь в клинику."
    )
    log = db.create_triage_log(
        settings.database_path,
        owner_id=int(user["id"]),
        pet_id=pet_id,
        complaint_text=_clean_text(payload.text),
        response_text=answer,
        urgency_level="yellow",
    )
    return {
        "status": "saved",
        "urgency": "yellow",
        "user_id": user["id"],
        "triage_id": log["id"] if log else None,
        "answer": answer,
    }


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(WEB_ROOT / "index.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=False)
