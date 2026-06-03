# TemichevVet PWA Roadmap

## Stage 1: PWA foundation

- FastAPI backend serves the PWA shell.
- Email one-time-code authentication works without paid SMS.
- Telegram and MAX login entry points are reserved as separate providers.
- SQLite is used for the first MVP version.
- Done.

## Stage 2: Messenger login

- Enable MAX login after bot moderation and token issue.
- Use local MAX polling for development and HTTPS webhook for production.
- Add Telegram login as an optional channel for users who can access it.
- Link external messenger accounts to the same PWA user profile.
- MAX login is connected in production through HTTPS webhook.
- Telegram login remains optional/backlog because the product should not depend on Telegram availability.

## Stage 3: Personal Cabinet

- Pet cards: create, read, update, delete.
- Main pet flag.
- Pet history.
- Observations.
- Weight history.
- Reminders with templates and periodicity.
- Nutrition checks from the same food knowledge base as Telegram bot.
- Feedback to project team.
- Basic triage safety layer: red symptoms before LLM, save event to pet history.
- Ownership checks for pet, reminder, observation, weight and history APIs.

## Stage 4: Full Triage And Payments

- Move full LLM triage prompts and subscription limits from Telegram bot.
- Add YooKassa payment flow for Plus inside PWA.
- Server-side payment validation only: amount, currency, paid status, metadata and user ownership.
- Add web subscription screen with clear Free/Plus limits.
- Add admin payment reports and reconciliation.

## Stage 5: Release Hardening

- Add backups, monitoring, error logs, and CI before public release.
- Add rate limits for auth endpoints and email code requests.
- Add privacy/data deletion process.
- Prepare PostgreSQL migration before active growth.
