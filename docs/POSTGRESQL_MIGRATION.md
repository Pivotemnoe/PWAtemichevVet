# PostgreSQL Migration Plan

Дата: 2026-06-08

SQLite подходит для MVP и первого рекламного теста. На PostgreSQL нужно переходить до активного роста, когда появятся параллельные пользователи, больше платежей, админка и аналитика.

## Цель

- Сохранить текущий API-контракт PWA.
- Не ломать Telegram NL -> RU Core API.
- Перенести персональные данные и события питомцев в управляемую PostgreSQL-базу.
- Оставить регулярный backup и понятный rollback.

## Подготовка

1. Добавить `POSTGRES_DSN` в `.env`, не включая его сразу в production.
2. Выбрать слой миграций: Alembic.
3. Зафиксировать текущую SQLite-схему из `app/db.py`.
4. Добавить интеграционные тесты ownership/payment/auth до переключения.

## Таблицы Первой Очереди

- `users`
- `external_accounts`
- `auth_challenges`
- `sessions`
- `pets`
- `pet_history`
- `pet_observations`
- `pet_measurements`
- `reminders`
- `subscriptions`
- `payments`
- `triage_logs`
- `triage_followups`
- `feedback`
- `security_audit_events`
- `core_sync_events`
- `core_outbound_events`

## Технический План

1. Вынести прямой SQL из `app/db.py` в репозитории или адаптер `Storage`.
2. Сделать две реализации: SQLite и PostgreSQL.
3. Ввести миграции Alembic для PostgreSQL.
4. Написать one-shot импорт SQLite -> PostgreSQL.
5. Прогнать тесты на обеих базах.
6. На проде:
   - остановить PWA;
   - сделать backup SQLite;
   - импортировать данные;
   - запустить PWA с `POSTGRES_DSN`;
   - проверить `/api/health`, вход, питомцев, триаж, оплату, Telegram sync.

## Rollback

До полного перехода держать SQLite backup и старый `.env`. Если после переключения появились критические ошибки:

1. Остановить PWA.
2. Вернуть `DATABASE_PATH` и отключить `POSTGRES_DSN`.
3. Запустить сервис.
4. Проверить `/api/health` и базовые сценарии.

## Когда Делать

Минимальный триггер для перехода:

- стабильный поток пользователей после рекламы;
- больше 50-100 активных пользователей в день;
- регулярные платежи в PWA;
- потребность в админке с фильтрами, поиском и отчётами;
- необходимость юридически точных выгрузок/удалений в более управляемой базе.
