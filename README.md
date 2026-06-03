# TemichevVet PWA

Separate PWA project for TemichevVet.

This repository is intentionally separate from the Telegram bot repository. The first stage prepares a web app with independent auth and a clean path for Telegram/MAX account linking.

## What Is Included

- FastAPI backend.
- Static installable PWA frontend.
- Email one-time-code login.
- Telegram and MAX login placeholders.
- SQLite schema for web users, auth challenges, sessions, and external account links.
- Deployment notes for VPS + nginx.

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

## Next Steps

1. Add SMTP provider for production email login.
2. Add MAX bot token and deep-link login after moderation.
3. Add Telegram bot deep-link login as optional channel.
4. Connect product APIs: pets, triage, food, subscription, payment.
5. Deploy behind HTTPS.
