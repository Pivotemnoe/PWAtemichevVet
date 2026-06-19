# TemichevVet Public PWA Verification Report

Дата проверки: 2026-06-19

## Что закрыто в текущем локальном проходе

- Пользовательская сессия переведена на серверную HttpOnly cookie `tvv_session`.
- Старый `localStorage`-токен больше не записывается, оставлена только мягкая миграция старых сессий.
- Logout теперь удаляет cookie, отзывает серверную сессию, очищает пользовательское состояние в памяти и убирает старые локальные маркеры.
- Email-коды стали одноразовыми: новый код инвалидирует старые активные коды, истёкший или перебранный код не проходит.
- Одноразовые Telegram/MAX login-state больше не записываются в `localStorage`; они живут только в памяти текущей вкладки.
- `review-login` ограничен по времени, одноразовый, отдаёт отдельную страницу ошибки и не кешируется.
- Service worker исключает приватные пути, API, `/app`, `/admin`, `/auth`, `/review-login` и URL с `token/payment/review` из кеша.
- API-ответы получают `Cache-Control: no-store, private`.
- Скрытые публичные модалки убраны из accessibility tree по умолчанию; технические DOM-артефакты `Документ` и видимые `×` удалены из HTML.
- Прямые юридические URL открываются как самостоятельные серверные документы без DOM личного кабинета и без формы входа:
  - `/privacy`
  - `/consent`
  - `/terms`
  - `/offer`
  - `/medical-disclaimer`
  - `/cookies`
  - `/contacts`
- Добавлены регрессионные тесты для email-кодов, logout/session revoke, review-login, standalone legal routes и повторного использования Telegram/MAX login-state.
- Проведён точечный XSS-аудит основных `innerHTML`-выводов: LLM-ответы, история, питомцы, платежные и knowledge-сообщения проходят через `escapeHtml`/`nl2br`.
- Усилены HTML-атрибуты в пустых состояниях и платежных notice-классах.
- Статический проектный check теперь падает, если пользовательский `tvv_token` или Telegram/MAX login-state снова начнут записывать в `localStorage`, если в публичный HTML вернутся технические modal-артефакты, если пропадёт standalone legal route или если service worker потеряет private cache guard.
- Публичная главная получила SEO-метаданные: человекочитаемый `title`, `description`, canonical, OpenGraph и JSON-LD для `WebApplication`, `Organization` и `Person`.
- `scripts/check_project.py` теперь проверяет наличие SEO-метаданных и JSON-LD, чтобы они не пропали при следующих правках.
- Админская сессия переведена с `localStorage` на отдельную HttpOnly cookie `tvv_admin_session`; logout отзывает серверную admin-сессию и удаляет cookie.
- Фронтенд админки больше не читает и не пишет `tvv_admin_token`; `scripts/check_project.py` теперь падает, если этот localStorage-маркер вернётся.

## Проверки

Команда:

```bash
make check
```

Результат:

- `scripts/check_project.py` — OK
- `scripts/test_api.py` — 37 тестов, OK
- `scripts/test_monitor_public.py` — 4 теста, OK
- `node --check web/app.js` — OK
- `node --check web/sw.js` — OK
- `web/manifest.webmanifest` — валидный JSON

Production-проверки после деплоя:

- `https://temichevvet.ru/api/health` — OK
- `https://temichevvet.ru/` — HTTP 200
- Security headers на главной — присутствуют: CSP, HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`
- В публичном HTML найдены `title`, canonical, OpenGraph и JSON-LD.
- В публичном HTML не найдены приватные DOM-блоки `dashboardView`/`workspaceView` и старые короткие trust-плашки.

## Что ещё осталось по security task

- Проверить публичные страницы в браузере после деплоя: mobile Safari/Chrome, desktop Chrome/Safari, PWA install.
- Проверить реальные production env-статусы: email, Telegram, MAX, YooKassa, LLM, Core API.
- Отдельно пройти полный браузерный XSS-аудит с вредоносными payload после деплоя: `<script>`, `<img onerror>`, `javascript:` и HTML в данных питомца/LLM/FAQ.
- На production дополнительно проверить реальные Telegram/MAX deep-link сценарии руками: вход, привязка, повторное открытие использованной ссылки.
- После деплоя проверить заголовки `curl -I` для `/`, `/app`, `/api/health`, `/privacy`, `/review-login`.
- Админская сессия пока использует отдельный `tvv_admin_token` в `localStorage`; это не пользовательский кабинет, но для полного hardening лучше отдельным этапом перевести админку на HttpOnly cookie с CSRF/2FA.
