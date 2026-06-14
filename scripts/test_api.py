from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from datetime import timedelta
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
        "CORE_API_SECRET": "core-test-secret",
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
    api._safe_sync_pwa_pet_deletion_to_telegram = lambda user, pet: result
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

    def test_me_includes_sync_status_for_cabinet(self) -> None:
        user, _ = login("sync-status@example.com")
        profile = api.me(user=user)

        self.assertIn("telegram_profile_sync", profile)
        self.assertEqual(profile["telegram_profile_sync"]["synced"], False)
        self.assertEqual(profile["telegram_profile_sync"]["reason"], "test_disabled")
        self.assertIn("external_accounts", profile)
        self.assertIn("subscription", profile)

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

    def test_reminder_delete_sync_runs_only_after_owner_check(self) -> None:
        user_a, _ = login("reminder-sync-owner-a@example.com")
        user_b, _ = login("reminder-sync-owner-b@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Сима", birth_year=2019),
            user=user_a,
        )["item"]
        reminder = api.add_reminder(
            api.ReminderPayload(
                pet_id=int(pet["id"]),
                reminder_type="checkup",
                title="Плановый осмотр",
                due_date="2026-08-01",
                periodicity="once",
            ),
            request("/api/reminders"),
            user=user_a,
        )["item"]

        calls: list[tuple[int, int]] = []
        original_sync = api._safe_sync_pwa_reminder_deactivation
        original_enqueue = api._enqueue_core_outbound_from_sync
        api._safe_sync_pwa_reminder_deactivation = lambda user, reminder_id: calls.append(
            (int(user["id"]), int(reminder_id))
        ) or {"synced": True}
        api._enqueue_core_outbound_from_sync = lambda sync_result, mappings: False
        try:
            with self.assertRaises(HTTPException) as reminder_exc:
                api.delete_reminder(
                    int(reminder["id"]),
                    request(f"/api/reminders/{reminder['id']}", "DELETE"),
                    user=user_b,
                )
            self.assertEqual(reminder_exc.exception.status_code, 404)
            self.assertEqual(calls, [])

            result = api.delete_reminder(
                int(reminder["id"]),
                request(f"/api/reminders/{reminder['id']}", "DELETE"),
                user=user_a,
            )
            self.assertEqual(result["ok"], True)
            self.assertEqual(calls, [(int(user_a["id"]), int(reminder["id"]))])
        finally:
            api._safe_sync_pwa_reminder_deactivation = original_sync
            api._enqueue_core_outbound_from_sync = original_enqueue

    def test_foreign_pet_mutations_do_not_trigger_side_effects(self) -> None:
        user_a, _ = login("pet-mutation-owner-a@example.com")
        user_b, _ = login("pet-mutation-owner-b@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Рэй", birth_year=2020),
            user=user_a,
        )["item"]

        calls: list[str] = []
        originals = {
            "pet": api._safe_sync_pwa_pet_to_telegram,
            "pet_delete": api._safe_sync_pwa_pet_deletion_to_telegram,
            "measurement": api._safe_sync_pwa_measurement_to_telegram,
            "observation": api._safe_sync_pwa_observation_to_telegram,
            "reminder": api._safe_sync_pwa_reminder_to_telegram,
            "triage": api._safe_sync_triage_to_telegram,
            "enqueue": api._enqueue_core_outbound_from_sync,
            "llm": api.call_triage_llm,
        }

        def fake_llm(*args, **kwargs):
            calls.append("llm")
            raise AssertionError("LLM must not run for a foreign pet")

        api._safe_sync_pwa_pet_to_telegram = lambda user, pet: calls.append("pet") or {"synced": True}
        api._safe_sync_pwa_pet_deletion_to_telegram = lambda user, pet: calls.append("pet_delete") or {"synced": True}
        api._safe_sync_pwa_measurement_to_telegram = lambda user, measurement: calls.append("measurement") or {"synced": True}
        api._safe_sync_pwa_observation_to_telegram = lambda user, observation: calls.append("observation") or {"synced": True}
        api._safe_sync_pwa_reminder_to_telegram = lambda user, reminder: calls.append("reminder") or {"synced": True}
        api._safe_sync_triage_to_telegram = lambda **kwargs: calls.append("triage") or {"synced": True}
        api._enqueue_core_outbound_from_sync = lambda sync_result, mappings: False
        api.call_triage_llm = fake_llm
        try:
            denied_calls = (
                lambda: api.update_pet(
                    int(pet["id"]),
                    api.PetPatchPayload(pet_name="Чужое имя"),
                    request(f"/api/pets/{pet['id']}", "PATCH"),
                    user=user_b,
                ),
                lambda: api.set_main_pet(
                    int(pet["id"]),
                    api.MainPetPayload(is_main=True),
                    request(f"/api/pets/{pet['id']}/main"),
                    user=user_b,
                ),
                lambda: api.add_pet_weight(
                    int(pet["id"]),
                    api.MeasurementPayload(weight_kg=12.4, note="чужой вес"),
                    request(f"/api/pets/{pet['id']}/weights"),
                    user=user_b,
                ),
                lambda: api.add_pet_observation(
                    int(pet["id"]),
                    api.ObservationPayload(obs_type="note", text="чужое наблюдение"),
                    request(f"/api/pets/{pet['id']}/observations"),
                    user=user_b,
                ),
                lambda: api.add_reminder(
                    api.ReminderPayload(
                        pet_id=int(pet["id"]),
                        reminder_type="checkup",
                        title="Чужой осмотр",
                        due_date="2026-09-01",
                        periodicity="once",
                    ),
                    request("/api/reminders"),
                    user=user_b,
                ),
                lambda: api.delete_pet(
                    int(pet["id"]),
                    request(f"/api/pets/{pet['id']}", "DELETE"),
                    user=user_b,
                ),
                lambda: api.triage(
                    api.TriageRequest(pet_id=int(pet["id"]), text="собака вялая второй день"),
                    request("/api/triage"),
                    user=user_b,
                ),
            )
            for denied_call in denied_calls:
                with self.assertRaises(HTTPException) as denied_exc:
                    denied_call()
                self.assertEqual(denied_exc.exception.status_code, 404)
            self.assertEqual(calls, [])

            api.update_pet(
                int(pet["id"]),
                api.PetPatchPayload(pet_name="Рэй обновлён"),
                request(f"/api/pets/{pet['id']}", "PATCH"),
                user=user_a,
            )
            api.add_pet_weight(
                int(pet["id"]),
                api.MeasurementPayload(weight_kg=12.5),
                request(f"/api/pets/{pet['id']}/weights"),
                user=user_a,
            )
            api.add_pet_observation(
                int(pet["id"]),
                api.ObservationPayload(obs_type="note", text="нормальная активность"),
                request(f"/api/pets/{pet['id']}/observations"),
                user=user_a,
            )
            api.add_reminder(
                api.ReminderPayload(
                    pet_id=int(pet["id"]),
                    reminder_type="checkup",
                    title="Плановый осмотр",
                    due_date="2026-09-01",
                    periodicity="once",
                ),
                request("/api/reminders"),
                user=user_a,
            )
            self.assertEqual(calls, ["pet", "measurement", "observation", "reminder"])
        finally:
            api._safe_sync_pwa_pet_to_telegram = originals["pet"]
            api._safe_sync_pwa_pet_deletion_to_telegram = originals["pet_delete"]
            api._safe_sync_pwa_measurement_to_telegram = originals["measurement"]
            api._safe_sync_pwa_observation_to_telegram = originals["observation"]
            api._safe_sync_pwa_reminder_to_telegram = originals["reminder"]
            api._safe_sync_triage_to_telegram = originals["triage"]
            api._enqueue_core_outbound_from_sync = originals["enqueue"]
            api.call_triage_llm = originals["llm"]

    def test_pet_delete_records_tombstone_and_queues_core_delete_after_owner_check(self) -> None:
        user_a, _ = login("pet-delete-owner-a@example.com")
        user_b, _ = login("pet-delete-owner-b@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Тиша", birth_year=2017),
            user=user_a,
        )["item"]
        telegram_pet_id = 98765
        with db.connect(api.settings.database_path) as conn:
            conn.execute(
                "UPDATE pets SET external_source = 'telegram', external_id = ? WHERE id = ?",
                (str(telegram_pet_id), int(pet["id"])),
            )
            conn.commit()

        calls: list[tuple[int, int]] = []
        outbound: list[tuple[str, int, str]] = []
        original_sync = api._safe_sync_pwa_pet_deletion_to_telegram
        original_enqueue = api._enqueue_core_outbound_event
        api._safe_sync_pwa_pet_deletion_to_telegram = lambda user, pet: calls.append(
            (int(user["id"]), int(pet["id"]))
        ) or {"synced": True, "telegram_pet_id": int(pet["external_id"])}
        api._enqueue_core_outbound_event = lambda table_name, row_id, operation="upsert": outbound.append(
            (table_name, int(row_id), operation)
        ) or True
        try:
            with self.assertRaises(HTTPException) as pet_exc:
                api.delete_pet(
                    int(pet["id"]),
                    request(f"/api/pets/{pet['id']}", "DELETE"),
                    user=user_b,
                )
            self.assertEqual(pet_exc.exception.status_code, 404)
            self.assertEqual(calls, [])
            self.assertEqual(outbound, [])
            self.assertIsNotNone(
                db.get_pet(api.settings.database_path, owner_id=int(user_a["id"]), pet_id=int(pet["id"]))
            )

            result = api.delete_pet(
                int(pet["id"]),
                request(f"/api/pets/{pet['id']}", "DELETE"),
                user=user_a,
            )
            self.assertEqual(result["ok"], True)
            self.assertEqual(calls, [(int(user_a["id"]), int(pet["id"]))])
            self.assertEqual(outbound, [("pets", telegram_pet_id, "delete")])
            self.assertTrue(
                db.sync_tombstone_exists(
                    api.settings.database_path,
                    owner_id=int(user_a["id"]),
                    provider="telegram",
                    entity_type="pet",
                    external_id=str(telegram_pet_id),
                )
            )
            self.assertIsNone(
                db.get_pet(api.settings.database_path, owner_id=int(user_a["id"]), pet_id=int(pet["id"]))
            )
        finally:
            api._safe_sync_pwa_pet_deletion_to_telegram = original_sync
            api._enqueue_core_outbound_event = original_enqueue

    def test_successful_pwa_sync_paths_enqueue_core_rows(self) -> None:
        user, _ = login("sync-success-owner@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Луна", birth_year=2021),
            user=user,
        )["item"]

        originals = {
            "pet": api._safe_sync_pwa_pet_to_telegram,
            "measurement": api._safe_sync_pwa_measurement_to_telegram,
            "observation": api._safe_sync_pwa_observation_to_telegram,
            "reminder": api._safe_sync_pwa_reminder_to_telegram,
            "triage": api._safe_sync_triage_to_telegram,
            "enqueue": api._enqueue_core_outbound_from_sync,
        }
        enqueued: list[tuple[dict, tuple[tuple[str, str], ...]]] = []

        def record_enqueue(sync_result: dict, mappings: tuple[tuple[str, str], ...]) -> dict[str, int]:
            enqueued.append((dict(sync_result), tuple(mappings)))
            return {"queued": len(mappings), "skipped": 0}

        api._safe_sync_pwa_pet_to_telegram = lambda user, pet: {
            "synced": True,
            "telegram_pet_id": int(pet["id"]) + 1000,
        }
        api._safe_sync_pwa_measurement_to_telegram = lambda user, measurement: {
            "synced": True,
            "telegram_pet_id": int(measurement["pet_id"]) + 1000,
            "telegram_measurement_id": int(measurement["id"]) + 2000,
        }
        api._safe_sync_pwa_observation_to_telegram = lambda user, observation: {
            "synced": True,
            "telegram_pet_id": int(observation["pet_id"]) + 1000,
            "telegram_observation_id": int(observation["id"]) + 3000,
        }
        api._safe_sync_pwa_reminder_to_telegram = lambda user, reminder: {
            "synced": True,
            "telegram_pet_id": int(reminder["pet_id"]) + 1000,
            "telegram_reminder_id": int(reminder["id"]) + 4000,
        }
        api._safe_sync_triage_to_telegram = lambda **kwargs: {
            "synced": True,
            "telegram_pet_id": int(kwargs["selected_pet"]["id"]) + 1000,
            "telegram_triage_id": int(kwargs["pwa_triage_id"]) + 5000,
            "telegram_history_id": int(kwargs["pwa_triage_id"]) + 6000,
            "telegram_observation_id": int(kwargs["pwa_triage_id"]) + 7000,
            "telegram_followup_id": int(kwargs["pwa_triage_id"]) + 8000,
        }
        api._enqueue_core_outbound_from_sync = record_enqueue
        try:
            api.update_pet(
                int(pet["id"]),
                api.PetPatchPayload(pet_name="Луна обновлена"),
                request(f"/api/pets/{pet['id']}", "PATCH"),
                user=user,
            )
            api.set_main_pet(
                int(pet["id"]),
                api.MainPetPayload(is_main=True),
                request(f"/api/pets/{pet['id']}/main"),
                user=user,
            )
            api.add_pet_weight(
                int(pet["id"]),
                api.MeasurementPayload(weight_kg=4.2),
                request(f"/api/pets/{pet['id']}/weights"),
                user=user,
            )
            api.add_pet_observation(
                int(pet["id"]),
                api.ObservationPayload(obs_type="note", text="активность нормальная"),
                request(f"/api/pets/{pet['id']}/observations"),
                user=user,
            )
            api.add_reminder(
                api.ReminderPayload(
                    pet_id=int(pet["id"]),
                    reminder_type="checkup",
                    title="Плановый осмотр",
                    due_date="2026-10-01",
                    periodicity="once",
                ),
                request("/api/reminders"),
                user=user,
            )
            api.triage(
                api.TriageRequest(pet_id=int(pet["id"]), text="у кошки судороги и кровь"),
                request("/api/triage"),
                user=user,
            )

            self.assertEqual(
                [mappings for _, mappings in enqueued],
                [
                    (("telegram_pet_id", "pets"),),
                    (("telegram_pet_id", "pets"),),
                    (("telegram_pet_id", "pets"), ("telegram_measurement_id", "pet_measurements")),
                    (("telegram_pet_id", "pets"), ("telegram_observation_id", "pet_observations")),
                    (("telegram_pet_id", "pets"), ("telegram_reminder_id", "reminders")),
                    (
                        ("telegram_pet_id", "pets"),
                        ("telegram_triage_id", "triage_logs"),
                        ("telegram_history_id", "pet_history"),
                        ("telegram_observation_id", "pet_observations"),
                        ("telegram_followup_id", "triage_followups"),
                    ),
                ],
            )
            self.assertTrue(all(sync_result["synced"] for sync_result, _ in enqueued))
        finally:
            api._safe_sync_pwa_pet_to_telegram = originals["pet"]
            api._safe_sync_pwa_measurement_to_telegram = originals["measurement"]
            api._safe_sync_pwa_observation_to_telegram = originals["observation"]
            api._safe_sync_pwa_reminder_to_telegram = originals["reminder"]
            api._safe_sync_triage_to_telegram = originals["triage"]
            api._enqueue_core_outbound_from_sync = originals["enqueue"]

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

    def test_core_api_secret_required(self) -> None:
        with self.assertRaises(HTTPException) as missing_exc:
            api._require_core_api_secret()
        self.assertEqual(missing_exc.exception.status_code, 401)

        with self.assertRaises(HTTPException) as invalid_header_exc:
            api._require_core_api_secret("wrong")
        self.assertEqual(invalid_header_exc.exception.status_code, 401)

        with self.assertRaises(HTTPException) as invalid_secret_exc:
            api._require_core_api_secret("Bearer wrong-secret")
        self.assertEqual(invalid_secret_exc.exception.status_code, 403)

        self.assertIsNone(api._require_core_api_secret("Bearer core-test-secret"))

    def test_duplicate_telegram_identity_merges_email_account_data(self) -> None:
        telegram_owner, _ = login("telegram-owner@example.com")
        linked = db.link_external_account(
            api.settings.database_path,
            user_id=int(telegram_owner["id"]),
            provider="telegram",
            provider_user_id="tg-duplicate-owner",
            display_name="TG Owner",
        )
        self.assertIsNotNone(linked)

        email_user, _ = login("telegram-linking@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Барс", birth_year=2020),
            user=email_user,
        )["item"]

        state, _ = api.create_telegram_login_challenge(api.settings, link_user_id=int(email_user["id"]))
        confirmed = api.confirm_telegram_login(
            api.settings,
            state=state,
            telegram_id="tg-duplicate-owner",
            display_name="TG Owner",
        )
        self.assertEqual(confirmed["handled"], True)

        completed = api.complete_telegram_login(api.settings, state)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(int(completed["user"]["id"]), int(telegram_owner["id"]))

        moved_pet = db.get_pet(
            api.settings.database_path,
            owner_id=int(telegram_owner["id"]),
            pet_id=int(pet["id"]),
        )
        self.assertIsNotNone(moved_pet)
        self.assertEqual(moved_pet["pet_name"], "Барс")

        old_owner_pet = db.get_pet(
            api.settings.database_path,
            owner_id=int(email_user["id"]),
            pet_id=int(pet["id"]),
        )
        self.assertIsNone(old_owner_pet)

    def test_duplicate_max_identity_merges_email_account_data(self) -> None:
        max_owner, _ = login("max-owner@example.com")
        linked = db.link_external_account(
            api.settings.database_path,
            user_id=int(max_owner["id"]),
            provider="max",
            provider_user_id="max-duplicate-owner",
            display_name="MAX Owner",
        )
        self.assertIsNotNone(linked)

        email_user, _ = login("max-linking@example.com")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Мия", birth_year=2021),
            user=email_user,
        )["item"]

        state, _ = api.create_max_login_challenge(api.settings, link_user_id=int(email_user["id"]))
        processed = api.process_max_update(
            api.settings,
            {
                "update_type": "bot_started",
                "payload": state,
                "user": {"user_id": "max-duplicate-owner", "name": "MAX Owner"},
            },
        )
        self.assertEqual(processed["handled"], True)

        completed = api.complete_max_login(api.settings, state)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(int(completed["user"]["id"]), int(max_owner["id"]))

        moved_pet = db.get_pet(
            api.settings.database_path,
            owner_id=int(max_owner["id"]),
            pet_id=int(pet["id"]),
        )
        self.assertIsNotNone(moved_pet)
        self.assertEqual(moved_pet["pet_name"], "Мия")

        old_owner_pet = db.get_pet(
            api.settings.database_path,
            owner_id=int(email_user["id"]),
            pet_id=int(pet["id"]),
        )
        self.assertIsNone(old_owner_pet)

    def test_payment_status_owner_only(self) -> None:
        user_a, _ = login("payment-owner-a@example.com")
        user_b, _ = login("payment-owner-b@example.com")
        db.create_payment_record(
            api.settings.database_path,
            user_id=int(user_a["id"]),
            provider=api.YOOKASSA_PROVIDER,
            provider_payment_id="pay_private_owner_a",
            amount_rub=200,
            status="pending",
            plan_code="plus",
            confirmation_url="https://yookassa.test/pay/private-owner-a",
            idempotence_key="payment-owner-a",
            raw_payload={"id": "pay_private_owner_a"},
        )

        with self.assertRaises(HTTPException) as payment_exc:
            api.payment_status("pay_private_owner_a", user=user_b)
        self.assertEqual(payment_exc.exception.status_code, 404)

        denied = db.list_security_audit_events(
            api.settings.database_path,
            event_type="payment.ownership_denied",
            status="warning",
        )
        self.assertGreaterEqual(len(denied), 1)

    def test_closed_monitoring_and_audit_helpers(self) -> None:
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="payment.ownership_denied",
            status="warning",
            actor="test",
            provider="yookassa",
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="llm.triage_failed",
            status="error",
            actor="test",
            provider="openai",
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="sync.telegram_failed",
            status="error",
            actor="test",
            provider="telegram",
        )

        status = api.monitoring_status()
        self.assertEqual(status["ok"], True)
        self.assertIn("events_1h", status)
        integration = {item["key"]: item for item in status["integration_events_24h"]}
        self.assertEqual(integration["payments"]["warnings"], 1)
        self.assertEqual(integration["llm"]["errors"], 1)
        self.assertEqual(integration["sync"]["errors"], 1)
        self.assertEqual(integration["api"]["status"], "ok")

        audit = api.admin_security_audit(limit=10)
        self.assertIn("items", audit)

        dashboard = api._admin_dashboard_payload()
        self.assertGreaterEqual(dashboard["overview"]["security_warnings_24h"], 1)
        self.assertGreaterEqual(dashboard["overview"]["security_events_24h"], 1)
        breakdown = dashboard["audit_breakdown_24h"]
        self.assertTrue(
            any(
                row["event_type"] == "payment.ownership_denied"
                and row["status"] == "warning"
                and row["count"] >= 1
                for row in breakdown
            )
        )

    def test_push_config_and_subscribe_guard(self) -> None:
        user, _ = login("push-owner@example.com")
        config = api.push_config()
        self.assertEqual(config["enabled"], False)
        self.assertEqual(config["public_key"], "")

        with self.assertRaises(HTTPException) as push_exc:
            api.push_subscribe(
                api.PushSubscribePayload(
                    endpoint="https://push.example.test/subscription/1",
                    keys=api.PushSubscriptionKeys(p256dh="p" * 88, auth="a" * 24),
                ),
                request("/api/push/subscribe"),
                user=user,
            )
        self.assertEqual(push_exc.exception.status_code, 503)

        events = db.list_security_audit_events(api.settings.database_path, event_type="push.subscribe_failed")
        self.assertGreaterEqual(len(events), 1)

    def test_due_followup_push_sender_skips_without_subscription(self) -> None:
        user, _ = login("push-followup-owner@example.com")
        triage = db.create_triage_log(
            api.settings.database_path,
            owner_id=int(user["id"]),
            pet_id=None,
            complaint_text="тестовый разбор",
            response_text="тестовый ответ",
            urgency_level="yellow",
        )
        self.assertIsNotNone(triage)
        followup = db.add_triage_followup(
            api.settings.database_path,
            owner_id=int(user["id"]),
            triage_id=int(triage["id"]),
            pet_id=None,
            urgency_level="yellow",
            scenario="basic",
            scheduled_at=(api.utc_now() - timedelta(minutes=1)).isoformat(),
        )
        self.assertIsNotNone(followup)

        result = api.send_due_followup_pushes(
            request("/api/internal/push/followups/send"),
            limit=10,
            _=None,
        )
        self.assertEqual(result["sent"], 0)
        self.assertGreaterEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
