from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def expires_in(minutes: int) -> str:
    return (utc_now() + timedelta(minutes=minutes)).isoformat()


def make_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def make_token() -> str:
    return secrets.token_urlsafe(32)


def hash_value(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left or "", right or "")
