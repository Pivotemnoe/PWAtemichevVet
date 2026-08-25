from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = (
    "README.md",
    ".env.example",
    "requirements.txt",
    "app/main.py",
    "app/db.py",
    "web/index.html",
    "web/styles.css",
    "web/app.js",
    "web/manifest.webmanifest",
    "web/sw.js",
    "web/assets/icon.svg",
    "docs/DB_SCHEMA.md",
    "scripts/max_poll.py",
    "scripts/setup_max_webhook.py",
)


class PublicDomGuard(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.template_depth = 0
        self.template_ids: set[str] = set()
        self.private_ids_outside_template: list[str] = []
        self.private_ids_anywhere: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        if tag == "template":
            self.template_depth += 1
            if element_id:
                self.template_ids.add(element_id)
            return
        if element_id in {"dashboardView", "adminView", "logoutBtn", "workspace"}:
            self.private_ids_anywhere.append(element_id)
        if self.template_depth == 0 and element_id in {"dashboardView", "adminView"}:
            self.private_ids_outside_template.append(element_id)

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self.template_depth > 0:
            self.template_depth -= 1


def check_public_dom_templates() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    parser = PublicDomGuard()
    parser.feed(html)

    forbidden_templates = {"dashboardTemplate", "adminTemplate"}
    forbidden_template_ids = sorted(forbidden_templates & parser.template_ids)
    if forbidden_template_ids:
        raise SystemExit(f"private templates must not be present in public HTML: {', '.join(forbidden_template_ids)}")
    if parser.private_ids_anywhere:
        ids = ", ".join(sorted(set(parser.private_ids_anywhere)))
        raise SystemExit(f"private view ids must not be present in public HTML: {ids}")

    forbidden_public_text = (
        "Личный кабинет",
        "Выберите действие",
        "Выйти",
        "Мои питомцы",
    )
    found_text = [text for text in forbidden_public_text if text in html]
    if found_text:
        raise SystemExit(f"private app text must not be present in public HTML: {', '.join(found_text)}")
    forbidden_artifacts = (
        "<h2 id=\"legalModalTitle\">Документ</h2>",
        ">×</button>",
    )
    found_artifacts = [text for text in forbidden_artifacts if text in html]
    if found_artifacts:
        raise SystemExit("public HTML contains technical modal artifacts")
    for modal_id in ("petOnboardingDialog", "authDialog", "legalModal"):
        if f'id="{modal_id}" hidden aria-hidden="true"' not in html:
            raise SystemExit(f"{modal_id} must be hidden from public accessibility tree by default")


def check_public_seo() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    required = {
        "public title": "<title>TemichevVet — здоровье питомца в одном месте</title>",
        "meta description": 'name="description"',
        "canonical": '<link rel="canonical" href="https://temichevvet.ru/"',
        "og title": 'property="og:title"',
        "og image": 'property="og:image"',
        "webapplication json-ld": '"@type": "WebApplication"',
        "organization json-ld": '"@type": "Organization"',
        "person json-ld": '"@type": "Person"',
    }
    missing = [label for label, needle in required.items() if needle not in html]
    if missing:
        raise SystemExit(f"public SEO metadata missing: {', '.join(missing)}")


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    check_public_dom_templates()
    check_public_seo()

    manifest = (ROOT / "web/manifest.webmanifest").read_text(encoding="utf-8")
    if "TemichevVet" not in manifest:
        raise SystemExit("manifest does not contain app name")

    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    doctor_photo_marker = "/* Homepage expert portrait: keep the real clinic photo, but make it part of the hero. */"
    if doctor_photo_marker not in styles:
        raise SystemExit("homepage doctor photo contract marker is missing")
    doctor_photo_css = styles[styles.rfind(doctor_photo_marker):]
    for photo_guard in (
        "linear-gradient(90deg",
        "object-fit: cover;",
        "position: absolute;",
        "transform: none;",
        "@media (max-width: 959px)",
        "aspect-ratio: 3 / 4;",
    ):
        if photo_guard not in doctor_photo_css:
            raise SystemExit(f"homepage doctor photo integration guard is missing: {photo_guard}")
    for forbidden_photo_rule in ("transform: scale(", "grid-template-rows: auto auto"):
        if forbidden_photo_rule in doctor_photo_css:
            raise SystemExit(f"homepage doctor photo must not return to the detached/cropped treatment: {forbidden_photo_rule}")
    if "pet-card-preview-blue.png" in html or "pet-card-preview-blue.png" in (ROOT / "web/sw.js").read_text(encoding="utf-8"):
        raise SystemExit("generated pet-card marketing mockup must not appear on the homepage or app shell")
    if 'localStorage.setItem("tvv_token"' in js or "localStorage.setItem('tvv_token'" in js:
        raise SystemExit("user auth token must not be written to localStorage")
    if "tvv_admin_token" in js:
        raise SystemExit("admin auth token must not be stored or read from localStorage")
    for key in ("tvv_telegram_login_state", "tvv_telegram_login_url", "tvv_max_login_state", "tvv_max_login_url"):
        if f'localStorage.setItem("{key}"' in js or f"localStorage.setItem('{key}'" in js:
            raise SystemExit(f"messenger login challenge must not be written to localStorage: {key}")
    for analytics_privacy_guard in (
        "function sanitizedAnalyticsUrl()",
        "function clearSensitiveMiniAppFragment()",
        "/^#WebAppData=/i",
        "url: sanitizedAnalyticsUrl()",
        "typeof window === \"undefined\" || isAdminRoute",
    ):
        if analytics_privacy_guard not in js:
            raise SystemExit(f"analytics privacy guard is missing: {analytics_privacy_guard}")
    if "url: location.href" in js:
        raise SystemExit("Metrika must not receive the unsanitized browser URL")
    if js.index("clearSensitiveMiniAppFragment();") > js.index("showCookieBannerIfNeeded();"):
        raise SystemExit("sensitive MAX fragment must be removed before Metrika can load")
    for funnel_event, metrika_goal in (
        ("food.result_shown", "food_result_shown"),
        ("food.card_start_click", "food_passport_start_click"),
        ("pet.card_start_click", "pet_passport_start_click"),
        ("pet.created", "pet_created"),
        ("service.first_record_saved", "first_health_record_saved"),
        ("service.activated", "service_activated"),
        ("summary.viewed", "doctor_summary_open"),
        ("payment.succeeded", "plus_payment_success"),
    ):
        mapping = f'"{funnel_event}": "{metrika_goal}"'
        if mapping not in js:
            raise SystemExit(f"Metrika goal mapping is missing: {mapping}")

    for public_check_ui in (
        "Получить разбор",
        "Готовим ответ…",
        "Попробовать ещё раз",
        "revealPublicCheckState",
        'aria-live="polite"',
    ):
        if public_check_ui not in js:
            raise SystemExit(f"public check progress UI is missing: {public_check_ui}")
    for admin_token_ui in (
        "Токенов за 30 дней",
        "overview.tokens_30d_public",
        "overview.tokens_30d_cabinet",
        'key: "total_tokens", label: "Токены"',
    ):
        if admin_token_ui not in js:
            raise SystemExit(f"admin token usage UI is missing: {admin_token_ui}")
    if ".map(([name, value]) => [name, encodeURIComponent(String(value))])" not in js:
        raise SystemExit("attribution request headers must encode Cyrillic UTM values before fetch")
    for attribution_guard in (
        'const FIRST_TOUCH_KEY = "tvv_first_touch"',
        'const CURRENT_TOUCH_KEY = "tvv_current_touch"',
        "function captureCurrentTouchAttribution()",
        "function attributionEventMetadata()",
        '"X-Tvv-Current-Flow-Id"',
        '"X-Tvv-First-Landing-Path"',
        'headers: { "Content-Type": "application/json", ...attributionRequestHeaders() }',
    ):
        if attribution_guard not in js:
            raise SystemExit(f"first/current attribution guard is missing: {attribution_guard}")
    pet_create_success = 'const data = await api("/api/pets", { method: "POST", body: JSON.stringify(payload) });'
    pet_created_goal = 'trackMetrikaGoalOnce("pet.created", `pet:${data.item.id}`'
    if pet_create_success not in js or pet_created_goal not in js or "if (data.created)" not in js:
        raise SystemExit("pet.created Metrika goal must follow a successful pet API response")
    if 'trackFunnel("pet.created"' in js:
        raise SystemExit("pet.created must remain a server-only funnel event")
    for public_copy in (
        "TemichevVet — здоровье питомца в одном месте",
        "Ведите карточку питомца: сохраняйте изменения, вес, питание и важные даты.",
        "Посмотреть возможности",
        "Карточка питомца",
        "История здоровья",
        "Питание",
        "Вес и наблюдения",
        "Важные даты",
        "Здоровье питомца — не только один ответ",
        "Ответ станет частью истории питомца",
        "Что случилось с питомцем?",
        "Расскажите простыми словами — как есть.",
        "Кошка не ест?",
        "Собаку рвёт?",
        "Кот не может пописать?",
        "Питомец съел что-то опасное?",
        "Если питомцу тяжело дышать, он теряет сознание, не может помочиться или есть сильное кровотечение — не ждите онлайн-разбора, сразу обратитесь в клинику.",
        "Сервис не ставит диагноз и не заменяет консультацию ветеринара.",
        "Что важно сейчас",
        "Константин Валерьевич Темичев",
        "ветеринарный врач",
        "Сохранить случай",
        "Вернитесь к результату и проверьте, стало ли питомцу лучше или хуже.",
        "Добавить питомца",
        "Можно ли собаке этот продукт или блюдо?",
        "Можно ли кошке этот продукт или блюдо?",
        "Узнать, можно ли давать",
        "Сохраните ответ в карточку питомца",
        "Сохранить ответ",
        "База общая для кошек и собак, не содержит отдельных правил по виду и не является анализом корма или этикетки.",
        "Уровень риска в базе",
        "Не заменяет официальный ветеринарный паспорт.",
    ):
        if public_copy not in js and public_copy not in html:
            raise SystemExit(f"public check copy may be out of sync: {public_copy}")
    for removed_positioning in (
        "срочность состояния",
        "можно наблюдать или пора к ветеринару",
        "диагноз за минуту",
        "нейросеть",
        "ИИ-ответ",
        "25+ лет практики",
    ):
        if removed_positioning.casefold() in (html + manifest).casefold():
            raise SystemExit(f"removed service positioning returned to public metadata: {removed_positioning}")
    for removed_public_copy in ("Токсичность:", "Уровень риска:", "Опасное количество:"):
        if removed_public_copy in js:
            raise SystemExit(f"technical food label leaked into public UI: {removed_public_copy}")
    for public_check_save_guard in (
        'const PUBLIC_CHECK_USED_KEY = "tvv_public_check_preview_used"',
        "function renderPendingPublicCheckPetSelection(pending)",
        "function pendingPublicCheckNeedsPetSelection(pending)",
        'if (data.usage_consumed) markPublicCheckPreviewUsed();',
        'renderPublicCheckAuthPrompt(readableError("check_preview_already_used"))',
        '"check.save_cta_view"',
        'function scheduleCheckStickySave(resultEl, level)',
        'if (level !== "red") window.setTimeout(reveal, 8000);',
        '"После входа автоматически вернём вас к результату и сохраним его."',
    ):
        if public_check_save_guard not in js:
            raise SystemExit(f"public check save/gate guard is missing: {public_check_save_guard}")
    for public_food_guard in (
        "body: JSON.stringify({ species: variant.petType, query, ingredients })",
        'if (data.species !== variant.petType) throw new Error("food_species_mismatch");',
        "Boolean(data.requires_immediate_vet_contact)",
        "item.dose_note",
        "даже если симптомов пока нет",
        '"food.save_cta_view"',
        'api("/api/food/check/save"',
    ):
        if public_food_guard not in js:
            raise SystemExit(f"public food species/safety guard is missing: {public_food_guard}")
    if "item.how_much_is_dangerous" in js:
        raise SystemExit("public food UI must not expose universal dose claims")
    if 'resultEl.scrollIntoView({ behavior: "smooth", block: "start" })' in js:
        raise SystemExit("public check must scroll to the visible state card, not the result container")
    for onboarding_guard in (
        'const PENDING_PET_CREATE_KEY = "tvv_pending_pet_create"',
        "function pendingPetCreate()",
        "function completePendingPetAfterLogin()",
        "client_request_id: pending.client_request_id",
        "openPetOnboarding();",
    ):
        if onboarding_guard not in js:
            raise SystemExit(f"service-first pet onboarding guard is missing: {onboarding_guard}")
    if 'window.open(data.url, "_blank", "noopener")' in js:
        raise SystemExit("messenger login popup must be opened synchronously before the async API request")
    if 'function openDeferredExternalWindow()' not in js:
        raise SystemExit("messenger login popup pre-open guard is missing")
    for auth_priority_guard in (
        'class="panel auth-email-primary"',
        '<p class="section-label">Основной способ</p>',
        'class="messenger-button is-secondary is-max-featured" id="maxBtn"',
        'class="auth-telegram-link" id="telegramBtn"',
    ):
        if auth_priority_guard not in html:
            raise SystemExit(f"auth method priority guard is missing: {auth_priority_guard}")
    if not html.index('class="panel auth-email-primary"') < html.index('id="maxBtn"') < html.index('id="telegramBtn"'):
        raise SystemExit("auth methods must be ordered email, MAX, then Telegram")
    if "const focusTarget = emailInput || maxBtn || telegramBtn;" not in js:
        raise SystemExit("email must receive first focus when the auth dialog opens")
    if 'navigator.serviceWorker.register("/sw.js", { scope: "/" })' not in js:
        raise SystemExit("PWA service worker must control the root application scope")
    if 'registration.scope.endsWith("/static/")' not in js or "registration.unregister()" not in js:
        raise SystemExit("legacy static-scope service worker cleanup is missing")

    for endpoint in (
        "/api/auth/email/start",
        "/api/auth/email/verify",
        "/api/auth/${provider}/start",
        "/api/auth/max/status",
        "/api/auth/max/init",
        "/api/food/check/save",
    ):
        if endpoint not in js:
            raise SystemExit(f"frontend does not reference {endpoint}")

    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    for funnel_guard in (
        '"pet.created": "pet_created"',
        '"service.activated": "service_activated"',
        '"summary.viewed": "summary_view"',
        '"service.activated",',
        "PET_CAMPAIGN_FUNNEL_STEPS",
        "FOOD_CAMPAIGN_FUNNEL_STEPS",
        '"check.save_cta_view": "check_save_cta_view"',
        '"food.save_cta_view": "food_save_cta_view"',
        '"food.saved_after_login": "food_saved"',
        '@app.post("/api/food/check/save")',
        '"conversion_funnel_72h_pet"',
        '"conversion_funnel_72h_food"',
        '"conversion_funnel_72h_service"',
        '@app.get("/api/pets/{pet_id}/summary")',
        '@app.post("/api/pets/{pet_id}/summary/export")',
    ):
        if funnel_guard not in backend:
            raise SystemExit(f"campaign funnel guard is missing: {funnel_guard}")
    for legal_path in (
        "/privacy",
        "/consent",
        "/terms",
        "/offer",
        "/medical-disclaimer",
        "/cookies",
        "/contacts",
    ):
        if f'@app.get("{legal_path}"' not in backend:
            raise SystemExit(f"backend does not expose standalone legal route {legal_path}")
    for service_worker_guard in (
        '@app.get("/sw.js"',
        'response.headers["Service-Worker-Allowed"] = "/"',
        'response.headers["Cache-Control"] = "no-cache"',
    ):
        if service_worker_guard not in backend:
            raise SystemExit(f"root service worker route guard is missing: {service_worker_guard}")

    sw = (ROOT / "web/sw.js").read_text(encoding="utf-8")
    for campaign_route in (
        '"/pet"',
        '"/pet-history"',
        '"/pet-reminders"',
        '"/pet-food"',
        '"/doctor-summary"',
        '"/food/dog"',
        '"/food/cat"',
        '"/check/what-to-do-now"',
        '"/check/find-out-what-to-do"',
    ):
        if campaign_route not in sw:
            raise SystemExit(f"service worker app shell misses campaign route {campaign_route}")
    for private_path in ('"/api/"', '"/admin"', '"/app"', '"/review-login"'):
        if private_path not in sw:
            raise SystemExit(f"service worker private cache guard misses {private_path}")

    print("pwa project check ok")


if __name__ == "__main__":
    main()
