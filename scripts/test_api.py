from __future__ import annotations

import hashlib
import hmac
import json
import os
from http.cookies import SimpleCookie
import sys
import tempfile
import types
import unittest
import urllib.parse
import urllib.request
from dataclasses import replace
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
        "VAPID_PUBLIC_KEY": "",
        "VAPID_PRIVATE_KEY": "",
        "VAPID_SUBJECT": "",
    }
)

from fastapi import HTTPException, Response  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app import main as api  # noqa: E402
from app import max_auth  # noqa: E402
from scripts import setup_max_webhook  # noqa: E402


class DummyRequest:
    method = "POST"
    headers: dict[str, str] = {}
    client = types.SimpleNamespace(host="127.0.0.1")
    url = types.SimpleNamespace(path="/test")


def request(
    path: str = "/test",
    method: str = "POST",
    client_host: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
) -> DummyRequest:
    item = DummyRequest()
    item.method = method
    item.headers = headers or {}
    item.client = types.SimpleNamespace(host=client_host)
    item.url = types.SimpleNamespace(path=path, hostname="127.0.0.1")
    item.query_params = {}
    item.cookies = {}
    item.state = types.SimpleNamespace()
    return item


def make_max_init_data(
    bot_token: str,
    *,
    user_id: int = 67890,
    first_name: str = "Max",
    last_name: str = "User",
    auth_date: int | None = None,
) -> str:
    params = {
        "auth_date": str(auth_date or int(max_auth.utc_now().timestamp())),
        "query_id": "test-query-id",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "username": "max_user",
                "language_code": "ru",
                "photo_url": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    launch_params = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, launch_params.encode("utf-8"), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(params)


def login(email: str) -> tuple[dict, str]:
    start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
    assert start.debug_code
    response = Response()
    session = api.auth_email_verify(
        api.EmailVerifyRequest(email=email, code=start.debug_code),
        request("/api/auth/email/verify"),
        response,
    )
    cookie = SimpleCookie()
    cookie.load(response.headers.get("set-cookie", ""))
    token = cookie[api.USER_SESSION_COOKIE].value if api.USER_SESSION_COOKIE in cookie else ""
    return session.user, token


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

    def _clear_broadcast_push_test_data(self) -> None:
        with db.connect(api.settings.database_path) as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint LIKE ?", ("https://broadcast.example.test/%",))
            conn.execute("DELETE FROM security_audit_events WHERE event_type = ?", ("push.broadcast_send",))
            conn.commit()

    def _activate_plus(self, user: dict) -> None:
        api.activate_paid_subscription(api.settings, user_id=int(user["id"]), plan_code="plus", days=30)

    def _add_broadcast_push_subscription(self, user: dict, suffix: str, *, revoked: bool = False) -> dict:
        item = db.upsert_push_subscription(
            api.settings.database_path,
            user_id=int(user["id"]),
            endpoint=f"https://broadcast.example.test/{suffix}",
            p256dh="p" * 88,
            auth="a" * 24,
            user_agent="test-agent",
        )
        if revoked:
            db.revoke_push_subscription(
                api.settings.database_path,
                user_id=int(user["id"]),
                endpoint=str(item["endpoint"]),
            )
        return item

    def _public_check_save_payload(self, **overrides) -> api.PublicCheckPreviewSaveRequest:
        values = {
            "pet_type": "cat",
            "age": "5 лет",
            "text": "кошка второй день плохо ест и стала менее активной",
            "answer": (
                "1) Кратко: по описанию нужно внимательно наблюдать за состоянием.\n"
                "2) Уровень срочности: 🟡 Нужна консультация — симптом сохраняется.\n"
                "3) Что делать сейчас — запишите воду, аппетит и активность.\n"
                "4) Чего делать нельзя — не давайте лекарства без назначения.\n"
                "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
            ),
            "urgency": "yellow",
            "summary": "Питомец стал хуже есть",
            "model": "gpt-5.1-mini",
            "prompt_tokens": 50,
            "completion_tokens": 80,
            "total_tokens": 130,
            "landing_slug": "cat-not-eating",
            "session_id": "preview-save-matrix",
        }
        values.update(overrides)
        return api.PublicCheckPreviewSaveRequest(**values)

    def test_health_and_email_login(self) -> None:
        response = api.health()
        self.assertEqual(response["ok"], True)

        user, token = login("owner@example.ru")
        self.assertTrue(token)
        self.assertEqual(user["email"], "owner@example.ru")

        audit_items = db.list_security_audit_events(api.settings.database_path, event_type="auth.login_success")
        self.assertGreaterEqual(len(audit_items), 1)
        self.assertEqual(audit_items[0]["provider"], "email")

    def test_service_first_pet_creation_is_idempotent_and_respects_plan_limits(self) -> None:
        free_user, _ = login("service-pet-free@example.ru")
        payload = api.PetPayload(
            pet_type="собака",
            pet_name="Лада",
            client_request_id="service-pet-request-1",
        )
        first = api.create_pet(payload, request("/api/pets"), user=free_user)
        repeated = api.create_pet(payload, request("/api/pets"), user=free_user)
        self.assertTrue(first["created"])
        self.assertFalse(repeated["created"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(first["item"]["id"], repeated["item"]["id"])
        self.assertEqual(len(api.pets(user=free_user)["items"]), 1)
        with self.assertRaises(HTTPException) as free_limit:
            api.create_pet(
                api.PetPayload(pet_type="кошка", pet_name="Мира", client_request_id="service-pet-request-2"),
                request("/api/pets"),
                user=free_user,
            )
        self.assertEqual(free_limit.exception.detail, "pet_limit_reached")

        plus_user, _ = login("service-pet-plus@example.ru")
        self._activate_plus(plus_user)
        for index in range(3):
            api.create_pet(
                api.PetPayload(
                    pet_type="кошка",
                    pet_name=f"Питомец {index + 1}",
                    client_request_id=f"service-plus-pet-{index + 1}",
                ),
                request("/api/pets"),
                user=plus_user,
            )
        with self.assertRaises(HTTPException) as plus_limit:
            api.create_pet(
                api.PetPayload(pet_type="собака", pet_name="Четвёртый"),
                request("/api/pets"),
                user=plus_user,
            )
        self.assertEqual(plus_limit.exception.detail, "pet_limit_reached")

    def test_first_permanent_record_activates_service_only_once(self) -> None:
        user, _ = login("service-activation@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Луна", client_request_id="activation-pet"),
            request("/api/pets"),
            user=user,
        )["item"]
        first_record = api.add_pet_weight(
            int(pet["id"]),
            api.MeasurementPayload(weight_kg=4.2, note="Первая запись"),
            request(f"/api/pets/{pet['id']}/weights"),
            user=user,
        )
        self.assertTrue(first_record["service"]["first_record_saved"])
        self.assertTrue(first_record["service"]["activated"])
        second_record = api.add_pet_observation(
            int(pet["id"]),
            api.ObservationPayload(obs_type="note", text="Аппетит обычный"),
            request(f"/api/pets/{pet['id']}/observations"),
            user=user,
        )
        self.assertFalse(second_record["service"]["first_record_saved"])
        self.assertFalse(second_record["service"]["activated"])
        with db.connect(api.settings.database_path) as conn:
            event_counts = dict(
                conn.execute(
                    "SELECT event_type, COUNT(*) FROM funnel_events WHERE user_id = ? AND event_type LIKE 'service.%' GROUP BY event_type",
                    (int(user["id"]),),
                ).fetchall()
            )
        self.assertEqual(event_counts.get("service.first_record_saved"), 1)
        self.assertEqual(event_counts.get("service.activated"), 1)

    def test_doctor_summary_owner_periods_and_export_follow_free_plus_rules(self) -> None:
        user, _ = login("service-summary-owner@example.ru")
        other_user, _ = login("service-summary-other@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Бим", client_request_id="summary-pet"),
            request("/api/pets"),
            user=user,
        )["item"]
        api.add_pet_weight(
            int(pet["id"]),
            api.MeasurementPayload(weight_kg=12.4, note="Контрольный вес"),
            request(f"/api/pets/{pet['id']}/weights"),
            user=user,
        )
        free_summary = api.pet_doctor_summary(
            int(pet["id"]), request(f"/api/pets/{pet['id']}/summary", "GET"), period="30", user=user
        )
        self.assertEqual(free_summary["allowed_periods"], ["30"])
        self.assertFalse(free_summary["can_export"])
        self.assertEqual(len(free_summary["weights"]), 1)
        with self.assertRaises(HTTPException) as free_period:
            api.pet_doctor_summary(
                int(pet["id"]), request(f"/api/pets/{pet['id']}/summary", "GET"), period="90", user=user
            )
        self.assertEqual(free_period.exception.detail, "summary_period_plus_required")
        with self.assertRaises(HTTPException) as free_export:
            api.pet_doctor_summary_export(
                int(pet["id"]), request(f"/api/pets/{pet['id']}/summary/export"), period="30", user=user
            )
        self.assertEqual(free_export.exception.detail, "summary_export_plus_required")
        with self.assertRaises(HTTPException) as foreign_summary:
            api.pet_doctor_summary(
                int(pet["id"]), request(f"/api/pets/{pet['id']}/summary", "GET"), period="30", user=other_user
            )
        self.assertEqual(foreign_summary.exception.status_code, 404)

        self._activate_plus(user)
        plus_summary = api.pet_doctor_summary(
            int(pet["id"]), request(f"/api/pets/{pet['id']}/summary", "GET"), period="90", user=user
        )
        self.assertEqual(plus_summary["allowed_periods"], ["30", "90", "all"])
        self.assertTrue(plus_summary["can_export"])
        exported = api.pet_doctor_summary_export(
            int(pet["id"]), request(f"/api/pets/{pet['id']}/summary/export"), period="all", user=user
        )
        self.assertTrue(exported["ok"])

    def test_free_reminder_limit_keeps_existing_records_readable(self) -> None:
        user, _ = login("service-reminder-limit@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Соня", client_request_id="reminder-pet"),
            request("/api/pets"),
            user=user,
        )["item"]
        for index in range(3):
            api.add_reminder(
                api.ReminderPayload(
                    pet_id=int(pet["id"]),
                    title=f"Важная дата {index + 1}",
                    due_date=f"2026-09-{index + 1:02d}",
                ),
                request("/api/reminders"),
                user=user,
            )
        with self.assertRaises(HTTPException) as reminder_limit:
            api.add_reminder(
                api.ReminderPayload(pet_id=int(pet["id"]), title="Лишняя дата", due_date="2026-09-10"),
                request("/api/reminders"),
                user=user,
            )
        self.assertEqual(reminder_limit.exception.detail, "reminder_limit_reached")
        self.assertEqual(len(api.reminders(user=user)["items"]), 3)

    def test_food_check_uses_existing_local_database_without_llm(self) -> None:
        original_llm = api.call_triage_llm

        def unexpected_llm(*args, **kwargs):
            raise AssertionError("food check must not call the LLM")

        api.call_triage_llm = unexpected_llm
        try:
            for species in ("dog", "cat"):
                with self.subTest(species=species):
                    allowed = api.food_check(api.FoodCheckPayload(species=species, query="Морковь"))
                    self.assertEqual(allowed["status"], "found")
                    self.assertEqual(allowed["species"], species)
                    self.assertFalse(allowed["species_specific"])
                    self.assertEqual(allowed["database_scope"], "general_cats_and_dogs")
                    self.assertIn("общей справочной базе", allowed["disclaimer"])
                    self.assertIn("не является анализом корма", allowed["disclaimer"])
                    self.assertTrue(allowed["item"]["allowed"])
                    self.assertEqual(allowed["item"]["name"], "Морковь")

                    avoided = api.food_check(api.FoodCheckPayload(species=species, query="Виноград"))
                    self.assertEqual(avoided["status"], "found")
                    self.assertEqual(avoided["species"], species)
                    self.assertFalse(avoided["item"]["allowed"])
                    self.assertTrue(avoided["requires_immediate_vet_contact"])
                    self.assertIn("немедленно свяжитесь", avoided["exposure_advice"])
                    self.assertIn("даже если симптомов пока нет", avoided["exposure_advice"])
                    self.assertIn("ветеринарной клиникой", avoided["message"])
                    self.assertNotIn("1–2", json.dumps(avoided, ensure_ascii=False))
                    self.assertNotIn("1-2", json.dumps(avoided, ensure_ascii=False))

            dish = api.food_check(api.FoodCheckPayload(species="dog", query="Харчо", ingredients="мясо, лук"))
            self.assertEqual(dish["status"], "ingredients_checked")
            self.assertEqual(dish["species"], "dog")
            self.assertTrue(dish["requires_immediate_vet_contact"])
            self.assertIn("немедленно свяжитесь", dish["message"])
            self.assertIn("Лук", dish["message"])

            missing = api.food_check(api.FoodCheckPayload(species="cat", query="абракадабраxyz"))
            self.assertEqual(missing["status"], "not_found")
            self.assertEqual(missing["species"], "cat")

            with self.assertRaises(ValidationError):
                api.FoodCheckPayload(species="rabbit", query="Морковь")
            with self.assertRaises(ValueError) as invalid_species_exc:
                api.check_food("Морковь", species="rabbit")
            self.assertEqual(str(invalid_species_exc.exception), "invalid_food_species")
        finally:
            api.call_triage_llm = original_llm

    def test_food_check_requires_and_echoes_dog_or_cat_context(self) -> None:
        for species in ("dog", "cat"):
            with self.subTest(species=species):
                result = api.food_check(api.FoodCheckPayload(species=species, query="Морковь"))
                self.assertEqual(result["species"], species)
                self.assertFalse(result["species_specific"])
                self.assertEqual(result["database_scope"], "general_cats_and_dogs")
                self.assertIn("общей справочной базе", result["disclaimer"])
                self.assertIn("не является анализом корма", result["disclaimer"])

    def test_food_check_rejects_invalid_species(self) -> None:
        with self.assertRaises(ValidationError):
            api.FoodCheckPayload(species="rabbit", query="Морковь")
        with self.assertRaises(ValueError) as invalid_species_exc:
            api.check_food("Морковь", species="rabbit")
        self.assertEqual(str(invalid_species_exc.exception), "invalid_food_species")

    def test_food_check_grape_exposure_requires_immediate_contact_without_dose_claim(self) -> None:
        for species in ("dog", "cat"):
            with self.subTest(species=species):
                result = api.food_check(api.FoodCheckPayload(species=species, query="Виноград"))
                serialized = json.dumps(result, ensure_ascii=False)
                self.assertEqual(result["species"], species)
                self.assertFalse(result["item"]["allowed"])
                self.assertEqual(result["item"]["how_much_is_dangerous"], "")
                self.assertTrue(result["requires_immediate_vet_contact"])
                self.assertIn("немедленно свяжитесь", result["exposure_advice"])
                self.assertIn("даже если симптомов пока нет", result["exposure_advice"])
                self.assertNotIn("1–2", serialized)
                self.assertNotIn("1-2", serialized)

    def test_public_food_answer_saves_to_pet_after_login_without_quota_spend(self) -> None:
        user, _ = login("food-save-after-login@example.ru")
        sub_before = api.get_effective_subscription(api.settings, user)
        query = "Морковь food-save-private-query"

        result = api.save_public_food_check(
            api.PublicFoodSaveRequest(
                species="dog",
                pet_type="dog",
                query=query,
                landing_slug="dog",
                session_id="food-save-after-login-session",
                traffic_source="yandex_direct",
                utm_campaign="food-dog-test",
                create_pet=True,
            ),
            request("/api/food/check/save", client_host="10.10.0.31"),
            user,
        )

        self.assertEqual(result["status"], "saved")
        self.assertTrue(result["created_pet"])
        self.assertEqual(result["pet"]["pet_type"], "собака")
        self.assertEqual(result["item"]["obs_type"], "food_check")
        self.assertEqual(result["item"]["source"], "public_food")
        self.assertIn(query, result["item"]["payload"]["text"])
        self.assertEqual(result["item"]["payload"]["species"], "dog")

        observations = api.pet_observations(
            int(result["pet"]["id"]),
            request(f"/api/pets/{result['pet']['id']}/observations", method="GET"),
            user=user,
        )["items"]
        self.assertTrue(any(int(item["id"]) == int(result["item"]["id"]) for item in observations))
        sub_after = api.get_effective_subscription(api.settings, user)
        self.assertEqual(sub_after.quota_used, sub_before.quota_used)

        audit_items = db.list_security_audit_events(
            api.settings.database_path,
            event_type="food.check_saved",
            user_id=int(user["id"]),
        )
        self.assertGreaterEqual(len(audit_items), 1)
        audit_metadata = json.dumps(audit_items[0].get("metadata") or {}, ensure_ascii=False)
        self.assertIn('"slug": "dog"', audit_metadata)
        self.assertNotIn(query, audit_metadata)

        funnel_items = db.list_funnel_events(api.settings.database_path, limit=30)
        self.assertTrue(
            any(
                item["event_type"] == "food.saved_after_login"
                and item["step"] == "food_saved"
                and int(item.get("user_id") or 0) == int(user["id"])
                for item in funnel_items
            )
        )

    def test_public_food_answer_rejects_mismatched_pet_selection(self) -> None:
        user, _ = login("food-save-pet-mismatch@example.ru")
        cat = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Муся"),
            request("/api/pets"),
            user=user,
        )["item"]

        with self.assertRaises(HTTPException) as mismatch_exc:
            api.save_public_food_check(
                api.PublicFoodSaveRequest(
                    species="dog",
                    pet_type="dog",
                    query="Морковь",
                    landing_slug="dog",
                    session_id="food-save-mismatch-session",
                    pet_id=int(cat["id"]),
                ),
                request("/api/food/check/save"),
                user,
            )
        self.assertEqual(mismatch_exc.exception.status_code, 409)
        self.assertEqual(mismatch_exc.exception.detail, "check_preview_pet_type_mismatch")

    def test_logout_revokes_session_and_deletes_cookie(self) -> None:
        user, token = login("logout-owner@example.ru")
        self.assertTrue(token)
        self.assertEqual(api.current_user(token)["id"], user["id"])

        response = api.auth_logout(request("/api/auth/logout"), token=token)
        cookie = SimpleCookie()
        cookie.load(response.headers.get("set-cookie", ""))

        self.assertIn(api.USER_SESSION_COOKIE, cookie)
        self.assertEqual(cookie[api.USER_SESSION_COOKIE].value, "")
        with self.assertRaises(HTTPException) as old_session_exc:
            api.current_user(token)
        self.assertEqual(old_session_exc.exception.status_code, 401)

    def test_admin_session_uses_httponly_cookie_and_revokes_on_logout(self) -> None:
        old_settings = api.settings
        api.settings = replace(
            api.settings,
            admin_username="admin",
            admin_password_hash=api.make_password_hash("admin-password-123"),
        )
        try:
            login_response = Response()
            login_result = api.admin_login(
                api.AdminLoginRequest(username="admin", password="admin-password-123"),
                request("/api/admin/auth/login"),
                login_response,
            )
            self.assertTrue(login_result.ok)
            self.assertIsNone(login_result.token)

            cookie = SimpleCookie()
            cookie.load(login_response.headers.get("set-cookie", ""))
            self.assertIn(api.ADMIN_SESSION_COOKIE, cookie)
            admin_token = cookie[api.ADMIN_SESSION_COOKIE].value
            self.assertTrue(admin_token)
            self.assertTrue(cookie[api.ADMIN_SESSION_COOKIE]["httponly"])

            session = api.current_admin_session(admin_token)
            dashboard = api.admin_dashboard(request("/api/admin/dashboard", method="GET"), session)
            self.assertIn("overview", dashboard)

            logout_response = Response()
            logout_result = api.admin_logout(request("/api/admin/auth/logout"), logout_response, token=admin_token)
            self.assertTrue(logout_result["ok"])
            deleted_cookie = SimpleCookie()
            deleted_cookie.load(logout_response.headers.get("set-cookie", ""))
            self.assertIn(api.ADMIN_SESSION_COOKIE, deleted_cookie)
            self.assertEqual(deleted_cookie[api.ADMIN_SESSION_COOKIE].value, "")

            with self.assertRaises(HTTPException) as old_admin_session_exc:
                api.current_admin_session(admin_token)
            self.assertEqual(old_admin_session_exc.exception.status_code, 401)
        finally:
            api.settings = old_settings

    def test_admin_dashboard_includes_site_visits_without_raw_ip(self) -> None:
        user, _ = login("site-visit-owner@example.ru")
        db.create_site_visit(
            api.settings.database_path,
            method="GET",
            path="/",
            status_code=200,
            user_id=int(user["id"]),
            ip_hash="hashed-ip-only",
            referrer_host="yandex.ru",
            source="yandex.ru",
            device="Телефон",
            browser="Safari",
        )
        db.create_site_visit(
            api.settings.database_path,
            method="GET",
            path="/app",
            status_code=200,
            user_id=None,
            ip_hash="anonymous-hash",
            source="Прямой заход",
            device="Компьютер",
            browser="Chrome",
        )

        dashboard = api._admin_dashboard_payload()
        overview = dashboard["overview"]
        self.assertGreaterEqual(overview["site_visits_24h"], 2)
        self.assertGreaterEqual(overview["site_visitors_24h"], 2)
        self.assertGreaterEqual(overview["site_logged_in_visits_24h"], 1)

        recent_visits = dashboard["recent_site_visits"]
        self.assertTrue(any(item.get("user_email") == "site-visit-owner@example.ru" for item in recent_visits))
        self.assertTrue(any(item.get("user_email") is None and item.get("path") == "/app" for item in recent_visits))
        self.assertTrue(any(item.get("source") == "yandex.ru" for item in dashboard["site_sources_24h"]))
        self.assertFalse(any("raw_ip" in item for item in recent_visits))

    def test_admin_dashboard_reports_token_usage_without_double_counting_saved_preview(self) -> None:
        before = api._admin_dashboard_payload()["overview"]
        user, _ = login("admin-token-usage@example.ru")

        cabinet_log = db.create_triage_log(
            api.settings.database_path,
            owner_id=int(user["id"]),
            pet_id=None,
            complaint_text="Проверка расхода токенов в кабинете",
            response_text="Тестовый ответ",
            urgency_level="green",
            prompt_tokens=80,
            completion_tokens=120,
            total_tokens=200,
            model="test-model",
            subscription_source="pwa",
        )
        preview_log = db.create_triage_log(
            api.settings.database_path,
            owner_id=int(user["id"]),
            pet_id=None,
            complaint_text="Сохранённая публичная проверка",
            response_text="Тестовый ответ публичной проверки",
            urgency_level="yellow",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            model="test-model",
            subscription_source="public_preview",
        )
        preview_hashes = ["admin-token-session", "admin-token-client"]
        claimed = db.claim_public_check_preview_usage(
            api.settings.database_path,
            identities=[("session", preview_hashes[0]), ("client", preview_hashes[1])],
            landing_slug="general",
        )
        self.assertIsNone(claimed)
        db.complete_public_check_preview_usage(
            api.settings.database_path,
            identity_hashes=preview_hashes,
            urgency_level="yellow",
            model="test-model",
            total_tokens=300,
        )

        dashboard = api._admin_dashboard_payload()
        overview = dashboard["overview"]
        self.assertEqual(overview["tokens_30d_cabinet"] - before["tokens_30d_cabinet"], 200)
        self.assertEqual(overview["tokens_30d_public"] - before["tokens_30d_public"], 300)
        self.assertEqual(overview["tokens_30d"] - before["tokens_30d"], 500)
        recent_by_id = {item["id"]: item for item in dashboard["recent_triage"]}
        self.assertEqual(recent_by_id[int(cabinet_log["id"])]["total_tokens"], 200)
        self.assertEqual(recent_by_id[int(preview_log["id"])]["total_tokens"], 300)

    def test_site_visit_logger_ignores_service_worker_preloads(self) -> None:
        response = Response(status_code=200)
        preload = request(
            "/",
            method="GET",
            headers={
                "accept": "*/*",
                "sec-fetch-mode": "no-cors",
                "sec-fetch-dest": "empty",
                "user-agent": "Mozilla/5.0 Chrome/140.0",
            },
        )
        navigation = request(
            "/",
            method="GET",
            headers={
                "accept": "text/html",
                "sec-fetch-mode": "navigate",
                "sec-fetch-dest": "document",
                "user-agent": "Mozilla/5.0 Chrome/140.0",
            },
        )

        self.assertFalse(api._should_log_site_visit(preload, response))
        self.assertTrue(api._should_log_site_visit(navigation, response))

    def test_funnel_events_are_sanitized_and_visible_in_admin(self) -> None:
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="landing.primary_cta_click",
                session_id="session-1",
                metadata={
                    "target": "hero",
                    "complaint_text": "secret symptom",
                    "internal_secret": "must not be stored",
                    "traffic_source": "yandex_direct<script>",
                    "landing_path": "/check/cat-not-eating?unsafe=1",
                    "utm_campaign": "search-cats",
                    "utm_content": "ad-01",
                },
            ),
            request("/api/funnel/event"),
        )
        campaign_events = {
            "pet.landing_view": "pet_landing",
            "pet.card_start_click": "pet_card_start",
            "food.landing_view": "food_landing",
            "food.submit": "food_submit",
            "food.result_shown": "food_result",
            "food.card_start_click": "food_card_start",
        }
        for event_type in campaign_events:
            api.funnel_event(
                api.FunnelEventRequest(
                    event_type=event_type,
                    session_id="campaign-session-1",
                    metadata={"slug": "food-dog", "pet_type": "dog", "landing_path": "/food/dog"},
                ),
                request("/api/funnel/event"),
            )
        user, _ = login("funnel-owner@example.ru")
        api._track_funnel(
            request(
                "/api/triage",
                headers={
                    "x-tvv-traffic-source": "yandex_direct",
                    "x-tvv-utm-campaign": "search-symptoms",
                    "x-tvv-utm-content": "ad-42",
                    "x-tvv-landing-path": "/check/dog-vomiting",
                    "x-tvv-has-yclid": "1",
                },
            ),
            "triage.completed",
            user_id=int(user["id"]),
            metadata={"urgency": "yellow", "text": "secret"},
        )

        items = db.list_funnel_events(api.settings.database_path, limit=20)
        self.assertTrue(any(item["step"] == "primary_cta" for item in items))
        self.assertTrue(any(item["step"] == "triage_success" for item in items))
        for expected_step in campaign_events.values():
            self.assertTrue(any(item["step"] == expected_step for item in items))
        triage_item = next(item for item in items if item["step"] == "triage_success")
        self.assertEqual(triage_item["source"], "yandex_direct")
        self.assertEqual(triage_item["path"], "/check/dog-vomiting")
        self.assertEqual(triage_item["metadata"]["utm_campaign"], "search-symptoms")
        self.assertTrue(triage_item["metadata"]["has_yclid"])
        primary_item = next(item for item in items if item["step"] == "primary_cta")
        self.assertEqual(primary_item["source"], "yandex_directscript")
        self.assertEqual(primary_item["path"], "/check/cat-not-eatingunsafe1")
        self.assertEqual(primary_item["metadata"]["utm_campaign"], "search-cats")
        for item in items:
            metadata = item.get("metadata") or {}
            self.assertNotIn("complaint_text", metadata)
            self.assertNotIn("text", metadata)
            self.assertNotIn("internal_secret", metadata)

        dashboard = api._admin_dashboard_payload()
        self.assertIn("conversion_funnel_72h", dashboard)
        steps = dashboard["conversion_funnel_72h"]["steps"]
        self.assertTrue(any(step["step"] == "primary_cta" and step["count"] >= 1 for step in steps))
        self.assertTrue(any(step["step"] == "triage_success" and step["count"] >= 1 for step in steps))
        recent_primary = next(item for item in dashboard["recent_funnel_events"] if item["step"] == "primary_cta")
        self.assertEqual(recent_primary["landing_path"], "/check/cat-not-eatingunsafe1")
        self.assertEqual(recent_primary["utm_campaign"], "search-cats")
        self.assertEqual(recent_primary["utm_content"], "ad-01")

    def test_funnel_request_attribution_decodes_cyrillic_headers(self) -> None:
        term = "кот часто ходит в лоток"
        attribution = api._funnel_request_attribution(
            request(
                "/api/check/preview",
                headers={
                    "x-tvv-traffic-source": "yandex",
                    "x-tvv-utm-source": "yandex",
                    "x-tvv-utm-medium": "cpc",
                    "x-tvv-utm-campaign": "711014575",
                    "x-tvv-utm-term": urllib.parse.quote(term, safe=""),
                    "x-tvv-landing-path": urllib.parse.quote("/check", safe=""),
                    "x-tvv-has-yclid": "1",
                    "x-tvv-current-flow-id": "flow-current-check",
                    "x-tvv-first-traffic-source": "direct",
                    "x-tvv-first-utm-campaign": "first-campaign",
                    "x-tvv-first-landing-path": urllib.parse.quote("/", safe=""),
                    "x-tvv-first-has-yclid": "0",
                },
            )
        )

        self.assertEqual(attribution["utm_term"], term)
        self.assertEqual(attribution["landing_path"], "/check")
        self.assertEqual(attribution["utm_campaign"], "711014575")
        self.assertTrue(attribution["has_yclid"])
        self.assertEqual(attribution["current_flow_id"], "flow-current-check")
        self.assertEqual(attribution["current_landing_path"], "/check")
        self.assertEqual(attribution["current_utm_campaign"], "711014575")
        self.assertEqual(attribution["first_traffic_source"], "direct")
        self.assertEqual(attribution["first_utm_campaign"], "first-campaign")
        self.assertEqual(attribution["first_landing_path"], "/")
        self.assertFalse(attribution["first_has_yclid"])

    def test_admin_tracks_pet_and_food_campaigns_without_cross_contamination(self) -> None:
        pet_session = "pet-campaign-complete-session"
        food_session = "food-campaign-complete-session"
        food_loss_session = "food-campaign-no-submit-session"
        session_ids = [pet_session, food_session, food_loss_session]
        before = api._admin_dashboard_payload()
        before_pet = {
            item["step"]: item["unique_count"]
            for item in before["conversion_funnel_72h_pet"]["steps"]
        }
        before_food = {
            item["step"]: item["unique_count"]
            for item in before["conversion_funnel_72h_food"]["steps"]
        }
        before_food_loss = before["conversion_funnel_72h_food"]["loss_reasons"]["not_submitted"]

        def send(event_type: str, session_id: str, landing_path: str, **metadata) -> None:
            api.funnel_event(
                api.FunnelEventRequest(
                    event_type=event_type,
                    session_id=session_id,
                    metadata={"landing_path": landing_path, **metadata},
                ),
                request(
                    "/api/funnel/event",
                    headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
                ),
            )

        try:
            send("pet.landing_view", pet_session, "/pet", slug="pet", utm_campaign="passport-test")
            send("pet.card_start_click", pet_session, "/pet", slug="pet", utm_campaign="passport-test")
            send("auth.dialog_open", pet_session, "/pet", utm_campaign="passport-test")
            pet_user, _ = login("passport-funnel-owner@example.ru")
            api._track_funnel(
                request(
                    "/api/auth/email/verify",
                    headers={
                        "x-tvv-funnel-session": pet_session,
                        "x-tvv-landing-path": "/pet",
                        "x-tvv-utm-campaign": "passport-test",
                    },
                ),
                "auth.login_success",
                user_id=int(pet_user["id"]),
            )
            api.create_pet(
                api.PetPayload(pet_type="кошка", pet_name="Секретная кличка"),
                user=pet_user,
                request=request(
                    "/api/pets",
                    headers={
                        "x-tvv-funnel-session": pet_session,
                        "x-tvv-landing-path": "/pet",
                        "x-tvv-utm-campaign": "passport-test",
                    },
                ),
            )

            send("food.landing_view", food_session, "/food/dog", slug="food-dog", pet_type="dog", utm_campaign="food-test")
            send("food.submit", food_session, "/food/dog", slug="food-dog", pet_type="dog", utm_campaign="food-test")
            send(
                "food.result_shown",
                food_session,
                "/food/dog",
                slug="food-dog",
                pet_type="dog",
                level="avoid",
                utm_campaign="food-test",
            )
            send("food.card_start_click", food_session, "/food/dog", slug="food-dog", pet_type="dog", utm_campaign="food-test")
            send("auth.dialog_open", food_session, "/food/dog", utm_campaign="food-test")
            food_user, _ = login("food-funnel-owner@example.ru")
            api._track_funnel(
                request(
                    "/api/auth/email/verify",
                    headers={
                        "x-tvv-funnel-session": food_session,
                        "x-tvv-landing-path": "/food/dog",
                        "x-tvv-utm-campaign": "food-test",
                    },
                ),
                "auth.login_success",
                user_id=int(food_user["id"]),
            )
            api.create_pet(
                api.PetPayload(pet_type="собака", pet_name="Другая секретная кличка"),
                user=food_user,
                request=request(
                    "/api/pets",
                    headers={
                        "x-tvv-funnel-session": food_session,
                        "x-tvv-landing-path": "/food/dog",
                        "x-tvv-utm-campaign": "food-test",
                    },
                ),
            )
            send("food.landing_view", food_loss_session, "/food/cat", slug="food-cat", pet_type="cat", utm_campaign="food-test")

            spoofed = api.funnel_event(
                api.FunnelEventRequest(
                    event_type="pet.created",
                    session_id="spoofed-pet-created",
                    metadata={"pet_name": "Не сохранять", "first_pet": True},
                ),
                request("/api/funnel/event"),
            )
            self.assertTrue(spoofed.get("ignored"))

            after = api._admin_dashboard_payload()
            after_pet = {
                item["step"]: item["unique_count"]
                for item in after["conversion_funnel_72h_pet"]["steps"]
            }
            after_food = {
                item["step"]: item["unique_count"]
                for item in after["conversion_funnel_72h_food"]["steps"]
            }
            for step in ("pet_landing", "pet_card_start", "auth_open", "login_success", "pet_created"):
                self.assertEqual(after_pet[step], before_pet[step] + 1)
            for step in ("food_landing", "food_submit", "food_result", "food_card_start", "auth_open", "login_success", "pet_created"):
                expected_delta = 2 if step == "food_landing" else 1
                self.assertEqual(after_food[step], before_food[step] + expected_delta)
            self.assertEqual(
                after["conversion_funnel_72h_food"]["loss_reasons"]["not_submitted"],
                before_food_loss + 1,
            )

            pet_landings = {row["name"] for row in after["conversion_funnel_72h_pet"]["cuts"]["landing"]}
            food_landings = {row["name"] for row in after["conversion_funnel_72h_food"]["cuts"]["landing"]}
            self.assertIn("pet", pet_landings)
            self.assertNotIn("food-dog", pet_landings)
            self.assertIn("food-dog", food_landings)
            self.assertIn("food-cat", food_landings)
            self.assertNotIn("pet", food_landings)
            self.assertTrue(
                any(
                    row["name"] == "avoid" and row["sessions"] >= 1
                    for row in after["conversion_funnel_72h_food"]["result_levels"]
                )
            )

            with db.connect(api.settings.database_path) as conn:
                pet_created_rows = conn.execute(
                    "SELECT metadata FROM funnel_events WHERE event_type = 'pet.created' AND session_hash IN (?, ?)",
                    tuple(
                        api.hash_value(value, api.settings.session_secret)[:24]
                        for value in (pet_session, food_session)
                    ),
                ).fetchall()
            self.assertEqual(len(pet_created_rows), 2)
            for row in pet_created_rows:
                metadata = json.loads(row["metadata"] or "{}")
                self.assertIn(metadata.get("pet_type"), {"cat", "dog"})
                self.assertIs(metadata.get("first_pet"), True)
                self.assertNotIn("pet_name", metadata)
                self.assertNotIn("Секрет", json.dumps(metadata, ensure_ascii=False))
        finally:
            with db.connect(api.settings.database_path) as conn:
                for raw_session in session_ids:
                    session_hash = api.hash_value(raw_session, api.settings.session_secret)[:24]
                    conn.execute("DELETE FROM funnel_events WHERE session_hash = ?", (session_hash,))
                conn.commit()

    def test_backend_funnel_uses_browser_session_header(self) -> None:
        user, _ = login("funnel-session-owner@example.ru")
        raw_session = "browser-funnel-session-1"
        expected_hash = api.hash_value(raw_session, api.settings.session_secret)[:24]
        api._track_funnel(
            request(
                "/api/auth/email/verify",
                headers={
                    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
                    "x-tvv-funnel-session": raw_session,
                    "x-tvv-traffic-source": "yandex_direct",
                    "x-tvv-landing-path": "/check/cat-not-eating",
                },
            ),
            "auth.login_success",
            user_id=int(user["id"]),
            metadata={"provider": "email"},
        )

        try:
            with db.connect(api.settings.database_path) as conn:
                row = conn.execute(
                    "SELECT session_hash, source, path FROM funnel_events WHERE session_hash = ? ORDER BY id DESC LIMIT 1",
                    (expected_hash,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["session_hash"], expected_hash)
            self.assertEqual(row["source"], "yandex_direct")
            self.assertEqual(row["path"], "/check/cat-not-eating")
        finally:
            with db.connect(api.settings.database_path) as conn:
                conn.execute("DELETE FROM funnel_events WHERE session_hash = ?", (expected_hash,))
                conn.commit()

    def test_current_flow_keeps_check_and_food_first_touches_out_of_pet_conversion(self) -> None:
        user, _ = login("current-flow-owner@example.ru")
        self._activate_plus(user)
        flows = (
            ("flow-check-to-pet", "/check", "check-first", "Кошка из pet-flow"),
            ("flow-food-to-pet", "/food/dog", "food-first", "Собака из pet-flow"),
        )
        before = api._admin_dashboard_payload()
        before_pet_created = next(
            item["unique_count"]
            for item in before["conversion_funnel_72h_pet"]["steps"]
            if item["step"] == "pet_created"
        )
        before_food_created = next(
            item["unique_count"]
            for item in before["conversion_funnel_72h_food"]["steps"]
            if item["step"] == "pet_created"
        )

        try:
            for index, (flow_id, first_path, first_campaign, pet_name) in enumerate(flows):
                api.create_pet(
                    api.PetPayload(
                        pet_type="кошка" if index == 0 else "собака",
                        pet_name=pet_name,
                    ),
                    user=user,
                    request=request(
                        "/api/pets",
                        headers={
                            "x-tvv-current-flow-id": flow_id,
                            "x-tvv-funnel-session": flow_id,
                            "x-tvv-traffic-source": "yandex",
                            "x-tvv-utm-source": "yandex",
                            "x-tvv-utm-medium": "cpc",
                            "x-tvv-utm-campaign": "pet-current",
                            "x-tvv-landing-path": "/pet",
                            "x-tvv-has-yclid": "1",
                            "x-tvv-first-traffic-source": "yandex",
                            "x-tvv-first-utm-source": "yandex",
                            "x-tvv-first-utm-medium": "cpc",
                            "x-tvv-first-utm-campaign": first_campaign,
                            "x-tvv-first-landing-path": first_path,
                            "x-tvv-first-has-yclid": "1",
                        },
                    ),
                )

            with db.connect(api.settings.database_path) as conn:
                rows = conn.execute(
                    "SELECT session_hash, path, metadata FROM funnel_events WHERE session_hash IN (?, ?)",
                    tuple(api.hash_value(flow_id, api.settings.session_secret)[:24] for flow_id, *_ in flows),
                ).fetchall()
            self.assertEqual(len(rows), 2)
            metadata_by_session = {
                str(row["session_hash"]): json.loads(row["metadata"] or "{}")
                for row in rows
            }
            for flow_id, first_path, first_campaign, _pet_name in flows:
                session_hash = api.hash_value(flow_id, api.settings.session_secret)[:24]
                metadata = metadata_by_session[session_hash]
                self.assertEqual(metadata["current_flow_id"], flow_id)
                self.assertEqual(metadata["landing_path"], "/pet")
                self.assertEqual(metadata["current_landing_path"], "/pet")
                self.assertEqual(metadata["utm_campaign"], "pet-current")
                self.assertEqual(metadata["current_utm_campaign"], "pet-current")
                self.assertEqual(metadata["first_landing_path"], first_path)
                self.assertEqual(metadata["first_utm_campaign"], first_campaign)

            after = api._admin_dashboard_payload()
            after_pet_created = next(
                item["unique_count"]
                for item in after["conversion_funnel_72h_pet"]["steps"]
                if item["step"] == "pet_created"
            )
            after_food_created = next(
                item["unique_count"]
                for item in after["conversion_funnel_72h_food"]["steps"]
                if item["step"] == "pet_created"
            )
            self.assertEqual(after_pet_created, before_pet_created + 2)
            self.assertEqual(after_food_created, before_food_created)
        finally:
            with db.connect(api.settings.database_path) as conn:
                for flow_id, *_ in flows:
                    session_hash = api.hash_value(flow_id, api.settings.session_secret)[:24]
                    conn.execute("DELETE FROM funnel_events WHERE session_hash = ?", (session_hash,))
                conn.commit()

    def test_admin_dashboard_separates_public_and_auth_funnel_data(self) -> None:
        before = api._admin_dashboard_payload()
        before_public = {
            item["step"]: item
            for item in before["conversion_funnel_72h_public"]["steps"]
        }
        before_auth = {
            item["step"]: item
            for item in before["conversion_funnel_72h_auth"]["steps"]
        }
        before_totals = before["funnel_cuts_72h"]

        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.view",
                session_id="admin-public-split-check-view",
                metadata={
                    "path": "/check/cat-not-eating",
                    "landing_path": "/check/cat-not-eating",
                    "utm_campaign": "split-public-campaign",
                },
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.start_click",
                session_id="admin-public-split-check-view",
                metadata={
                    "landing_path": "/check/cat-not-eating",
                    "utm_campaign": "split-public-campaign",
                },
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.submit",
                session_id="admin-public-split-check-view",
                metadata={"landing_path": "/check/cat-not-eating", "utm_campaign": "split-public-campaign"},
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X)"},
            ),
        )
        user, _ = login("admin-auth-split-owner@example.ru")
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="landing.primary_cta_click",
                session_id="admin-auth-split-session",
                metadata={"path": "/check/cat-not-eating", "utm_campaign": "split-auth-campaign"},
            ),
            request("/"),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="auth.login_success",
                session_id="admin-auth-split-session",
                metadata={"provider": "email"},
            ),
            request("/api/auth/email/verify"),
        )
        api._track_funnel(
            request("/api/auth/email/verify"),
            "auth.login_success",
            user_id=int(user["id"]),
            session_id="admin-auth-split-session",
            metadata={"provider": "email"},
        )

        admin_session_ids = [
            "admin-public-split-check-view",
            "admin-auth-split-session",
        ]
        admin_site_ips = ["bot-visit-hash-admin-1", "human-visit-hash-admin-1"]

        try:
            after = api._admin_dashboard_payload()
            after_public = {
                item["step"]: item
                for item in after["conversion_funnel_72h_public"]["steps"]
            }
            after_auth = {
                item["step"]: item
                for item in after["conversion_funnel_72h_auth"]["steps"]
            }
            cuts = after["funnel_cuts_72h"]
            public_cuts = cuts.get("public", {})

            self.assertGreaterEqual(
                int(after_public["check_view"]["unique_count"]),
                int(before_public["check_view"]["unique_count"]) + 1,
            )
            self.assertGreaterEqual(
                int(after_public["check_submit"]["unique_count"]),
                int(before_public["check_submit"]["unique_count"]) + 1,
            )
            self.assertGreaterEqual(
                int(after_auth["primary_cta"]["unique_count"]),
                int(before_auth["primary_cta"]["unique_count"]) + 1,
            )
            self.assertGreaterEqual(
                int(after_auth["login_success"]["unique_count"]),
                int(before_auth["login_success"]["unique_count"]) + 1,
            )
            self.assertIn("split-public-campaign", {row["name"] for row in public_cuts["campaign"]})
            self.assertIn("cat-not-eating", {row["name"] for row in public_cuts["landing"]})

            before_new = next(
                (row["sessions"] for row in before_totals.get("returning", []) if row["name"] == "new"),
                0,
            )
            after_new = next(
                (row["sessions"] for row in cuts.get("returning", []) if row["name"] == "new"),
                0,
            )
            self.assertGreater(after_new, before_new)
        finally:
            with db.connect(api.settings.database_path) as conn:
                for raw_session in admin_session_ids:
                    session_hash = api.hash_value(raw_session, api.settings.session_secret)[:24]
                    conn.execute("DELETE FROM funnel_events WHERE session_hash = ?", (session_hash,))
                conn.execute(
                    "DELETE FROM site_visits WHERE ip_hash IN (?, ?)",
                    tuple(admin_site_ips),
                )
                conn.commit()

    def test_admin_dashboard_exposes_service_activation_and_return_metrics(self) -> None:
        user, _ = login("admin-service-funnel@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Рой", client_request_id="admin-service-pet"),
            request("/api/pets"),
            user=user,
        )["item"]
        api.add_pet_observation(
            int(pet["id"]),
            api.ObservationPayload(obs_type="note", text="Активность обычная"),
            request(f"/api/pets/{pet['id']}/observations"),
            user=user,
        )
        dashboard = api._admin_dashboard_payload()
        service_steps = {
            item["step"]: item
            for item in dashboard["conversion_funnel_72h_service"]["steps"]
        }
        self.assertIn("pet_created", service_steps)
        self.assertIn("first_record", service_steps)
        self.assertIn("service_activated", service_steps)
        self.assertGreaterEqual(service_steps["service_activated"]["unique_count"], 1)
        self.assertIn("return_d1_users_30d", dashboard["overview"])
        self.assertIn("return_d7_users_30d", dashboard["overview"])

    def test_admin_dashboard_keeps_raw_bot_logs_and_tracks_public_loss_reasons(self) -> None:
        before = api._admin_dashboard_payload()
        before_loss = before["funnel_loss_reasons_72h"]
        before_visits_total = before["overview"]["site_visits_24h"]
        before_visits_human = before["overview"]["site_visits_24h_human"]
        before_visits_technical = before["overview"]["site_visits_24h_technical"]
        before_public_views = next(
            item["unique_count"]
            for item in before["conversion_funnel_72h_public"]["steps"]
            if item["step"] == "check_view"
        )
        before_synthetic_events = before["funnel_technical_72h"]["events"]

        db.create_site_visit(
            api.settings.database_path,
            method="GET",
            path="/check/cat-not-eating",
            status_code=200,
            user_id=None,
            ip_hash="bot-visit-hash-admin-1",
            source="scanner.example",
            device="Бот/проверка",
            browser="Бот/проверка",
            is_bot=True,
        )
        db.create_site_visit(
            api.settings.database_path,
            method="GET",
            path="/check/cat-not-eating",
            status_code=200,
            user_id=None,
            ip_hash="human-visit-hash-admin-1",
            source="yandex",
            device="Телефон",
            browser="Chrome",
            is_bot=False,
        )
        db.create_site_visit(
            api.settings.database_path,
            method="GET",
            path="/wp-admin/install.php",
            status_code=200,
            user_id=None,
            ip_hash="scanner-path-hash-admin-1",
            source="Прямой заход",
            device="Компьютер",
            browser="Неизвестно",
            is_bot=False,
        )

        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.view",
                session_id="qa-synthetic-session",
                metadata={
                    "landing_path": "/check/cat-not-eating",
                    "traffic_source": "codex_test",
                    "utm_campaign": "marketing_funnel_qa",
                },
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            ),
        )

        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.view",
                session_id="loss-not-started-session",
                metadata={"landing_path": "/check/cat-not-eating", "utm_campaign": "loss-public"},
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.start_click",
                session_id="loss-start-only-session",
                metadata={"landing_path": "/check/cat-not-eating", "utm_campaign": "loss-public"},
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.save_click",
                session_id="loss-save-incomplete-session",
                metadata={"landing_path": "/check/cat-not-eating", "utm_campaign": "loss-public"},
            ),
            request(
                "/check/cat-not-eating",
                headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="check.submit",
                session_id="loss-result-missing-session",
                metadata={"landing_path": "/check", "utm_campaign": "loss-public"},
            ),
            request(
                "/check",
                headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"},
            ),
        )
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="landing.login_cta_click",
                session_id="loss-login-opened-session",
                metadata={"landing_path": "/check/cat-not-eating"},
            ),
            request("/check/cat-not-eating"),
        )
        user, _ = login("loss-login-success-owner@example.ru")
        api.funnel_event(
            api.FunnelEventRequest(
                event_type="auth.login_success",
                session_id="loss-login-success-session",
                metadata={"provider": "email"},
            ),
            request("/check/cat-not-eating"),
        )
        api._track_funnel(
            request("/check/cat-not-eating"),
            "auth.login_success",
            user_id=int(user["id"]),
            session_id="loss-login-success-session",
            metadata={"provider": "email"},
        )

        db.create_security_audit_event(
            api.settings.database_path,
            event_type="check.preview_blocked",
            status="warning",
            actor="test",
            metadata={"reason": "already_used"},
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="llm.check_preview_failed",
            status="error",
            actor="test",
            provider="openai",
            metadata={"reason": "simulated failure"},
        )

        loss_session_ids = [
            "loss-not-started-session",
            "loss-start-only-session",
            "loss-save-incomplete-session",
            "loss-result-missing-session",
            "loss-login-opened-session",
            "loss-login-success-session",
            "qa-synthetic-session",
        ]
        loss_site_ips = [
            "bot-visit-hash-admin-1",
            "human-visit-hash-admin-1",
            "scanner-path-hash-admin-1",
        ]

        try:
            after = api._admin_dashboard_payload()
            after_loss = after["funnel_loss_reasons_72h"]
            after_recent_visits = after["recent_site_visits"]
            after_product_visits = after["recent_site_visits_product"]
            after_technical_visits = after["recent_site_visits_technical"]
            campaign_rows = after["funnel_cuts_72h"].get("public", {}).get("campaign", [])
            after_public_views = next(
                item["unique_count"]
                for item in after["conversion_funnel_72h_public"]["steps"]
                if item["step"] == "check_view"
            )

            self.assertEqual(after["overview"]["site_visits_24h"], before_visits_total + 3)
            self.assertEqual(after["overview"]["site_visits_24h_human"], before_visits_human + 1)
            self.assertEqual(after["overview"]["site_visits_24h_technical"], before_visits_technical + 2)
            self.assertEqual(after_public_views, before_public_views + 1)
            self.assertEqual(after["funnel_technical_72h"]["events"], before_synthetic_events + 1)
            self.assertTrue(
                any(
                    item.get("path") == "/check/cat-not-eating"
                    and item.get("source") == "scanner.example"
                    and item.get("is_bot") in (1, True)
                    for item in after_recent_visits
                )
            )
            self.assertTrue(any(item.get("path") == "/wp-admin/install.php" for item in after_technical_visits))
            self.assertFalse(any(item.get("path") == "/wp-admin/install.php" for item in after_product_visits))
            self.assertTrue(
                any(item.get("source") == "codex_test" for item in after["recent_funnel_events_technical"])
            )
            self.assertFalse(
                any(item.get("source") == "codex_test" for item in after["recent_funnel_events_product"])
            )
            self.assertTrue(
                any(
                    row["name"] == "loss-public"
                    and row["sessions"] >= 1
                    for row in campaign_rows
                )
            )
            self.assertGreaterEqual(after_loss["not_started"], before_loss["not_started"] + 1)
            self.assertGreaterEqual(after_loss["not_submitted"], before_loss["not_submitted"] + 1)
            self.assertGreaterEqual(
                after_loss["result_not_received"], before_loss["result_not_received"] + 1
            )
            self.assertGreaterEqual(after_loss["save_incomplete"], before_loss["save_incomplete"] + 1)
            self.assertGreaterEqual(after_loss["login_opened"], before_loss["login_opened"] + 1)
            self.assertGreaterEqual(after_loss["login_successful"], before_loss["login_successful"] + 1)
            self.assertGreaterEqual(after_loss["repeat_limit"], before_loss["repeat_limit"] + 1)
            self.assertGreaterEqual(after_loss["model_error"], before_loss["model_error"] + 1)
        finally:
            with db.connect(api.settings.database_path) as conn:
                for raw_session in loss_session_ids:
                    session_hash = api.hash_value(raw_session, api.settings.session_secret)[:24]
                    conn.execute("DELETE FROM funnel_events WHERE session_hash = ?", (session_hash,))
                conn.execute(
                    "DELETE FROM site_visits WHERE ip_hash IN (?, ?, ?)",
                    tuple(loss_site_ips),
                )
                conn.execute(
                    """
                    DELETE FROM security_audit_events
                    WHERE actor = 'test'
                      AND ((event_type = 'check.preview_blocked' AND json_extract(metadata, '$.reason') = 'already_used')
                           OR (event_type = 'llm.check_preview_failed' AND json_extract(metadata, '$.reason') = 'simulated failure'))
                    """,
                )
                conn.commit()

    def test_public_check_preview_red_flag_does_not_call_llm_or_save_history(self) -> None:
        original_llm = api.call_triage_llm
        calls: list[str] = []

        def forbidden_llm(**kwargs):
            calls.append("llm")
            raise AssertionError("LLM must not run for public red flags")

        api.call_triage_llm = forbidden_llm
        try:
            with db.connect(api.settings.database_path) as conn:
                before = conn.execute("SELECT COUNT(*) FROM triage_logs").fetchone()[0]

            result = api.public_check_preview(
                api.PublicCheckPreviewRequest(
                    pet_type="cat",
                    text="кот часто сидит в лотке и не может помочиться",
                    landing_slug="urination",
                    session_id="public-red-1",
                ),
                request("/api/check/preview", client_host="10.10.0.11"),
            )

            with db.connect(api.settings.database_path) as conn:
                after = conn.execute("SELECT COUNT(*) FROM triage_logs").fetchone()[0]

            self.assertEqual(calls, [])
            self.assertEqual(before, after)
            self.assertFalse(result["usage_consumed"])
            self.assertEqual(result["urgency"], "red")
            self.assertIn("невозможность мочиться", result["matched"])
            self.assertIn("Срочно", result["answer"])
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_honeypot_blocks_without_llm(self) -> None:
        original_llm = api.call_triage_llm
        calls: list[str] = []

        def forbidden_llm(**kwargs):
            calls.append("llm")
            raise AssertionError("LLM must not run for honeypot submissions")

        api.call_triage_llm = forbidden_llm
        try:
            with self.assertRaises(HTTPException) as exc:
                api.public_check_preview(
                    api.PublicCheckPreviewRequest(
                        pet_type="dog",
                        text="собака кашляет после прогулки, активность чуть ниже обычной",
                        landing_slug="general",
                        session_id="public-honeypot-1",
                        website="https://spam.example",
                    ),
                    request("/api/check/preview", client_host="10.10.0.12"),
                )
            self.assertEqual(exc.exception.status_code, 400)
            self.assertEqual(exc.exception.detail, "invalid_check_preview")
            self.assertEqual(calls, [])
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_short_text_rejects_without_llm(self) -> None:
        original_llm = api.call_triage_llm
        calls: list[str] = []

        def forbidden_llm(**kwargs):
            calls.append("llm")
            raise AssertionError("LLM must not run for too short public text")

        api.call_triage_llm = forbidden_llm
        try:
            with self.assertRaises(HTTPException) as exc:
                api.public_check_preview(
                    api.PublicCheckPreviewRequest(
                        pet_type="dog",
                        text="рвота",
                        landing_slug="dog-vomiting",
                        session_id="public-short-1",
                    ),
                    request("/api/check/preview", client_host="10.10.0.13"),
                )
            self.assertEqual(exc.exception.status_code, 400)
            self.assertEqual(exc.exception.detail, "check_preview_text_too_short")
            self.assertEqual(calls, [])
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_uses_plus_llm_without_auth_or_history_write(self) -> None:
        original_llm = api.call_triage_llm
        captured: dict = {}

        def fake_llm(**kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                text=(
                    "1) Кратко: по описанию есть повод внимательно наблюдать за состоянием.\n"
                    "2) Уровень срочности: 🟡 Нужна консультация — симптом сохраняется и требует связи с врачом.\n"
                    "3) Что делать сейчас — запишите время симптома, воду и активность.\n"
                    "4) Чего делать нельзя — не давайте лекарства без назначения.\n"
                    "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                    "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
                ),
                model="gpt-5.1-mini",
                prompt_tokens=100,
                completion_tokens=120,
                total_tokens=220,
            )

        api.call_triage_llm = fake_llm
        try:
            with db.connect(api.settings.database_path) as conn:
                before = conn.execute("SELECT COUNT(*) FROM triage_logs").fetchone()[0]

            result = api.public_check_preview(
                api.PublicCheckPreviewRequest(
                    pet_type="cat",
                    age="7 лет",
                    text="кошка не ест второй день, стала вялая",
                    landing_slug="cat-not-eating",
                    session_id="public-llm-1",
                ),
                request("/api/check/preview", client_host="10.10.0.14"),
            )

            with db.connect(api.settings.database_path) as conn:
                after = conn.execute("SELECT COUNT(*) FROM triage_logs").fetchone()[0]

            self.assertEqual(captured["plan_code"], "plus")
            self.assertEqual(captured["selected_pet"]["pet_type"], "кошка")
            self.assertIn("7 лет", captured["complaint_text"])
            self.assertIn("кошка не ест второй день", captured["complaint_text"])
            self.assertEqual(before, after)
            self.assertTrue(result["usage_consumed"])
            self.assertEqual(result["urgency"], "yellow")
            self.assertEqual(result["model"], "gpt-5.1-mini")
            self.assertEqual(result["total_tokens"], 220)
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_allows_only_one_successful_llm_preview(self) -> None:
        original_llm = api.call_triage_llm
        calls: list[str] = []

        def fake_llm(**kwargs):
            calls.append(kwargs["complaint_text"])
            return types.SimpleNamespace(
                text=(
                    "1) Кратко: по описанию состояние требует наблюдения.\n"
                    "2) Уровень срочности: 🟡 Нужна консультация — симптом лучше обсудить с врачом.\n"
                    "3) Что делать сейчас — записать время симптома и общее поведение.\n"
                    "4) Чего делать нельзя — не давать лекарства без назначения.\n"
                    "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                    "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
                ),
                model="gpt-5.1-mini",
                prompt_tokens=40,
                completion_tokens=80,
                total_tokens=120,
            )

        api.call_triage_llm = fake_llm
        try:
            result = api.public_check_preview(
                api.PublicCheckPreviewRequest(
                    pet_type="dog",
                    text="собака кашляет после прогулки, ест и пьет обычно",
                    landing_slug="general",
                    session_id="public-limit-session-1",
                ),
                request("/api/check/preview", client_host="10.10.0.15"),
            )
            self.assertEqual(result["status"], "preview")

            with self.assertRaises(HTTPException) as exc:
                api.public_check_preview(
                    api.PublicCheckPreviewRequest(
                        pet_type="dog",
                        text="собака снова кашляет, хочется проверить ещё раз бесплатно",
                        landing_slug="general",
                        session_id="public-limit-session-1",
                    ),
                    request("/api/check/preview", client_host="10.10.0.15"),
                )
            self.assertEqual(exc.exception.status_code, 403)
            self.assertEqual(exc.exception.detail, "check_preview_already_used")
            self.assertEqual(len(calls), 1)
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_blocks_same_client_after_session_reset(self) -> None:
        original_llm = api.call_triage_llm
        calls: list[str] = []

        def fake_llm(**kwargs):
            calls.append(kwargs["complaint_text"])
            return types.SimpleNamespace(
                text=(
                    "1) Кратко: по описанию состояние требует наблюдения.\n"
                    "2) Уровень срочности: 🟡 Нужна консультация — симптом лучше обсудить с врачом.\n"
                    "3) Что делать сейчас — записать время симптома и общее поведение.\n"
                    "4) Чего делать нельзя — не давать лекарства без назначения.\n"
                    "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                    "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
                ),
                model="gpt-5.1-mini",
                prompt_tokens=40,
                completion_tokens=80,
                total_tokens=120,
            )

        api.call_triage_llm = fake_llm
        headers = {"user-agent": "Mozilla/5.0 TemichevVetPublicCheckTest/1.0"}
        try:
            first = api.public_check_preview(
                api.PublicCheckPreviewRequest(
                    pet_type="cat",
                    text="кошка стала вялая вечером, ест меньше обычного",
                    landing_slug="general",
                    session_id="public-client-session-1",
                ),
                request("/api/check/preview", client_host="10.10.0.17", headers=headers),
            )
            self.assertEqual(first["status"], "preview")

            with self.assertRaises(HTTPException) as exc:
                api.public_check_preview(
                    api.PublicCheckPreviewRequest(
                        pet_type="cat",
                        text="кошка стала вялая утром, хочу второй пробник",
                        landing_slug="general",
                        session_id="public-client-session-2",
                    ),
                    request("/api/check/preview", client_host="10.10.0.17", headers=headers),
                )
            self.assertEqual(exc.exception.status_code, 403)
            self.assertEqual(exc.exception.detail, "check_preview_already_used")
            self.assertEqual(len(calls), 1)
        finally:
            api.call_triage_llm = original_llm

    def test_public_check_preview_llm_failure_audit_excludes_medical_text(self) -> None:
        original_llm = api.call_triage_llm

        def failing_llm(**kwargs):
            raise RuntimeError("openai_down")

        api.call_triage_llm = failing_llm
        try:
            with self.assertRaises(HTTPException) as exc:
                api.public_check_preview(
                    api.PublicCheckPreviewRequest(
                        pet_type="dog",
                        age="3 года",
                        text="секретный медицинский текст: собаку тошнит после еды",
                        landing_slug="dog-vomiting",
                        session_id="public-failure-1",
                    ),
                    request("/api/check/preview", client_host="10.10.0.16"),
                )
            self.assertEqual(exc.exception.status_code, 503)
        finally:
            api.call_triage_llm = original_llm

        def fake_llm_after_failure(**kwargs):
            return types.SimpleNamespace(
                text=(
                    "1) Кратко: по описанию состояние требует наблюдения.\n"
                    "2) Уровень срочности: 🟡 Нужна консультация — симптом лучше обсудить с врачом.\n"
                    "3) Что делать сейчас — записать время симптома и общее поведение.\n"
                    "4) Чего делать нельзя — не давать лекарства без назначения.\n"
                    "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                    "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
                ),
                model="gpt-5.1-mini",
                prompt_tokens=40,
                completion_tokens=80,
                total_tokens=120,
            )

        api.call_triage_llm = fake_llm_after_failure
        try:
            retry_result = api.public_check_preview(
                api.PublicCheckPreviewRequest(
                    pet_type="dog",
                    age="3 года",
                    text="секретный медицинский текст: собаку тошнит после еды",
                    landing_slug="dog-vomiting",
                    session_id="public-failure-1",
                ),
                request("/api/check/preview", client_host="10.10.0.16"),
            )
            self.assertEqual(retry_result["status"], "preview")
        finally:
            api.call_triage_llm = original_llm

        events = db.list_security_audit_events(
            api.settings.database_path,
            event_type="llm.check_preview_failed",
        )
        self.assertGreaterEqual(len(events), 1)
        serialized = json.dumps(events[0].get("metadata") or {}, ensure_ascii=False)
        self.assertIn("RuntimeError", serialized)
        self.assertNotIn("секретный медицинский текст", serialized)
        self.assertNotIn("собаку тошнит", serialized)

    def test_public_check_preview_save_after_login_creates_pet_history_without_quota_spend(self) -> None:
        user, _ = login("preview-save@example.ru")
        sub_before = api.get_effective_subscription(api.settings, user)
        with db.connect(api.settings.database_path) as conn:
            before_logs = conn.execute("SELECT COUNT(*) FROM triage_logs WHERE user_id = ?", (int(user["id"]),)).fetchone()[0]

        result = api.save_public_check_preview(
            api.PublicCheckPreviewSaveRequest(
                pet_type="cat",
                age="7 лет",
                text="кошка не ест второй день, стала вялая",
                answer=(
                    "1) Кратко: по описанию нужно внимательно наблюдать за состоянием.\n"
                    "2) Уровень срочности: 🟡 Нужна консультация — симптом сохраняется.\n"
                    "3) Что делать сейчас — запишите воду, аппетит и активность.\n"
                    "4) Чего делать нельзя — не давайте лекарства без назначения.\n"
                    "5) Тревожные признаки — ухудшение, кровь, тяжёлое дыхание.\n"
                    "6) Этот ответ не заменяет очный осмотр ветеринарного врача."
                ),
                urgency="yellow",
                summary="Кошка не ест второй день",
                model="gpt-5.1-mini",
                prompt_tokens=50,
                completion_tokens=80,
                total_tokens=130,
                landing_slug="cat-not-eating",
                session_id="preview-save-session-1",
            ),
            request("/api/check/preview/save", client_host="10.10.0.18"),
            user,
        )

        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["pet"]["pet_type"], "кошка")
        self.assertEqual(result["pet"]["pet_name"], "Кошка")
        self.assertEqual(result["created_pet"], True)
        sub_after = api.get_effective_subscription(api.settings, user)
        self.assertEqual(sub_before.quota_total, sub_after.quota_total)
        self.assertEqual(sub_before.quota_used, sub_after.quota_used)

        with db.connect(api.settings.database_path) as conn:
            after_logs = conn.execute("SELECT COUNT(*) FROM triage_logs WHERE user_id = ?", (int(user["id"]),)).fetchone()[0]
            log = conn.execute("SELECT * FROM triage_logs WHERE id = ?", (int(result["triage_id"]),)).fetchone()
            history = conn.execute(
                "SELECT * FROM pet_history WHERE triage_id = ?",
                (int(result["triage_id"]),),
            ).fetchone()

        self.assertEqual(after_logs, before_logs + 1)
        self.assertIsNotNone(log)
        self.assertIsNotNone(history)
        visible_history = api.pet_history(
            int(result["pet"]["id"]),
            request(f"/api/pets/{result['pet']['id']}/history", "GET"),
            user=user,
        )["items"]
        self.assertTrue(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in visible_history))
        self.assertEqual(log["subscription_source"], "public_preview")
        self.assertEqual(log["quota_before"], sub_before.quota_used)
        self.assertEqual(log["quota_after"], sub_before.quota_used)
        self.assertEqual(log["model"], "gpt-5.1-mini")
        self.assertIn("кошка не ест второй день", log["complaint_text"])

        audit_items = db.list_security_audit_events(
            api.settings.database_path,
            event_type="check.preview_saved",
            user_id=int(user["id"]),
        )
        self.assertGreaterEqual(len(audit_items), 1)
        audit_metadata = json.dumps(audit_items[0].get("metadata") or {}, ensure_ascii=False)
        self.assertIn("cat-not-eating", audit_metadata)
        self.assertNotIn("кошка не ест", audit_metadata)
        self.assertNotIn("запишите воду", audit_metadata)
        funnel_items = db.list_funnel_events(api.settings.database_path, limit=10)
        self.assertTrue(any(item["event_type"] == "check.saved_after_login" and item["step"] == "check_saved" for item in funnel_items))

    def test_public_check_preview_save_uses_single_matching_pet_and_is_visible_in_history(self) -> None:
        user, _ = login("preview-save-one-same@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Муся"),
            request("/api/pets"),
            user=user,
        )["item"]

        result = api.save_public_check_preview(
            self._public_check_save_payload(session_id="preview-save-one-same"),
            request("/api/check/preview/save"),
            user,
        )

        self.assertEqual(int(result["pet"]["id"]), int(pet["id"]))
        self.assertFalse(result["created_pet"])
        history = api.pet_history(
            int(pet["id"]),
            request(f"/api/pets/{pet['id']}/history", "GET"),
            user=user,
        )["items"]
        self.assertTrue(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in history))

    def test_public_check_preview_save_requires_choice_for_single_different_pet(self) -> None:
        user, _ = login("preview-save-one-other@example.ru")
        self._activate_plus(user)
        dog = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Рекс"),
            request("/api/pets"),
            user=user,
        )["item"]
        with db.connect(api.settings.database_path) as conn:
            logs_before = conn.execute("SELECT COUNT(*) FROM triage_logs WHERE user_id = ?", (int(user["id"]),)).fetchone()[0]

        with self.assertRaises(HTTPException) as required_exc:
            api.save_public_check_preview(
                self._public_check_save_payload(session_id="preview-save-one-other-required"),
                request("/api/check/preview/save"),
                user,
            )
        self.assertEqual(required_exc.exception.status_code, 409)
        self.assertEqual(required_exc.exception.detail, "check_preview_pet_required")

        with self.assertRaises(HTTPException) as mismatch_exc:
            api.save_public_check_preview(
                self._public_check_save_payload(
                    pet_id=int(dog["id"]),
                    session_id="preview-save-one-other-mismatch",
                ),
                request("/api/check/preview/save"),
                user,
            )
        self.assertEqual(mismatch_exc.exception.status_code, 409)
        self.assertEqual(mismatch_exc.exception.detail, "check_preview_pet_type_mismatch")

        with db.connect(api.settings.database_path) as conn:
            logs_after_rejections = conn.execute("SELECT COUNT(*) FROM triage_logs WHERE user_id = ?", (int(user["id"]),)).fetchone()[0]
        self.assertEqual(logs_after_rejections, logs_before)

        result = api.save_public_check_preview(
            self._public_check_save_payload(
                create_pet=True,
                session_id="preview-save-one-other-create",
            ),
            request("/api/check/preview/save"),
            user,
        )
        self.assertTrue(result["created_pet"])
        self.assertEqual(result["pet"]["pet_type"], "кошка")
        self.assertNotEqual(int(result["pet"]["id"]), int(dog["id"]))
        created_history = api.pet_history(
            int(result["pet"]["id"]),
            request(f"/api/pets/{result['pet']['id']}/history", "GET"),
            user=user,
        )["items"]
        dog_history = api.pet_history(
            int(dog["id"]),
            request(f"/api/pets/{dog['id']}/history", "GET"),
            user=user,
        )["items"]
        self.assertTrue(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in created_history))
        self.assertFalse(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in dog_history))

    def test_public_check_preview_save_requires_owned_choice_for_multiple_pets(self) -> None:
        user, _ = login("preview-save-multi@example.ru")
        self._activate_plus(user)
        other_user, _ = login("preview-save-multi-other@example.ru")
        first = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Луна"),
            request("/api/pets"),
            user=user,
        )["item"]
        second = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Сима"),
            request("/api/pets"),
            user=user,
        )["item"]
        foreign = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Чужая карточка"),
            request("/api/pets"),
            user=other_user,
        )["item"]

        with self.assertRaises(HTTPException) as required_exc:
            api.save_public_check_preview(
                self._public_check_save_payload(session_id="preview-save-multi-required"),
                request("/api/check/preview/save"),
                user,
            )
        self.assertEqual(required_exc.exception.status_code, 409)
        self.assertEqual(required_exc.exception.detail, "check_preview_pet_required")

        with self.assertRaises(HTTPException) as ownership_exc:
            api.save_public_check_preview(
                self._public_check_save_payload(
                    pet_id=int(foreign["id"]),
                    session_id="preview-save-multi-foreign",
                ),
                request("/api/check/preview/save"),
                user,
            )
        self.assertEqual(ownership_exc.exception.status_code, 404)
        self.assertEqual(ownership_exc.exception.detail, "check_preview_pet_not_found")

        result = api.save_public_check_preview(
            self._public_check_save_payload(
                pet_id=int(second["id"]),
                session_id="preview-save-multi-selected",
            ),
            request("/api/check/preview/save"),
            user,
        )
        self.assertEqual(int(result["pet"]["id"]), int(second["id"]))
        first_history = api.pet_history(
            int(first["id"]),
            request(f"/api/pets/{first['id']}/history", "GET"),
            user=user,
        )["items"]
        second_history = api.pet_history(
            int(second["id"]),
            request(f"/api/pets/{second['id']}/history", "GET"),
            user=user,
        )["items"]
        self.assertFalse(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in first_history))
        self.assertTrue(any(int(item.get("triage_id") or 0) == int(result["triage_id"]) for item in second_history))

    def test_email_code_is_single_use(self) -> None:
        email = "single-use@example.ru"
        start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
        self.assertTrue(start.debug_code)

        first_response = Response()
        session = api.auth_email_verify(
            api.EmailVerifyRequest(email=email, code=start.debug_code),
            request("/api/auth/email/verify"),
            first_response,
        )
        self.assertEqual(session.user["email"], email)

        with self.assertRaises(HTTPException) as reuse_exc:
            api.auth_email_verify(
                api.EmailVerifyRequest(email=email, code=start.debug_code),
                request("/api/auth/email/verify"),
                Response(),
            )
        self.assertEqual(reuse_exc.exception.status_code, 400)
        self.assertEqual(reuse_exc.exception.detail, "code_expired_or_not_found")

    def test_foreign_email_registration_is_allowed_while_domain_restriction_is_disabled(self) -> None:
        email = "new-foreign-registration@gmail.com"
        start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
        self.assertTrue(start.debug_code)
        response = Response()
        session = api.auth_email_verify(
            api.EmailVerifyRequest(email=email, code=start.debug_code),
            request("/api/auth/email/verify"),
            response,
        )
        self.assertEqual(session.user["email"], email)

    def test_email_registration_accepts_russian_domain_names(self) -> None:
        for email in ("new-russian-domain@example.ru", "new-russian-idn@почта.рф"):
            start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
            self.assertTrue(start.debug_code)

    def test_new_email_code_invalidates_previous_code(self) -> None:
        email = "new-code-invalidates-old@example.ru"
        first = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
        self.assertTrue(first.debug_code)
        with db.connect(api.settings.database_path) as conn:
            conn.execute(
                "UPDATE auth_challenges SET created_at = ? WHERE channel = 'email' AND target = ?",
                ((api.utc_now() - timedelta(seconds=api.EMAIL_CODE_COOLDOWN_SECONDS + 1)).isoformat(), email),
            )
            conn.commit()

        second = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
        self.assertTrue(second.debug_code)
        self.assertNotEqual(first.debug_code, second.debug_code)

        with self.assertRaises(HTTPException) as old_code_exc:
            api.auth_email_verify(
                api.EmailVerifyRequest(email=email, code=first.debug_code),
                request("/api/auth/email/verify"),
                Response(),
            )
        self.assertEqual(old_code_exc.exception.status_code, 400)
        self.assertEqual(old_code_exc.exception.detail, "invalid_code")

        second_response = Response()
        session = api.auth_email_verify(
            api.EmailVerifyRequest(email=email, code=second.debug_code),
            request("/api/auth/email/verify"),
            second_response,
        )
        self.assertEqual(session.user["email"], email)

    def test_email_code_attempt_limit_consumes_challenge(self) -> None:
        email = "attempt-limit@example.ru"
        start = api.auth_email_start(api.EmailStartRequest(email=email), request("/api/auth/email/start"))
        self.assertTrue(start.debug_code)

        for attempt in range(api.EMAIL_CODE_MAX_VERIFY_ATTEMPTS):
            with self.assertRaises(HTTPException) as wrong_code_exc:
                api.auth_email_verify(
                    api.EmailVerifyRequest(email=email, code="000000"),
                    request("/api/auth/email/verify"),
                    Response(),
                )
            if attempt + 1 < api.EMAIL_CODE_MAX_VERIFY_ATTEMPTS:
                self.assertEqual(wrong_code_exc.exception.detail, "invalid_code")
            else:
                self.assertEqual(wrong_code_exc.exception.detail, "code_attempts_exceeded")

        with self.assertRaises(HTTPException) as consumed_exc:
            api.auth_email_verify(
                api.EmailVerifyRequest(email=email, code=start.debug_code),
                request("/api/auth/email/verify"),
                Response(),
            )
        self.assertEqual(consumed_exc.exception.detail, "code_expired_or_not_found")

    def test_expired_email_code_is_rejected(self) -> None:
        email = "expired-code@example.ru"
        raw_code = "123456"
        db.create_auth_challenge(
            api.settings.database_path,
            channel="email",
            target=email,
            code_hash=api.hash_value(raw_code, api.settings.session_secret),
            expires_at=(api.utc_now() - timedelta(minutes=1)).isoformat(),
        )

        with self.assertRaises(HTTPException) as expired_exc:
            api.auth_email_verify(
                api.EmailVerifyRequest(email=email, code=raw_code),
                request("/api/auth/email/verify"),
                Response(),
            )
        self.assertEqual(expired_exc.exception.status_code, 400)
        self.assertEqual(expired_exc.exception.detail, "code_expired_or_not_found")

    def test_review_login_token_is_one_time_and_sets_cookie(self) -> None:
        raw_token = "review-token-for-one-time-test-123456"
        token_hash = api.hash_value(raw_token, api.settings.session_secret)
        expires_at = (api.utc_now() + timedelta(minutes=30)).isoformat()
        with db.connect(api.settings.database_path) as conn:
            conn.execute(
                """
                INSERT INTO review_login_tokens (token_hash, email, note, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    api.REVIEW_ACCOUNT_EMAIL,
                    "unit-test",
                    api.utc_now().isoformat(),
                    expires_at,
                ),
            )
            conn.commit()

        first = api.review_login(request("/review-login", "GET"), token=raw_token)
        self.assertEqual(first.status_code, 303)
        self.assertEqual(first.headers["location"], "/app")
        self.assertIn(api.USER_SESSION_COOKIE, first.headers.get("set-cookie", ""))
        self.assertEqual(db.get_active_review_login_token(api.settings.database_path, token_hash=token_hash), None)

        second = api.review_login(request("/review-login", "GET"), token=raw_token)
        self.assertEqual(second.status_code, 410)
        self.assertIn("Ссылка для аудита недействительна", second.body.decode("utf-8"))

    def test_legal_routes_are_standalone_documents(self) -> None:
        for page_key, page in api.LEGAL_PAGES.items():
            with self.subTest(page_key=page_key):
                response = api._legal_page_response(page_key)
                body = response.body.decode("utf-8")
                self.assertEqual(response.status_code, 200)
                self.assertIn(str(page["title"]), body)
                self.assertIn("<h1>", body)
                self.assertNotIn('id="authView"', body)
                self.assertNotIn('id="dashboardView"', body)
                self.assertNotIn("Что нужно сделать?", body)
                self.assertNotIn("legalModal", body)
                self.assertNotIn("Документ</h2>", body)

    def test_me_includes_sync_status_for_cabinet(self) -> None:
        _, token = login("sync-status@example.ru")
        profile = api.me(request("/api/me", "GET"), Response(), token=token)

        self.assertIn("telegram_profile_sync", profile)
        self.assertEqual(profile["telegram_profile_sync"]["synced"], False)
        self.assertEqual(profile["telegram_profile_sync"]["reason"], "test_disabled")
        self.assertIn("external_accounts", profile)
        self.assertIn("subscription", profile)

    def test_pet_and_reminder_ownership(self) -> None:
        user_a, _ = login("pet-owner-a@example.ru")
        user_b, _ = login("pet-owner-b@example.ru")

        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Лео", birth_year=2018),
            request("/api/pets"),
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
        user_a, _ = login("reminder-sync-owner-a@example.ru")
        user_b, _ = login("reminder-sync-owner-b@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Сима", birth_year=2019),
            request("/api/pets"),
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
        user_a, _ = login("pet-mutation-owner-a@example.ru")
        user_b, _ = login("pet-mutation-owner-b@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Рэй", birth_year=2020),
            request("/api/pets"),
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
        user_a, _ = login("pet-delete-owner-a@example.ru")
        user_b, _ = login("pet-delete-owner-b@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Тиша", birth_year=2017),
            request("/api/pets"),
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
        user, _ = login("sync-success-owner@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Луна", birth_year=2021),
            request("/api/pets"),
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
        user, _ = login("payer@example.ru")

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
        telegram_owner, _ = login("telegram-owner@example.ru")
        linked = db.link_external_account(
            api.settings.database_path,
            user_id=int(telegram_owner["id"]),
            provider="telegram",
            provider_user_id="tg-duplicate-owner",
            display_name="TG Owner",
        )
        self.assertIsNotNone(linked)

        email_user, _ = login("telegram-linking@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="собака", pet_name="Барс", birth_year=2020),
            request("/api/pets"),
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

    def test_telegram_login_challenge_is_one_time_after_complete(self) -> None:
        state, _ = api.create_telegram_login_challenge(api.settings)
        confirmed = api.confirm_telegram_login(
            api.settings,
            state=state,
            telegram_id="tg-one-time",
            display_name="TG One Time",
        )
        self.assertEqual(confirmed["handled"], True)

        completed = api.complete_telegram_login(api.settings, state)
        replay = api.complete_telegram_login(api.settings, state)
        reconfirm = api.confirm_telegram_login(
            api.settings,
            state=state,
            telegram_id="tg-one-time",
            display_name="TG One Time",
        )

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(replay["status"], "expired")
        self.assertEqual(reconfirm["handled"], False)
        self.assertEqual(reconfirm["reason"], "challenge_not_found")

    def test_duplicate_max_identity_merges_email_account_data(self) -> None:
        max_owner, _ = login("max-owner@example.ru")
        linked = db.link_external_account(
            api.settings.database_path,
            user_id=int(max_owner["id"]),
            provider="max",
            provider_user_id="max-duplicate-owner",
            display_name="MAX Owner",
        )
        self.assertIsNotNone(linked)

        email_user, _ = login("max-linking@example.ru")
        pet = api.create_pet(
            api.PetPayload(pet_type="кошка", pet_name="Мия", birth_year=2021),
            request("/api/pets"),
            user=email_user,
        )["item"]

        state, _ = api.create_max_login_challenge(api.settings, link_user_id=int(email_user["id"]))
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: None
        try:
            processed = api.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "payload": state,
                    "user": {"user_id": "max-duplicate-owner", "name": "MAX Owner"},
                },
            )
        finally:
            max_auth.send_max_text = original
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

    def test_max_login_challenge_confirms_and_completes_session(self) -> None:
        calls: list[dict] = []
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: calls.append(
            {"user_id": user_id, "text": text, "attachments": attachments}
        )
        try:
            state, _ = api.create_max_login_challenge(api.settings)
            processed = api.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "payload": state,
                    "user": {"user_id": "max-login-user", "name": "MAX Login"},
                },
            )
            completed = api.complete_max_login(api.settings, state)
        finally:
            max_auth.send_max_text = original

        self.assertEqual(processed["handled"], True)
        self.assertEqual(processed["action"], "auth_confirmed")
        self.assertEqual(completed["status"], "complete")
        self.assertTrue(completed["token"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["user_id"], "max-login-user")
        self.assertIn("Вход в TemichevVet подтвержден", calls[0]["text"])
        self.assertNotIn("Разобрать жалобу", calls[0]["text"])

    def test_max_login_challenge_is_one_time_after_complete(self) -> None:
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: None
        try:
            state, _ = api.create_max_login_challenge(api.settings)
            processed = api.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "payload": state,
                    "user": {"user_id": "max-one-time", "name": "MAX One Time"},
                },
            )
            completed = api.complete_max_login(api.settings, state)
            replay = api.complete_max_login(api.settings, state)
            replay_update = api.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "payload": state,
                    "user": {"user_id": "max-one-time", "name": "MAX One Time"},
                },
            )
        finally:
            max_auth.send_max_text = original

        self.assertEqual(processed["handled"], True)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(replay["status"], "expired")
        self.assertEqual(replay_update["handled"], False)
        self.assertEqual(replay_update["reason"], "challenge_not_found")

    def test_max_init_data_login_creates_session_from_verified_user_id(self) -> None:
        settings = replace(api.settings, max_bot_token="fake-max-token-for-init-data")
        init_data = make_max_init_data(settings.max_bot_token, user_id=246813)

        completed = max_auth.complete_max_init_login(settings, init_data)

        self.assertEqual(completed["status"], "complete")
        self.assertTrue(completed["token"])
        account = db.get_external_account(
            api.settings.database_path,
            user_id=int(completed["user"]["id"]),
            provider="max",
        )
        self.assertIsNotNone(account)
        self.assertEqual(account["provider_user_id"], "246813")
        self.assertEqual(account["display_name"], "Max User")

    def test_max_init_data_rejects_tampered_hash(self) -> None:
        settings = replace(api.settings, max_bot_token="fake-max-token-for-init-data")
        init_data = make_max_init_data(settings.max_bot_token, user_id=555555).replace("555555", "777777")

        completed = max_auth.complete_max_init_login(settings, init_data)

        self.assertEqual(completed["status"], "expired")
        self.assertEqual(completed["reason"], "hash_mismatch")

    def test_max_send_message_uses_user_id_query(self) -> None:
        calls: list[dict] = []
        original = max_auth._max_request
        max_auth._max_request = lambda settings, method, path, body=None, query=None: calls.append(
            {"method": method, "path": path, "body": body, "query": query}
        ) or {"ok": True}
        try:
            max_auth.send_max_text(api.settings, user_id="12345", text="Привет")
        finally:
            max_auth._max_request = original

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["path"], "/messages")
        self.assertEqual(calls[0]["query"], {"user_id": 12345})
        self.assertEqual(calls[0]["body"], {"text": "Привет"})

    def test_max_api_base_url_defaults_to_platform_api2_and_normalizes_legacy_url(self) -> None:
        original = os.environ.get("MAX_API_BASE_URL")
        try:
            os.environ.pop("MAX_API_BASE_URL", None)
            self.assertEqual(get_settings().max_api_base_url, "https://platform-api2.max.ru")
            os.environ["MAX_API_BASE_URL"] = "https://platform-api.max.ru"
            self.assertEqual(get_settings().max_api_base_url, "https://platform-api2.max.ru")
            os.environ["MAX_API_BASE_URL"] = "https://max-api.example.test"
            self.assertEqual(get_settings().max_api_base_url, "https://max-api.example.test")
        finally:
            if original is None:
                os.environ.pop("MAX_API_BASE_URL", None)
            else:
                os.environ["MAX_API_BASE_URL"] = original

    def test_max_request_uses_authorization_header_without_token_query(self) -> None:
        requests: list[urllib.request.Request] = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"ok": true}'

        original_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda request, timeout=0, context=None: requests.append(request) or FakeResponse()
        try:
            settings = replace(
                api.settings,
                max_api_base_url="https://platform-api2.max.ru",
                max_bot_token="test-max-token",
            )
            max_auth._max_request(settings, "POST", "/messages", {"text": "ok"}, query={"user_id": 12345})
        finally:
            urllib.request.urlopen = original_urlopen

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].full_url, "https://platform-api2.max.ru/messages?user_id=12345")
        self.assertEqual(requests[0].headers.get("Authorization"), "test-max-token")
        self.assertNotIn("access_token", requests[0].full_url)

    def test_plain_max_start_sends_menu_without_completing_pending_login(self) -> None:
        calls: list[dict] = []
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: calls.append(
            {"user_id": user_id, "text": text, "attachments": attachments}
        )
        try:
            pending_state, _ = api.create_max_login_challenge(api.settings)
            result = max_auth.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "user": {"user_id": "98765", "name": "MAX User"},
                },
            )
            pending = api.complete_max_login(api.settings, pending_state)
        finally:
            max_auth.send_max_text = original

        self.assertEqual(result["handled"], True)
        self.assertEqual(result["action"], "welcome")
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(calls[0]["user_id"], "98765")
        self.assertIn("TemichevVet", calls[0]["text"])
        self.assertEqual(calls[0]["attachments"][0]["type"], "inline_keyboard")

    def test_max_bot_started_with_valid_payload_does_not_send_regular_menu(self) -> None:
        calls: list[dict] = []
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: calls.append(
            {"user_id": user_id, "text": text, "attachments": attachments}
        )
        try:
            state, _ = api.create_max_login_challenge(api.settings)
            result = max_auth.process_max_update(
                api.settings,
                {
                    "update_type": "bot_started",
                    "payload": state,
                    "user": {"user_id": "max-valid-state", "name": "MAX User"},
                },
            )
            completed = api.complete_max_login(api.settings, state)
        finally:
            max_auth.send_max_text = original

        self.assertEqual(result["handled"], True)
        self.assertEqual(result["action"], "auth_confirmed")
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(calls), 1)
        self.assertIn("Вход в TemichevVet подтвержден", calls[0]["text"])
        self.assertNotIn("Разобрать жалобу", calls[0]["text"])

    def test_max_message_created_sends_welcome(self) -> None:
        calls: list[dict] = []
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: calls.append(
            {"user_id": user_id, "text": text, "attachments": attachments}
        )
        try:
            result = max_auth.process_max_update(
                api.settings,
                {
                    "update_type": "message_created",
                    "message": {
                        "sender": {"user_id": "24680", "name": "MAX User"},
                        "body": {"text": "старт"},
                    },
                },
            )
        finally:
            max_auth.send_max_text = original

        self.assertEqual(result["handled"], True)
        self.assertEqual(result["action"], "message_menu")
        self.assertEqual(calls[0]["user_id"], "24680")
        self.assertIn("Открыть кабинет", calls[0]["attachments"][0]["payload"]["buttons"][0][0]["text"])

    def test_max_menu_uses_mini_app_deep_links_when_app_base_url_is_local(self) -> None:
        settings = replace(
            api.settings,
            app_base_url="http://127.0.0.1:8080",
            max_bot_username="id230210303969_bot",
        )
        buttons = max_auth._open_app_keyboard(settings)[0]["payload"]["buttons"]

        self.assertEqual(buttons[0][0]["url"], "https://max.ru/id230210303969_bot?startapp=home")
        self.assertEqual(buttons[1][0]["url"], "https://max.ru/id230210303969_bot?startapp=triage")
        self.assertEqual(buttons[1][1]["url"], "https://max.ru/id230210303969_bot?startapp=pets")
        self.assertEqual(buttons[2][0]["url"], "https://max.ru/id230210303969_bot?startapp=reminders")
        self.assertEqual(buttons[2][1]["url"], "https://max.ru/id230210303969_bot?startapp=subscription")
        self.assertEqual(buttons[3][0]["url"], "https://max.ru/id230210303969_bot?startapp=more")

    def test_max_message_callback_sends_menu(self) -> None:
        calls: list[dict] = []
        original = max_auth.send_max_text
        max_auth.send_max_text = lambda settings, user_id, text, attachments=None: calls.append(
            {"user_id": user_id, "text": text, "attachments": attachments}
        )
        try:
            result = max_auth.process_max_update(
                api.settings,
                {
                    "update_type": "message_callback",
                    "user": {"user_id": "13579", "name": "MAX User"},
                    "callback": {"payload": "menu"},
                },
            )
        finally:
            max_auth.send_max_text = original

        self.assertEqual(result["handled"], True)
        self.assertEqual(result["action"], "callback_menu")
        self.assertEqual(calls[0]["user_id"], "13579")
        self.assertIn("Открыть кабинет", calls[0]["attachments"][0]["payload"]["buttons"][0][0]["text"])

    def test_max_webhook_setup_defaults_to_production_url_when_app_url_is_local(self) -> None:
        resolved = setup_max_webhook._resolve_webhook_url("http://127.0.0.1:8080", "")
        self.assertEqual(resolved, "https://temichevvet.ru/api/webhooks/max")

    def test_max_webhook_setup_rejects_non_https_url(self) -> None:
        with self.assertRaises(SystemExit):
            setup_max_webhook._resolve_webhook_url("", "http://temichevvet.ru/api/webhooks/max")

    def test_max_webhook_setup_redacts_secrets_from_output(self) -> None:
        redacted = setup_max_webhook._redact_sensitive(
            {
                "id": "sub-1",
                "secret": "live-secret",
                "nested": {"access_token": "live-token", "url": "https://temichevvet.ru"},
            }
        )
        self.assertEqual(redacted["secret"], "***")
        self.assertEqual(redacted["nested"]["access_token"], "***")
        self.assertEqual(redacted["nested"]["url"], "https://temichevvet.ru")

    def test_payment_status_owner_only(self) -> None:
        user_a, _ = login("payment-owner-a@example.ru")
        user_b, _ = login("payment-owner-b@example.ru")
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
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="auth.provider_start_failed",
            status="warning",
            actor="test",
            provider="telegram",
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="auth.max_init_failed",
            status="warning",
            actor="test",
            provider="max",
        )

        status = api.monitoring_status()
        self.assertEqual(status["ok"], True)
        self.assertIn("events_1h", status)
        self.assertIn("status_help", status)
        status_help = status["status_help"]
        self.assertIn("SMTP_HOST", status_help["email_configured"])
        self.assertIn("Telegram-вход", status_help["telegram_login_configured"])
        self.assertIn("MAX-вход", status_help["max_login_configured"])
        self.assertIn("YOOKASSA_SHOP_ID", status_help["yookassa_configured"])
        self.assertIn("OPENAI_API_KEY", status_help["llm_configured"])
        self.assertIn("CORE_API_SECRET", status_help["core_api_configured"])
        integration = {item["key"]: item for item in status["integration_events_24h"]}
        self.assertEqual(integration["payments"]["warnings"], 1)
        self.assertEqual(integration["llm"]["errors"], 1)
        self.assertEqual(integration["sync"]["errors"], 1)
        self.assertEqual(integration["telegram_login"]["warnings"], 1)
        self.assertEqual(integration["max_login"]["warnings"], 1)
        self.assertEqual(integration["api"]["status"], "ok")
        self.assertIn("YooKassa", integration["payments"]["help"])
        self.assertIn("OpenAI", integration["llm"]["help"])
        self.assertIn("Telegram-ботом", integration["sync"]["help"])
        self.assertIn("Telegram", integration["telegram_login"]["help"])
        self.assertIn("MAX", integration["max_login"]["help"])

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

    def test_admin_audit_hides_empty_push_followup_checks(self) -> None:
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="admin.dashboard_view",
            status="ok",
            actor="admin",
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="push.followups_send",
            status="ok",
            actor="system",
            metadata={"followups": 0, "processed_followups": 0, "sent": 0, "failed": 0, "skipped": 0},
        )
        db.create_security_audit_event(
            api.settings.database_path,
            event_type="push.followups_send",
            status="ok",
            actor="system",
            metadata={"followups": 1, "processed_followups": 1, "sent": 1, "failed": 0, "skipped": 0},
        )

        audit = api.admin_security_audit(limit=10)
        visible_push = [item for item in audit["items"] if item["event_type"] == "push.followups_send"]
        self.assertEqual(len(visible_push), 1)
        self.assertEqual(visible_push[0]["metadata"]["sent"], 1)

        explicit = db.list_security_audit_events(
            api.settings.database_path,
            event_type="push.followups_send",
            hide_noisy_system_events=True,
        )
        self.assertEqual(len(explicit), 2)

        dashboard = api._admin_dashboard_payload()
        self.assertFalse(any(item["event_type"] == "admin.dashboard_view" for item in dashboard["recent_audit"]))
        self.assertTrue(any(item["event_type"] == "admin.dashboard_view" for item in dashboard["recent_audit_raw"]))

        with db.connect(api.settings.database_path) as conn:
            conn.execute(
                "DELETE FROM security_audit_events WHERE event_type IN (?, ?)",
                ("push.followups_send", "admin.dashboard_view"),
            )

    def test_security_audit_metadata_filters_medical_text(self) -> None:
        complaint = "кошка вялая второй день, была рвота желтым"
        llm_answer = "подробный ответ модели с медицинскими рекомендациями"
        event = db.create_security_audit_event(
            api.settings.database_path,
            event_type="llm.triage_failed",
            status="error",
            actor="test",
            metadata={
                "error": "RuntimeError",
                "plan": "free",
                "complaint_text": complaint,
                "response_text": llm_answer,
                "symptoms": "рвота, кровь, отказ от еды",
                "message": "пользовательский текст",
                "safe_long": "x" * 400,
            },
        )

        metadata = event["metadata"]
        serialized = json.dumps(metadata, ensure_ascii=False)
        self.assertEqual(metadata["error"], "RuntimeError")
        self.assertEqual(metadata["plan"], "free")
        self.assertEqual(len(metadata["safe_long"]), 240)
        self.assertNotIn("complaint_text", metadata)
        self.assertNotIn("response_text", metadata)
        self.assertNotIn("symptoms", metadata)
        self.assertNotIn("message", metadata)
        self.assertNotIn(complaint, serialized)
        self.assertNotIn(llm_answer, serialized)

    def test_push_config_and_subscribe_guard(self) -> None:
        user, _ = login("push-owner@example.ru")
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

    def test_push_broadcast_endpoint_requires_monitoring_secret(self) -> None:
        self._clear_broadcast_push_test_data()
        route = next(route for route in api.app.routes if getattr(route, "path", "") == "/api/internal/push/broadcast")
        dependency_names = {getattr(dependency.call, "__name__", "") for dependency in route.dependant.dependencies}
        self.assertIn("_require_monitoring_api_secret", dependency_names)

        with self.assertRaises(HTTPException) as missing_exc:
            api._require_monitoring_api_secret()
        self.assertEqual(missing_exc.exception.status_code, 403)
        self.assertEqual(missing_exc.exception.detail, "invalid_monitoring_api_secret")
        self.assertIsNone(api._require_monitoring_api_secret("monitoring-test-secret"))

    def test_push_broadcast_dry_run_counts_active_subscriptions_without_sending(self) -> None:
        self._clear_broadcast_push_test_data()
        active_user, _ = login("push-broadcast-dry-active@example.ru")
        revoked_user, _ = login("push-broadcast-dry-revoked@example.ru")
        self._add_broadcast_push_subscription(active_user, "dry-active")
        self._add_broadcast_push_subscription(revoked_user, "dry-revoked", revoked=True)

        original_send = api.send_web_push
        api.send_web_push = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry-run sent push"))
        try:
            result = api.send_push_broadcast(
                api.PushBroadcastPayload(
                    title="TemichevVet: работа восстановлена",
                    body="Сервис доступен, работа восстановлена.",
                    url="/app",
                    dry_run=True,
                    limit=10,
                ),
                request("/api/internal/push/broadcast"),
                _=None,
            )
        finally:
            api.send_web_push = original_send

        self.assertEqual(result["dry_run"], True)
        self.assertEqual(result["subscriptions"], 1)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)
        events = db.list_security_audit_events(api.settings.database_path, event_type="push.broadcast_send")
        self.assertEqual(events, [])

    def test_push_broadcast_real_send_requires_confirm(self) -> None:
        self._clear_broadcast_push_test_data()
        with self.assertRaises(HTTPException) as exc:
            api.send_push_broadcast(
                api.PushBroadcastPayload(
                    title="TemichevVet: работа восстановлена",
                    body="Сервис доступен, работа восстановлена.",
                    url="/app",
                    dry_run=False,
                ),
                request("/api/internal/push/broadcast"),
                _=None,
            )
        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "push_broadcast_confirmation_required")

    def test_push_broadcast_real_send_requires_vapid(self) -> None:
        self._clear_broadcast_push_test_data()
        old_settings = api.settings
        api.settings = replace(api.settings, vapid_public_key="", vapid_private_key="", vapid_subject="")
        try:
            with self.assertRaises(HTTPException) as exc:
                api.send_push_broadcast(
                    api.PushBroadcastPayload(
                        title="TemichevVet: работа восстановлена",
                        body="Сервис доступен, работа восстановлена.",
                        url="/app",
                        dry_run=False,
                        confirm="SEND_PUSH_BROADCAST",
                    ),
                    request("/api/internal/push/broadcast"),
                    _=None,
                )
        finally:
            api.settings = old_settings
        self.assertEqual(exc.exception.status_code, 503)
        self.assertEqual(exc.exception.detail, "push_not_configured")

    def test_push_broadcast_real_send_uses_active_pwa_subscriptions_and_safe_audit(self) -> None:
        self._clear_broadcast_push_test_data()
        user_a, _ = login("push-broadcast-send-a@example.ru")
        user_b, _ = login("push-broadcast-send-b@example.ru")
        user_revoked, _ = login("push-broadcast-send-revoked@example.ru")
        self._add_broadcast_push_subscription(user_a, "send-ok")
        self._add_broadcast_push_subscription(user_b, "send-fail")
        self._add_broadcast_push_subscription(user_revoked, "send-revoked", revoked=True)

        calls: list[dict] = []
        old_settings = api.settings
        original_send = api.send_web_push
        api.settings = replace(
            api.settings,
            vapid_public_key="test-public-key",
            vapid_private_key="test-private-key",
            vapid_subject="mailto:test@example.ru",
        )

        def fake_send(settings, *, subscription: dict, payload: dict) -> dict:
            calls.append({"subscription": subscription, "payload": payload})
            if str(subscription["endpoint"]).endswith("send-fail"):
                return {"sent": False, "reason": "provider_down"}
            return {"sent": True, "reason": "ok"}

        api.send_web_push = fake_send
        try:
            result = api.send_push_broadcast(
                api.PushBroadcastPayload(
                    title="TemichevVet: работа восстановлена",
                    body="Приносим извинения: был кратковременный сбой. Сейчас сервис доступен.",
                    url="/app",
                    dry_run=False,
                    confirm="SEND_PUSH_BROADCAST",
                    limit=10,
                ),
                request("/api/internal/push/broadcast"),
                _=None,
            )
        finally:
            api.send_web_push = original_send
            api.settings = old_settings

        self.assertEqual(len(calls), 2)
        self.assertEqual(result["subscriptions"], 2)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failure_reasons"], {"provider_down": 1})
        self.assertTrue(all(call["payload"]["url"] == "/app" for call in calls))

        events = db.list_security_audit_events(api.settings.database_path, event_type="push.broadcast_send")
        self.assertEqual(len(events), 1)
        metadata = events[0]["metadata"]
        serialized = json.dumps(metadata, ensure_ascii=False)
        self.assertEqual(metadata["message_type"], "incident_recovered")
        self.assertEqual(metadata["subscriptions"], 2)
        self.assertEqual(metadata["sent"], 1)
        self.assertEqual(metadata["failed"], 1)
        self.assertNotIn("работа восстановлена", serialized)
        self.assertNotIn("кратковременный сбой", serialized)

    def test_due_followup_push_sender_skips_without_subscription(self) -> None:
        user, _ = login("push-followup-owner@example.ru")
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
        events = db.list_security_audit_events(api.settings.database_path, event_type="push.followups_send")
        self.assertEqual(events, [])

    def test_due_followup_push_sender_does_not_audit_empty_queue(self) -> None:
        result = api.send_due_followup_pushes(
            request("/api/internal/push/followups/send"),
            limit=10,
            _=None,
        )
        self.assertEqual(result["followups"], 0)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 0)
        events = db.list_security_audit_events(api.settings.database_path, event_type="push.followups_send")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
