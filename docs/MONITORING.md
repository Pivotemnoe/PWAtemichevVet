# Monitoring

Дата: 2026-06-08

## Public Uptime

Внешний мониторинг должен проверять:

```text
GET https://temichevvet.ru/api/health
```

Ожидаемый ответ:

```json
{"ok": true, "service": "temichevvet-pwa", "database": "ok"}
```

Если база недоступна, endpoint возвращает `503` и не раскрывает внутренние детали ошибки.

## Closed Status Endpoint

Подробный статус закрыт секретом:

```bash
curl -sS https://temichevvet.ru/api/monitoring/status \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET"
```

Endpoint показывает:

- доступность SQLite;
- настроены ли email, Telegram/MAX login, YooKassa, LLM и Core API;
- количество 5xx, ошибок YooKassa, LLM и sync за 1 час и 24 часа;
- `integration_events_24h`: понятные группы warning/error по API, email, Telegram/MAX входу, YooKassa, LLM, Telegram/Core sync и PWA push.
- PWA push-настройки проверяются отдельно через `GET /api/push/config` и отправку закрытым endpoint ниже.

Если `MONITORING_API_SECRET` не задан, endpoint возвращает `503 monitoring_api_not_configured`.

## Admin Security Audit

Закрытый журнал:

```bash
curl -sS "https://temichevvet.ru/api/admin/security-audit?limit=100" \
  -H "X-Temichevvet-Admin-Secret: $ADMIN_API_SECRET"
```

Можно фильтровать:

```text
event_type=payment.created
status=error
user_id=123
```

В журнале хранятся только служебные события: входы, привязки, платежи, смены подписки, ошибки LLM/YooKassa/sync и попытки доступа к чужим объектам. Тексты жалоб, ответы LLM и заметки питомца в audit не пишутся.

## Recommended Alerts

- `/api/health` не отвечает или отдаёт `503` дольше 2 минут.
- В `/api/monitoring/status` `events_1h.server_5xx > 0`.
- `events_1h.payment_errors > 0` после запуска рекламы.
- `events_1h.llm_errors > 0`, если пользователи жалуются на разборы.
- `events_1h.sync_errors > 0`, если Telegram/PWA показывают разные данные.
- В `integration_events_24h` у любой группы `status = error` после запуска рекламы.
- `POST /api/internal/push/followups/send` возвращает `sent=0` при наличии подписанных пользователей и ожидаемых follow-up.

## Built-In Monitor Script

В репозитории есть проверочный скрипт без внешних зависимостей:

```bash
MONITORING_API_SECRET=... .venv/bin/python scripts/monitor_public.py \
  --base-url https://temichevvet.ru \
  --strict-config
```

Что проверяет:

- публичный `GET /api/health`;
- закрытый `GET /api/monitoring/status`, если задан `MONITORING_API_SECRET`;
- ошибки за 1 час: `server_5xx`, `payment_errors`, `llm_errors`, `sync_errors`;
- группы интеграций за 24 часа: API, email, Telegram/MAX, YooKassa, LLM, Telegram/Core sync, PWA push;
- базовую настройку ключевых интеграций.

Exit codes:

- `0` — критических ошибок нет;
- `1` — есть предупреждения и запущено с `--fail-on-warning`;
- `2` — есть критическая ошибка, скрипт должен поднять alert.

Если секрет не задан, скрипт всё равно проверит публичный healthcheck и напишет предупреждение, что закрытый статус не проверен.

Пример cron на внешнем сервере или отдельной машине:

```cron
*/2 * * * * cd /opt/temichevvet/pwa && MONITORING_API_SECRET=... .venv/bin/python scripts/monitor_public.py --strict-config >/tmp/temichevvet-monitor.log 2>&1
```

Production timer на VPS:

```bash
systemctl list-timers --all | grep temichevvet_pwa_monitor
systemctl status temichevvet_pwa_monitor.timer
journalctl -u temichevvet_pwa_monitor.service -n 50 --no-pager
```

Unit-файлы лежат в `infra/systemd/temichevvet_pwa_monitor.service` и `infra/systemd/temichevvet_pwa_monitor.timer`.

## PWA Push Follow-Ups

Проверить публичную конфигурацию:

```bash
curl -sS https://temichevvet.ru/api/push/config
```

Отправить накопленные follow-up уведомления:

```bash
curl -sS -X POST "https://temichevvet.ru/api/internal/push/followups/send?limit=50" \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET"
```

Endpoint не раскрывает медицинские тексты в audit-журнал. В журнал попадает только служебный итог: сколько follow-up найдено, отправлено и пропущено.

Production timer:

```bash
systemctl list-timers --all | grep temichevvet_pwa_followups
systemctl status temichevvet_pwa_followups.timer
journalctl -u temichevvet_pwa_followups.service -n 50 --no-pager
```

## Server Logs

На сервере:

```bash
systemctl status temichevvet_pwa.service
journalctl -u temichevvet_pwa.service -n 200 --no-pager
journalctl -u nginx -n 200 --no-pager
```

Для проверки HTTP:

```bash
curl -sS http://127.0.0.1:8081/api/health
curl -sSI https://temichevvet.ru/
```
