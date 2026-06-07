# TemichevVet PWA Roadmap

## Stage 1: PWA foundation

- FastAPI backend serves the PWA shell.
- Email one-time-code authentication works without paid SMS.
- Telegram and MAX login entry points are reserved as separate providers.
- SQLite is used for the first MVP version.
- Done.

## Stage 2: Messenger login

- Add a separate login choice dialog instead of sending users straight to email.
- Add Telegram login as an optional channel for users who can access it.
- Link Telegram account IDs to the same PWA user profile.
- Keep MAX as a login provider for identity confirmation.
- Build the full MAX bot menus and service scenarios separately from login.
- Telegram-linked users can reuse Telegram subscription entitlement in PWA.
- Next: synchronize Telegram bot pets and future PWA payment activations through the linked identity.

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

- LLM triage is connected server-side.
- Red symptoms run before LLM and do not consume quota.
- PWA can read and consume the linked Telegram subscription quota when Telegram login is connected.
- Paid PWA subscription rows can be mirrored to the linked Telegram `bot.db` so Telegram sees the same entitlement.
- Add YooKassa payment flow for Plus inside PWA.
- Mirror successful PWA Plus activation to the linked Telegram account.
- Server-side payment validation only: amount, currency, paid status, metadata and user ownership.
- Add web subscription screen with clear Free/Plus limits.
- Add admin payment reports and reconciliation.

## Stage 5: Release Hardening

- Add backups, monitoring, error logs, and CI before public release.
- Rate limits for auth, payments, triage, feedback, export and data deletion requests are in place.
- Security headers are applied by the FastAPI middleware.
- User can revoke current session, revoke all sessions, export account data and submit a data deletion request.
- Next: add structured access/error audit logs and CI checks.
- Prepare PostgreSQL migration before active growth.
