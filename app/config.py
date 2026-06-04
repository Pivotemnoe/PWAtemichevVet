from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_base_url: str
    session_secret: str
    database_path: Path
    telegram_bot_username: str
    telegram_auth_secret: str
    max_bot_username: str
    max_bot_token: str
    max_api_base_url: str
    max_webhook_secret: str
    dev_auth_code_log: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    smtp_use_tls: bool
    bot_database_path: str


def get_settings() -> Settings:
    database_path = Path(os.getenv("DATABASE_PATH", "./pwa.db")).expanduser()
    return Settings(
        app_env=os.getenv("APP_ENV", "development").strip().lower() or "development",
        app_base_url=os.getenv("APP_BASE_URL", "http://127.0.0.1:8080").strip(),
        session_secret=os.getenv("SESSION_SECRET", "change-me-long-random-secret"),
        database_path=database_path,
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
        telegram_auth_secret=os.getenv("TELEGRAM_AUTH_SECRET", "").strip(),
        max_bot_username=os.getenv("MAX_BOT_USERNAME", "").strip().lstrip("@"),
        max_bot_token=os.getenv("MAX_BOT_TOKEN", "").strip(),
        max_api_base_url=os.getenv("MAX_API_BASE_URL", "https://platform-api.max.ru").strip().rstrip("/"),
        max_webhook_secret=os.getenv("MAX_WEBHOOK_SECRET", "").strip(),
        dev_auth_code_log=_bool_env("DEV_AUTH_CODE_LOG", default=False),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587") or "587"),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "").strip(),
        smtp_use_tls=_bool_env("SMTP_USE_TLS", default=True),
        bot_database_path=os.getenv("BOT_DATABASE_PATH", "").strip(),
    )
