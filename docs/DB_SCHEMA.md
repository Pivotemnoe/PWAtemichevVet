# TemichevVet PWA Database Schema

Дата: 2026-06-19

Рабочая база MVP сейчас SQLite. Этот документ фиксирует смысл таблиц, чтобы разработчик мог безопасно менять API, готовить PostgreSQL-миграцию и понимать, где хранятся персональные, медицинские и платёжные данные.

## Принципы

- Один пользователь может входить через email, Telegram и MAX: связь хранится через `external_accounts`.
- Медицинские тексты пользователя хранятся только там, где они нужны для личного кабинета: `triage_logs`, `pet_history`, `pet_observations`, `feedback`.
- В `security_audit_events` нельзя писать полный текст жалоб, LLM-ответы, заметки питомца и другие медицинские подробности.
- Оплата проверяется сервером: локальный платёж в `payments` должен совпадать с YooKassa по сумме, валюте, владельцу и metadata.
- Синхронизация с Telegram/Core API идёт через внешние идентификаторы и tombstone-защиту, чтобы удалённый в PWA питомец не импортировался обратно.

## Пользователи И Вход

| Таблица | Что хранит | Важные поля |
| --- | --- | --- |
| `users` | основной профиль пользователя | `email`, `name`, `phone`, `created_at`, `updated_at` |
| `external_accounts` | привязанные провайдеры входа | `user_id`, `provider`, `provider_user_id`, `display_name` |
| `auth_challenges` | одноразовые email/Telegram/MAX коды и challenge | `channel`, `target`, `code_hash`, `payload`, `expires_at`, `consumed_at`, `failed_attempts` |
| `sessions` | пользовательские сессии | `user_id`, `token_hash`, `expires_at`, `revoked_at` |
| `review_login_tokens` | временный тестовый вход для аудита | `token_hash`, `email`, `expires_at`, `last_used_at`, `revoked_at` |
| `admin_sessions` | админские сессии | `token_hash`, `expires_at`, `revoked_at`, `ip_hash`, `user_agent` |

## Питомцы И История

| Таблица | Что хранит | Важные поля |
| --- | --- | --- |
| `pets` | карточки питомцев | `owner_id`, `pet_type`, `pet_name`, `birth_year`, `sex`, `weight_kg`, `breed`, `is_main`, `external_source`, `external_id` |
| `pet_history` | события истории здоровья | `pet_id`, `event_type`, `title`, `details`, `triage_id`, `reminder_id`, `metadata`, `external_source`, `external_id` |
| `pet_observations` | наблюдения владельца | `user_id`, `pet_id`, `obs_type`, `payload`, `source`, `external_source`, `external_id` |
| `pet_measurements` | вес и измерения | `pet_id`, `weight_kg`, `note`, `metadata`, `external_source`, `external_id` |
| `reminders` | напоминания и график процедур | `user_id`, `pet_id`, `reminder_type`, `title`, `due_date`, `due_time`, `periodicity`, `is_active`, `external_source`, `external_id` |

## Подписка, Оплаты, Разборы

| Таблица | Что хранит | Важные поля |
| --- | --- | --- |
| `subscriptions` | текущий тариф и лимиты | `user_id`, `plan`, `quota_total`, `quota_used`, `period_start`, `period_end`, `source` |
| `payments` | локальные записи платежей | `user_id`, `provider`, `provider_payment_id`, `plan_code`, `amount_rub`, `status`, `confirmation_url`, `paid_at`, `raw_payload` |
| `triage_logs` | разборы состояния питомца | `user_id`, `pet_id`, `complaint_text`, `response_text`, `urgency_level`, `quota_before`, `quota_after`, `total_tokens`, `model`, `subscription_source`, `external_source`, `external_id` |
| `triage_followups` | follow-up после разбора | `triage_id`, `user_id`, `pet_id`, `urgency_level`, `scheduled_at`, `answered_at`, `status`, `answer`, `payload`, `push_notified_at`, `push_last_error` |
| `push_subscriptions` | PWA push-устройства | `user_id`, `endpoint`, `p256dh`, `auth`, `user_agent`, `revoked_at` |
| `feedback` | обратная связь команде сервиса | `user_id`, `text`, `category`, `created_at` |

## Безопасность И Синхронизация

| Таблица | Что хранит | Важные поля |
| --- | --- | --- |
| `security_audit_events` | служебный журнал безопасности | `event_type`, `user_id`, `provider`, `status`, `ip_hash`, `actor`, `entity_type`, `entity_id`, `metadata`, `created_at` |
| `sync_tombstones` | запрет повторного импорта удалённых сущностей | `owner_id`, `provider`, `entity_type`, `external_id`, `local_id` |

Служебные sync-очереди создаются в коде через Core API/Telegram-интеграцию. При PostgreSQL-переходе их нужно переносить вместе с основными таблицами, чтобы не потерять порядок событий.

## Индексы И Ограничения

- `users.email` уникален.
- `external_accounts(provider, provider_user_id)` уникален.
- Внешние сущности питомцев, истории, наблюдений, измерений, напоминаний и разборов имеют уникальные partial indexes по `external_source/external_id`.
- `payments(provider, provider_payment_id)` уникален.
- Пользовательские и админские сессии ищутся по `token_hash`.
- Частые списки оптимизированы индексами по `user_id`, `pet_id`, `created_at`, `status`, `due_date`.

## Что Учесть При PostgreSQL

1. Сохранить уникальность external identity и payment id.
2. Перевести JSON-строки `payload`, `metadata`, `raw_payload` в `jsonb`, если это не ломает экспорт/импорт.
3. Для `security_audit_events.metadata` оставить лимит и фильтрацию: без медицинских текстов и секретов.
4. Перенести SQLite timestamps как UTC ISO-строки или сразу привести к `timestamptz`.
5. Прогнать тесты ownership/payment/auth на обеих базах до переключения production.
