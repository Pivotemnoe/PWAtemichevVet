# RU Server Migration Runbook

Документ фиксирует подготовленный российский стенд TemichevVet и порядок безопасного переключения без изменения проекта `Что поесть`.

## Текущий статус

- Действующий TemichevVet сейчас остается на сервере `5.129.239.104`.
- Российский стенд подготовлен на сервере `193.188.23.65`.
- DNS `temichevvet.ru` пока не менялся.
- HTTP-конфиг nginx для `temichevvet.ru` на российском сервере включен заранее и проксирует PWA на `127.0.0.1:8081`.
- HTTPS для `temichevvet.ru` пока не включен: сертификат нужно выпустить после смены DNS.
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

## Синхронизация баз перед переключением

На российском сервере подготовлен скрипт:

```text
/opt/temichevvet/scripts/sync_from_nl.sh
```

Проверочный запуск без изменения российских баз:

```bash
/opt/temichevvet/scripts/sync_from_nl.sh dry-run
```

Что делает `dry-run`:

- создает SQLite backup snapshots на старом NL-сервере;
- скачивает `pwa.db` и `bot.db` во временный release-каталог на RU-сервере;
- проверяет `PRAGMA integrity_check`;
- не заменяет базы в `/opt/temichevvet/data`.

Применение свежих баз на RU-сервере:

```bash
/opt/temichevvet/scripts/sync_from_nl.sh apply
```

Что делает `apply`:

- отказывается работать, если RU Telegram bot уже активен;
- временно останавливает RU PWA;
- сохраняет текущие RU-базы в release-каталог;
- ставит свежие базы из NL backup snapshots в `/opt/temichevvet/data`;
- проверяет integrity;
- запускает RU PWA обратно;
- оставляет RU Telegram bot выключенным до явного финального запуска.

## Nginx

Включенный HTTP-конфиг:

```text
/etc/nginx/sites-available/temichevvet.ru
/etc/nginx/sites-enabled/temichevvet.ru
```

Проверка:

```bash
test -f /etc/nginx/sites-available/temichevvet.ru
test -e /etc/nginx/sites-enabled/temichevvet.ru
nginx -t
curl -sS -H "Host: temichevvet.ru" http://127.0.0.1/api/config
```

После смены DNS на RU-сервер нужно выпустить SSL-сертификат и включить HTTPS.

## Порядок переключения

1. Остановить действующий TemichevVet bot на старом сервере.
2. Остановить или закрыть доступ к старой PWA на время финального переноса, чтобы новые действия пользователей не записались в старую базу после sync.
3. Синхронизировать свежие базы через подготовленный скрипт:

```bash
/opt/temichevvet/scripts/sync_from_nl.sh apply
```

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
8. Сменить DNS `temichevvet.ru` и `www.temichevvet.ru` на российский сервер `193.188.23.65`.
9. После DNS выпустить SSL и включить HTTPS для домена.

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
