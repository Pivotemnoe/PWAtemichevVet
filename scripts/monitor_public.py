from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


DEFAULT_BASE_URL = "https://temichevvet.ru"
ERROR_EVENT_KEYS = ("server_5xx", "payment_errors", "llm_errors", "sync_errors")
IMPORTANT_CONFIG_CHECKS = {
    "email_configured": "Email-вход не настроен",
    "telegram_login_configured": "Telegram-вход не настроен",
    "max_login_configured": "MAX-вход не настроен",
    "yookassa_configured": "YooKassa не настроена",
    "llm_configured": "LLM-разбор не настроен",
    "core_api_configured": "Core API синхронизация не настроена",
}


@dataclass
class MonitorResult:
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    critical: list[str] = field(default_factory=list)

    def exit_code(self, *, fail_on_warning: bool = False) -> int:
        if self.critical:
            return 2
        if fail_on_warning and self.warnings:
            return 1
        return 0

    def merge(self, other: "MonitorResult") -> None:
        self.ok.extend(other.ok)
        self.warnings.extend(other.warnings)
        self.critical.extend(other.critical)


def normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def endpoint(base_url: str, path: str) -> str:
    return f"{normalize_base_url(base_url)}{path}"


def fetch_json(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TemichevVet-Monitor/1.0",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024)
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network_error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("timeout") from exc

    if status >= 400:
        raise RuntimeError(f"HTTP {status}")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid_json") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("json_root_is_not_object")
    return parsed


def evaluate_health(data: dict[str, Any]) -> MonitorResult:
    result = MonitorResult()
    if data.get("ok") is True and data.get("database") == "ok":
        result.ok.append("Публичный healthcheck работает, база отвечает.")
        return result
    result.critical.append(
        "Публичный healthcheck вернул проблему: "
        f"ok={data.get('ok')!r}, database={data.get('database')!r}."
    )
    return result


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_monitoring(data: dict[str, Any], *, strict_config: bool = False) -> MonitorResult:
    result = MonitorResult()
    if data.get("ok") is not True:
        result.critical.append("Закрытый мониторинг сообщает, что сервис не в норме.")

    checks = data.get("checks") or {}
    database = checks.get("database") or {}
    if isinstance(database, dict) and database.get("ok") is False:
        result.critical.append("База данных PWA недоступна по закрытому статусу.")

    for key, label in IMPORTANT_CONFIG_CHECKS.items():
        if checks.get(key) is False:
            if strict_config:
                result.critical.append(label)
            else:
                result.warnings.append(label)

    events_1h = data.get("events_1h") or {}
    for key in ERROR_EVENT_KEYS:
        count = _as_int(events_1h.get(key))
        if count > 0:
            result.critical.append(f"За 1 час есть ошибки {key}: {count}.")

    integration_groups = data.get("integration_events_24h") or []
    if isinstance(integration_groups, list):
        for group in integration_groups:
            if not isinstance(group, dict):
                continue
            label = group.get("label") or group.get("key") or "интеграция"
            errors = _as_int(group.get("errors"))
            warnings = _as_int(group.get("warnings"))
            if errors > 0:
                result.critical.append(f"Интеграция '{label}' за 24 часа: ошибок {errors}.")
            elif warnings > 0:
                result.warnings.append(f"Интеграция '{label}' за 24 часа: предупреждений {warnings}.")

    if not result.critical:
        result.ok.append("Закрытый мониторинг не показывает критических ошибок.")
    return result


def format_report(result: MonitorResult) -> str:
    lines: list[str] = []
    for item in result.ok:
        lines.append(f"OK: {item}")
    for item in result.warnings:
        lines.append(f"WARNING: {item}")
    for item in result.critical:
        lines.append(f"CRITICAL: {item}")
    return "\n".join(lines) if lines else "OK: проверка выполнена."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Проверить публичный uptime и закрытый статус TemichevVet PWA.")
    parser.add_argument("--base-url", default=os.getenv("TEMICHEVVET_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TEMICHEVVET_MONITOR_TIMEOUT", "10")))
    parser.add_argument("--secret", default=os.getenv("MONITORING_API_SECRET", ""))
    parser.add_argument("--strict-config", action="store_true", help="считать ненастроенные интеграции критической ошибкой")
    parser.add_argument("--fail-on-warning", action="store_true", help="возвращать код 1 даже при предупреждениях")
    parser.add_argument("--json", action="store_true", help="вывести машинно-читаемый JSON")
    return parser


def run(args: argparse.Namespace) -> MonitorResult:
    result = MonitorResult()
    base_url = normalize_base_url(args.base_url)

    try:
        health = fetch_json(endpoint(base_url, "/api/health"), timeout=args.timeout)
        result.merge(evaluate_health(health))
    except RuntimeError as exc:
        result.critical.append(f"Публичный healthcheck недоступен: {exc}.")

    if args.secret:
        try:
            monitoring = fetch_json(
                endpoint(base_url, "/api/monitoring/status"),
                timeout=args.timeout,
                headers={"X-Temichevvet-Monitoring-Secret": args.secret},
            )
            result.merge(evaluate_monitoring(monitoring, strict_config=args.strict_config))
        except RuntimeError as exc:
            result.critical.append(f"Закрытый monitoring status недоступен: {exc}.")
    else:
        result.warnings.append("Закрытый monitoring status не проверен: MONITORING_API_SECRET не задан.")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run(args)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not result.critical,
                    "ok_messages": result.ok,
                    "warnings": result.warnings,
                    "critical": result.critical,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_report(result))
    return result.exit_code(fail_on_warning=args.fail_on_warning)


if __name__ == "__main__":
    raise SystemExit(main())
