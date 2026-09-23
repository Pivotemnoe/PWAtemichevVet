"""Local-only synthetic browser fixture. Never deploy this runner."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({key: "" for key in ("OPENAI_API_KEY", "BOT_DATABASE_PATH", "MAX_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_AUTH_SECRET")})
from scripts import test_api as fixture
from fastapi.responses import HTMLResponse, Response
import uvicorn

fixture.disable_external_sync()
fixture.api.settings = fixture.replace(
    fixture.api.settings, bot_database_path="", yookassa_shop_id="", yookassa_secret_key="",
)

@fixture.api.app.get("/qa-seed", response_class=HTMLResponse)
def seed():
    return '<script src="/api/qa-seed.js"></script>'

@fixture.api.app.get("/api/qa-seed.js")
def seed_script():
    pending = {
        "pet_type": "cat", "age": "1 год", "text": "Синтетическая проверка: питомец менее активен после переезда.",
        "answer": "Это синтетический разбор для проверки интерфейса. Запишите наблюдения и обсудите изменения с ветеринаром.",
        "urgency": "yellow", "landing_slug": "cat-not-eating",
        "client_request_id": "qa-service-case-20260911", "created_at": "2026-09-10T10:00:00Z",
    }
    return Response("localStorage.setItem('tvv_pending_check_save',JSON.stringify(" + json.dumps(pending, ensure_ascii=False) + "));localStorage.setItem('tvv_public_check_preview_used','1');location.href='/check/cat-not-eating';", media_type="application/javascript")

if __name__ == "__main__":
    fixture.api.app.router.routes.insert(0, fixture.api.app.router.routes.pop())
    fixture.api.app.router.routes.insert(0, fixture.api.app.router.routes.pop())
    uvicorn.run(fixture.api.app, host="127.0.0.1", port=8080)
