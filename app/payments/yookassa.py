from __future__ import annotations

import base64
import json
import ssl
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from app.config import Settings
from app.subscriptions import SUBSCRIPTION_PLANS


API_BASE_URL = "https://api.yookassa.ru/v3"
PROVIDER = "yookassa"
PLUS_DAYS = 30


class YooKassaConfigError(RuntimeError):
    pass


class YooKassaPaymentError(RuntimeError):
    pass


class YooKassaPaymentValidationError(RuntimeError):
    pass


def _plus_price_rub() -> int:
    return int(SUBSCRIPTION_PLANS["plus"]["price"])


def _amount_value(amount_rub: int | float) -> str:
    return f"{float(amount_rub):.2f}"


def _auth_header(settings: Settings) -> str:
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise YooKassaConfigError("yookassa_not_configured")
    token = f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def _request_json(
    settings: Settings,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    idempotence_key: str | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": _auth_header(settings),
        "Content-Type": "application/json",
    }
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(f"{API_BASE_URL}{path}", data=body, headers=headers, method=method)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=20, context=context) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise YooKassaPaymentError(f"yookassa_http_{exc.code}: {raw[:500]}") from exc
    except URLError as exc:
        raise YooKassaPaymentError("yookassa_network_error") from exc

    try:
        result = json.loads(data)
    except json.JSONDecodeError as exc:
        raise YooKassaPaymentError("yookassa_invalid_json") from exc
    if not isinstance(result, dict):
        raise YooKassaPaymentError("yookassa_invalid_response")
    return result


def _build_receipt(settings: Settings, *, amount_rub: int, description: str, user_email: str | None) -> dict[str, Any] | None:
    customer_email = (user_email or settings.yookassa_receipt_email or "").strip()
    if not customer_email:
        return None
    try:
        vat_code = int(settings.yookassa_vat_code or "1")
    except ValueError as exc:
        raise YooKassaConfigError("invalid_yookassa_vat_code") from exc

    receipt: dict[str, Any] = {
        "customer": {"email": customer_email},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": _amount_value(amount_rub), "currency": "RUB"},
                "vat_code": vat_code,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ],
    }
    if settings.yookassa_tax_system_code:
        try:
            receipt["tax_system_code"] = int(settings.yookassa_tax_system_code)
        except ValueError as exc:
            raise YooKassaConfigError("invalid_yookassa_tax_system_code") from exc
    return receipt


def _return_url(settings: Settings) -> str:
    if settings.yookassa_return_url:
        return settings.yookassa_return_url
    return settings.app_base_url.rstrip("/") + "/?payment=plus"


def create_plus_payment(settings: Settings, *, user_id: int, user_email: str | None = None) -> dict[str, Any]:
    amount_rub = _plus_price_rub()
    description = "TemichevVet Plus — доступ на 30 дней"
    metadata = {
        "source": "pwa",
        "pwa_user_id": str(int(user_id)),
        "plan_code": "plus",
        "access_days": str(PLUS_DAYS),
    }
    payload: dict[str, Any] = {
        "amount": {"value": _amount_value(amount_rub), "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": _return_url(settings)},
        "description": description[:128],
        "metadata": metadata,
    }
    receipt = _build_receipt(settings, amount_rub=amount_rub, description=description, user_email=user_email)
    if receipt:
        payload["receipt"] = receipt

    idempotence_key = str(uuid.uuid4())
    payment = _request_json(settings, method="POST", path="/payments", payload=payload, idempotence_key=idempotence_key)
    payment["idempotence_key"] = idempotence_key
    return payment


def get_payment(settings: Settings, payment_id: str) -> dict[str, Any]:
    payment_id = str(payment_id or "").strip()
    if not payment_id:
        raise YooKassaPaymentValidationError("empty_payment_id")
    return _request_json(settings, method="GET", path=f"/payments/{payment_id}")


def _decimal_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise YooKassaPaymentValidationError("invalid_payment_amount") from exc


def _metadata_int(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise YooKassaPaymentValidationError(f"invalid_metadata_{key}") from exc


def validate_plus_payment(payment: dict[str, Any], *, expected_user_id: int, expected_amount_rub: int | None = None) -> None:
    status = str(payment.get("status") or "").lower()
    if status != "succeeded":
        raise YooKassaPaymentValidationError("payment_not_succeeded")

    if payment.get("paid") is not True:
        raise YooKassaPaymentValidationError("payment_not_paid")

    amount = payment.get("amount") or {}
    if not isinstance(amount, dict):
        raise YooKassaPaymentValidationError("payment_amount_missing")

    if str(amount.get("currency") or "").upper() != "RUB":
        raise YooKassaPaymentValidationError("payment_currency_not_rub")

    paid_amount = _decimal_amount(amount.get("value"))
    expected_amount = Decimal(str(expected_amount_rub or _plus_price_rub())).quantize(Decimal("0.01"))
    if paid_amount != expected_amount:
        raise YooKassaPaymentValidationError("payment_amount_mismatch")

    metadata = payment.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise YooKassaPaymentValidationError("payment_metadata_missing")

    if str(metadata.get("source") or "").lower() != "pwa":
        raise YooKassaPaymentValidationError("payment_source_mismatch")
    if str(metadata.get("plan_code") or "").lower() != "plus":
        raise YooKassaPaymentValidationError("payment_plan_mismatch")
    if _metadata_int(metadata, "pwa_user_id") != int(expected_user_id):
        raise YooKassaPaymentValidationError("payment_user_mismatch")


def confirmation_url(payment: dict[str, Any]) -> str | None:
    confirmation = payment.get("confirmation") or {}
    if not isinstance(confirmation, dict):
        return None
    url = confirmation.get("confirmation_url")
    return str(url) if url else None


def payment_status(payment: dict[str, Any]) -> str:
    return str(payment.get("status") or "unknown").lower()
