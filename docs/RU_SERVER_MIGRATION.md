# RU Server Migration Runbook

Документ фиксирует подготовленный российский стенд TemichevVet и порядок безопасного переключения без изменения проекта `Что поесть`.

## Текущий статус

- Действующий TemichevVet сейчас остается на сервере `5.129.239.104`.
- Российский стенд подготовлен на сервере `193.188.23.65`.
- DNS `temichevvet.ru` пока не менялся.
- Конфиг nginx для `temichevvet.ru` на российском сервере подготовлен только как draft и не включен.
- Telegram-бот на российском сервере установлен, но выключен, чтобы не было двух процессов с одним `BOT_TOKEN`.
- PWA на российском сервере работает локально на `127.0.0.1:8081`.
- SQLite-базы вынесены в отдельный каталог данных и не лежат внутри кода.
- Регулярный backup настроен локально и в S3.

## Российский сервер

- VPS: `193.188.23.65`
- Рабочий каталог: `/opt/temichevvet`
- PWA: `/opt/temichevvet/pwa`
- Telegram bot: `/opt/temichevvet/bot`
- Базы данных: `/opt/temichevvet/data`
- Бэкапы: `/opt/temichevvet/backups`
- Скрипты: `/opt/temichevvet/scripts`
- S3 env: `/opt/temichevvet/s3.env`
- Пользователь сервисов: `temichevvet`

## Сервисы

```bash
systemctl status temichevvet_pwa.service
systemctl status temichevvet_bot.service
systemctl status temichevvet_backup.timer
```

Ожидаемое состояние до переключения:

- `temichevvet_pwa.service`: active/enabled
- `temichevvet_bot.service`: inactive/disabled
- `temichevvet_backup.timer`: active/enabled

## Проверки стенда

```bash
curl -sS http://127.0.0.1:8081/api/config
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/
nginx -t
docker ps
```

`docker ps` нужен только чтобы убедиться, что контейнеры проекта `Что поесть` не затронуты.

## Backup

Ручной запуск:

```bash
systemctl start temichevvet_backup.service
journalctl -u temichevvet_backup.service -n 30 --no-pager
ls -lh /opt/temichevvet/backups
```

Нормальный результат в журнале:

```text
backup ok: <timestamp>; local_files=2; s3_uploaded=2
```

В S3 используется отдельный префикс:

```text
temichevvet/backups/
```

## Nginx

Подготовленный draft:

```text
/etc/nginx/sites-available/temichevvet.ru.draft
```

До смены DNS и получения SSL он не должен быть включен в `sites-enabled`.

Проверка:

```bash
test -f /etc/nginx/sites-available/temichevvet.ru.draft
test ! -e /etc/nginx/sites-enabled/temichevvet.ru
nginx -t
```

## Порядок переключения

1. Остановить действующий TemichevVet bot на старом сервере.
2. Снять свежий backup баз на старом сервере.
3. Перенести актуальные базы PWA и Telegram bot на российский сервер в `/opt/temichevvet/data`.
4. Проверить права на базы:

```bash
chown temichevvet:temichevvet /opt/temichevvet/data/*.db
chmod 640 /opt/temichevvet/data/*.db
```

5. Перезапустить PWA на российском сервере:

```bash
systemctl restart temichevvet_pwa.service
```

6. Запустить Telegram bot на российском сервере:

```bash
systemctl enable --now temichevvet_bot.service
```

7. Проверить Telegram `/start`, PWA login, email login, Telegram login, MAX login, LLM triage, питание, питомцев, напоминания, подписку и платеж.
8. После проверки сменить DNS `temichevvet.ru` и `www.temichevvet.ru` на российский сервер.
9. После DNS выпустить SSL и включить nginx-конфиг для домена.

## Откат

Если после переключения есть критическая проблема:

1. Остановить Telegram bot на российском сервере:

```bash
systemctl stop temichevvet_bot.service
systemctl disable temichevvet_bot.service
```

2. Запустить Telegram bot на старом сервере.
3. Вернуть DNS на старый сервер, если DNS уже менялся.
4. Российский PWA можно оставить как staging, пока исправляется проблема.

## Что нельзя делать без отдельной проверки

- Не запускать одновременно два Telegram bot процесса с одним `BOT_TOKEN`.
- Не менять nginx-конфиги проекта `Что поесть`.
- Не менять DNS до финальной проверки и готовности SSL.
- Не хранить новые персональные данные вне `/opt/temichevvet/data`.
- Не коммитить `.env`, S3-ключи, SMTP-пароли, токены Telegram, MAX или OpenAI.
