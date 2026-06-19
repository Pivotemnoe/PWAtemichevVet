from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.max_auth import MAX_WEBHOOK_UPDATE_TYPES, create_max_webhook_subscription


PRODUCTION_MAX_WEBHOOK_URL = "https://temichevvet.ru/api/webhooks/max"
_SENSITIVE_KEY_PARTS = ("token", "secret", "authorization")


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "***"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _is_public_https_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "::1"}


def _resolve_webhook_url(app_base_url: str, arg_url: str) -> str:
    if arg_url:
        webhook_url = arg_url.strip()
    else:
        base_url = app_base_url.strip().rstrip("/")
        webhook_url = (
            f"{base_url}/api/webhooks/max"
            if _is_public_https_url(base_url)
            else PRODUCTION_MAX_WEBHOOK_URL
        )
    if not _is_public_https_url(webhook_url):
        raise SystemExit("MAX webhook URL must be a public HTTPS URL.")
    return webhook_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the TemichevVet MAX webhook subscription.")
    parser.add_argument(
        "--url",
        default="",
        help="Webhook URL. Defaults to APP_BASE_URL + /api/webhooks/max, or production temichevvet.ru when APP_BASE_URL is local.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.max_bot_token:
        raise SystemExit("MAX_BOT_TOKEN must be configured in .env.")
    if not settings.max_webhook_secret:
        raise SystemExit("MAX_WEBHOOK_SECRET must be configured in .env.")
    webhook_url = _resolve_webhook_url(settings.app_base_url, args.url)

    result = create_max_webhook_subscription(
        settings,
        url=webhook_url,
        update_types=MAX_WEBHOOK_UPDATE_TYPES,
    )
    print(f"Registered MAX webhook: {webhook_url}", file=sys.stderr)
    print(json.dumps(_redact_sensitive(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
