# TemichevVet PWA

Separate PWA project for TemichevVet.

This repository is intentionally separate from the Telegram bot repository. The first stage prepares a web app with independent auth and a clean path for Telegram/MAX account linking.

## What Is Included

- FastAPI backend.
- Static installable PWA frontend.
- Email one-time-code login.
- Telegram login placeholder.
- MAX deep-link login with webhook and local polling support.
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

## MAX Login

Set these values in `.env`:

```text
MAX_BOT_USERNAME=id230210303969_bot
MAX_BOT_TOKEN=...
```

For local development without a public HTTPS webhook, run polling in a second terminal:

```bash
.venv/bin/python scripts/max_poll.py
```

Production uses `POST /api/webhooks/max` behind HTTPS and requires `MAX_WEBHOOK_SECRET`.

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

1. Add SMTP provider for production email login.
2. Move Plus/YooKassa payment flow from Telegram bot into PWA with server-side validation.
3. Connect full LLM triage prompts and subscription limits.
4. Add backups and monitoring for the PWA SQLite database.
5. Prepare PostgreSQL migration before active growth.
