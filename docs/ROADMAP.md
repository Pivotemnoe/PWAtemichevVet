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
- Telegram-linked users can synchronize core profile data server-side: pet cards, reminders, observations, measurements, history, triage logs and subscription entitlement.
- Duplicate Telegram/MAX identities are covered by regression tests: linking an already known messenger account merges the temporary email cabinet into the existing user and keeps pet data.
- Sync side effects are guarded by ownership checks for reminder deletion: a foreign reminder ID returns 404 and does not send a Telegram/Core sync event.
- Foreign pet mutation attempts are covered by regression tests: edit pet, main pet, weight, observation, reminder and triage operations return 404 and do not run sync or LLM side effects.
- Successful PWA sync paths are covered by regression tests: pet edits, main-pet changes, weight, observation, reminder and red-flag triage enqueue the expected Telegram/Core rows after successful owner operations.
- Telegram-backed pet deletion is guarded by owner checks, records a tombstone to prevent re-import from Telegram, and queues a Core delete event only after the PWA delete succeeds.
- Next: monitor sync lag/errors in production and review deletion UX copy so users understand that deletion affects linked channels.

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
- Structured security audit logs are in place for auth, provider linking, payments, LLM errors, sync errors and ownership-denied attempts.
- Public `/api/health` and closed `/api/monitoring/status` are available for uptime and operational checks.
- GitHub CI is prepared for Python checks, JS checks, API smoke tests, mocked payments and ownership tests.
- PostgreSQL migration is documented and should be done before active growth.

## P2: Development And Growth

- Keep SQLite for MVP, but prepare PostgreSQL before scaling.
- Richer admin UI for `security_audit_events` is in place: the dashboard groups recent warnings/errors and explains them in human-readable language.
- Add real external uptime provider for `https://temichevvet.ru/api/health`.
- Add alert rules for 5xx, YooKassa errors, LLM failures and Telegram sync failures.
- Add more API regression tests as new PWA scenarios move from Telegram into the web app. Duplicate Telegram/MAX identity merges, reminder-delete ownership/sync ordering, foreign pet mutation side effects, successful PWA sync enqueue paths and Telegram-backed pet deletion are already covered.
- Show only a simple user-facing sync status: connected channels, last check and a short readable warning. Keep technical Telegram/MAX sync internals in admin logs.
