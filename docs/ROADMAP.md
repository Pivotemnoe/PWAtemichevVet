# TemichevVet PWA Roadmap

## Stage 1: PWA foundation

- FastAPI backend serves the PWA shell.
- Email one-time-code authentication works without paid SMS.
- Telegram and MAX login entry points are reserved as separate providers.
- SQLite is used for the first MVP version.

## Stage 2: Messenger login

- Enable MAX login after bot moderation and token issue.
- Add Telegram login as an optional channel for users who can access it.
- Link external messenger accounts to the same PWA user profile.

## Stage 3: Product scenarios

- Move pet cards, triage, nutrition checks, reminders, and subscription state into shared product services.
- Keep Telegram bot and PWA as two frontends over the same business rules.
- Add ownership checks for every pet, reminder, payment, and health record.

## Stage 4: Payments and release hardening

- Add YooKassa payment flow for Plus inside PWA.
- Add admin payment reports and reconciliation.
- Add backups, monitoring, error logs, and CI before public release.
