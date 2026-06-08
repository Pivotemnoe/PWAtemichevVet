from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = tempfile.TemporaryDirectory()
os.environ.update(
    {
        "APP_ENV": "development",
        "APP_BASE_URL": "http://127.0.0.1:8080",
        "DATABASE_PATH": str(Path(TMP.name) / "pwa-test.db"),
        "SESSION_SECRET": "test-session-secret-for-ci-and-local-checks-123456",
        "DEV_AUTH_CODE_LOG": "1",
        "ADMIN_API_SECRET": "admin-test-secret",
        "MONITORING_API_SECRET": "monitoring-test-secret",
        "YOOKASSA_SHOP_ID": "test-shop",
        "YOOKASSA_SECRET_KEY": "test-secret",
        "YOOKASSA_RETURN_URL": "http://127.0.0.1:8080/?payment=plus",
        "SMTP_HOST": "",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_FROM_EMAIL": "",
    }
)

from fastapi import HTTPException  # noqa: E402

from app import db  # noqa: E402
from app import main as api  # noqa: E402


class DummyRequest:
    method = "POST"
    headers: dict[str, str] = {}
    client = types.SimpleNamespace(host="127.0.0.1")
    url = types.SimpleNamespace(path="/test")


def request(path: str = "/test", method: str = "POST") -> DummyRequest:
    item = DummyRequest()
    item.method = method
    item.url = types.SimpleNamespace(path=path)
    return item


def login(email: str) -> tuple[dict, str]:
    start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
    assert start.debug_code
    session = api.auth_email_verify(
        api.EmailVerifyRequest(email=email, code=start.debug_code),
        request("/api/auth/email/verify"),
    )
    return session.user, session.token


def disable_external_sync() -> None:
    result = {"synced": False, "reason": "test_disabled"}
    api._safe_sync_telegram_profile_to_pwa = lambda user: result
    api._safe_sync_pwa_pet_to_telegram = lambda user, pet: result
    api._safe_sync_pwa_reminder_to_telegram = lambda user, reminder: result
    api._safe_sync_pwa_reminder_deactivation = lambda user, reminder_id: result
    api._safe_sync_pwa_observation_to_telegram = lambda user, observation: result
    api._safe_sync_pwa_measurement_to_telegram = lambda user, measurement: result
    api._safe_sync_triage_to_telegram = lambda **kwargs: result
    api._enqueue_core_outbound_from_sync = lambda sync_result, mappings: False
    api._enqueue_core_outbound_subscription_for_bot_user = lambda user_id: False


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        disable_external_sync()

    def test_health_and_email_login(self) -> None:
        response = api.health()
        self.assertEqual(response["ok"], True)

        user, token = login("owner@example.com")
        self.assertTrue(token)
        self.assertEqual(user["email"], "owner@example.com")

        audit_items = db.list_security_audit_events(api.settings.database_path, event_type="auth.login_success")
        self.assertGreaterEqual(len(audit_items), 1)
        self.assertEqual(audit_items[0]["provider"], "email")

    def test_pet_and_reminder_ownership(self) -> None:
        user_a, _ = login("pet-owner-a@example.com")
        user_b, _ = login("pet-owner-b@example.com")

        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Лео", birth_year=2018),
            user=user_a,
        )["item"]
        reminder = api.add_reminder(
            api.ReminderPayload(
                pet_id=int(pet["id"]),
                reminder_type="checkup",
                title="Осмотр",
                due_date="2026-07-01",
                periodicity="once",
            ),
            request("/api/reminders"),
            user=user_a,
        )["item"]

        with self.assertRaises(HTTPException) as pet_exc:
            api.get_pet(int(pet["id"]), request(f"/api/pets/{pet['id']}", "GET"), user=user_b)
        self.assertEqual(pet_exc.exception.status_code, 404)

        with self.assertRaises(HTTPException) as reminder_exc:
            api.delete_reminder(int(reminder["id"]), request(f"/api/reminders/{reminder['id']}", "DELETE"), user=user_b)
        self.assertEqual(reminder_exc.exception.status_code, 404)

        denied = db.list_security_audit_events(
            api.settings.database_path,
            event_type="access.ownership_denied",
            status="warning",
        )
        self.assertGreaterEqual(len(denied), 2)

    def test_mock_payment_plus_activation(self) -> None:
        user, _ = login("payer@example.com")

        def fake_create_payment(settings, *, user_id: int, user_email: str | None = None) -> dict:
            return {
                "id": "pay_test_1",
                "status": "pending",
                "paid": False,
                "amount": {"value": "200.00", "currency": "RUB"},
                "metadata": {"source": "pwa", "pwa_user_id": str(user_id), "plan_code": "plus"},
                "confirmation": {"confirmation_url": "https://yookassa.test/pay/pay_test_1"},
                "idempotence_key": "idem-test",
            }

        def fake_get_payment(settings, payment_id: str) -> dict:
            return {
                "id": payment_id,
                "status": "succeeded",
                "paid": True,
                "captured_at": "2026-06-08T12:00:00+03:00",
                "amount": {"value": "200.00", "currency": "RUB"},
                "metadata": {"source": "pwa", "pwa_user_id": str(user["id"]), "plan_code": "plus"},
            }

        api.create_yookassa_plus_payment = fake_create_payment
        api.get_yookassa_payment = fake_get_payment

        created = api.payment_plus_create(request("/api/payments/plus/create"), user=user)
        self.assertEqual(created.status, "pending")
        self.assertEqual(created.payment_id, "pay_test_1")

        status = api.payment_status("pay_test_1", user=user)
        self.assertEqual(status.status, "succeeded")
        self.assertEqual(status.subscription["plan"], "plus")

        events = db.list_security_audit_events(api.settings.database_path, event_type="payment.succeeded")
        self.assertGreaterEqual(len(events), 1)

    def test_closed_monitoring_and_audit_helpers(self) -> None:
        status = api.monitoring_status()
        self.assertEqual(status["ok"], True)
        self.assertIn("events_1h", status)

        audit = api.admin_security_audit(limit=10)
        self.assertIn("items", audit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
