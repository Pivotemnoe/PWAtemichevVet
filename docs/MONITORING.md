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
