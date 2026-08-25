# TemichevVet PWA

Separate PWA project for TemichevVet.

This repository is intentionally separate from the Telegram bot repository. The first stage prepares a web app with independent auth and a clean path for Telegram/MAX account linking.

## What Is Included

- FastAPI backend.
- Static installable PWA frontend.
- Email one-time-code login.
- Telegram deep-link login bridge to the working bot.
- MAX deep-link login with webhook and local polling support.
- Optional PWA push notifications for follow-up reminders after health checks.
- Service-first onboarding that keeps the pet draft through login and creates the card idempotently.
- Personal cabinet centered on the selected pet: history, observations, weight, reminders, food checks and saved health changes.
- Owner-only doctor summary for 30/90 days or all history, with Plus print/PDF export.
- Free/Plus entity limits that keep over-limit historical data readable after Plus expires.
- Activation analytics for first permanent record, service activation, D1/D7 returns, summary use and Plus payment.
- SQLite schema for web users, auth challenges, sessions, external account links, pets, reminders, history, and observations.
- Production deployment notes for VPS + nginx.

## Local Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
make check
DEV_AUTH_CODE_LOG=1 .venv/bin/python -m app.main
```

Open:

```text
http://127.0.0.1:8080
```

In development mode the email auth code is returned in the API response so the flow can be tested without SMTP.

## Service Activation And Summary

Product activation is recorded once when a signed-in user has a pet and saves the first permanent record: weight, observation, reminder, saved health check or saved food answer.

Doctor summary endpoints:

```text
GET  /api/pets/{pet_id}/summary?period=30|90|all
POST /api/pets/{pet_id}/summary/export?period=30|90|all
```

Free can view 30 days without export. Plus can select 30/90 days or all history and open the browser print/PDF flow. The summary aggregates existing records and does not generate a new diagnosis.

The prepared, not-uploaded Direct package is in `marketing/service-first-direct-draft.json`. Applying it to campaign `713573600` or creating Metrika goals remains a separate live action and requires explicit approval.

## Telegram Login Bridge

Set these values in PWA `.env`:

```text
TELEGRAM_BOT_USERNAME=TemichevVet23_bot
TELEGRAM_AUTH_SECRET=...
```

Set matching values in the Telegram bot `.env`:

```text
PWA_BASE_URL=https://temichevvet.ru
PWA_TELEGRAM_AUTH_SECRET=...
```

The PWA creates a short-lived login state, opens the Telegram bot with `/start web_auth_<state>`, and the Telegram bot confirms that state through a server-to-server request. This links the PWA account to the Telegram user ID without exposing the shared secret to the browser.

This bridge creates a shared identity link. A logged-in PWA user can also connect Telegram to the current account in `Способы входа`, so pet/payment/subscription synchronization has a single owner.

The PWA can reuse Telegram subscription entitlement through the linked Telegram ID. If a paid PWA subscription is later issued to a user with linked Telegram, the PWA mirrors that entitlement to the Telegram `bot.db`.

When Telegram is connected, the server synchronizes core profile data between Telegram and PWA: pet cards, reminders, observations, weight records, pet history and triage logs. This sync is server-side only; the browser never receives access to `bot.db` or synchronization secrets. Some destructive or legacy Telegram-side operations are intentionally best-effort and must be checked through admin sync logs.

## Email Login

Email login uses a one-time code for 10 minutes. In production it requires SMTP:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=1
```

If SMTP is not configured in production, the API returns `email_not_configured` instead of pretending that an email was sent.

## MAX Login

Set these values in `.env`:

```text
MAX_BOT_USERNAME=id230210303969_bot
MAX_BOT_TOKEN=...
MAX_API_BASE_URL=https://platform-api2.max.ru
# Set only if the server OS trust store does not already trust the Ministry of Digital Development CA.
MAX_API_CA_BUNDLE=/path/to/ministry-digital-ca-bundle.pem
MAX_WEBHOOK_SECRET=long-random-secret-with-letters-digits-dashes-or-underscores
```

MAX login confirms identity and opens or connects the same PWA account. The MAX bot is also a lightweight entry point: if `bot_started` arrives without a valid PWA login state, or MAX sends `message_created`/`message_callback`, the bot sends a basic menu with links to the PWA cabinet, triage, pets, reminders, subscription, and help. Telegram remains a separate channel and is not reimplemented in MAX chat.

MAX requires API calls to use `https://platform-api2.max.ru` by July 19, 2026 and authenticates bot API requests with `Authorization: <token>`, not a token query parameter. The app normalizes the legacy `https://platform-api.max.ru` value to the new API host at startup. Python uses the system trust store for MAX API TLS; install the Ministry of Digital Development CA into the OS trust store or set `MAX_API_CA_BUNDLE` to a PEM bundle that includes it.

When the PWA is opened as a MAX mini app, the frontend sends `window.WebApp.initData` to `POST /api/auth/max/init`. The backend validates the MAX signature with `MAX_BOT_TOKEN`, checks `auth_date`, reads the verified MAX `user.id`, and creates the same PWA session used by email, Telegram, and challenge-based MAX login.

For local development without a public HTTPS webhook, run polling in a second terminal:

```bash
.venv/bin/python scripts/max_poll.py
```

Production uses `POST /api/webhooks/max` behind HTTPS and requires `MAX_WEBHOOK_SECRET`.

After the production PWA is deployed on HTTPS, register the webhook subscription:

```bash
make max-webhook
```

By default this sends `APP_BASE_URL + /api/webhooks/max` to MAX when `APP_BASE_URL` is public HTTPS. If `.env` still has the local development URL, the script uses the production webhook `https://temichevvet.ru/api/webhooks/max`. It subscribes to `bot_started`, `message_created`, and `message_callback`. MAX requires a trusted HTTPS certificate on port 443; long polling is only for local checks. The bot token is available in MAX Partners: `Чат-боты -> Перейти -> Расширенные настройки -> Настроить`.

For the current MAX bot created in the partner cabinet:

```text
MAX_BOT_USERNAME=id230210303969_bot
```

Do not commit `.env`; it contains the live MAX token.

## PWA Push Follow-Ups

PWA can show browser notifications after a health check, similar to Telegram follow-up reminders. Push delivery requires VAPID keys:

```text
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:support@temichevvet.ru
```

Users enable notifications in `Способы входа`. On iPhone this normally works after the site is added to the Home Screen as a PWA.

Delivery is started by a closed internal endpoint:

```bash
curl -X POST "https://temichevvet.ru/api/internal/push/followups/send?limit=50" \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET"
```

Run it from cron or a systemd timer. If VAPID keys are absent, the user interface explains that notifications are still being prepared and regular app logic continues to work.

Production uses the templates in `infra/systemd/` and the helper script `scripts/send_pwa_followups.sh`.

## PWA Push Service Broadcast

One-off service broadcasts use only active PWA web-push subscriptions. They do not send Telegram or MAX messages.

Dry-run counts active subscriptions and does not send notifications:

```bash
curl -X POST "https://temichevvet.ru/api/internal/push/broadcast" \
  -H "Content-Type: application/json" \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET" \
  -d '{
    "title": "TemichevVet: работа восстановлена",
    "body": "Приносим извинения: был кратковременный сбой в работе серверов из-за повышенной нагрузки. Сейчас сервис доступен, работа восстановлена.",
    "url": "/app",
    "dry_run": true,
    "limit": 500
  }'
```

Real delivery requires an explicit confirmation token:

```bash
curl -X POST "https://temichevvet.ru/api/internal/push/broadcast" \
  -H "Content-Type: application/json" \
  -H "X-Temichevvet-Monitoring-Secret: $MONITORING_API_SECRET" \
  -d '{
    "title": "TemichevVet: работа восстановлена",
    "body": "Приносим извинения: был кратковременный сбой в работе серверов из-за повышенной нагрузки. Сейчас сервис доступен, работа восстановлена.",
    "url": "/app",
    "dry_run": false,
    "confirm": "SEND_PUSH_BROADCAST",
    "limit": 500
  }'
```

## GitHub

Repository:

```text
Pivotemnoe/PWAtemichevVet
```

Remote:

```bash
git remote add origin https://github.com/Pivotemnoe/PWAtemichevVet.git
git push -u origin main
```

## Documentation

- `docs/ROADMAP.md`: implementation stages and priorities.
- `docs/DEPLOYMENT.md`: local run, environment variables, Docker, production checklist.
- `docs/DB_SCHEMA.md`: current SQLite tables, data ownership, audit and PostgreSQL migration notes.
- `docs/PRODUCTION.md`: live VPS layout, domains, services, and health checks.
- `scripts/monitor_public.py`: public healthcheck and closed monitoring status checker for cron/systemd/external uptime agents.
- `infra/systemd/`: production timers for monitoring checks and PWA follow-up notifications.
- `docs/SECURITY_PRIVACY.md`: personal data, ownership checks, SQLite/PostgreSQL path.

## Next Steps

1. Keep backup and monitoring checks for the PWA SQLite database.
2. Prepare PostgreSQL migration before active growth.
3. Connect an external uptime provider to `https://temichevvet.ru/api/health` and closed monitoring alerts.
