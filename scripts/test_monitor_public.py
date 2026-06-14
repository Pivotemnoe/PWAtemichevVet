from __future__ import annotations

import unittest

from monitor_public import evaluate_health, evaluate_monitoring


class MonitorPublicTests(unittest.TestCase):
    def test_evaluate_health_ok(self) -> None:
        result = evaluate_health({"ok": True, "database": "ok"})
        self.assertEqual(result.critical, [])
        self.assertEqual(result.exit_code(), 0)

    def test_evaluate_health_bad_database_is_critical(self) -> None:
        result = evaluate_health({"ok": False, "database": "error"})
        self.assertEqual(result.exit_code(), 2)
        self.assertIn("healthcheck", result.critical[0])

    def test_monitoring_detects_hourly_errors(self) -> None:
        result = evaluate_monitoring(
            {
                "ok": True,
                "checks": {
                    "database": {"ok": True},
                    "email_configured": True,
                    "telegram_login_configured": True,
                    "max_login_configured": True,
                    "yookassa_configured": True,
                    "llm_configured": True,
                    "core_api_configured": True,
                },
                "events_1h": {
                    "server_5xx": 1,
                    "payment_errors": 0,
                    "llm_errors": 2,
                    "sync_errors": 0,
                },
                "integration_events_24h": [],
            }
        )
        self.assertEqual(result.exit_code(), 2)
        self.assertEqual(len(result.critical), 2)

    def test_monitoring_config_warnings_can_be_strict(self) -> None:
        payload = {
            "ok": True,
            "checks": {
                "database": {"ok": True},
                "email_configured": False,
                "telegram_login_configured": True,
                "max_login_configured": True,
                "yookassa_configured": True,
                "llm_configured": False,
                "core_api_configured": True,
            },
            "events_1h": {},
            "integration_events_24h": [],
        }
        soft = evaluate_monitoring(payload)
        self.assertEqual(soft.critical, [])
        self.assertEqual(len(soft.warnings), 2)

        strict = evaluate_monitoring(payload, strict_config=True)
        self.assertEqual(strict.exit_code(), 2)
        self.assertEqual(len(strict.critical), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
