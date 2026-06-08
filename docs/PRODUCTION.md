# Production

## Public URLs

- Main PWA: `https://temichevvet.ru`
- WWW alias: `https://www.temichevvet.ru`
- Healthcheck: `https://temichevvet.ru/api/health`
- MAX webhook: `https://temichevvet.ru/api/webhooks/max`

## VPS Layout

- App path: `/opt/temichevvet/pwa`
- App database: `/opt/temichevvet/data/pwa.db`
- App env file: `/opt/temichevvet/pwa/.env`
- Systemd service: `temichevvet_pwa.service`
- Reverse proxy: `nginx`
- Internal app bind: `127.0.0.1:8081`

The Telegram bot is separate and stays on `temichevvet_bot.service`.

## Runtime Checks

```bash
systemctl is-active temichevvet_bot.service
systemctl is-active temichevvet_pwa.service
systemctl is-active nginx
curl -sS http://127.0.0.1:8081/api/health
curl -sS https://temichevvet.ru/api/health
```

Closed monitoring:

```bash
curl -sS https://temichevvet.ru/api/monitoring/status \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET"
```

Closed audit:

```bash
curl -sS "https://temichevvet.ru/api/admin/security-audit?limit=50" \
  -H "X-Temichevvet-Admin-Secret: $ADMIN_API_SECRET"
```

## MAX Webhook

MAX Bot API subscription points to:

```text
https://temichevvet.ru/api/webhooks/max
```

The webhook accepts `bot_started` updates and checks `MAX_WEBHOOK_SECRET` through the `X-Max-Bot-Api-Secret` header.

## SSL

Certificates are issued by Let's Encrypt through certbot and nginx.

```bash
certbot certificates
systemctl list-timers | grep certbot
```

The current certificate is stored under:

```text
/etc/letsencrypt/live/temichevvet.ru/
```
