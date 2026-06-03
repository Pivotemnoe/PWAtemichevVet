# Deployment Notes

## Local Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make check
DEV_AUTH_CODE_LOG=1 .venv/bin/python -m app.main
```

Open:

```text
http://127.0.0.1:8080
```

## Environment

Copy `.env.example` to `.env` and set values:

- `APP_ENV`: `development` or `production`.
- `DATABASE_PATH`: SQLite path for the PWA database.
- `DEV_AUTH_CODE_LOG`: `1` only for local development.
- `EMAIL_FROM`: sender address for email codes.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`: email delivery settings.
- `TELEGRAM_BOT_USERNAME`: optional Telegram login provider.
- `MAX_BOT_USERNAME`, `MAX_BOT_TOKEN`: MAX login provider after moderation.

## Docker

```bash
docker compose up --build
```

The app listens on port `8080` by default.

## Production Checklist

- Use HTTPS through nginx or another reverse proxy.
- Keep `.env` out of git.
- Disable `DEV_AUTH_CODE_LOG`.
- Configure real SMTP before public login.
- Back up the SQLite database or switch to Postgres before active marketing traffic.
- Add monitoring for 5xx errors and failed auth attempts.
