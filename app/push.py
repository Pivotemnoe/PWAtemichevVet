from __future__ import annotations

import json
from typing import Any

from app.config import Settings

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - optional production dependency
    WebPushException = Exception
    webpush = None


def send_web_push(settings: Settings, *, subscription: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.vapid_public_key or not settings.vapid_private_key:
        return {"sent": False, "reason": "not_configured"}
    if webpush is None:
        return {"sent": False, "reason": "dependency_missing"}

    endpoint = str(subscription.get("endpoint") or "").strip()
    p256dh = str(subscription.get("p256dh") or "").strip()
    auth = str(subscription.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return {"sent": False, "reason": "invalid_subscription"}

    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {
                    "p256dh": p256dh,
                    "auth": auth,
                },
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
    except WebPushException as exc:  # pragma: no cover - depends on remote push provider
        return {"sent": False, "reason": type(exc).__name__}
    return {"sent": True, "reason": "ok"}
