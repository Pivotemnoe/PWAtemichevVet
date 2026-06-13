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
- Personal cabinet: pets, pet cards, history, observations, weight, reminders, food checks, feedback.
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

The PWA can reuse Telegram subscription entitlement through the linked Telegram ID. If a paid PWA subscription is later issued to a user with linked Telegram, the PWA mirrors that entitlement to the Telegram `bot.db`. Full pet synchronization is a separate migration step.

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
```

MAX login is used only to confirm identity and open or connect the same PWA account. The full MAX bot with service menus and scenarios is a separate product step.

For local development without a public HTTPS webhook, run polling in a second terminal:

```bash
.venv/bin/python scripts/max_poll.py
```

Production uses `POST /api/webhooks/max` behind HTTPS and requires `MAX_WEBHOOK_SECRET`.

## PWA Push Follow-Ups

PWA can show browser notifications after a health check, similar to Telegram follow-up reminders. Push delivery is disabled until VAPID keys are configured:

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
- `docs/PRODUCTION.md`: live VPS layout, domains, services, and health checks.
- `docs/SECURITY_PRIVACY.md`: personal data, ownership checks, SQLite/PostgreSQL path.

## Next Steps

1. Generate and configure VAPID keys for PWA push notifications.
2. Add the push follow-up sender to cron or a systemd timer.
3. Add backups and monitoring for the PWA SQLite database.
4. Prepare PostgreSQL migration before active growth.
