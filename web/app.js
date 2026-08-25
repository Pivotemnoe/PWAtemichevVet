const legacySessionToken = localStorage.getItem("tvv_token") || "";

const state = {
  token: legacySessionToken,
  telegramLoginState: "",
  telegramLoginUrl: "",
  maxLoginState: "",
  maxLoginUrl: "",
  deferredInstall: null,
  telegramPollTimer: null,
  maxPollTimer: null,
  lastPlusPaymentId: localStorage.getItem("tvv_last_plus_payment_id") || "",
  pushConfig: null,
  user: null,
  externalAccounts: [],
  subscription: null,
  pets: [],
  currentPetId: null,
  telegramProfileSync: null,
  lastSyncCheckAt: ""
};

const LEGAL_UPDATED_AT = "5 июня 2026";
const OPERATOR_EMAIL = "support@temichevvet.ru";
const METRIKA_ID = 109726654;
let metrikaLoaded = false;
const isAdminRoute = window.location.pathname.replace(/\/+$/, "") === "/admin";
const STARTUP_ACTIONS = new Set(["home", "triage", "pets", "reminders", "subscription", "more"]);
const PENDING_STARTUP_ACTION_KEY = "tvv_pending_startup_action";
let consumedStartupAction = "";
let checkLandingViewTrackedPath = "";
let campaignLandingViewTrackedPath = "";
let authDialogContextLead = "";

const METRIKA_GOALS = {
  "check.start_click": "check_start_click",
  "check.submit": "check_submit",
  "check.result_shown": "check_result_shown",
  "check.save_click": "check_save_click",
  "check.saved_after_login": "check_saved_after_login",
  "auth.login_success": "auth_login_success",
  "food.result_shown": "food_result_shown",
  "food.card_start_click": "food_passport_start_click",
  "pet.card_start_click": "pet_passport_start_click",
  "pet.created": "pet_created",
  "service.first_record_saved": "first_health_record_saved",
  "service.activated": "service_activated",
  "summary.viewed": "doctor_summary_open",
  "payment.succeeded": "plus_payment_success"
};

const CHECK_LANDING_VARIANTS = {
  general: {
    slug: "general",
    title: "Что случилось с питомцем?",
    lead: "Расскажите простыми словами — как есть.",
    label: "Здоровье питомца",
    image: "/static/assets/check-ad-general.png",
    imageAlt: "Собака и кошка рядом с владельцем",
    defaultPet: "",
    placeholder: "Например: кошка второй день не ест, прячется и почти не пьёт"
  },
  "what-to-do-now": {
    slug: "what-to-do-now",
    title: "Здоровье питомца — не только один ответ",
    lead: "Расскажите, что изменилось, и сохраните разбор в общей истории питомца.",
    label: "Здоровье питомца",
    image: "/static/assets/doctor-konstantin-cat-table-retouched.jpg",
    imageAlt: "Ветеринарный врач Константин Темичев с кошкой",
    defaultPet: "",
    placeholder: "Например: кошка второй день не ест, прячется и почти не пьёт"
  },
  "find-out-what-to-do": {
    slug: "find-out-what-to-do",
    title: "Ответ станет частью истории питомца",
    lead: "Сохраните изменения рядом с весом, питанием и важными датами.",
    label: "Здоровье питомца",
    image: "/static/assets/doctor-konstantin-cat-table-retouched.jpg",
    imageAlt: "Ветеринарный врач Константин Темичев с кошкой",
    defaultPet: "",
    placeholder: "Например: кошка второй день не ест, прячется и почти не пьёт"
  },
  "cat-not-eating": {
    slug: "cat-not-eating",
    title: "Кошка не ест?",
    lead: "Напишите, как давно и что ещё изменилось.",
    label: "Здоровье питомца",
    image: "/static/assets/check-ad-cat.png",
    imageAlt: "Кошка рядом с владельцем",
    defaultPet: "cat",
    placeholder: "Например: кошка второй день не ест, прячется и почти не пьёт"
  },
  "dog-vomiting": {
    slug: "dog-vomiting",
    title: "Собаку рвёт?",
    lead: "Напишите, сколько раз была рвота и как собака ведёт себя сейчас.",
    label: "Здоровье питомца",
    image: "/static/assets/check-ad-dog.png",
    imageAlt: "Собака рядом с владельцем",
    defaultPet: "dog",
    placeholder: "Например: собаку вырвало два раза, она стала вялой и мало пьёт"
  },
  urination: {
    slug: "urination",
    title: "Кот не может пописать?",
    lead: "Если моча есть, но её мало, напишите, что происходит.",
    label: "Здоровье питомца",
    image: "/static/assets/check-ad-general.png",
    imageAlt: "Кот рядом с владельцем",
    defaultPet: "cat",
    placeholder: "Например: кот часто садится в лоток, мочи выходит очень мало"
  },
  poisoning: {
    slug: "poisoning",
    title: "Питомец съел что-то опасное?",
    lead: "Напишите, что именно, сколько и когда это произошло.",
    label: "Здоровье питомца",
    image: "/static/assets/check-ad-general.png",
    imageAlt: "Питомец рядом с владельцем",
    defaultPet: "",
    placeholder: "Например: собака съела шоколад около часа назад, пока ведёт себя обычно"
  }
};

const PUBLIC_CAMPAIGN_LANDINGS = {
  pet: {
    slug: "pet",
    path: "/pet",
    kind: "service",
    title: "Здоровье питомца в одном месте",
    headline: "Карточка здоровья питомца",
    description: "Сохраняйте изменения, вес, питание и важные даты. Вся история питомца всегда рядом.",
    label: "Весь сервис",
    image: "/static/assets/campaign-home-pet.jpg",
    imageAlt: "Семья с собакой и кошкой пользуется карточкой питомца",
    benefits: ["Карточка каждого питомца", "Вес и наблюдения", "Питание и важные даты", "История для визита к врачу"]
  },
  "pet-history": {
    slug: "pet-history",
    path: "/pet-history",
    kind: "service",
    title: "История здоровья питомца",
    headline: "История питомца, которую не нужно вспоминать заново",
    description: "Сохраняйте наблюдения, изменения, ответы по питанию и важные события в одной хронологии.",
    label: "История здоровья",
    image: "/static/assets/campaign-home-pet.jpg",
    imageAlt: "Владелец ведёт историю здоровья питомца",
    benefits: ["Наблюдения по датам", "Сохранённые разборы", "Питание в общей истории", "Сводка перед посещением врача"]
  },
  "pet-reminders": {
    slug: "pet-reminders",
    path: "/pet-reminders",
    kind: "service",
    title: "Важные даты питомца",
    headline: "Прививки, обработки и осмотры — вовремя",
    description: "Добавляйте важные даты в карточку питомца и держите ближайшие события перед глазами.",
    label: "Важные даты",
    image: "/static/assets/campaign-home-pet.jpg",
    imageAlt: "Владелец добавляет важную дату питомца",
    benefits: ["Прививки", "Обработки", "Осмотры", "Свои важные события"]
  },
  "pet-food": {
    slug: "pet-food",
    path: "/pet-food",
    kind: "service",
    title: "Питание питомца",
    headline: "Проверяйте питание и сохраняйте ответы",
    description: "Узнавайте, что можно и нельзя питомцу, и храните полезные ответы в его карточке.",
    label: "Питание",
    image: "/static/assets/campaign-food-dog.jpg",
    imageAlt: "Владелец проверяет питание питомца",
    benefits: ["Проверка продуктов", "Проверка состава блюда", "Сохранение ответа", "Связь с историей питомца"]
  },
  "doctor-summary": {
    slug: "doctor-summary",
    path: "/doctor-summary",
    kind: "service",
    title: "Сводка для ветеринарного врача",
    headline: "Подготовьте историю питомца к визиту в клинику",
    description: "Вес, наблюдения, важные даты и сохранённые изменения собираются в понятную хронологию.",
    label: "Сводка для врача",
    image: "/static/assets/doctor-konstantin-cat-table-retouched.jpg",
    imageAlt: "Ветеринарный врач изучает историю питомца",
    benefits: ["Период 30 или 90 дней", "Вся история для Plus", "Печать и PDF", "Без нового диагноза"]
  },
  "food/dog": {
    slug: "food-dog",
    kind: "food",
    petType: "dog",
    petLabel: "собаки",
    title: "Можно ли собаке этот продукт или блюдо?",
    description: "Проверьте продукт или состав блюда по общей базе для кошек и собак.",
    label: "База продуктов",
    placeholder: "Например: виноград, морковь или борщ",
    examples: ["Виноград", "Морковь", "Борщ"],
    image: "/static/assets/campaign-food-dog.jpg",
    imageAlt: "Владелец собаки проверяет продукт"
  },
  "food/cat": {
    slug: "food-cat",
    kind: "food",
    petType: "cat",
    petLabel: "кошки",
    title: "Можно ли кошке этот продукт или блюдо?",
    description: "Проверьте продукт или состав блюда по общей базе для кошек и собак.",
    label: "База продуктов",
    placeholder: "Например: молоко, курица или шоколад",
    examples: ["Молоко", "Курица", "Шоколад"],
    image: "/static/assets/campaign-food-cat.jpg",
    imageAlt: "Владелица кошки пользуется TemichevVet"
  }
};

function isAuthLinkRequested() {
  const value = new URLSearchParams(window.location.search).get("auth") || "";
  return ["1", "true", "login", "cabinet"].includes(value.trim().toLowerCase());
}

function clearAuthLinkRequest() {
  if (!isAuthLinkRequested()) return;
  const url = new URL(window.location.href);
  url.searchParams.delete("auth");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

const FIRST_TOUCH_KEY = "tvv_first_touch";
const CURRENT_TOUCH_KEY = "tvv_current_touch";
const FIRST_TOUCH_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const CURRENT_TOUCH_TTL_MS = 24 * 60 * 60 * 1000;
const PENDING_CHECK_SAVE_KEY = "tvv_pending_check_save";
const PENDING_FOOD_SAVE_KEY = "tvv_pending_food_save";
const PENDING_PET_CREATE_KEY = "tvv_pending_pet_create";
const PUBLIC_CHECK_USED_KEY = "tvv_public_check_preview_used";
const CHECK_SAVE_CTA = "Сохранить случай";
const AUTH_DIALOG_DEFAULT_LEAD =
  "Войдите удобным способом. Если аккаунта ещё нет, он создастся автоматически.";
let currentTouchAttribution = null;
const sentMetrikaGoalKeys = new Set();
const visibleFunnelEventKeys = new Set();

function createFlowId() {
  return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cleanAttributionValue(value, maxLength = 120) {
  return String(value || "")
    .trim()
    .replace(/[^a-zA-Z0-9а-яА-ЯёЁ._:/ -]/g, "")
    .slice(0, maxLength);
}

function attributionFromCurrentLocation() {
  const params = new URLSearchParams(window.location.search);
  let referrerHost = "";
  try {
    const referrer = document.referrer ? new URL(document.referrer) : null;
    if (referrer && referrer.hostname !== window.location.hostname) {
      referrerHost = referrer.hostname;
    }
  } catch {
    referrerHost = "";
  }

  const utmSource = cleanAttributionValue(params.get("utm_source"), 80);
  const hasYclid = Boolean(cleanAttributionValue(params.get("yclid"), 120));
  return {
    traffic_source: utmSource || (hasYclid ? "yandex_direct" : cleanAttributionValue(referrerHost, 80) || "direct"),
    utm_source: utmSource,
    utm_medium: cleanAttributionValue(params.get("utm_medium"), 80),
    utm_campaign: cleanAttributionValue(params.get("utm_campaign"), 120),
    utm_content: cleanAttributionValue(params.get("utm_content"), 120),
    utm_term: cleanAttributionValue(params.get("utm_term"), 120),
    has_yclid: hasYclid,
    landing_path: cleanAttributionValue(window.location.pathname || "/", 160) || "/",
    captured_at: new Date().toISOString()
  };
}

function storedAttribution(storage, key, ttlMs, { requireFlowId = false } = {}) {
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const value = JSON.parse(raw);
    const capturedAt = Date.parse(value?.captured_at || "");
    const flowId = cleanAttributionValue(value?.flow_id, 128);
    if (
      !value
      || typeof value !== "object"
      || !Number.isFinite(capturedAt)
      || Date.now() - capturedAt > ttlMs
      || (requireFlowId && !flowId)
    ) {
      storage.removeItem(key);
      return null;
    }
    return requireFlowId ? { ...value, flow_id: flowId } : value;
  } catch {
    return null;
  }
}

function readFirstTouchAttribution() {
  try {
    return storedAttribution(window.localStorage, FIRST_TOUCH_KEY, FIRST_TOUCH_TTL_MS);
  } catch {
    return null;
  }
}

function captureFirstTouchAttribution() {
  if (isAdminRoute) return {};
  const existing = readFirstTouchAttribution();
  if (existing) return existing;
  const attribution = attributionFromCurrentLocation();
  try {
    window.localStorage.setItem(FIRST_TOUCH_KEY, JSON.stringify(attribution));
  } catch {
    // Attribution must never block the product flow.
  }
  return attribution;
}

function isAdvertisingEntryLocation() {
  const path = (window.location.pathname || "/").replace(/\/+$/, "") || "/";
  const campaignPath = path === "/pet" || path === "/food/dog" || path === "/food/cat"
    || path === "/check" || path.startsWith("/check/");
  const params = new URLSearchParams(window.location.search);
  const campaignQuery = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "yclid"]
    .some((key) => Boolean(cleanAttributionValue(params.get(key), 120)));
  return campaignPath || campaignQuery;
}

function readCurrentTouchAttribution() {
  try {
    return storedAttribution(window.sessionStorage, CURRENT_TOUCH_KEY, CURRENT_TOUCH_TTL_MS, { requireFlowId: true });
  } catch {
    return null;
  }
}

function captureCurrentTouchAttribution() {
  if (isAdminRoute) return {};
  if (currentTouchAttribution) return currentTouchAttribution;

  if (!isAdvertisingEntryLocation()) {
    const existing = readCurrentTouchAttribution();
    if (existing) {
      currentTouchAttribution = existing;
      return currentTouchAttribution;
    }
  }

  currentTouchAttribution = {
    ...attributionFromCurrentLocation(),
    flow_id: cleanAttributionValue(createFlowId(), 128)
  };
  try {
    window.sessionStorage.setItem(CURRENT_TOUCH_KEY, JSON.stringify(currentTouchAttribution));
  } catch {
    // Attribution must never block the product flow.
  }
  return currentTouchAttribution;
}

function getFunnelSessionId() {
  return captureCurrentTouchAttribution().flow_id || cleanAttributionValue(createFlowId(), 128);
}

function attributionEventMetadata() {
  const first = captureFirstTouchAttribution();
  const current = captureCurrentTouchAttribution();
  return {
    traffic_source: current.traffic_source,
    utm_source: current.utm_source,
    utm_medium: current.utm_medium,
    utm_campaign: current.utm_campaign,
    utm_content: current.utm_content,
    utm_term: current.utm_term,
    has_yclid: Boolean(current.has_yclid),
    landing_path: current.landing_path,
    current_flow_id: current.flow_id,
    current_traffic_source: current.traffic_source,
    current_utm_source: current.utm_source,
    current_utm_medium: current.utm_medium,
    current_utm_campaign: current.utm_campaign,
    current_utm_content: current.utm_content,
    current_utm_term: current.utm_term,
    current_has_yclid: Boolean(current.has_yclid),
    current_landing_path: current.landing_path,
    first_traffic_source: first.traffic_source,
    first_utm_source: first.utm_source,
    first_utm_medium: first.utm_medium,
    first_utm_campaign: first.utm_campaign,
    first_utm_content: first.utm_content,
    first_utm_term: first.utm_term,
    first_has_yclid: Boolean(first.has_yclid),
    first_landing_path: first.landing_path
  };
}

function attributionRequestHeaders() {
  const first = captureFirstTouchAttribution();
  const current = captureCurrentTouchAttribution();
  const headers = {
    "X-Tvv-Traffic-Source": current.traffic_source,
    "X-Tvv-Utm-Source": current.utm_source,
    "X-Tvv-Utm-Medium": current.utm_medium,
    "X-Tvv-Utm-Campaign": current.utm_campaign,
    "X-Tvv-Utm-Content": current.utm_content,
    "X-Tvv-Utm-Term": current.utm_term,
    "X-Tvv-Landing-Path": current.landing_path,
    "X-Tvv-Has-Yclid": current.has_yclid ? "1" : "0",
    "X-Tvv-Current-Flow-Id": current.flow_id,
    "X-Tvv-Funnel-Session": current.flow_id,
    "X-Tvv-First-Traffic-Source": first.traffic_source,
    "X-Tvv-First-Utm-Source": first.utm_source,
    "X-Tvv-First-Utm-Medium": first.utm_medium,
    "X-Tvv-First-Utm-Campaign": first.utm_campaign,
    "X-Tvv-First-Utm-Content": first.utm_content,
    "X-Tvv-First-Utm-Term": first.utm_term,
    "X-Tvv-First-Landing-Path": first.landing_path,
    "X-Tvv-First-Has-Yclid": first.has_yclid ? "1" : "0"
  };
  return Object.fromEntries(
    Object.entries(headers)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([name, value]) => [name, encodeURIComponent(String(value))])
  );
}

function safeMetrikaParams(metadata = {}) {
  const allowedKeys = new Set([
    "slug", "pet_type", "level", "urgency", "target", "provider", "path", "has_pet",
    "traffic_source", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "landing_path",
    "current_flow_id", "current_traffic_source", "current_utm_source", "current_utm_medium",
    "current_utm_campaign", "current_utm_content", "current_utm_term", "current_has_yclid", "current_landing_path",
    "first_traffic_source", "first_utm_source", "first_utm_medium", "first_utm_campaign",
    "first_utm_content", "first_utm_term", "first_has_yclid", "first_landing_path"
  ]);
  const params = {};
  for (const [key, value] of Object.entries(metadata || {})) {
    if (!allowedKeys.has(key)) continue;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      params[key] = value;
    }
  }
  return params;
}

function trackMetrikaGoal(eventType, metadata = {}) {
  const goal = METRIKA_GOALS[eventType];
  if (!goal || typeof window.ym !== "function") return false;
  try {
    window.ym(METRIKA_ID, "reachGoal", goal, safeMetrikaParams(metadata));
    return true;
  } catch {
    // Metrics must never break the product flow.
    return false;
  }
}

function trackMetrikaGoalOnce(eventType, dedupeKey, metadata = {}) {
  const cleanKey = cleanAttributionValue(dedupeKey, 160);
  if (!cleanKey) return false;
  const key = `${eventType}:${cleanKey}`;
  if (sentMetrikaGoalKeys.has(key)) return false;
  const sent = trackMetrikaGoal(eventType, metadata);
  if (sent) sentMetrikaGoalKeys.add(key);
  return sent;
}

function analyticsPetType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["cat", "кошка", "кот"].includes(normalized)) return "cat";
  if (["dog", "собака", "пес", "пёс"].includes(normalized)) return "dog";
  return "other";
}

function trackFunnel(eventType, metadata = {}) {
  if (isAdminRoute) return;
  const enrichedMetadata = { ...metadata, ...attributionEventMetadata() };
  trackMetrikaGoal(eventType, enrichedMetadata);
  fetch("/api/funnel/event", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...attributionRequestHeaders() },
    credentials: "same-origin",
    body: JSON.stringify({
      event_type: eventType,
      session_id: getFunnelSessionId(),
      metadata: enrichedMetadata
    })
  }).catch(() => {});
}

function trackAuthLoginSuccess(provider) {
  trackMetrikaGoal("auth.login_success", {
    ...attributionEventMetadata(),
    provider
  });
}

function normalizeStartupAction(action) {
  return STARTUP_ACTIONS.has(action) ? action : "";
}

function getMaxMiniAppStartParam() {
  const webApp = window.WebApp;
  const unsafeParam = webApp?.initDataUnsafe?.start_param;
  if (typeof unsafeParam === "string" && unsafeParam.trim()) {
    return unsafeParam.trim();
  }
  const initData = typeof webApp?.initData === "string" ? webApp.initData.trim() : "";
  if (!initData) return "";
  try {
    return new URLSearchParams(initData).get("start_param") || "";
  } catch {
    return "";
  }
}

function getStartupAction() {
  const queryAction = new URLSearchParams(window.location.search).get("action") || "";
  const queuedAction = sessionStorage.getItem(PENDING_STARTUP_ACTION_KEY) || "";
  const action = normalizeStartupAction(queryAction || getMaxMiniAppStartParam() || queuedAction);
  return action && action !== consumedStartupAction ? action : "";
}
let maxMiniAppAuthTried = false;

const authView = document.querySelector("#authView");
const publicCheckView = document.querySelector("#publicCheckView");
const mainView = document.querySelector("main");
let dashboardView = document.querySelector("#dashboardView");
let adminView = document.querySelector("#adminView");
let adminLoginPanel = null;
let adminDashboardPanel = null;
let adminLoginForm = null;
let adminUsernameInput = null;
let adminPasswordInput = null;
let adminLoginHint = null;
let adminCredentialsForm = null;
let adminCurrentPasswordInput = null;
let adminNewUsernameInput = null;
let adminNewPasswordInput = null;
let adminCredentialsHint = null;
let adminRefreshBtn = null;
let adminLogoutBtn = null;
let adminContent = null;
let adminMarkupReady = false;
const ADMIN_PAGES = [
  { id: "overview", label: "Обзор" },
  { id: "funnel", label: "Воронка" },
  { id: "traffic", label: "Посещения" },
  { id: "system", label: "Система" },
  { id: "payments", label: "Платежи" },
  { id: "users", label: "Пользователи" },
  { id: "audit", label: "Журнал" }
];
let adminDashboardData = null;
let adminSystemData = null;
let adminCurrentPage = "overview";
const openCheckBtn = document.querySelector("#openCheckBtn");
const openLoginBtn = document.querySelector("#openLoginBtn");
const petOnboardingDialog = document.querySelector("#petOnboardingDialog");
const petOnboardingCloseBtn = document.querySelector("#petOnboardingCloseBtn");
const publicPetOnboardingForm = document.querySelector("#publicPetOnboardingForm");
const petOnboardingHint = document.querySelector("#petOnboardingHint");
const authDialog = document.querySelector("#authDialog");
const authDialogTitle = document.querySelector("#authDialogTitle");
const authDialogLead = document.querySelector("#authDialogLead");
const authCloseBtn = document.querySelector("#authCloseBtn");
const emailForm = document.querySelector("#emailForm");
const emailInput = document.querySelector("#emailInput");
const codeInput = document.querySelector("#codeInput");
const codeRow = document.querySelector("#codeRow");
const verifyCodeBtn = document.querySelector("#verifyCodeBtn");
const emailHint = document.querySelector("#emailHint");
const messengerHint = document.querySelector("#messengerHint");
const telegramBtn = document.querySelector("#telegramBtn");
const maxBtn = document.querySelector("#maxBtn");
const installBtn = document.querySelector("#installBtn");
let workspace = document.querySelector("#workspace");
const privacyConsent = document.querySelector("#privacyConsent");
const legalModal = document.querySelector("#legalModal");
const legalModalTitle = document.querySelector("#legalModalTitle");
const legalContent = document.querySelector("#legalContent");
const legalCloseBtn = document.querySelector("#legalCloseBtn");
const cookieBanner = document.querySelector("#cookieBanner");
const cookieAcceptBtn = document.querySelector("#cookieAcceptBtn");
const cookieNecessaryBtn = document.querySelector("#cookieNecessaryBtn");

const DASHBOARD_VIEW_HTML = `
  <section class="dashboard-view" id="dashboardView" hidden>
    <div class="dashboard-head">
      <div>
        <p class="section-label">Личный кабинет</p>
        <h1>Здоровье питомца</h1>
      </div>
      <button class="profile-button" data-action="account" type="button">
        <span class="app-icon icon-user-round" aria-hidden="true"></span>
        <span>Профиль</span>
      </button>
    </div>

    <nav class="app-navigation" aria-label="Разделы личного кабинета">
      <button class="app-nav-item is-active" data-action="home" type="button">
        <span class="app-icon icon-house" aria-hidden="true"></span>
        <span>Главная</span>
      </button>
      <button class="app-nav-item" data-action="pets" type="button">
        <span class="app-icon icon-paw-print" aria-hidden="true"></span>
        <span>Питомцы</span>
      </button>
      <button class="app-nav-item" data-action="triage" type="button">
        <span class="app-icon icon-heart-pulse" aria-hidden="true"></span>
        <span>Изменения</span>
      </button>
      <button class="app-nav-item" data-action="reminders" type="button">
        <span class="app-icon icon-bell" aria-hidden="true"></span>
        <span>Напоминания</span>
      </button>
      <button class="app-nav-item" data-action="more" type="button">
        <span class="app-icon icon-ellipsis" aria-hidden="true"></span>
        <span>Ещё</span>
      </button>
    </nav>

    <div class="workspace" id="workspace">
      <h2>Ваш кабинет</h2>
      <p>Добавьте питомца или расскажите, что случилось.</p>
    </div>
  </section>
`;

const ADMIN_VIEW_HTML = `<section class="admin-view notranslate" id="adminView" translate="no" hidden></section>`;

const reminderTypes = [
  ["vaccine", "Вакцинация"],
  ["parasites", "Обработка от паразитов"],
  ["checkup", "Плановый осмотр"],
  ["grooming", "Груминг"],
  ["diet", "Корм/диета"],
  ["custom", "Другое"]
];

const reminderDefaultTitles = {
  vaccine: "Вакцинация",
  parasites: "Обработка от паразитов",
  checkup: "Плановый осмотр",
  grooming: "Груминг",
  diet: "Корм/диета",
  custom: "Напоминание"
};

const periodicityOptions = [
  ["once", "Один раз"],
  ["daily", "Ежедневно"],
  ["weekly", "Еженедельно"],
  ["monthly", "Ежемесячно"],
  ["every_3_months", "Раз в 3 месяца"],
  ["every_6_months", "Раз в 6 месяцев"],
  ["yearly", "Раз в год"]
];

function periodicityLabel(value) {
  return periodicityOptions.find(([key]) => key === value)?.[1] || "Один раз";
}

function createElementFromHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

function ensureDashboardView() {
  if (dashboardView && document.body.contains(dashboardView)) return dashboardView;
  const dashboardNode = createElementFromHtml(DASHBOARD_VIEW_HTML);
  if (!dashboardNode || !mainView) return null;
  mainView.append(dashboardNode);
  dashboardView = document.querySelector("#dashboardView");
  workspace = document.querySelector("#workspace");
  return dashboardView;
}

function removeDashboardView() {
  if (dashboardView && document.body.contains(dashboardView)) dashboardView.remove();
  dashboardView = null;
  workspace = null;
}

function setDashboardActiveAction(action) {
  const navAction = ["home", "pets", "triage", "reminders"].includes(action) ? action : "more";
  document.querySelectorAll(".app-nav-item").forEach((button) => {
    const isActive = button.dataset.action === navAction;
    button.classList.toggle("is-active", isActive);
    if (isActive) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function ensureAdminView() {
  if (adminView && document.body.contains(adminView)) return adminView;
  const adminNode = createElementFromHtml(ADMIN_VIEW_HTML);
  if (!adminNode || !mainView) return null;
  mainView.append(adminNode);
  adminView = document.querySelector("#adminView");
  adminMarkupReady = false;
  return adminView;
}

function setAuthMode(isAuthed) {
  if (isAuthed) {
    ensureDashboardView();
  }
  authView.hidden = isAuthed;
  if (dashboardView) dashboardView.hidden = !isAuthed;
  if (adminView) adminView.hidden = true;
  document.body.classList.toggle("is-authed", Boolean(isAuthed));
  document.body.classList.remove("is-admin");
  if (isAuthed) closeAuthDialog();
  if (!isAuthed) removeDashboardView();
}

function setAdminMode(isAuthed) {
  ensureAdminView();
  ensureAdminMarkup();
  if (authView) authView.hidden = true;
  if (dashboardView) dashboardView.hidden = true;
  if (adminView) adminView.hidden = false;
  if (adminLoginPanel) adminLoginPanel.hidden = isAuthed;
  if (adminDashboardPanel) adminDashboardPanel.hidden = !isAuthed;
  document.body.classList.toggle("is-admin", true);
  document.body.classList.remove("is-authed");
}

function openAuthDialog({ lead = "", startupAction = "" } = {}) {
  authDialogContextLead = String(lead || "").trim();
  const normalizedAction = normalizeStartupAction(startupAction);
  if (normalizedAction) {
    consumedStartupAction = "";
    sessionStorage.setItem(PENDING_STARTUP_ACTION_KEY, normalizedAction);
  }
  trackFunnel("auth.dialog_open", { source: "dialog" });
  updateAuthDialogForPendingSave();
  authDialog.hidden = false;
  authDialog.setAttribute("aria-hidden", "false");
  const focusTarget = emailInput || maxBtn || telegramBtn;
  setTimeout(() => focusTarget?.focus(), 0);
}

function openAuthDialogFromLink() {
  if (!isAuthLinkRequested()) return false;
  openAuthDialog();
  clearAuthLinkRequest();
  return true;
}

function closeAuthDialog() {
  if (!authDialog) return;
  authDialog.hidden = true;
  authDialog.setAttribute("aria-hidden", "true");
  authDialogContextLead = "";
  updateAuthDialogForPendingSave();
}

function openPetOnboarding() {
  if (!petOnboardingDialog) return;
  const pending = pendingPetCreate();
  if (pending && publicPetOnboardingForm) {
    const typeInput = publicPetOnboardingForm.querySelector(`input[name="pet_type"][value="${pending.pet_type}"]`);
    if (typeInput) typeInput.checked = true;
    const nameInput = publicPetOnboardingForm.querySelector("input[name='pet_name']");
    if (nameInput) nameInput.value = pending.pet_name;
  }
  petOnboardingDialog.hidden = false;
  petOnboardingDialog.setAttribute("aria-hidden", "false");
  setTimeout(() => publicPetOnboardingForm?.querySelector("input[name='pet_type']:checked, input[name='pet_type']")?.focus(), 0);
}

function closePetOnboarding() {
  if (!petOnboardingDialog) return;
  petOnboardingDialog.hidden = true;
  petOnboardingDialog.setAttribute("aria-hidden", "true");
}

async function performLogout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } catch {
    // Local logout still needs to happen even if the session is already expired.
  }
  stopTelegramPolling();
  clearTelegramLogin();
  stopMaxPolling();
  clearMaxLogin();
  clearAccountState();
  setAuthMode(false);
}

function readableError(message) {
  const text = String(message || "");
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(text)) {
    return "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";
  }
  const messages = {
    email_not_configured: "Вход по email временно недоступен. Попробуйте позже или используйте Telegram/MAX для подтверждения входа.",
    email_delivery_failed: "Не удалось отправить письмо. Проверьте адрес или попробуйте позже.",
    email_registration_russian_domain_required: "Регистрация по email доступна только с российской почтой .ru или .рф. Войдите через Telegram или MAX либо укажите другую почту.",
    email_code_too_many_requests: "Код уже отправлен. Подождите около минуты перед повторной отправкой.",
    email_code_hour_limit: "Слишком много кодов на этот email. Попробуйте позже.",
    invalid_code: "Код не подошёл. Проверьте цифры и попробуйте ещё раз.",
    code_attempts_exceeded: "Слишком много неверных попыток. Запросите новый код.",
    code_expired_or_not_found: "Код истёк. Запросите новый код.",
    payment_provider_not_configured: "Оплата в веб-кабинете временно недоступна. Попробуйте позже или напишите в поддержку.",
    payment_provider_error: "Платёжный сервис временно не ответил. Попробуйте позже.",
    payment_confirmation_missing: "Не удалось получить ссылку оплаты. Попробуйте позже.",
    payment_not_found: "Платёж не найден. Сначала нажмите «Оплатить Plus».",
    payment_verification_failed: "Платёж не прошёл серверную проверку. Напишите в поддержку.",
    push_not_configured: "Напоминания на этом устройстве временно недоступны. Остальные функции работают как обычно.",
    push_unsupported: "Этот браузер не поддерживает напоминания.",
    push_permission_denied: "Браузер не дал разрешение на уведомления.",
    rate_limited: "Слишком много запросов. Подождите немного и попробуйте снова.",
    check_preview_already_used: "Пробный разбор уже использован. Войдите или зарегистрируйтесь, чтобы делать следующие разборы в личном кабинете.",
    check_preview_rate_limited: "Пробные разборы временно ограничены. Войдите через Telegram или MAX, чтобы продолжить в личном кабинете.",
    check_preview_ip_limit: "Слишком много пробных разборов с этой сети. Попробуйте позже или войдите через Telegram/MAX.",
    check_preview_burst_limit: "Слишком много быстрых запросов подряд. Подождите минуту и попробуйте снова.",
    check_preview_text_too_short: "Опишите состояние чуть подробнее: что произошло, когда началось и как питомец ведёт себя сейчас.",
    invalid_check_preview: "Не удалось принять форму. Обновите страницу и попробуйте ещё раз.",
    invalid_check_preview_save: "Не удалось сохранить пробный разбор. Откройте кабинет и сделайте новый разбор там.",
    invalid_check_preview_pet_selection: "Выберите одну карточку питомца или создание новой.",
    check_preview_pet_required: "Выберите питомца, в историю которого нужно сохранить результат.",
    check_preview_pet_not_found: "Выбранная карточка питомца больше недоступна. Выберите другую.",
    check_preview_pet_type_mismatch: "Результат можно сохранить только в карточку питомца того же вида.",
    food_species_mismatch: "Сервер вернул ответ для другого вида питомца. Обновите страницу и попробуйте снова.",
    pet_limit_reached: "Лимит питомцев по текущему тарифу исчерпан. Существующие карточки и записи остаются доступны.",
    reminder_limit_reached: "Лимит активных напоминаний по текущему тарифу исчерпан.",
    summary_period_plus_required: "Периоды 90 дней и вся история доступны в Plus.",
    summary_export_plus_required: "Печать и сохранение сводки в PDF доступны в Plus.",
    invalid_deletion_confirmation: "Для запроса удаления нужно ввести слово УДАЛИТЬ."
  };
  return messages[text] || text || "Не удалось выполнить действие.";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function nl2br(value) {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function pendingPublicCheckSave() {
  try {
    const raw = localStorage.getItem(PENDING_CHECK_SAVE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload || typeof payload !== "object") return null;
    if (!payload.text || !payload.answer) return null;
    return payload;
  } catch {
    localStorage.removeItem(PENDING_CHECK_SAVE_KEY);
    return null;
  }
}

function pendingPublicFoodSave() {
  try {
    const raw = localStorage.getItem(PENDING_FOOD_SAVE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload || typeof payload !== "object") return null;
    if (!payload.query || !payload.pet_type) return null;
    return payload;
  } catch {
    localStorage.removeItem(PENDING_FOOD_SAVE_KEY);
    return null;
  }
}

function pendingPublicSave() {
  return pendingPublicCheckSave() || pendingPublicFoodSave();
}

function pendingPetCreate() {
  try {
    const raw = sessionStorage.getItem(PENDING_PET_CREATE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!payload?.pet_name || !["собака", "кошка"].includes(payload.pet_type)) return null;
    return payload;
  } catch {
    sessionStorage.removeItem(PENDING_PET_CREATE_KEY);
    return null;
  }
}

function storePendingPetCreate(payload) {
  if (!payload?.pet_name || !payload?.pet_type) return;
  sessionStorage.setItem(PENDING_PET_CREATE_KEY, JSON.stringify(payload));
  updateAuthDialogForPendingSave();
}

function clearPendingPetCreate() {
  sessionStorage.removeItem(PENDING_PET_CREATE_KEY);
  updateAuthDialogForPendingSave();
}

function trackServiceGoals(data, keyPrefix = "record") {
  const service = data?.service || {};
  if (service.first_record_saved) {
    trackMetrikaGoalOnce("service.first_record_saved", `${keyPrefix}:first-record`, attributionEventMetadata());
  }
  if (service.activated) {
    trackMetrikaGoalOnce("service.activated", `${keyPrefix}:activated`, attributionEventMetadata());
  }
}

function publicCheckPreviewAlreadyUsed() {
  try {
    return localStorage.getItem(PUBLIC_CHECK_USED_KEY) === "1";
  } catch {
    return false;
  }
}

function markPublicCheckPreviewUsed() {
  try {
    localStorage.setItem(PUBLIC_CHECK_USED_KEY, "1");
  } catch {
    // A storage failure must not hide a medical result or block authentication.
  }
}

function storePendingPublicCheckSave(payload) {
  if (!payload?.text || !payload?.answer) return;
  localStorage.removeItem(PENDING_FOOD_SAVE_KEY);
  localStorage.setItem(PENDING_CHECK_SAVE_KEY, JSON.stringify(payload));
}

function clearPendingPublicCheckSave() {
  localStorage.removeItem(PENDING_CHECK_SAVE_KEY);
  publicCheckView?.classList.remove("has-pending-save");
  updateAuthDialogForPendingSave();
}

function storePendingPublicFoodSave(payload) {
  if (!payload?.query || !payload?.pet_type) return;
  localStorage.removeItem(PENDING_CHECK_SAVE_KEY);
  localStorage.setItem(PENDING_FOOD_SAVE_KEY, JSON.stringify(payload));
}

function clearPendingPublicFoodSave() {
  localStorage.removeItem(PENDING_FOOD_SAVE_KEY);
  publicCheckView?.classList.remove("has-pending-save");
  updateAuthDialogForPendingSave();
}

function storePendingPublicSave(payload) {
  if (payload?.save_kind === "food") storePendingPublicFoodSave(payload);
  else storePendingPublicCheckSave(payload);
}

function pendingPublicCheckPetType(pending) {
  const value = String(pending?.pet_type || "").trim().toLowerCase();
  if (["cat", "кошка", "кот"].includes(value)) return "кошка";
  if (["dog", "собака", "пес", "пёс"].includes(value)) return "собака";
  return "питомец";
}

function pendingPublicCheckPetMatches(pet, pending) {
  const expectedType = pendingPublicCheckPetType(pending);
  if (expectedType === "питомец") return true;
  return String(pet?.pet_type || "").trim().toLowerCase() === expectedType;
}

function pendingPublicCheckNeedsPetSelection(pending) {
  if (pending?.pet_id || pending?.create_pet) return false;
  if (!state.pets.length) return false;
  return state.pets.length !== 1 || !pendingPublicCheckPetMatches(state.pets[0], pending);
}

function pendingSaveCopy(pending) {
  if (pending?.save_kind === "food") {
    return {
      section: "Сохранение ответа",
      pending: "Ответ ещё не сохранён.",
      submit: "Сохранить ответ",
    };
  }
  return {
    section: "Сохранение случая",
    pending: "Случай ещё не сохранён.",
    submit: "Сохранить случай",
  };
}

function renderPendingPublicCheckPetSelection(pending) {
  ensureDashboardView();
  const copy = pendingSaveCopy(pending);
  const expectedType = pendingPublicCheckPetType(pending);
  const compatiblePets = state.pets.filter((pet) => pendingPublicCheckPetMatches(pet, pending));
  const petTypeLabel = expectedType === "кошка" ? "кошки" : expectedType === "собака" ? "собаки" : "питомца";
  const existingChoices = compatiblePets
    .map((pet) => `
      <label class="checkbox-row">
        <input name="pet_choice" value="${Number(pet.id)}" type="radio" required />
        Сохранить в историю «${escapeHtml(pet.pet_name || "Питомец")}»
      </label>
    `)
    .join("");

  setWorkspace(`
    <div class="workspace-head">
      <div>
        <p class="section-label">${copy.section}</p>
        <h2>Выберите питомца</h2>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
    </div>
    <div class="notice">
      <strong>${copy.pending}</strong>
      <p>Чтобы он появился в истории, укажите карточку ${petTypeLabel}.</p>
    </div>
    ${compatiblePets.length ? "" : `<div class="care-note">Подходящей карточки ${petTypeLabel} пока нет. Можно создать новую и сохранить результат в неё.</div>`}
    <form class="form-grid one-column" id="pendingCheckPetForm">
      <fieldset>
        <legend>Куда сохранить результат?</legend>
        ${existingChoices}
        <label class="checkbox-row">
          <input name="pet_choice" value="new" type="radio" required />
          Создать новую карточку ${petTypeLabel}
        </label>
      </fieldset>
      <p class="field-error" data-pet-choice-error role="alert" hidden>Выберите карточку или создание новой.</p>
      <button class="primary-button" type="submit">${copy.submit}</button>
    </form>
  `);

  document.querySelector("#pendingCheckPetForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const choice = String(new FormData(form).get("pet_choice") || "");
    const errorEl = form.querySelector("[data-pet-choice-error]");
    if (!choice) {
      if (errorEl) errorEl.hidden = false;
      form.querySelector("input[name='pet_choice']")?.focus();
      return;
    }

    const nextPending = { ...pending, create_pet: choice === "new" };
    delete nextPending.pet_id;
    if (choice !== "new") nextPending.pet_id = Number(choice);
    storePendingPublicSave(nextPending);
    const submitButton = form.querySelector("button[type='submit']");
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Сохраняю…";
    }
    await completePendingSaveAfterLogin();
  });
}

function publicCheckSavePayload(data, variant, formValues) {
  return {
    pet_type: formValues.pet_type || "unknown",
    age: formValues.age || "",
    text: formValues.text || "",
    answer: data.answer || "",
    urgency: data.urgency || "",
    urgency_label: data.urgency_label || "",
    summary: data.summary || "",
    model: data.model || "",
    prompt_tokens: data.prompt_tokens || 0,
    completion_tokens: data.completion_tokens || 0,
    total_tokens: data.total_tokens || 0,
    landing_slug: variant.slug,
    session_id: getFunnelSessionId(),
    ...attributionEventMetadata(),
    created_at: new Date().toISOString()
  };
}

function renderCheckSaveCallout() {
  return `
    <div class="check-save-callout">
      <div>
        <strong>Сохранить случай</strong>
        <p>Вернитесь к результату и проверьте, стало ли питомцу лучше или хуже.</p>
      </div>
      <button class="primary-button" data-check-save type="button">${CHECK_SAVE_CTA}</button>
    </div>
  `;
}

function renderCheckStickySave() {
  return `
    <div class="check-sticky-save" data-check-save-sticky role="region" aria-live="polite" aria-label="Сохранить случай" hidden>
      <div>
        <strong>Сохранить случай</strong>
        <span>Проверить позже, стало ли лучше или хуже</span>
      </div>
      <button class="primary-button compact" data-check-save type="button">${CHECK_SAVE_CTA}</button>
    </div>
  `;
}

function scheduleCheckStickySave(resultEl, level) {
  const sticky = resultEl?.querySelector("[data-check-save-sticky]");
  const callout = resultEl?.querySelector(".check-save-callout");
  if (!sticky || !callout) return;
  let revealed = false;
  let observer = null;
  const reveal = () => {
    if (revealed || !sticky.isConnected) return;
    revealed = true;
    sticky.hidden = false;
    sticky.classList.add("is-visible");
    observer?.disconnect();
  };
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.35)) reveal();
    }, { threshold: [0.35] });
    observer.observe(callout);
  }
  if (level !== "red") window.setTimeout(reveal, 8000);
}

function updateAuthDialogForPendingSave() {
  const pendingPet = pendingPetCreate();
  const pendingCheck = pendingPublicCheckSave();
  const pendingFood = pendingPublicFoodSave();
  const pending = pendingPet || pendingCheck || pendingFood;
  authDialog?.classList.toggle("auth-save-intent", Boolean(pending));
  if (authDialogTitle) {
    const petType = pendingPublicCheckPetType(pending);
    const petLabel = petType === "собака" ? "собаки" : petType === "кошка" ? "кошки" : "питомца";
    authDialogTitle.textContent = pendingPet
      ? `Сохранить карточку «${pendingPet.pet_name}»`
      : pendingCheck
        ? `Сохранить случай для ${petLabel}`
        : pendingFood
          ? `Сохранить ответ для ${petLabel}`
          : "Войдите или создайте личный кабинет";
  }
  if (!authDialogLead) return;
  authDialogLead.textContent = pendingPet
    ? "После входа карточка питомца создастся автоматически и только один раз."
    : pending
    ? "После входа автоматически вернём вас к результату и сохраним его."
    : authDialogContextLead || AUTH_DIALOG_DEFAULT_LEAD;
}

async function completePendingSaveAfterLogin() {
  if (pendingPetCreate()) return completePendingPetAfterLogin();
  if (pendingPublicFoodSave()) return completePendingPublicFoodAfterLogin();
  return completePendingPublicCheckAfterLogin();
}

async function completePendingPetAfterLogin() {
  const pending = pendingPetCreate();
  if (!pending) return false;
  ensureDashboardView();
  setWorkspace(`<div class="notice" role="status"><strong>Создаю карточку питомца…</strong></div>`);
  try {
    const data = await api("/api/pets", {
      method: "POST",
      body: JSON.stringify({
        pet_type: pending.pet_type,
        pet_name: pending.pet_name,
        client_request_id: pending.client_request_id,
        is_main: true
      })
    });
    clearPendingPetCreate();
    await refreshAccountState();
    await refreshPets();
    state.currentPetId = data.item.id;
    if (data.created) {
      trackMetrikaGoalOnce("pet.created", `pet:${data.item.id}`, {
        ...attributionEventMetadata(),
        pet_type: analyticsPetType(data.item.pet_type),
        has_pet: true
      });
    }
    setWorkspace(`
      <div class="workspace-head">
        <div><p class="section-label">Карточка создана</p><h2>Что сохраним первым для «${escapeHtml(data.item.pet_name)}»?</h2></div>
      </div>
      <div class="care-note">Первая запись активирует постоянную историю питомца.</div>
      <div class="pet-action-grid first-value-actions">
        <button class="menu-card" data-pet-view="weight" data-pet-id="${data.item.id}" type="button">${renderAppIcon("scale")}<span><strong>Записать вес</strong><small>Начать динамику веса</small></span></button>
        <button class="menu-card" data-pet-view="observations" data-pet-id="${data.item.id}" type="button">${renderAppIcon("clipboard-list")}<span><strong>Сохранить наблюдение</strong><small>Аппетит, активность, поведение</small></span></button>
        <button class="menu-card" data-pet-view="reminders" data-pet-id="${data.item.id}" type="button">${renderAppIcon("bell")}<span><strong>Добавить важную дату</strong><small>Прививка, обработка или осмотр</small></span></button>
        <button class="menu-card" data-action="food" type="button">${renderAppIcon("utensils")}<span><strong>Проверить продукт</strong><small>Сохранить ответ в карточку</small></span></button>
        <button class="menu-card" data-pet-view="triage" data-pet-id="${data.item.id}" type="button">${renderAppIcon("heart-pulse")}<span><strong>Рассказать, что изменилось</strong><small>Сохранить разбор в историю</small></span></button>
      </div>
    `);
    return true;
  } catch (error) {
    setWorkspace(`<div class="notice danger" role="alert"><strong>Не удалось создать карточку</strong><p>${escapeHtml(readableError(error.message))}</p><button class="secondary-button compact" data-action="pets" type="button">Открыть питомцев</button></div>`);
    return true;
  }
}

async function completePendingPublicCheckAfterLogin() {
  const pending = pendingPublicCheckSave();
  if (!pending) return false;
  ensureDashboardView();
  try {
    await refreshPets();
    if (pendingPublicCheckNeedsPetSelection(pending)) {
      renderPendingPublicCheckPetSelection(pending);
      return true;
    }

    const savePayload = { ...pending };
    if (!savePayload.pet_id && !savePayload.create_pet) {
      if (!state.pets.length) savePayload.create_pet = true;
      else if (state.pets.length === 1 && pendingPublicCheckPetMatches(state.pets[0], savePayload)) {
        savePayload.pet_id = Number(state.pets[0].id);
      }
    }
    storePendingPublicCheckSave(savePayload);
    setWorkspace(`<div class="notice check-saved-state">Сохраняю пробный разбор в личный кабинет...</div>`);
    const data = await api("/api/check/preview/save", {
      method: "POST",
      body: JSON.stringify(savePayload)
    });
    if (!data.pet?.id) throw new Error("check_preview_pet_required");
    trackServiceGoals(data, `check:${data.item?.id || data.pet.id}`);
    clearPendingPublicCheckSave();
    await refreshAccountState();
    await refreshPets();
    state.currentPetId = data.pet.id;
    const petName = `«${escapeHtml(data.pet.pet_name || "Питомец")}»`;
    trackMetrikaGoal("check.saved_after_login", {
      ...attributionEventMetadata(),
      slug: savePayload.landing_slug || "general",
      pet_type: savePayload.pet_type || "unknown",
      urgency: savePayload.urgency || "",
      has_pet: true
    });
    setWorkspace(`
      <div class="workspace-head">
        <h2>Результат сохранён</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
      </div>
      <div class="notice success check-saved-state">
        <strong>Готово: результат появился в истории ${petName}.</strong>
        <p>Теперь к нему можно вернуться в любой момент.</p>
        <div class="next-actions">
          <button class="primary-button" data-action="triage" type="button">Рассказать ещё раз</button>
          <button class="secondary-button" data-open-pet="${Number(data.pet.id)}" type="button">Открыть карточку питомца</button>
        </div>
      </div>
    `);
    return true;
  } catch (error) {
    const selectionErrors = new Set([
      "check_preview_pet_required",
      "check_preview_pet_not_found",
      "check_preview_pet_type_mismatch",
      "invalid_check_preview_pet_selection"
    ]);
    if (selectionErrors.has(error.message)) {
      const retryPending = { ...(pendingPublicCheckSave() || pending), create_pet: false };
      delete retryPending.pet_id;
      storePendingPublicCheckSave(retryPending);
      try {
        await refreshPets();
      } catch {
        // The selection screen still gives the user an honest retry path.
      }
      renderPendingPublicCheckPetSelection(retryPending);
      return true;
    }
    setWorkspace(`
      <div class="workspace-head">
        <h2>Сохранение не завершено</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
      </div>
      <div class="notice danger check-saved-state">
        <strong>Не удалось автоматически сохранить пробный разбор.</strong>
        <p>${escapeHtml(readableError(error.message))}</p>
        <div class="next-actions">
          <button class="primary-button" data-action="triage" type="button">Рассказать ещё раз</button>
          <button class="secondary-button" data-action="home" type="button">На главную</button>
        </div>
      </div>
    `);
    return true;
  }
}

async function completePendingPublicFoodAfterLogin() {
  const pending = pendingPublicFoodSave();
  if (!pending) return false;
  ensureDashboardView();
  try {
    await refreshPets();
    if (pendingPublicCheckNeedsPetSelection(pending)) {
      renderPendingPublicCheckPetSelection(pending);
      return true;
    }

    const savePayload = { ...pending };
    if (!savePayload.pet_id && !savePayload.create_pet) {
      if (!state.pets.length) savePayload.create_pet = true;
      else if (state.pets.length === 1 && pendingPublicCheckPetMatches(state.pets[0], savePayload)) {
        savePayload.pet_id = Number(state.pets[0].id);
      }
    }
    storePendingPublicFoodSave(savePayload);
    setWorkspace(`<div class="notice check-saved-state">Сохраняю ответ в карточку питомца…</div>`);
    const data = await api("/api/food/check/save", {
      method: "POST",
      body: JSON.stringify(savePayload),
    });
    if (!data.pet?.id) throw new Error("check_preview_pet_required");
    trackServiceGoals(data, `food:${data.item?.id || data.pet.id}`);
    clearPendingPublicFoodSave();
    await refreshAccountState();
    await refreshPets();
    state.currentPetId = data.pet.id;
    const petName = `«${escapeHtml(data.pet.pet_name || "Питомец")}»`;
    setWorkspace(`
      <div class="workspace-head">
        <h2>Ответ сохранён</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
      </div>
      <div class="notice success check-saved-state">
        <strong>Готово: ответ появился в наблюдениях ${petName}.</strong>
        <p>Теперь к нему можно вернуться в карточке питомца.</p>
        <div class="next-actions">
          <button class="primary-button" data-pet-view="observations" data-pet-id="${Number(data.pet.id)}" type="button">Открыть сохранённый ответ</button>
          <button class="secondary-button" data-action="food" type="button">Проверить ещё продукт</button>
        </div>
      </div>
    `);
    return true;
  } catch (error) {
    const selectionErrors = new Set([
      "check_preview_pet_required",
      "check_preview_pet_not_found",
      "check_preview_pet_type_mismatch",
      "invalid_check_preview_pet_selection",
    ]);
    if (selectionErrors.has(error.message)) {
      const retryPending = { ...(pendingPublicFoodSave() || pending), create_pet: false };
      delete retryPending.pet_id;
      storePendingPublicFoodSave(retryPending);
      try {
        await refreshPets();
      } catch {
        // The selection screen still gives the user an honest retry path.
      }
      renderPendingPublicCheckPetSelection(retryPending);
      return true;
    }
    setWorkspace(`
      <div class="workspace-head">
        <h2>Сохранение не завершено</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
      </div>
      <div class="notice danger check-saved-state">
        <strong>Не удалось автоматически сохранить ответ.</strong>
        <p>${escapeHtml(readableError(error.message))}</p>
        <div class="next-actions">
          <button class="primary-button" data-action="food" type="button">Проверить продукт ещё раз</button>
          <button class="secondary-button" data-action="home" type="button">На главную</button>
        </div>
      </div>
    `);
    return true;
  }
}

function isCheckLandingRoute() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return path === "/check" || path.startsWith("/check/");
}

function getCheckLandingVariant() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const slug = path.startsWith("/check/") ? path.slice("/check/".length) : "general";
  return CHECK_LANDING_VARIANTS[slug] || CHECK_LANDING_VARIANTS.general;
}

function renderExampleChips(examples) {
  return (examples || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
}

function publicCheckResultLabel(data) {
  if (data.urgency === "red") return "Нужна клиника сейчас";
  if (data.urgency === "green") return "Ответ готов";
  return "Обратите внимание";
}

function publicCheckResultClass(data) {
  if (data.urgency === "red") return "danger";
  if (data.urgency === "green") return "success";
  return "warning";
}

function revealPublicCheckState(element, { block = "start", settleViewport = false } = {}) {
  if (!element) return;
  const activeElement = document.activeElement;
  if (activeElement && activeElement !== document.body && typeof activeElement.blur === "function") {
    activeElement.blur();
  }

  const scroll = (behavior = "smooth") => {
    element.scrollIntoView({ behavior, block, inline: "nearest" });
  };
  window.requestAnimationFrame(() => scroll());

  if (!settleViewport) return;
  let viewportSettled = false;
  const finishViewportScroll = () => {
    if (viewportSettled) return;
    viewportSettled = true;
    window.visualViewport?.removeEventListener("resize", finishViewportScroll);
    window.requestAnimationFrame(() => scroll("auto"));
  };
  window.visualViewport?.addEventListener("resize", finishViewportScroll, { once: true });
  window.setTimeout(finishViewportScroll, 350);
}

function trackFunnelWhenVisible(element, eventType, metadata = {}, key = eventType) {
  if (!element || visibleFunnelEventKeys.has(key)) return;
  const send = () => {
    if (visibleFunnelEventKeys.has(key)) return;
    visibleFunnelEventKeys.add(key);
    trackFunnel(eventType, metadata);
  };
  if (!("IntersectionObserver" in window)) {
    send();
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.5)) return;
    observer.disconnect();
    send();
  }, { threshold: [0.5] });
  observer.observe(element);
}

function setPublicCheckGateState() {
  const promise = publicCheckView?.querySelector(".check-promise");
  const promiseTitle = promise?.querySelector("strong");
  const promiseHint = promise?.querySelector("span");
  const form = publicCheckView?.querySelector("#publicCheckForm");
  if (promiseTitle) promiseTitle.textContent = "Пробный разбор уже получен";
  if (promiseHint) promiseHint.textContent = "Войдите, чтобы сохранить результат и продолжить";
  if (form) form.hidden = true;
}

function renderPublicCheckAuthPrompt(message) {
  const resultEl = publicCheckView?.querySelector("#publicCheckResult");
  if (!resultEl) return;
  setPublicCheckGateState();
  publicCheckView?.classList.remove("has-pending-save");
  resultEl.innerHTML = `
    <div class="notice check-auth-notice">
      <strong>${escapeHtml(message)}</strong>
      <p>Чтобы продолжить, войдите через Telegram, MAX или электронную почту. В кабинете сохраняется история питомца.</p>
      <div class="next-actions check-result-actions">
        <button class="primary-button" data-check-save type="button">Войти и продолжить в кабинете</button>
        <a class="secondary-link compact" href="/">На главную TemichevVet</a>
        <a class="secondary-link compact" href="https://t.me/TemichevVet23_bot" target="_blank" rel="noopener">Telegram</a>
        <a class="secondary-link compact" href="https://max.ru/id230210303969_bot" target="_blank" rel="noopener">MAX</a>
      </div>
    </div>
  `;
  revealPublicCheckState(resultEl.querySelector(".check-auth-notice"));
}

function renderPublicCheckResult(data, variant, petType, formValues) {
  const resultEl = publicCheckView?.querySelector("#publicCheckResult");
  if (!resultEl) return;
  const level = data.urgency || "yellow";
  const className = publicCheckResultClass(data);
  const label = publicCheckResultLabel(data);
  const answer = data.answer || "Не удалось сформировать разбор.";
  if (data.usage_consumed) markPublicCheckPreviewUsed();
  storePendingPublicCheckSave(publicCheckSavePayload(data, variant, formValues));
  publicCheckView.classList.add("has-pending-save");
  resultEl.innerHTML = `
    <div class="result-box check-result ${className}" data-triage-answer="${escapeHtml(answer)}">
      <span class="check-result-badge">${escapeHtml(label)}</span>
      <h2>Что важно сейчас</h2>
      ${formatTriageAnswer(answer)}
    </div>
    ${renderCheckSaveCallout()}
    ${renderCheckStickySave()}
  `;
  trackFunnel("check.result_shown", { slug: variant.slug, pet_type: petType || "unknown", level });
  const saveCtaViewKey = `check-save-cta:${getFunnelSessionId()}:${variant.slug}`;
  const saveCtaMetadata = { slug: variant.slug, pet_type: petType || "unknown", level };
  trackFunnelWhenVisible(
    resultEl.querySelector(".check-save-callout"),
    "check.save_cta_view",
    saveCtaMetadata,
    saveCtaViewKey,
  );
  trackFunnelWhenVisible(
    resultEl.querySelector("[data-check-save-sticky]"),
    "check.save_cta_view",
    saveCtaMetadata,
    saveCtaViewKey,
  );
  scheduleCheckStickySave(resultEl, level);
  if (level === "red") {
    trackFunnel("check.red_flag", { slug: variant.slug, pet_type: petType || "unknown", level });
  }
  revealPublicCheckState(resultEl.querySelector(".check-result"));
}

function renderPublicCheckLanding() {
  if (!publicCheckView || !isCheckLandingRoute()) return false;
  const variant = getCheckLandingVariant();
  const previewAlreadyUsed = !state.user && publicCheckPreviewAlreadyUsed();
  document.body.classList.add("is-check-landing");
  document.title = `${variant.title} — TemichevVet`;
  const checkDescription = document.querySelector('meta[name="description"]');
  if (checkDescription) checkDescription.setAttribute("content", "Разберите изменение и сохраните ответ в истории питомца рядом с весом, питанием и важными датами.");
  const checkCanonical = document.querySelector('link[rel="canonical"]');
  if (checkCanonical) checkCanonical.setAttribute("href", "https://temichevvet.ru/check");
  let robots = document.querySelector('meta[name="robots"]');
  if (!robots) {
    robots = document.createElement("meta");
    robots.setAttribute("name", "robots");
    document.head.append(robots);
  }
  robots.setAttribute("content", "noindex,follow");
  publicCheckView.hidden = false;
  publicCheckView.classList.remove("has-pending-save");
  publicCheckView.innerHTML = `
    <div class="intro-panel check-hero">
      <div class="check-hero-copy">
        <p class="section-label">${escapeHtml(variant.label)}</p>
        <h1>${escapeHtml(variant.title)}</h1>
        <div class="check-promise" aria-label="Условия сервиса">
          <strong>${previewAlreadyUsed ? "Пробный разбор уже получен" : "Бесплатно · без регистрации"}</strong>
          <span>${previewAlreadyUsed ? "Войдите, чтобы сохранить результат и продолжить" : "Обычно 15–30 секунд"}</span>
        </div>
        <p class="lead">${escapeHtml(variant.lead)}</p>
        <div class="check-expert-trust">
          <img src="/static/assets/doctor-konstantin-cat-table-retouched.jpg" alt="Ветеринарный врач Константин Темичев с кошкой" />
          <div>
            <strong>Константин Валерьевич Темичев</strong>
            <span>ветеринарный врач</span>
          </div>
        </div>
      </div>
      <section class="check-hero-form" id="checkFormPanel" aria-labelledby="checkFormTitle">
        <h2 id="checkFormTitle">Расскажите, что происходит</h2>
      <form class="form-grid one-column check-form" id="publicCheckForm" novalidate ${previewAlreadyUsed ? "hidden" : ""}>
        <div class="check-species-control" role="radiogroup" aria-label="Тип питомца">
          <label>
            <input type="radio" name="pet_type" value="dog" ${variant.defaultPet === "dog" ? "checked" : ""} required />
            <span>Собака</span>
          </label>
          <label>
            <input type="radio" name="pet_type" value="cat" ${variant.defaultPet === "cat" ? "checked" : ""} />
            <span>Кошка</span>
          </label>
        </div>
        <p class="field-error" id="checkSpeciesError" role="alert" hidden>Выберите: кошка или собака.</p>
        <label>
          <span>Что изменилось?</span>
          <textarea name="text" placeholder="${escapeHtml(variant.placeholder)}" minlength="10" maxlength="1200" required></textarea>
        </label>
        <p class="field-error" id="checkTextError" role="alert" hidden>Добавьте немного деталей: что произошло, когда началось и как питомец ведёт себя сейчас.</p>
        <label class="check-honeypot" aria-hidden="true" tabindex="-1">
          <span>Сайт</span>
          <input name="website" autocomplete="off" tabindex="-1" />
        </label>
        <details class="check-optional">
          <summary>Возраст и тревожные признаки <span>необязательно</span></summary>
          <label>
            <span>Возраст или примерный возраст</span>
            <input name="age" placeholder="Например: 3 года, щенок, пожилая кошка" />
          </label>
          <fieldset class="check-red-flags">
            <legend>Есть что-то из этого?</legend>
            <label class="checkbox-row"><input name="red_flags" value="breathing" type="checkbox" /> Тяжело дышит или задыхается</label>
            <label class="checkbox-row"><input name="red_flags" value="consciousness" type="checkbox" /> Судороги, обморок или потеря сознания</label>
            <label class="checkbox-row"><input name="red_flags" value="poisoning" type="checkbox" /> Мог съесть опасное: лекарство, яд, шоколад, виноград</label>
            <label class="checkbox-row"><input name="red_flags" value="urination" type="checkbox" /> Не может помочиться или мочи почти нет</label>
            <label class="checkbox-row"><input name="red_flags" value="bleeding" type="checkbox" /> Кровь, сильная боль или резкое ухудшение</label>
          </fieldset>
        </details>
        <p class="check-urgent-warning">
          Если питомцу тяжело дышать, он теряет сознание, не может помочиться или есть сильное кровотечение — не ждите онлайн-разбора, сразу обратитесь в клинику.
        </p>
        <button class="primary-button" type="submit">Получить разбор</button>
        <p class="check-form-disclaimer">Сервис не ставит диагноз и не заменяет консультацию ветеринара.</p>
      </form>
      <div id="publicCheckResult"></div>
      </section>
    </div>

    <section class="content-section check-benefits" aria-labelledby="checkBenefitsTitle">
      <div class="section-head">
        <p class="section-label">После ответа</p>
        <h2 id="checkBenefitsTitle">Всё важное останется перед глазами</h2>
      </div>
      <div class="feature-card-grid">
        <article class="feature-card">
          <strong>Понятный ответ</strong>
          <p>Вы получите понятный разбор изменений и сможете сохранить его в историю питомца.</p>
        </article>
        <article class="feature-card">
          <strong>Опасные признаки сразу</strong>
          <p>Предупреждения об опасных признаках показываются до регистрации и не скрываются.</p>
        </article>
        <article class="feature-card">
          <strong>Сохранить динамику</strong>
          <p>После результата можно войти и сохранить его в истории питомца.</p>
        </article>
      </div>
    </section>
  `;

  if (checkLandingViewTrackedPath !== window.location.pathname) {
    checkLandingViewTrackedPath = window.location.pathname;
    trackFunnel("check.view", { slug: variant.slug, path: window.location.pathname });
  }

  const form = publicCheckView.querySelector("#publicCheckForm");
  const symptomsInput = form?.querySelector("textarea[name='text']");
  const speciesError = form?.querySelector("#checkSpeciesError");
  const textError = form?.querySelector("#checkTextError");
  let checkStartTracked = false;

  const trackCheckStart = (target) => {
    if (checkStartTracked) return;
    checkStartTracked = true;
    trackFunnel("check.start_click", { slug: variant.slug, target });
  };
  publicCheckView.querySelectorAll("input[name='pet_type']").forEach((input) => {
    input.addEventListener("change", () => {
      trackCheckStart("pet_type");
      if (speciesError) speciesError.hidden = true;
      trackFunnel("check.pet_selected", { slug: variant.slug, pet_type: input.value });
    });
  });
  symptomsInput?.addEventListener("focus", () => trackCheckStart("symptoms"));
  symptomsInput?.addEventListener("input", () => {
    trackCheckStart("symptoms");
    if (textError && symptomsInput.value.trim().length >= 10) textError.hidden = true;
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submittedForm = event.currentTarget;
    const formData = new FormData(submittedForm);
    const text = String(formData.get("text") || "").trim();
    const redFlags = formData.getAll("red_flags").map(String);
    const petType = String(formData.get("pet_type") || "");
    const age = String(formData.get("age") || "").trim();
    const website = String(formData.get("website") || "");
    const hasSpecies = petType === "dog" || petType === "cat";
    const hasEnoughText = text.length >= 10;
    if (speciesError) speciesError.hidden = hasSpecies;
    if (textError) textError.hidden = hasEnoughText;
    if (!hasSpecies || !hasEnoughText) {
      (hasSpecies ? symptomsInput : submittedForm.querySelector("input[name='pet_type']"))?.focus();
      return;
    }
    const previewInput = {
      pet_type: petType,
      age,
      text,
      red_flags: redFlags,
      landing_slug: variant.slug,
      session_id: getFunnelSessionId()
    };
    const resultEl = publicCheckView.querySelector("#publicCheckResult");
    const submitButton = submittedForm.querySelector("button[type='submit']");
    if (submitButton?.disabled) return;
    trackFunnel("check.submit", { slug: variant.slug, pet_type: petType });
    submittedForm.setAttribute("aria-busy", "true");
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Готовим ответ…";
    }
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="notice check-loading" role="status" aria-live="polite" aria-atomic="true">
          <strong>Готовим ответ…</strong>
          <span>Обычно это занимает 15–30 секунд. Не закрывайте страницу.</span>
        </div>
      `;
      revealPublicCheckState(resultEl.querySelector(".check-loading"), { block: "center", settleViewport: true });
    }
    try {
      const data = await api("/api/check/preview", {
        method: "POST",
        body: JSON.stringify({
          ...previewInput,
          website
        })
      });
      renderPublicCheckResult(data, variant, petType, previewInput);
    } catch (error) {
      if (resultEl) {
        const authRequired = [
          "check_preview_already_used",
          "check_preview_rate_limited",
          "check_preview_ip_limit",
          "check_preview_burst_limit"
        ].includes(error.message);
        if (authRequired) {
          if (error.message === "check_preview_already_used") markPublicCheckPreviewUsed();
          renderPublicCheckAuthPrompt(readableError(error.message));
        } else {
          resultEl.innerHTML = `<div class="notice danger" role="alert"><strong>Не получилось загрузить результат</strong><p>${escapeHtml(readableError(error.message))}</p><p>Текст остался в форме.</p><button class="secondary-button compact" data-check-retry type="button">Попробовать ещё раз</button></div>`;
          revealPublicCheckState(resultEl.querySelector(".notice.danger"));
        }
      }
    } finally {
      submittedForm.removeAttribute("aria-busy");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Узнать, что делать";
      }
    }
  });
  publicCheckView.addEventListener("click", async (event) => {
    const retryButton = event.target.closest("[data-check-retry]");
    if (retryButton) {
      form?.requestSubmit();
      return;
    }
    const saveButton = event.target.closest("[data-check-save]");
    if (saveButton) {
      trackFunnel("check.save_click", { slug: variant.slug });
      if (state.user) {
        saveButton.disabled = true;
        await completePendingSaveAfterLogin();
        saveButton.disabled = false;
        return;
      }
      openAuthDialog();
      return;
    }
  });
  if (previewAlreadyUsed) {
    renderPublicCheckAuthPrompt(readableError("check_preview_already_used"));
  }
  return true;
}

function getPublicCampaignLanding() {
  const path = window.location.pathname.replace(/^\/+|\/+$/g, "");
  return PUBLIC_CAMPAIGN_LANDINGS[path] || null;
}

function setPublicCampaignMetadata(variant) {
  const canonicalUrl = `https://temichevvet.ru${variant.path || (variant.kind === "food" ? `/food/${variant.petType}` : "/pet")}`;
  document.title = `${variant.title} — TemichevVet`;
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute("content", variant.description);
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.setAttribute("href", canonicalUrl);
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle) ogTitle.setAttribute("content", `${variant.title} — TemichevVet`);
  const ogDescription = document.querySelector('meta[property="og:description"]');
  if (ogDescription) ogDescription.setAttribute("content", variant.description);
  const ogUrl = document.querySelector('meta[property="og:url"]');
  if (ogUrl) ogUrl.setAttribute("content", canonicalUrl);
  const ogImage = document.querySelector('meta[property="og:image"]');
  if (ogImage && variant.image) ogImage.setAttribute("content", `https://temichevvet.ru${variant.image}`);
  let robots = document.querySelector('meta[name="robots"]');
  if (!robots) {
    robots = document.createElement("meta");
    robots.setAttribute("name", "robots");
    document.head.append(robots);
  }
  robots.setAttribute("content", "index,follow");
}

async function openPublicCampaignCabinet(variant, target) {
  const eventType = variant.kind === "food" ? "food.card_start_click" : "pet.card_start_click";
  trackFunnel(eventType, { slug: variant.slug, pet_type: variant.petType || "unknown", target });
  openPetOnboarding();
}

function renderPetCampaignLanding(variant) {
  const benefits = (variant.benefits || []).map((item, index) => {
    const icons = ["paw-print", "scale", "book-open", "calendar-days"];
    return `<li>${renderAppIcon(icons[index] || "heart-pulse")}<span>${escapeHtml(item)}</span></li>`;
  }).join("");
  publicCheckView.innerHTML = `
    <div class="campaign-page pet-campaign-page">
      <section class="intro-panel campaign-hero pet-passport-landing" aria-labelledby="petCampaignTitle">
        <div class="campaign-hero-copy pet-passport-copy">
          <p class="section-label">${escapeHtml(variant.label)}</p>
          <h1 id="petCampaignTitle">${escapeHtml(variant.headline)}</h1>
          <p class="lead">${escapeHtml(variant.description)}</p>
          <ul class="passport-benefit-list" aria-label="Что хранится в карточке питомца">
            ${benefits}
          </ul>
          <div class="campaign-hero-actions">
            <button class="primary-button" data-public-campaign-auth data-target="hero" type="button">Добавить питомца</button>
          </div>
          <p class="campaign-microcopy">Бесплатно. Для начала достаточно клички и вида питомца.</p>
        </div>
        <div class="campaign-hero-media campaign-pet-media">
          <img src="${escapeHtml(variant.image)}" alt="${escapeHtml(variant.imageAlt)}" />
        </div>
      </section>
      <aside class="passport-legal-note" aria-label="Важное уточнение">
        <strong>Личный журнал владельца.</strong>
        <span>Не заменяет официальный ветеринарный паспорт.</span>
      </aside>
    </div>
  `;
}

function publicFoodSavePayload(variant, formValues) {
  return {
    save_kind: "food",
    pet_type: variant.petType,
    species: variant.petType,
    query: formValues.query || "",
    ingredients: formValues.ingredients || "",
    landing_slug: variant.slug,
    session_id: getFunnelSessionId(),
    ...attributionEventMetadata(),
    created_at: new Date().toISOString(),
  };
}

function renderFoodSaveCallout() {
  return `
    <div class="campaign-result-next food-save-callout">
      <div>
        <strong>Сохраните ответ в карточку питомца</strong>
        <p>Он останется вместе с наблюдениями, чтобы к нему можно было вернуться.</p>
      </div>
      <button class="primary-button" data-food-save type="button">Сохранить ответ</button>
    </div>
  `;
}

function renderPublicFoodResult(data, variant, formValues) {
  const resultEl = publicCheckView.querySelector("#publicFoodResult");
  if (!resultEl) return;
  const item = data.item || null;
  const ingredientDanger = Array.isArray(data.items) && data.items.some((entry) => entry && entry.allowed === false);
  const isDanger = Boolean(item && item.allowed === false) || ingredientDanger;
  const requiresImmediateContact = Boolean(data.requires_immediate_vet_contact);
  const exposureAdvice = data.exposure_advice
    || "Если питомец уже съел этот продукт, немедленно свяжитесь с ветеринарной клиникой или ветеринарной токсикологической службой, даже если симптомов пока нет.";
  const sharedDatabaseDisclaimer = data.disclaimer
    || "Ответ сформирован по общей справочной базе для кошек и собак и не является анализом корма, этикетки или индивидуальной рекомендацией.";
  const resultLevel = isDanger ? "avoid" : item?.allowed ? "allowed" : data.status || "unknown";
  const resultClass = isDanger ? "danger" : item?.allowed ? "success" : "warning";
  let answerMarkup = "";
  if (item) {
    const details = [
      ["Сведения из общей базы", item.effects],
      ["Уровень риска в базе", item.risk_level],
      ["О количестве", item.dose_note],
      ["Общая рекомендация", item.advice]
    ].filter(([, value]) => String(value || "").trim());
    answerMarkup = `
      <div class="campaign-food-answer-head">
        <span>${item.allowed ? "Можно понемногу" : "Лучше не давать"}</span>
        <h2>${escapeHtml(item.name || "Продукт")}</h2>
      </div>
      <dl class="campaign-food-answer-details">
        ${details.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}
      </dl>
    `;
  } else {
    const fallbackTitle = isDanger
      ? "Лучше не давать"
      : data.status === "ingredients_checked"
        ? "Состав проверен"
        : "Нужно уточнение";
    answerMarkup = `
      <div class="campaign-food-answer-head">
        <h2>${escapeHtml(fallbackTitle)}</h2>
      </div>
      <p class="campaign-food-answer-message">${escapeHtml(data.message || "Не удалось найти ответ.")}</p>
    `;
  }
  const resultMarkup = `<div class="result-box campaign-food-result ${resultClass}">${answerMarkup}</div>`;
  const safetyMarkup = requiresImmediateContact
    ? `
      <div class="campaign-food-safety">
        <strong>Питомец уже съел этот продукт?</strong>
        <p>${escapeHtml(exposureAdvice)}</p>
      </div>
    `
    : `
      <div class="campaign-food-safety">
        <strong>После продукта появились симптомы?</strong>
        <p>При рвоте, слабости, судорогах, тяжёлом дыхании или быстром ухудшении срочно обратитесь в клинику.</p>
        <a class="secondary-link compact" href="/check/poisoning">Узнать, что делать</a>
      </div>
    `;

  resultEl.innerHTML = `
    ${resultMarkup}
    ${safetyMarkup}
    <p class="campaign-food-disclaimer">Запрос для ${escapeHtml(data.species_label || variant.petLabel)}. ${escapeHtml(sharedDatabaseDisclaimer)}</p>
    ${renderFoodSaveCallout()}
  `;
  storePendingPublicFoodSave(publicFoodSavePayload(variant, formValues));
  trackFunnel("food.result_shown", { slug: variant.slug, pet_type: data.species || variant.petType, level: resultLevel });
  trackFunnelWhenVisible(
    resultEl.querySelector(".food-save-callout"),
    "food.save_cta_view",
    { slug: variant.slug, pet_type: data.species || variant.petType, level: resultLevel },
    `food-save-cta:${getFunnelSessionId()}:${variant.slug}`,
  );
  revealPublicCheckState(resultEl.querySelector(".campaign-food-result"));
}

function renderFoodCampaignLanding(variant) {
  const exampleButtons = variant.examples
    .map((example) => `<button type="button" data-food-example="${escapeHtml(example)}">${escapeHtml(example)}</button>`)
    .join("");
  publicCheckView.innerHTML = `
    <div class="campaign-page food-campaign-page">
      <section class="intro-panel campaign-food-hero" aria-labelledby="foodCampaignTitle">
        <div class="campaign-food-copy">
          <div class="campaign-food-photo">
            <img src="${escapeHtml(variant.image)}" alt="${escapeHtml(variant.imageAlt)}" />
          </div>
          <p class="section-label">${escapeHtml(variant.label)}</p>
          <h1 id="foodCampaignTitle">${escapeHtml(variant.title)}</h1>
          <p class="lead">Сверим продукт или состав блюда с общей справочной базой.</p>
          <div class="campaign-food-points" aria-label="Условия проверки">
            <span>Бесплатно</span>
            <span>Без регистрации</span>
          </div>
          <p class="campaign-food-note">Запрос для ${escapeHtml(variant.petLabel)}. База общая для кошек и собак, не содержит отдельных правил по виду и не является анализом корма или этикетки.</p>
        </div>
        <section class="campaign-food-form-panel" aria-labelledby="foodFormTitle">
          <h2 id="foodFormTitle">Какой продукт проверить?</h2>
          <form class="form-grid one-column campaign-food-form" id="publicFoodForm">
            <label>
              <span>Название продукта или блюда</span>
              <input name="query" maxlength="160" placeholder="${escapeHtml(variant.placeholder)}" required />
            </label>
            <div class="campaign-food-examples" aria-label="Примеры продуктов">${exampleButtons}</div>
            <label>
              <span>Если это готовое блюдо, напишите состав <small>необязательно</small></span>
              <textarea name="ingredients" maxlength="1000" placeholder="Например: мясо, рис, лук, соль"></textarea>
            </label>
            <button class="primary-button" type="submit">Узнать, можно ли давать</button>
            <p class="campaign-microcopy">Ответ сразу на странице</p>
          </form>
          <div id="publicFoodResult" aria-live="polite"></div>
        </section>
      </section>
    </div>
  `;

  const form = publicCheckView.querySelector("#publicFoodForm");
  const queryInput = form?.querySelector("input[name='query']");
  publicCheckView.querySelectorAll("[data-food-example]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!queryInput) return;
      queryInput.value = button.dataset.foodExample || "";
      queryInput.focus();
    });
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submittedForm = event.currentTarget;
    const formData = new FormData(submittedForm);
    const query = String(formData.get("query") || "").trim();
    const ingredients = String(formData.get("ingredients") || "").trim();
    if (!query) {
      queryInput?.focus();
      return;
    }
    const resultEl = publicCheckView.querySelector("#publicFoodResult");
    const submitButton = submittedForm.querySelector("button[type='submit']");
    if (submitButton?.disabled) return;
    trackFunnel("food.submit", { slug: variant.slug, pet_type: variant.petType });
    submittedForm.setAttribute("aria-busy", "true");
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Проверяю…";
    }
    if (resultEl) {
      resultEl.innerHTML = `<div class="notice check-loading" role="status"><strong>Проверяю продукт…</strong><span>Ответ появится здесь.</span></div>`;
    }
    try {
      const data = await api("/api/food/check", {
        method: "POST",
        body: JSON.stringify({ species: variant.petType, query, ingredients })
      });
      if (data.species !== variant.petType) throw new Error("food_species_mismatch");
      renderPublicFoodResult(data, variant, { query, ingredients });
    } catch (error) {
      if (resultEl) {
        resultEl.innerHTML = `<div class="notice danger" role="alert"><strong>Не получилось проверить продукт</strong><p>${escapeHtml(readableError(error.message))}</p><button class="secondary-button compact" data-food-retry type="button">Попробовать ещё раз</button></div>`;
      }
    } finally {
      submittedForm.removeAttribute("aria-busy");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Узнать, можно ли давать";
      }
    }
  });
}

function renderPublicCampaignLanding() {
  const variant = getPublicCampaignLanding();
  if (!publicCheckView || !variant) return false;
  document.body.classList.add("is-public-campaign", `is-${variant.kind}-campaign`);
  publicCheckView.hidden = false;
  publicCheckView.classList.remove("has-pending-save");
  setPublicCampaignMetadata(variant);
  if (variant.kind === "food") renderFoodCampaignLanding(variant);
  else renderPetCampaignLanding(variant);

  if (campaignLandingViewTrackedPath !== window.location.pathname) {
    campaignLandingViewTrackedPath = window.location.pathname;
    const eventType = variant.kind === "food" ? "food.landing_view" : "pet.landing_view";
    trackFunnel(eventType, { slug: variant.slug, pet_type: variant.petType || "unknown", path: window.location.pathname });
  }

  publicCheckView.addEventListener("click", async (event) => {
    const retryButton = event.target.closest("[data-food-retry]");
    if (retryButton) {
      publicCheckView.querySelector("#publicFoodForm")?.requestSubmit();
      return;
    }
    const foodSaveButton = event.target.closest("[data-food-save]");
    if (foodSaveButton) {
      trackFunnel("food.card_start_click", { slug: variant.slug, pet_type: variant.petType, target: "food_result" });
      foodSaveButton.disabled = true;
      if (state.user) await completePendingSaveAfterLogin();
      else openAuthDialog();
      foodSaveButton.disabled = false;
      return;
    }
    const authButton = event.target.closest("[data-public-campaign-auth]");
    if (authButton) {
      authButton.disabled = true;
      await openPublicCampaignCabinet(variant, authButton.dataset.target || "unknown");
      authButton.disabled = false;
    }
  });
  return true;
}

function legalEmailLink() {
  return `<a href="mailto:${OPERATOR_EMAIL}">${OPERATOR_EMAIL}</a>`;
}

const legalDocuments = {
  privacy: {
    title: "Политика конфиденциальности",
    html: `
      <div class="legal-meta">Редакция от ${LEGAL_UPDATED_AT}. Контакт оператора: ${legalEmailLink()}.</div>
      <section>
        <h3>1. Для чего нужна политика</h3>
        <p>Эта политика объясняет, какие данные обрабатывает сервис TemichevVet, зачем они нужны, где хранятся и как пользователь может запросить доступ, исправление или удаление данных.</p>
      </section>
      <section>
        <h3>2. Оператор и контакт</h3>
        <p>Оператор сервиса TemichevVet обрабатывает данные пользователей сайта, PWA и подключённых мессенджеров. По вопросам персональных данных и работы сервиса можно написать на ${legalEmailLink()}.</p>
      </section>
      <section>
        <h3>3. Какие данные обрабатываются</h3>
        <ul>
          <li>email, внешние идентификаторы Telegram и MAX, сведения о способе входа;</li>
          <li>данные о питомцах: кличка, вид, возраст, вес, порода, пол, наблюдения, напоминания, история обращений;</li>
          <li>тексты симптомов и вопросов, которые пользователь вводит для оценки состояния или проверки питания;</li>
          <li>данные подписки, лимитов и платежных событий без хранения полных реквизитов банковской карты;</li>
          <li>технические данные: IP-адрес, время запроса, ошибки, данные сессии, cookie/localStorage, записи безопасности.</li>
        </ul>
      </section>
      <section>
        <h3>4. Цели обработки</h3>
        <ul>
          <li>создание и защита личного кабинета;</li>
          <li>ведение карточек питомцев, истории, наблюдений, веса и напоминаний;</li>
          <li>проверка опасных признаков, разбор введённых изменений и подготовка понятной информации владельцу;</li>
          <li>синхронизация одного аккаунта между сайтом, PWA, Telegram и MAX;</li>
          <li>поддержка пользователей, обработка обратной связи, улучшение безопасности и качества сервиса;</li>
          <li>учет подписки, лимитов и платежей.</li>
        </ul>
      </section>
      <section>
        <h3>5. Правовые основания</h3>
        <p>Обработка выполняется на основании согласия пользователя, пользовательского соглашения, необходимости предоставления функций сервиса и требований законодательства Российской Федерации.</p>
      </section>
      <section>
        <h3>6. Хранение и передача</h3>
        <p>Основные базы личного кабинета размещаются на сервере в Российской Федерации. Для работы сервиса могут использоваться серверные интеграции с Telegram, MAX, email-провайдером, платежным провайдером и LLM-провайдером. Передаются только данные, необходимые для конкретной функции: входа, уведомления, оплаты, ответа на запрос или синхронизации.</p>
      </section>
      <section>
        <h3>7. Срок хранения</h3>
        <p>Данные хранятся, пока пользователь использует сервис, пока требуется история питомца или пока это необходимо для исполнения закона, безопасности, платежного учета и разрешения спорных ситуаций. Пользователь может запросить удаление данных.</p>
      </section>
      <section>
        <h3>8. Права пользователя</h3>
        <p>Пользователь может запросить сведения об обработке, уточнение, блокирование или удаление данных, а также отозвать согласие. Запрос можно отправить на ${legalEmailLink()}.</p>
      </section>
      <section>
        <h3>9. Безопасность</h3>
        <p>Сервис использует серверную проверку доступа, защищенные токены, раздельные секреты для интеграций, резервное копирование и ограничение доступа к внутренним API. Пользователь отвечает за сохранность доступа к своей почте и мессенджерам.</p>
      </section>
    `
  },
  consent: {
    title: "Согласие на обработку персональных данных",
    html: `
      <div class="legal-meta">Редакция от ${LEGAL_UPDATED_AT}. Согласие даётся при регистрации, входе, отправке формы или использовании сервиса.</div>
      <section>
        <h3>1. Что подтверждает пользователь</h3>
        <p>Пользователь свободно, своей волей и в своём интересе даёт согласие оператору TemichevVet на обработку персональных данных для работы личного кабинета и функций сервиса.</p>
      </section>
      <section>
        <h3>2. Данные</h3>
        <p>Согласие распространяется на email, идентификаторы Telegram/MAX, сведения о питомцах, тексты обращений, историю, напоминания, подписку, платежные события и технические данные, необходимые для безопасности и работы сервиса.</p>
      </section>
      <section>
        <h3>3. Действия с данными</h3>
        <p>Разрешаются сбор, запись, систематизация, хранение, уточнение, использование, передача партнерам для выполнения функций сервиса, обезличивание, блокирование, удаление и уничтожение данных.</p>
      </section>
      <section>
        <h3>4. Передача и интеграции</h3>
        <p>Для входа, уведомлений, оплаты, синхронизации и подготовки ответа данные могут передаваться Telegram, MAX, email-сервису, платежному провайдеру, инфраструктурным провайдерам и LLM-провайдеру в объеме, необходимом для выбранной функции.</p>
      </section>
      <section>
        <h3>5. Срок действия и отзыв</h3>
        <p>Согласие действует до его отзыва или до достижения целей обработки. Отозвать согласие можно письмом на ${legalEmailLink()}. После отзыва часть функций сервиса может стать недоступной.</p>
      </section>
    `
  },
  terms: {
    title: "Пользовательское соглашение",
    html: `
      <div class="legal-meta">Редакция от ${LEGAL_UPDATED_AT}. Используя сайт, PWA или подключённые мессенджеры, пользователь принимает это соглашение.</div>
      <section>
        <h3>1. Предмет</h3>
        <p>TemichevVet предоставляет информационный сервис для владельцев собак и кошек: карточки питомцев, историю, напоминания, оценку состояния питомца, проверку питания, подписку и синхронизацию входов.</p>
      </section>
      <section>
        <h3>2. Один аккаунт</h3>
        <p>Email, Telegram и MAX могут быть связаны с одним личным кабинетом. Это нужно, чтобы не создавать две регистрации, не разделять историю питомцев и не оплачивать подписку повторно.</p>
      </section>
      <section>
        <h3>3. Обязанности пользователя</h3>
        <ul>
          <li>указывать достоверные данные о питомце и ситуации;</li>
          <li>не использовать сервис вместо очного осмотра ветеринарного врача;</li>
          <li>не передавать доступ к личному кабинету третьим лицам;</li>
          <li>не загружать незаконные, вредоносные или чужие персональные данные без оснований.</li>
        </ul>
      </section>
      <section>
        <h3>4. Ограничения сервиса</h3>
        <p>Ответы сервиса являются информационной поддержкой. Сервис не ставит диагноз, не назначает лечение, не гарантирует исход ситуации и не заменяет ветеринарного врача.</p>
      </section>
      <section>
        <h3>5. Подписка и оплата</h3>
        <p>Платные функции предоставляются по условиям выбранного тарифа. Plus оплачивается разово на указанный срок без автосписаний, если явно не указано иное. Платежные данные обрабатываются платежным провайдером.</p>
      </section>
      <section>
        <h3>6. Изменения</h3>
        <p>Сервис может обновлять функции, интерфейс, тарифы и документы. Актуальная редакция документов публикуется на сайте.</p>
      </section>
    `
  },
  offer: {
    title: "Публичная оферта",
    html: `
      <div class="legal-meta">Редакция от ${LEGAL_UPDATED_AT}. Оферта определяет условия покупки доступа Plus в сервисе TemichevVet.</div>
      <section>
        <h3>1. Услуга</h3>
        <p>Платная услуга TemichevVet — предоставление доступа Plus к расширенным функциям личного кабинета здоровья питомца на 30 календарных дней.</p>
      </section>
      <section>
        <h3>2. Что входит в Plus</h3>
        <ul>
          <li>до 10 оценок состояния питомца в месяц;</li>
          <li>расширенная история обращений по питомцам;</li>
          <li>до 20 активных напоминаний;</li>
          <li>ведение до 3 питомцев в личном кабинете;</li>
          <li>синхронизация доступа между сайтом, PWA и подключёнными мессенджерами.</li>
        </ul>
      </section>
      <section>
        <h3>3. Стоимость и срок</h3>
        <p>Стоимость Plus составляет 200 рублей за 30 дней. Оплата разовая, автоматических списаний нет. После окончания оплаченного срока сервис возвращает доступ на Free, если Plus не продлён повторной оплатой.</p>
      </section>
      <section>
        <h3>4. Порядок оказания услуги</h3>
        <p>Доступ Plus активируется после успешного подтверждения платежа платёжным провайдером. Полные данные банковской карты TemichevVet не хранит.</p>
      </section>
      <section>
        <h3>5. Ограничения</h3>
        <p>TemichevVet является информационным сервисом. Платный доступ не является медицинской услугой, ветеринарной консультацией, постановкой диагноза или назначением лечения.</p>
      </section>
      <section>
        <h3>6. Возвраты и обращения</h3>
        <p>По вопросам оплаты, технических ошибок и доступа Plus пользователь может написать на ${legalEmailLink()}. Запрос рассматривается по существу обращения и данным платежа.</p>
      </section>
      <section>
        <h3>7. Принятие оферты</h3>
        <p>Нажатие кнопки оплаты и успешная оплата означают принятие этой оферты, пользовательского соглашения, политики конфиденциальности и медицинского дисклеймера.</p>
      </section>
    `
  },
  medical: {
    title: "Медицинский дисклеймер",
    html: `
      <div class="legal-meta">TemichevVet — информационный помощник, а не ветеринарная клиника.</div>
      <section>
        <h3>Что важно понимать</h3>
        <p>Сервис помогает вести историю питомца, разбирать сохранённые изменения и готовить понятную информацию к визиту. Он не ставит диагноз, не назначает лечение, не подбирает дозировки лекарств и не заменяет очный осмотр ветеринарного врача.</p>
      </section>
      <section>
        <h3>Когда срочно в клинику</h3>
        <p>При тяжелом дыхании, судорогах, потере сознания, признаках отравления, крови, сильной боли, невозможности мочиться, резком вздутии живота, тяжелой травме или быстром ухудшении состояния нужно срочно обращаться в ветеринарную клинику и не ждать ответа сервиса.</p>
      </section>
      <section>
        <h3>Как использовать ответы</h3>
        <p>Ответы удобно использовать как чек-лист: что наблюдать, что подготовить для врача, какие признаки считать тревожными. Окончательное решение по диагностике и лечению принимает ветеринарный врач.</p>
      </section>
    `
  },
  cookies: {
    title: "Cookie и локальное хранение",
    html: `
      <div class="legal-meta">Редакция от ${LEGAL_UPDATED_AT}. Вы можете принять все cookie или оставить только необходимые.</div>
      <section>
        <h3>Что используется сейчас</h3>
        <ul>
          <li>необходимые данные входа: токен сессии, состояние входа через Telegram/MAX, одноразовые состояния формы;</li>
          <li>PWA-кеш: файлы интерфейса, чтобы приложение быстрее открывалось и могло устанавливаться на устройство;</li>
          <li>настройка cookie-согласия, чтобы не показывать баннер повторно;</li>
          <li>технические серверные журналы безопасности и ошибок.</li>
        </ul>
      </section>
      <section>
        <h3>Аналитика</h3>
        <p>При выборе “Принять все” сервис подключает Яндекс.Метрику для понимания посещаемости, кликов, технических ошибок и удобства интерфейса. Это помогает улучшать сайт, но не является обязательным для входа и работы личного кабинета.</p>
      </section>
      <section>
        <h3>Как отказаться</h3>
        <p>Необходимые cookie/localStorage нужны для входа и безопасности. От аналитики можно отказаться, выбрав “Только необходимые”. Данные можно удалить в настройках браузера, но после этого потребуется войти снова.</p>
      </section>
    `
  },
  contacts: {
    title: "Контакты оператора",
    html: `
      <div class="legal-meta">Основной контакт для обращений: ${legalEmailLink()}.</div>
      <section>
        <h3>По каким вопросам писать</h3>
        <ul>
          <li>вопросы по личному кабинету и входу;</li>
          <li>запрос доступа, исправления или удаления персональных данных;</li>
          <li>отзыв согласия на обработку персональных данных;</li>
          <li>вопросы по подписке, оплате и синхронизации Telegram/MAX;</li>
          <li>технические ошибки сайта или PWA.</li>
        </ul>
      </section>
      <section>
        <h3>Важно</h3>
        <p>Этот контакт не является экстренной ветеринарной консультацией. При тяжелом состоянии питомца обращайтесь в ближайшую ветеринарную клинику.</p>
      </section>
    `
  }
};

function openLegalModal(type = "privacy") {
  const doc = legalDocuments[type] || legalDocuments.privacy;
  legalModalTitle.textContent = doc.title;
  legalContent.innerHTML = doc.html;
  legalModal.hidden = false;
  legalModal.setAttribute("aria-hidden", "false");
}

function closeLegalModal() {
  legalModal.hidden = true;
  legalModal.setAttribute("aria-hidden", "true");
}

const legalPathMap = {
  "/privacy": "privacy",
  "/consent": "consent",
  "/terms": "terms",
  "/offer": "offer",
  "/medical-disclaimer": "medical",
  "/cookies": "cookies",
  "/contacts": "contacts"
};

function openLegalFromCurrentPath() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const type = legalPathMap[path];
  if (!type) return false;
  openLegalModal(type);
  return true;
}

function showCookieBannerIfNeeded() {
  if (!cookieBanner) return;
  const consent = getCookieConsent();
  if (!consent) {
    cookieBanner.hidden = false;
    return;
  }
  if (consent.value === "all") loadMetrika();
}

function setCookieConsent(value) {
  localStorage.setItem("tvv_cookie_consent", JSON.stringify({
    value,
    accepted_at: new Date().toISOString(),
    version: "20260615-trust-compact-1"
  }));
  cookieBanner.hidden = true;
  if (value === "all") loadMetrika();
}

function getCookieConsent() {
  try {
    const raw = localStorage.getItem("tvv_cookie_consent");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function sanitizedAnalyticsUrl() {
  const url = new URL(window.location.href);
  url.hash = "";
  return url.toString();
}

function clearSensitiveMiniAppFragment() {
  const hash = window.location.hash || "";
  if (!/^#WebAppData=/i.test(hash)) return;
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
}

function loadMetrika() {
  if (metrikaLoaded || typeof window === "undefined" || isAdminRoute) return;
  metrikaLoaded = true;
  window.ym = window.ym || function () {
    (window.ym.a = window.ym.a || []).push(arguments);
  };
  window.ym.l = 1 * new Date();
  if (![...document.scripts].some((script) => script.src === `https://mc.yandex.ru/metrika/tag.js?id=${METRIKA_ID}`)) {
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://mc.yandex.ru/metrika/tag.js?id=${METRIKA_ID}`;
    document.head.append(script);
  }
  window.ym(METRIKA_ID, "init", {
    ssr: true,
    webvisor: true,
    clickmap: true,
    ecommerce: "dataLayer",
    referrer: document.referrer,
    url: sanitizedAnalyticsUrl(),
    accurateTrackBounce: true,
    trackLinks: true
  });
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function maskEmail(email) {
  const value = String(email || "");
  const [name, domain] = value.split("@");
  if (!name || !domain) return value;
  const visible = name.length <= 2 ? name[0] || "" : `${name.slice(0, 2)}…${name.slice(-1)}`;
  return `${visible}@${domain}`;
}

function formatPetSpecies(type) {
  const value = String(type || "").toLowerCase();
  if (value.includes("кош") || value === "cat") return "Кошка";
  if (value.includes("соб") || value === "dog") return "Собака";
  return value ? value[0].toUpperCase() + value.slice(1) : "Питомец";
}

function formatPetSex(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return "";
  if (["м", "m", "male", "самец", "кобель", "кот"].includes(text)) return "самец";
  if (["ж", "f", "female", "самка", "сука", "кошка"].includes(text)) return "самка";
  return text;
}

function formatPetAgeCompact(pet) {
  if (pet.age_text) return pet.age_text;
  if (!pet.birth_year) return "";
  const years = new Date().getFullYear() - Number(pet.birth_year);
  if (!Number.isFinite(years) || years < 0) return "";
  const last = years % 10;
  const lastTwo = years % 100;
  const unit = last === 1 && lastTwo !== 11 ? "год" : [2, 3, 4].includes(last) && ![12, 13, 14].includes(lastTwo) ? "года" : "лет";
  return `${years} ${unit}`;
}

function formatPetWeight(pet) {
  if (!pet.weight_kg) return "";
  return `${pet.weight_kg} кг`;
}

function petTitle(pet) {
  return `${formatPetSpecies(pet.pet_type)} — ${pet.pet_name || "без имени"}`;
}

function observationTypeLabel(value) {
  const labels = {
    note: "Наблюдение",
    appetite: "Аппетит",
    activity: "Активность",
    stool: "Стул",
    symptom: "Симптом",
    triage: "Разбор ситуации",
    food_check: "Проверка питания"
  };
  return labels[value] || "Наблюдение";
}

function observationDisplayText(item) {
  const payload = item?.payload;
  if (typeof payload === "string") return payload.trim();
  for (const key of ["text", "summary", "complaint"]) {
    const value = payload?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function setWorkspace(html, options = {}) {
  ensureDashboardView();
  if (!workspace) return;
  workspace.innerHTML = html;
  if (options.scroll !== false) {
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function showError(message) {
  ensureDashboardView();
  if (!workspace) return;
  workspace.querySelector("[data-workspace-error]")?.remove();
  const notice = document.createElement("div");
  notice.className = "notice danger workspace-error";
  notice.dataset.workspaceError = "true";
  notice.setAttribute("role", "alert");
  notice.innerHTML = `<strong>Не получилось выполнить действие</strong><p>${escapeHtml(message)}</p>`;
  workspace.prepend(notice);
  notice.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...attributionRequestHeaders(),
    ...(options.headers || {})
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "request_failed");
  }
  return data;
}

async function adminApi(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "admin_request_failed");
  }
  return data;
}

function adminReadableError(message) {
  const messages = {
    admin_not_configured: "Админка не настроена на сервере.",
    invalid_admin_password: "Пароль не подошёл.",
    invalid_admin_credentials: "Логин или пароль не подошли.",
    invalid_current_password: "Текущий пароль не подошёл.",
    invalid_admin_username: "Логин может содержать только латинские буквы, цифры, точку, подчёркивание, дефис или @.",
    nothing_to_change: "Введите новый логин или новый пароль.",
    env_file_not_found: "Сервер не нашёл .env для сохранения настроек.",
    invalid_admin_session: "Админ-сессия истекла. Войдите снова.",
    authorization_required: "Нужно войти в админку.",
    rate_limited: "Слишком много попыток входа. Подождите и попробуйте снова."
  };
  return messages[message] || readableError(message);
}

function ensureAdminMarkup() {
  if (!adminView || adminMarkupReady) return;
  adminView.innerHTML = `
    <div class="admin-login-panel" id="adminLoginPanel">
      <div class="panel admin-login-card">
        <p class="section-label">Админка TemichevVet</p>
        <h1>Вход администратора</h1>
        <p>Доступ только для владельца сервиса. Вход защищён отдельным логином, паролем, короткой сессией и журналом безопасности.</p>
        <form id="adminLoginForm" class="admin-login-form">
          <label>
            <span>Логин администратора</span>
            <input id="adminUsernameInput" type="text" autocomplete="username" minlength="3" required value="admin" />
          </label>
          <label>
            <span>Пароль администратора</span>
            <input id="adminPasswordInput" type="password" autocomplete="current-password" minlength="8" required />
          </label>
          <button class="primary-button" type="submit">Войти</button>
        </form>
        <p class="hint" id="adminLoginHint"></p>
      </div>
    </div>

    <div class="admin-dashboard" id="adminDashboardPanel" hidden>
      <div class="dashboard-head">
        <div>
          <p class="section-label">Администрирование</p>
          <h1>TemichevVet: контроль сервиса</h1>
          <p>Пользователи, оплаты, подписки, безопасность, синхронизация и технические ошибки.</p>
        </div>
        <div class="inline-actions">
          <button class="secondary-button compact" id="adminRefreshBtn" type="button">Обновить</button>
          <button class="secondary-button compact" id="adminLogoutBtn" type="button">Выйти</button>
        </div>
      </div>
      <details class="admin-settings">
        <summary>Сменить логин/пароль администратора</summary>
        <form id="adminCredentialsForm" class="admin-credentials-form">
          <label>
            <span>Текущий пароль</span>
            <input id="adminCurrentPasswordInput" type="password" autocomplete="current-password" minlength="8" required />
          </label>
          <label>
            <span>Новый логин</span>
            <input id="adminNewUsernameInput" type="text" autocomplete="username" minlength="3" placeholder="admin" />
          </label>
          <label>
            <span>Новый пароль</span>
            <input id="adminNewPasswordInput" type="password" autocomplete="new-password" minlength="12" placeholder="минимум 12 символов" />
          </label>
          <button class="secondary-button compact" type="submit">Сохранить</button>
        </form>
        <p class="hint" id="adminCredentialsHint">Пароль сохраняется только как хэш. После смены используйте новый логин и пароль при следующем входе.</p>
      </details>
      <div id="adminContent" class="admin-content">
        <div class="notice">Загружаю данные админки...</div>
      </div>
    </div>
  `;
  adminLoginPanel = adminView.querySelector("#adminLoginPanel");
  adminDashboardPanel = adminView.querySelector("#adminDashboardPanel");
  adminLoginForm = adminView.querySelector("#adminLoginForm");
  adminUsernameInput = adminView.querySelector("#adminUsernameInput");
  adminPasswordInput = adminView.querySelector("#adminPasswordInput");
  adminLoginHint = adminView.querySelector("#adminLoginHint");
  adminCredentialsForm = adminView.querySelector("#adminCredentialsForm");
  adminCurrentPasswordInput = adminView.querySelector("#adminCurrentPasswordInput");
  adminNewUsernameInput = adminView.querySelector("#adminNewUsernameInput");
  adminNewPasswordInput = adminView.querySelector("#adminNewPasswordInput");
  adminCredentialsHint = adminView.querySelector("#adminCredentialsHint");
  adminRefreshBtn = adminView.querySelector("#adminRefreshBtn");
  adminLogoutBtn = adminView.querySelector("#adminLogoutBtn");
  adminContent = adminView.querySelector("#adminContent");
  bindAdminEvents();
  adminMarkupReady = true;
}

function bindAdminEvents() {
  adminLoginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setAdminHint("Проверяю логин и пароль...");
    try {
      await adminApi("/api/admin/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: adminUsernameInput.value,
          password: adminPasswordInput.value
        })
      });
      adminPasswordInput.value = "";
      setAdminHint("");
      await loadAdminDashboard();
    } catch (error) {
      setAdminHint(adminReadableError(error.message), true);
    }
  });

  adminCredentialsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    adminCredentialsHint.textContent = "Сохраняю...";
    adminCredentialsHint.className = "hint";
    try {
      const payload = {
        current_password: adminCurrentPasswordInput.value,
        new_username: adminNewUsernameInput.value.trim() || null,
        new_password: adminNewPasswordInput.value || null
      };
      const data = await adminApi("/api/admin/auth/credentials", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (data.username && adminUsernameInput) {
        adminUsernameInput.value = data.username;
      }
      adminCurrentPasswordInput.value = "";
      adminNewPasswordInput.value = "";
      adminCredentialsHint.textContent = "Сохранено. При следующем входе используйте новый логин и пароль.";
    } catch (error) {
      adminCredentialsHint.textContent = adminReadableError(error.message);
      adminCredentialsHint.className = "hint danger-text";
    }
  });

  adminRefreshBtn?.addEventListener("click", async () => {
    try {
      await loadAdminDashboard();
    } catch (error) {
      adminContent.innerHTML = `<div class="notice danger">Ошибка: ${escapeHtml(adminReadableError(error.message))}</div>`;
    }
  });

  adminLogoutBtn?.addEventListener("click", async () => {
    try {
      await adminApi("/api/admin/auth/logout", { method: "POST", body: "{}" });
    } catch {
      // Local admin logout still needs to happen if the server session has expired.
    }
    setAdminMode(false);
  });

  adminContent?.addEventListener("click", (event) => {
    const pageButton = event.target.closest("[data-admin-page]");
    if (!pageButton) return;
    event.preventDefault();
    setAdminPage(pageButton.dataset.adminPage || "overview");
  });
}

function setAdminHint(text, danger = false) {
  if (!adminLoginHint) return;
  adminLoginHint.textContent = text || "";
  adminLoginHint.className = danger ? "hint danger-text" : "hint";
}

function adminCell(value) {
  return escapeHtml(value === null || value === undefined || value === "" ? "—" : value);
}

function adminStatusLabel(status) {
  const labels = {
    ok: "OK",
    warning: "Внимание",
    error: "Ошибка"
  };
  return labels[status] || status || "—";
}

function adminIntegrationStatusLabel(key, ok) {
  if (ok) return "Работает";
  if (key === "database") return "Проблема";
  return "Не подключено";
}

function adminIntegrationStatusClass(key, ok) {
  if (ok) return "ok";
  if (key === "database") return "error";
  return "off";
}

function adminAuditEventInfo(eventType) {
  const exact = {
    "access.ownership_denied": {
      title: "Попытка открыть чужие данные",
      help: "Система заблокировала доступ к чужому питомцу, напоминанию, платежу или истории."
    },
    "admin.login_failed": {
      title: "Неверный вход в админку",
      help: "Кто-то ввёл неправильный логин или пароль администратора."
    },
    "admin.login_disabled": {
      title: "Админка не настроена",
      help: "На сервере нет хэша пароля администратора."
    },
    "auth.login_failed": {
      title: "Неверный код входа",
      help: "Пользователь ввёл неверный или истёкший одноразовый код."
    },
    "auth.email_code_failed": {
      title: "Код email не создан",
      help: "Email-вход не настроен или письмо с кодом не удалось отправить."
    },
    "auth.email_code_rate_limited": {
      title: "Слишком много попыток входа",
      help: "Сработал лимит отправки кодов на email. Это защищает от спама и перебора."
    },
    "auth.email_verify_failed": {
      title: "Неверный email-код",
      help: "Пользователь ввёл неправильный код, код истёк или превышено число попыток."
    },
    "auth.provider_start_failed": {
      title: "Мессенджер-вход не стартовал",
      help: "Telegram или MAX не настроен на сервере либо не хватает обязательного секрета."
    },
    "account.provider_link_start_failed": {
      title: "Привязка мессенджера не стартовала",
      help: "Пользователь хотел подключить Telegram/MAX к кабинету, но интеграция не настроена."
    },
    "account.provider_link_blocked": {
      title: "Привязка заблокирована",
      help: "Система не дала подключить мессенджер к временной или неподходящей учётной записи."
    },
    "auth.email_send_failed": {
      title: "Email не отправился",
      help: "SMTP не принял письмо или временно недоступен."
    },
    "payment.ownership_denied": {
      title: "Чужой платёж заблокирован",
      help: "Пользователь попытался проверить платёж, который принадлежит другому аккаунту."
    },
    "payment.create_failed": {
      title: "Платёж не создан",
      help: "YooKassa не создала платёж или не настроены платёжные ключи."
    },
    "payment.provider_error": {
      title: "Ошибка YooKassa",
      help: "Платёжный провайдер вернул ошибку при создании или проверке платежа."
    },
    "payment.validation_failed": {
      title: "Платёж не прошёл проверку",
      help: "Сумма, валюта, владелец или metadata платежа не совпали с ожидаемыми."
    },
    "payment.webhook_unknown": {
      title: "Webhook по неизвестному платежу",
      help: "YooKassa прислала событие по платежу, которого нет в локальной базе."
    },
    "payment.webhook_failed": {
      title: "Webhook платежа не обработан",
      help: "Событие YooKassa пришло, но сервер не смог безопасно подтвердить или активировать оплату."
    },
    "llm.error": {
      title: "Ошибка LLM",
      help: "Не удалось получить разбор состояния от модели или шлюза."
    },
    "sync.error": {
      title: "Ошибка синхронизации",
      help: "Не прошёл обмен данными между Telegram-ботом, Core API или PWA."
    },
    "push.subscribe_failed": {
      title: "Push не подключён",
      help: "Пользователь попытался включить PWA-уведомления, но VAPID ещё не настроен."
    },
    "push.followups_send": {
      title: "Контрольное напоминание",
      help: "Система отправила PWA-напоминание после разбора состояния питомца. Пустые проверки очереди в журнал не попадают."
    },
    "push.broadcast_send": {
      title: "Сервисная PWA-рассылка",
      help: "Разовое служебное уведомление пользователям, у которых включены push-уведомления."
    },
    "review_login.denied": {
      title: "Review-ссылка не принята",
      help: "Временная ссылка аудита недействительна, истекла или относится не к review-аккаунту."
    }
  };
  if (exact[eventType]) return exact[eventType];
  const prefixRules = [
    ["auth.", "Вход пользователя", "Событие авторизации: email, Telegram, MAX или сессия."],
    ["account.", "Аккаунт пользователя", "Привязка входов, выход из сессий, экспорт или запрос удаления данных."],
    ["admin.", "Админка", "Событие входа, выхода, смены пароля или просмотра админки."],
    ["payment.", "Оплата", "Событие создания, проверки, ошибки или успешной оплаты."],
    ["subscription.", "Подписка", "Изменение тарифа или лимитов пользователя."],
    ["llm.", "LLM-разбор", "Событие оценки состояния через модель или LLM-шлюз."],
    ["sync.", "Синхронизация", "Обмен данными между PWA, Telegram-ботом и Core API."],
    ["push.", "PWA-уведомления", "Подписка, отправка или ошибка push-напоминаний."],
    ["http.", "API/сервер", "Техническое событие HTTP-запроса или серверной ошибки."]
  ];
  const match = prefixRules.find(([prefix]) => String(eventType || "").startsWith(prefix));
  if (match) return { title: match[1], help: match[2] };
  return {
    title: eventType || "Неизвестное событие",
    help: "Техническое событие. Если повторяется часто, нужно смотреть время, канал и соседние события."
  };
}

function renderAuditEventCell(row) {
  const info = adminAuditEventInfo(row.event_type);
  return `
    <strong>${escapeHtml(info.title)}</strong>
    <small>${escapeHtml(row.event_type || "")}</small>
  `;
}

function renderAuditHelpCell(row) {
  const info = adminAuditEventInfo(row.event_type);
  return escapeHtml(info.help);
}

function renderSiteVisitUser(row) {
  if (row.user_email) {
    return adminCell(row.user_email);
  }
  if (row.user_id) {
    return adminCell(`User ${row.user_id}`);
  }
  return `<span class="admin-visitor-label">Анонимно<small>без входа</small></span>`;
}

function renderSiteVisitSource(row) {
  const source = row.source || row.referrer_host || "Прямой заход";
  return adminCell(source);
}

function renderSiteVisitDevice(row) {
  const parts = [row.device, row.browser].filter(Boolean);
  const label = parts.length ? parts.join(" / ") : "Неизвестно";
  return adminCell(row.is_bot ? `${label} · бот/проверка` : label);
}

function renderAdminMetric(label, value, hint = "") {
  return `
    <div class="summary-card admin-metric">
      <strong>${adminCell(value)}</strong>
      <span>${escapeHtml(label)}</span>
      ${hint ? `<small>${escapeHtml(hint)}</small>` : ""}
    </div>
  `;
}

function formatAdminInteger(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return Math.max(0, Math.round(number)).toLocaleString("ru-RU");
}

function renderAdminTable(title, rows, columns, emptyText = "Данных пока нет") {
  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = rows.length
    ? rows.map((row) => `
        <tr>
          ${columns.map((column) => `<td>${column.render ? column.render(row) : adminCell(row[column.key])}</td>`).join("")}
        </tr>
      `).join("")
    : `<tr><td colspan="${columns.length}">${escapeHtml(emptyText)}</td></tr>`;
  return `
    <section class="admin-section">
      <h2>${escapeHtml(title)}</h2>
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderAdminTechnicalDetails(summary, content, hint = "") {
  return `
    <details class="admin-technical-details">
      <summary>${escapeHtml(summary)}</summary>
      ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
      <div class="admin-technical-details-content">${content}</div>
    </details>
  `;
}

function normalizeAdminPage(pageId) {
  return ADMIN_PAGES.some((page) => page.id === pageId) ? pageId : "overview";
}

function adminPageFromLocation() {
  const hash = window.location.hash.replace(/^#/, "");
  return normalizeAdminPage(hash || "overview");
}

function setAdminPage(pageId, options = {}) {
  const nextPage = normalizeAdminPage(pageId);
  adminCurrentPage = nextPage;
  if (isAdminRoute) {
    const url = new URL(window.location.href);
    url.hash = nextPage;
    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    if (nextUrl !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      if (options.replace) {
        window.history.replaceState(null, "", nextUrl);
      } else {
        window.history.pushState(null, "", nextUrl);
      }
    }
  }
  renderAdminActivePage();
}

function syncAdminPageFromLocation() {
  if (!isAdminRoute || !adminDashboardData) return;
  const nextPage = adminPageFromLocation();
  if (nextPage === adminCurrentPage) return;
  adminCurrentPage = nextPage;
  renderAdminActivePage();
}

function renderAdminNav() {
  return `
    <nav class="admin-page-nav" aria-label="Разделы админки">
      ${ADMIN_PAGES.map((page) => `
        <button class="admin-page-tab${page.id === adminCurrentPage ? " active" : ""}" type="button" data-admin-page="${escapeHtml(page.id)}" aria-pressed="${page.id === adminCurrentPage ? "true" : "false"}">
          ${escapeHtml(page.label)}
        </button>
      `).join("")}
    </nav>
  `;
}

function renderAdminPageHead(title, text) {
  return `
    <div class="admin-page-head">
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(text)}</p>
    </div>
  `;
}

function renderAdminOverviewPage(data) {
  const overview = data.overview || {};
  const rawUsers = overview.users_total_raw ?? overview.users_total ?? 0;
  const serviceUsers = overview.users_service || 0;
  const productVisits = overview.site_visits_24h_product ?? overview.site_visits_24h_human ?? 0;
  const technicalVisits = overview.site_visits_24h_technical || 0;
  return `
    ${renderAdminPageHead("Обзор", "Только продуктовые показатели. Боты, сканеры и служебные проверки вынесены в технические разделы.")}
    <div class="summary-grid admin-summary">
      ${renderAdminMetric(
        "Пользователей",
        overview.users_total,
        serviceUsers
          ? `${rawUsers} всего · ${serviceUsers} служебный · +${overview.users_today || 0} сегодня`
          : `+${overview.users_today || 0} сегодня`
      )}
      ${renderAdminMetric("Питомцев", overview.pets_total)}
      ${renderAdminMetric("Заходов людей за 24 часа", productVisits, `${technicalVisits} технических скрыто`)}
      ${renderAdminMetric("Уникальных посетителей за 24 часа", overview.site_visitors_24h_product ?? 0)}
      ${renderAdminMetric("Заходов в кабинет за 24 часа", overview.site_logged_in_visits_24h)}
      ${renderAdminMetric(
        "Вошедших пользователей за 72 часа",
        overview.successful_login_users_72h ?? 0,
        `${overview.successful_login_events_72h || 0} событий входа`
      )}
      ${renderAdminMetric("Проверок в кабинете за 24 часа", overview.triage_24h)}
      ${renderAdminMetric("Активный Plus", overview.active_plus)}
      ${renderAdminMetric("Возврат D1 за 30 дней", overview.return_d1_users_30d || 0)}
      ${renderAdminMetric("Возврат D7 за 30 дней", overview.return_d7_users_30d || 0)}
      ${renderAdminMetric("Платежей за 30 дней", overview.paid_payments_30d, `${overview.revenue_30d_rub || 0} ₽`)}
      ${renderAdminMetric(
        "Токенов за 30 дней",
        formatAdminInteger(overview.tokens_30d),
        `Публичная проверка: ${formatAdminInteger(overview.tokens_30d_public)} · кабинет: ${formatAdminInteger(overview.tokens_30d_cabinet)}`
      )}
      ${renderAdminMetric("Активных напоминаний", overview.active_reminders)}
    </div>
  `;
}

function renderAdminFunnelPage(data) {
  const serviceFunnel = data.conversion_funnel_72h_service || {};
  const publicFunnel = data.conversion_funnel_72h_public || {};
  const authFunnel = data.conversion_funnel_72h_auth || {};
  const petFunnel = data.conversion_funnel_72h_pet || {};
  const foodFunnel = data.conversion_funnel_72h_food || {};
  const cuts = data.funnel_cuts_72h || {};
  const publicCuts = cuts.public || {};
  const petCuts = petFunnel.cuts || {};
  const foodCuts = foodFunnel.cuts || {};
  const lossReasons = data.funnel_loss_reasons_72h || {};
  const technical = data.funnel_technical_72h || {};
  const funnelColumns = [
    { key: "label", label: "Шаг", render: (row) => `<strong>${escapeHtml(row.label || row.step)}</strong>` },
    { key: "unique_count", label: "Уникальные" },
    { key: "count", label: "Всего событий" },
    { key: "conversion_from_previous", label: "Переход", render: (row) => row.conversion_from_previous == null ? "—" : `${escapeHtml(row.conversion_from_previous)}%` },
    { key: "issues", label: "Ошибки" },
    { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) },
    { key: "help", label: "Что значит" }
  ];
  const lossRows = [
    { name: "Не начат", sessions: lossReasons.not_started || 0 },
    { name: "Не отправлен", sessions: lossReasons.not_submitted || 0 },
    { name: "Результат не получен", sessions: lossReasons.result_not_received || 0 },
    { name: "Не увидели сохранение", sessions: lossReasons.save_cta_not_seen || 0 },
    { name: "Увидели, но не нажали сохранить", sessions: lossReasons.save_not_clicked || 0 },
    { name: "Повторный лимит", sessions: lossReasons.repeat_limit || 0 },
    { name: "Ошибка модели", sessions: lossReasons.model_error || 0 },
    { name: "Вход открыт", sessions: lossReasons.login_opened || 0 },
    { name: "Вход успешен", sessions: lossReasons.login_successful || 0 },
    { name: "Сохранение не завершено", sessions: lossReasons.save_incomplete || 0 },
  ];
  const petLoss = petFunnel.loss_reasons || {};
  const petLossRows = [
    { name: "Не нажали создать паспорт", sessions: petLoss.cta_not_clicked || 0 },
    { name: "Не открыли вход", sessions: petLoss.login_not_opened || 0 },
    { name: "Вход не завершили", sessions: petLoss.login_incomplete || 0 },
    { name: "Вошли, но питомца не добавили", sessions: petLoss.passport_not_created || 0 }
  ];
  const foodLoss = foodFunnel.loss_reasons || {};
  const foodLossRows = [
    { name: "Не отправили продукт", sessions: foodLoss.not_submitted || 0 },
    { name: "Ответ не получен", sessions: foodLoss.result_not_received || 0 },
    { name: "Не увидели сохранение", sessions: foodLoss.save_cta_not_seen || 0 },
    { name: "Увидели, но не нажали сохранить", sessions: foodLoss.save_not_clicked || 0 },
    { name: "Не открыли вход", sessions: foodLoss.login_not_opened || 0 },
    { name: "Вход не завершили", sessions: foodLoss.login_incomplete || 0 },
    { name: "Вошли, но ответ не сохранился", sessions: foodLoss.answer_not_saved || 0 }
  ];
  const foodLevelLabels = {
    allowed: "Можно понемногу",
    avoid: "Лучше не давать",
    not_found: "Не найдено в базе",
    need_ingredients: "Нужен состав",
    ingredients_checked: "Состав проверен",
    unknown: "Без категории"
  };
  const foodResultRows = (foodFunnel.result_levels || []).map((row) => ({
    ...row,
    name: foodLevelLabels[row.name] || row.name || "Не указано"
  }));
  const returns = cuts.returning || [];
  const eventColumns = [
    { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) },
    { key: "event_type", label: "Событие" },
    { key: "step", label: "Шаг" },
    { key: "status", label: "Статус", render: (row) => adminCell(adminStatusLabel(row.status)) },
    { key: "source", label: "Источник" },
    { key: "landing_path", label: "Первая страница" },
    { key: "utm_campaign", label: "Кампания" },
    { key: "device", label: "Устройство" }
  ];
  return `
    ${renderAdminPageHead("Воронка", "Путь людей за последние 72 часа. Автотесты и QA не участвуют в процентах.")}
    <section class="admin-section">
      <p class="admin-explain">Уникальность считается по обезличенной сессии или пользователю. Прямой переход из рекламы на /check считается с шага «Открыли проверку», поэтому главная страница больше не искажает конверсию.</p>
    </section>
    ${renderAdminTable("Главная продуктовая воронка — последние 72 часа", serviceFunnel.steps || [], funnelColumns, "За последние 72 часа продуктовых событий пока нет.")}
    ${renderAdminTable("Электронный паспорт — последние 72 часа", petFunnel.steps || [], funnelColumns, "За последние 72 часа событий паспорта пока нет.")}
    ${renderAdminTable("База продуктов — последние 72 часа", foodFunnel.steps || [], funnelColumns, "За последние 72 часа событий питания пока нет.")}
    ${renderAdminTable("Публичная проверка симптомов — последние 72 часа", publicFunnel.steps || [], funnelColumns, "За последние 72 часа событий проверки пока нет.")}
    ${renderAdminTable("Вход и кабинет — последние 72 часа", authFunnel.steps || [], funnelColumns, "За последние 72 часа авторизационных шагов пока нет.")}
    ${renderAdminTable("Где теряются люди: электронный паспорт — 72 часа", petLossRows, [
      { key: "name", label: "Причина" },
      { key: "sessions", label: "Сессии" }
    ])}
    ${renderAdminTable("Где теряются люди: база продуктов — 72 часа", foodLossRows, [
      { key: "name", label: "Причина" },
      { key: "sessions", label: "Сессии" }
    ])}
    ${renderAdminTable("Ответы базы продуктов — 72 часа", foodResultRows, [
      { key: "name", label: "Результат" },
      { key: "sessions", label: "Уникальные сессии" },
      { key: "events", label: "Всего ответов" }
    ], "Ответов базы продуктов за 72 часа пока нет.")}
    ${renderAdminTable("Причины потери до полного результата", lossRows, [
      { key: "name", label: "Причина" },
      { key: "sessions", label: "Сессии" }
    ], "Для расчёта причин потерь пока недостаточно данных.")}
    <p class="admin-data-note">«Результат не получен» означает, что форма отправлена, но показ результата не зафиксирован. «Повторный лимит» и «Ошибка модели» берутся из технического журнала. Директ считает клики, а Метрика — только визиты с разрешённой аналитикой, поэтому их числа могут отличаться.</p>
    ${renderAdminTable("Срез по рекламной кампании — 72 часа", publicCuts.campaign || [], [
      { key: "name", label: "Кампания" },
      { key: "sessions", label: "Сессии" }
    ], "По кампаниям данных за 72ч пока нет.")}
    ${renderAdminTable("Срез по посадочным страницам — 72 часа", publicCuts.landing || [], [
      { key: "name", label: "Посадка" },
      { key: "sessions", label: "Сессии" }
    ], "По посадкам данных за 72ч пока нет.")}
    ${renderAdminTable("Срез по устройствам — 72 часа", publicCuts.device || [], [
      { key: "name", label: "Устройство" },
      { key: "sessions", label: "Сессии" }
    ], "По устройствам данных за 72ч пока нет.")}
    ${renderAdminTable("Новый или повторный посетитель — 72 часа", returns || [], [
      { key: "name", label: "Тип" },
      { key: "sessions", label: "Сессии" }
    ], "Для новых и повторных посетителей данных за 72ч пока нет.")}
    ${renderAdminTechnicalDetails(
      "Срезы рекламы: электронный паспорт — 72 часа",
      `${renderAdminTable("Кампании", petCuts.campaign || [], [
        { key: "name", label: "Кампания" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Посадочные страницы", petCuts.landing || [], [
        { key: "name", label: "Посадка" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Устройства", petCuts.device || [], [
        { key: "name", label: "Устройство" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Новые и повторные", petFunnel.returning || [], [
        { key: "name", label: "Тип" },
        { key: "sessions", label: "Сессии" }
      ])}`,
      "Срезы не смешиваются с проверкой симптомов."
    )}
    ${renderAdminTechnicalDetails(
      "Срезы рекламы: база продуктов — 72 часа",
      `${renderAdminTable("Кампании", foodCuts.campaign || [], [
        { key: "name", label: "Кампания" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Посадочные страницы", foodCuts.landing || [], [
        { key: "name", label: "Посадка" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Устройства", foodCuts.device || [], [
        { key: "name", label: "Устройство" },
        { key: "sessions", label: "Сессии" }
      ])}
      ${renderAdminTable("Новые и повторные", foodFunnel.returning || [], [
        { key: "name", label: "Тип" },
        { key: "sessions", label: "Сессии" }
      ])}`,
      "Кошка и собака остаются отдельными посадками."
    )}
    ${renderAdminTechnicalDetails(
      `Технические данные и автотесты: ${technical.events || 0} событий / ${technical.sessions || 0} сессий`,
      `${renderAdminTable("Автотесты и QA", data.recent_funnel_events_technical || [], eventColumns, "QA-событий за период нет.")}
       ${renderAdminTable("Сырой журнал продуктовых событий", data.recent_funnel_events_product || [], eventColumns, "Продуктовых событий пока нет.")}`,
      "Эти строки сохранены для диагностики, но не входят в основные проценты воронки."
    )}
  `;
}

function renderAdminTrafficPage(data) {
  const overview = data.overview || {};
  const visitColumns = [
    { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) },
    { key: "path", label: "Страница" },
    { key: "user_email", label: "Кто", render: renderSiteVisitUser },
    { key: "source", label: "Источник", render: renderSiteVisitSource },
    { key: "device", label: "Устройство", render: renderSiteVisitDevice },
    { key: "status_code", label: "HTTP" }
  ];
  return `
    ${renderAdminPageHead("Посещения", "Посещения людей за последние 24 часа. Боты, сканеры и проверки вынесены отдельно.")}
    <section class="admin-section">
      <div class="summary-grid admin-summary admin-traffic-summary">
        ${renderAdminMetric("Заходов людей", overview.site_visits_24h_product ?? 0)}
        ${renderAdminMetric("Уникальных посетителей", overview.site_visitors_24h_product ?? 0)}
        ${renderAdminMetric("Технических заходов", overview.site_visits_24h_technical ?? 0, "Не входят в продуктовую статистику")}
      </div>
      <p class="admin-explain">«Анонимно» означает, что человек не вошёл. IP не хранится в открытом виде; для уникальности используется только обезличенный хэш.</p>
    </section>
    ${renderAdminTable("Источники людей — 24 часа", data.site_sources_24h_product || [], [
      { key: "source", label: "Источник" },
      { key: "count", label: "Заходы" },
      { key: "visitors", label: "Уникальные" },
      { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) }
    ], "За последние 24 часа посещений людей не было.")}
    ${renderAdminTable("Страницы людей — 24 часа", data.site_paths_24h_product || [], [
      { key: "path", label: "Страница" },
      { key: "count", label: "Заходы" },
      { key: "visitors", label: "Уникальные" },
      { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) }
    ], "За последние 24 часа люди не открывали публичные страницы.")}
    ${renderAdminTable("Последние посещения людей", data.recent_site_visits_product || [], visitColumns, "Посещения людей ещё не записаны.")}
    ${renderAdminTechnicalDetails(
      `Боты, сканеры и автоматические проверки: ${overview.site_visits_24h_technical || 0}`,
      `${renderAdminTable("Технические источники — 24 часа", data.site_sources_24h_technical || [], [
        { key: "source", label: "Источник" },
        { key: "count", label: "Заходы" },
        { key: "visitors", label: "Уникальные" },
        { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) }
      ], "Технического трафика нет.")}
      ${renderAdminTable("Технические пути — 24 часа", data.site_paths_24h_technical || [], [
        { key: "path", label: "Путь" },
        { key: "count", label: "Запросы" },
        { key: "visitors", label: "Уникальные" },
        { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) }
      ], "Технических путей нет.")}
      ${renderAdminTable("Последние технические заходы", data.recent_site_visits_technical || [], visitColumns, "Технических заходов нет.")}`,
      "Ничего не удалено: технический трафик остаётся доступным для диагностики."
    )}
  `;
}

function renderAdminSystemPage(data, system, statusItems) {
  const events1h = system?.events_1h || {};
  const events24h = system?.events_24h || {};
  const integrationEvents = system?.integration_events_24h || [];
  const statusHelp = system?.status_help || {};
  return `
    ${renderAdminPageHead("Система", "Подключения, серверные ошибки, интеграции и короткая сводка безопасности.")}
    <section class="admin-section">
      <h2>Системный статус</h2>
      <p class="admin-explain">«Не подключено» не означает взлом или потерю данных: функция просто не будет доступна, пока не добавлены нужные ключи или секреты. Критично только если «Проблема» у базы.</p>
      <div class="admin-status-grid">
        ${statusItems.map(([key, label, ok]) => `
          <div class="admin-status ${adminIntegrationStatusClass(key, ok)}">
            <strong>${adminIntegrationStatusLabel(key, ok)}</strong>
            <span>${escapeHtml(label)}</span>
            <small>${escapeHtml(statusHelp[key] || "")}</small>
          </div>
        `).join("")}
      </div>
    </section>
    <section class="admin-section">
      <h2>Как читать ошибки</h2>
      <p class="admin-explain">«События с ошибкой» — это не всегда взлом. Сюда попадают неверные коды входа, истёкшие сессии, частые запросы, попытки открыть чужие данные и технические ошибки API.</p>
      <div class="admin-error-grid">
        ${renderAdminMetric("API/сервер за 1ч", events1h.server_5xx ?? "—", "Если 0, сайт сейчас отвечает; число за 24ч может быть старой историей после перезапуска.")}
        ${renderAdminMetric("API/сервер за 24ч", events24h.server_5xx ?? "—", "5xx: серверная ошибка или временная недоступность API.")}
        ${renderAdminMetric("Оплата за 24ч", events24h.payment_errors ?? "—", "Сбои создания/проверки платежа YooKassa.")}
        ${renderAdminMetric("LLM за 24ч", events24h.llm_errors ?? "—", "Сбои оценки состояния через модель или шлюз OpenAI.")}
        ${renderAdminMetric("Синхронизация за 24ч", events24h.sync_errors ?? "—", "Сбои обмена данными между Telegram-ботом и PWA.")}
      </div>
    </section>
    ${renderAdminTable("Интеграции за 24 часа", integrationEvents, [
      { key: "label", label: "Блок" },
      { key: "status", label: "Статус", render: (row) => adminCell(adminStatusLabel(row.status)) },
      { key: "errors", label: "Ошибки" },
      { key: "warnings", label: "Предупреждения" },
      { key: "last_at", label: "Последнее событие", render: (row) => formatDateTime(row.last_at) },
      { key: "help", label: "Что проверять" }
    ], "За последние 24 часа интеграционных предупреждений и ошибок не было.")}
    ${renderAdminTable("Что произошло за последние 24 часа", data.audit_breakdown_24h || [], [
      { key: "event_type", label: "Событие", render: renderAuditEventCell },
      { key: "status", label: "Уровень", render: (row) => adminCell(adminStatusLabel(row.status)) },
      { key: "count", label: "Сколько раз" },
      { key: "last_at", label: "Последний раз", render: (row) => formatDateTime(row.last_at) },
      { key: "help", label: "Что это значит", render: renderAuditHelpCell }
    ], "За последние 24 часа предупреждений и ошибок не было.")}
  `;
}

function renderAdminPaymentsPage(data) {
  return `
    ${renderAdminPageHead("Платежи", "Статусы оплат, сумма и последние события YooKassa.")}
    ${renderAdminTable("Платежи по статусам", data.payments_by_status || [], [
      { key: "status", label: "Статус" },
      { key: "count", label: "Кол-во" },
      { key: "amount_rub", label: "Сумма, ₽" }
    ])}
    ${renderAdminTable("Последние платежи", data.recent_payments || [], [
      { key: "id", label: "ID" },
      { key: "email", label: "Пользователь" },
      { key: "provider", label: "Провайдер" },
      { key: "provider_payment_id", label: "Платёж" },
      { key: "amount_rub", label: "₽" },
      { key: "status", label: "Статус" },
      { key: "created_at", label: "Создан", render: (row) => formatDateTime(row.created_at) },
      { key: "paid_at", label: "Оплачен", render: (row) => formatDateTime(row.paid_at) }
    ])}
  `;
}

function renderAdminUsersPage(data) {
  const userColumns = [
    { key: "id", label: "ID" },
    { key: "email", label: "Email" },
    { key: "providers", label: "Способ входа" },
    { key: "plan", label: "Тариф" },
    { key: "pets_count", label: "Питомцы" },
    { key: "triage_count", label: "Проверки" },
    { key: "created_at", label: "Создан", render: (row) => formatDateTime(row.created_at) }
  ];
  return `
    ${renderAdminPageHead("Пользователи", "Пользовательские аккаунты, проверки и обратная связь. Служебный аккаунт показан отдельно.")}
    ${renderAdminTable("Последние пользователи", data.recent_users_product || data.recent_users || [], userColumns)}
    ${renderAdminTable("Последние проверки без медицинского текста", data.recent_triage || [], [
      { key: "id", label: "ID" },
      { key: "user_id", label: "User" },
      { key: "pet_name", label: "Питомец", render: (row) => adminCell(row.pet_name ? `${row.pet_type || "питомец"} — ${row.pet_name}` : "—") },
      { key: "urgency_level", label: "Срочность" },
      { key: "total_tokens", label: "Токены", render: (row) => adminCell(formatAdminInteger(row.total_tokens)) },
      { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
    ])}
    ${renderAdminTable("Обратная связь", data.recent_feedback || [], [
      { key: "id", label: "ID" },
      { key: "email", label: "Пользователь" },
      { key: "category", label: "Категория" },
      { key: "preview", label: "Кратко" },
      { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
    ])}
    ${renderAdminTechnicalDetails(
      `Служебные аккаунты: ${(data.recent_users_service || []).length}`,
      renderAdminTable("Служебные аккаунты", data.recent_users_service || [], userColumns, "Служебных аккаунтов нет."),
      "Служебный аккаунт не входит в число пользователей на главном экране, но его данные не удалены."
    )}
  `;
}

function renderAdminAuditPage(data) {
  const auditColumns = [
    { key: "id", label: "ID" },
    { key: "event_type", label: "Событие", render: renderAuditEventCell },
    { key: "status", label: "Статус", render: (row) => adminCell(adminStatusLabel(row.status)) },
    { key: "help", label: "Пояснение", render: renderAuditHelpCell },
    { key: "actor", label: "Кто" },
    { key: "user_id", label: "User" },
    { key: "provider", label: "Канал" },
    { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
  ];
  return `
    ${renderAdminPageHead("Журнал", "Важные входы, предупреждения и ошибки. Обычные просмотры админки скрыты в техническом журнале.")}
    ${renderAdminTable("Важные события", data.recent_audit || [], auditColumns)}
    ${renderAdminTechnicalDetails(
      "Полный технический журнал",
      renderAdminTable("Все служебные события", data.recent_audit_raw || [], auditColumns),
      "Здесь остаются просмотры админки и пустые автоматические проверки. Ничего не удалено."
    )}
  `;
}

function renderAdminPageContent(data, system, statusItems) {
  if (adminCurrentPage === "funnel") return renderAdminFunnelPage(data);
  if (adminCurrentPage === "traffic") return renderAdminTrafficPage(data);
  if (adminCurrentPage === "system") return renderAdminSystemPage(data, system, statusItems);
  if (adminCurrentPage === "payments") return renderAdminPaymentsPage(data);
  if (adminCurrentPage === "users") return renderAdminUsersPage(data);
  if (adminCurrentPage === "audit") return renderAdminAuditPage(data);
  return renderAdminOverviewPage(data);
}

function renderAdminActivePage() {
  if (!adminContent || !adminDashboardData) return;
  const data = adminDashboardData;
  const system = adminSystemData || {};
  const checks = system?.checks || {};
  const statusItems = [
    ["database", "База", system?.checks?.database?.ok],
    ["email_configured", "Email", checks.email_configured],
    ["telegram_login_configured", "Telegram-вход", checks.telegram_login_configured],
    ["max_login_configured", "MAX-вход", checks.max_login_configured],
    ["yookassa_configured", "YooKassa", checks.yookassa_configured],
    ["llm_configured", "LLM-разбор", checks.llm_configured],
    ["core_api_configured", "Core API синхронизации", checks.core_api_configured]
  ];
  adminContent.innerHTML = `
    <div class="admin-toolbar">
      <div class="admin-generated">Обновлено: ${formatDateTime(data.generated_at)}</div>
      ${renderAdminNav()}
    </div>
    <div class="admin-page">
      ${renderAdminPageContent(data, system, statusItems)}
    </div>
  `;
}

function renderAdminDashboard(data, system = null) {
  adminDashboardData = data;
  adminSystemData = system;
  adminCurrentPage = adminPageFromLocation();
  renderAdminActivePage();
}

async function loadAdminDashboard() {
  setAdminMode(true);
  adminContent.innerHTML = `<div class="notice">Загружаю данные админки...</div>`;
  const [dashboard, system] = await Promise.all([
    adminApi("/api/admin/dashboard"),
    adminApi("/api/admin/system/status")
  ]);
  renderAdminDashboard(dashboard, system);
}

async function bootstrapAdmin() {
  setAdminMode(false);
  try {
    await loadAdminDashboard();
  } catch (error) {
    setAdminMode(false);
    if (!["authorization_required", "invalid_admin_session"].includes(error.message)) {
      setAdminHint(adminReadableError(error.message), true);
    }
    setTimeout(() => adminPasswordInput?.focus(), 0);
  }
}

function clearStartupAction() {
  const startupAction = getStartupAction();
  if (!startupAction) return;
  consumedStartupAction = startupAction;
  sessionStorage.removeItem(PENDING_STARTUP_ACTION_KEY);
  const url = new URL(window.location.href);
  url.searchParams.delete("action");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

async function renderStartupView() {
  const startupAction = getStartupAction();
  if (startupAction === "home") {
    await renderHome();
    clearStartupAction();
    return;
  }
  if (startupAction === "triage") {
    await renderTriage();
    clearStartupAction();
    return;
  }
  if (startupAction === "pets") {
    await renderPets();
    clearStartupAction();
    return;
  }
  if (startupAction === "reminders") {
    await renderReminders();
    clearStartupAction();
    return;
  }
  if (startupAction === "subscription") {
    await refreshAccountState();
    renderSubscription();
    clearStartupAction();
    return;
  }
  if (startupAction === "more") {
    renderMore();
    clearStartupAction();
    return;
  }
  const campaign = getPublicCampaignLanding();
  if (campaign?.kind === "pet") {
    await renderPets();
    return;
  }
  if (campaign?.kind === "food") {
    await renderFood();
    return;
  }
  await renderHome();
}

function applyAccountState(data) {
  state.token = "";
  localStorage.removeItem("tvv_token");
  state.user = data.user || null;
  state.externalAccounts = data.external_accounts || [];
  state.subscription = data.subscription || null;
  state.telegramProfileSync = data.telegram_profile_sync || null;
  state.lastSyncCheckAt = new Date().toISOString();
}

function clearAccountState() {
  state.token = "";
  state.user = null;
  state.externalAccounts = [];
  state.subscription = null;
  state.pets = [];
  state.currentPetId = null;
  state.pushConfig = null;
  state.lastPlusPaymentId = "";
  state.telegramProfileSync = null;
  state.lastSyncCheckAt = "";
  localStorage.removeItem("tvv_token");
  localStorage.removeItem("tvv_last_plus_payment_id");
}

async function bootstrap() {
  if (isAdminRoute) {
    await bootstrapAdmin();
    return;
  }
  const shouldCheckPayment = new URLSearchParams(window.location.search).get("payment") === "plus";
  if (!state.token) {
    if (await tryMaxMiniAppLogin()) return;
    try {
      const data = await api("/api/me");
      applyAccountState(data);
      setAuthMode(true);
      if (shouldCheckPayment) {
        renderSubscription(`<div class="notice">Вернулись с оплаты. Проверяю статус платежа...</div>`);
        await checkPlusPaymentStatus({ replaceHistory: true });
        return;
      }
      clearAuthLinkRequest();
      if (await completePendingSaveAfterLogin()) return;
      await renderStartupView();
      return;
    } catch {
      clearAccountState();
    }
    setAuthMode(false);
    openAuthDialogFromLink();
    if (state.telegramLoginState) {
      openAuthDialog();
      renderTelegramWaiting(state.telegramLoginUrl, state.telegramLoginState);
      pollTelegramLogin(state.telegramLoginState);
    }
    if (state.maxLoginState) {
      openAuthDialog();
      renderMaxWaiting(state.maxLoginUrl, state.maxLoginState);
      pollMaxLogin(state.maxLoginState);
    }
    return;
  }
  try {
    const data = await api("/api/me");
    applyAccountState(data);
    setAuthMode(true);
    if (shouldCheckPayment) {
      renderSubscription(`<div class="notice">Вернулись с оплаты. Проверяю статус платежа...</div>`);
      await checkPlusPaymentStatus({ replaceHistory: true });
      return;
    }
    clearAuthLinkRequest();
    if (await completePendingSaveAfterLogin()) return;
    await renderStartupView();
  } catch {
    localStorage.removeItem("tvv_token");
    state.token = "";
    clearAccountState();
    setAuthMode(false);
    openAuthDialogFromLink();
    if (state.telegramLoginState) {
      openAuthDialog();
      renderTelegramWaiting(state.telegramLoginUrl, state.telegramLoginState);
      pollTelegramLogin(state.telegramLoginState);
    }
    if (state.maxLoginState) {
      openAuthDialog();
      renderMaxWaiting(state.maxLoginUrl, state.maxLoginState);
      pollMaxLogin(state.maxLoginState);
    }
  }
}

async function refreshPets() {
  const data = await api("/api/pets");
  state.pets = data.items || [];
  return state.pets;
}

async function refreshAccountState() {
  const data = await api("/api/me");
  applyAccountState(data);
  return data;
}

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = `${base64String}${padding}`.replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) output[index] = raw.charCodeAt(index);
  return output;
}

async function loadPushConfig(force = false) {
  if (state.pushConfig && !force) return state.pushConfig;
  try {
    state.pushConfig = await api("/api/push/config");
  } catch {
    state.pushConfig = {
      enabled: false,
      public_key: "",
      message: "Напоминания на этом устройстве временно недоступны."
    };
  }
  return state.pushConfig;
}

async function loadPushStatus() {
  const config = await loadPushConfig();
  let status = { enabled: Boolean(config.enabled), count: 0, items: [] };
  try {
    status = await api("/api/push/subscriptions");
  } catch {
    status = { enabled: Boolean(config.enabled), count: 0, items: [] };
  }
  return { config, status };
}

function petOptions(selectedId = "") {
  if (!state.pets.length) return `<option value="">Сначала добавьте питомца</option>`;
  return state.pets
    .map((pet) => `<option value="${pet.id}" ${String(pet.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(petTitle(pet))}</option>`)
    .join("");
}

function renderAppIcon(name, extraClass = "") {
  const safeName = String(name || "activity").replace(/[^a-z0-9-]/g, "");
  const safeExtraClass = String(extraClass || "").replace(/[^a-z0-9 _-]/gi, "");
  return `<span class="app-icon icon-${safeName}${safeExtraClass ? ` ${safeExtraClass}` : ""}" aria-hidden="true"></span>`;
}

function renderPetBadges(pet) {
  const parts = [];
  const age = formatPetAgeCompact(pet);
  const weight = formatPetWeight(pet);
  const sex = formatPetSex(pet.sex);
  if (age) parts.push(`Возраст: ${age}`);
  if (weight) parts.push(`Вес: ${weight}`);
  if (pet.breed) parts.push(`Порода: ${pet.breed}`);
  if (sex) parts.push(`Пол: ${sex}`);
  return parts.length ? `<div class="meta-row">${parts.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : "";
}

function subscriptionSummary() {
  const sub = state.subscription || {};
  const planTitle = sub.title || (sub.plan === "plus" ? "Plus" : "Free");
  const quotaTotal = Number.isFinite(Number(sub.quota_total)) ? Number(sub.quota_total) : 0;
  const quotaUsed = Number.isFinite(Number(sub.quota_used)) ? Number(sub.quota_used) : 0;
  const quotaLeft = Number.isFinite(Number(sub.quota_left)) ? Number(sub.quota_left) : Math.max(0, quotaTotal - quotaUsed);
  const source = sub.source === "telegram" ? "Telegram" : "PWA";
  return { planTitle, quotaTotal, quotaUsed, quotaLeft, source };
}

function connectedProviderLabels() {
  const labels = [];
  if (state.user?.email) labels.push("Электронная почта");
  if (isProviderConnected("telegram")) labels.push("Telegram");
  if (isProviderConnected("max")) labels.push("MAX");
  return labels.length ? labels.join(", ") : "не подключены";
}

function renderHomeGuide(hasPets) {
  return `
    <section class="guide-panel">
      <div class="guide-copy">
        <p class="section-label">С чего начать</p>
        <h3>Это ваш личный кабинет здоровья питомца</h3>
        <p>Выберите ближайший шаг. Все события сохраняются в истории, если привязать их к карточке питомца.</p>
      </div>
      <div class="guide-steps">
        <button class="guide-step" data-action="pets" type="button">
          <strong>${hasPets ? "1. Проверьте карточку" : "1. Добавьте питомца"}</strong>
          <span>${hasPets ? "Возраст, вес и основной питомец уже сохранены в карточке." : "Так ответы, вес и напоминания будут храниться в одном месте."}</span>
        </button>
        <button class="guide-step" data-action="triage" type="button">
          <strong>2. Расскажите, что случилось</strong>
          <span>Опишите ситуацию простыми словами, чтобы получить понятный ответ.</span>
        </button>
        <button class="guide-step" data-action="reminders" type="button">
          <strong>3. Поставьте напоминание</strong>
          <span>Вакцинация, обработка от паразитов, осмотр, груминг или своя задача.</span>
        </button>
      </div>
    </section>
  `;
}

function isStandalonePwa() {
  return window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;
}

function renderPwaInstallGuide() {
  const installed = isStandalonePwa();
  return `
    <section class="guide-panel install-guide-panel">
      <div class="guide-copy">
        <p class="section-label">Приложение на экране</p>
        <h3>${installed ? "TemichevVet открыт как приложение" : "Добавьте TemichevVet на экран телефона"}</h3>
        <p>${installed
          ? "Можно пользоваться личным кабинетом как обычным приложением: питомцы, история и напоминания останутся в одном аккаунте."
          : "На iPhone нажмите «Поделиться» → «На экран Домой». На Android откройте меню браузера → «Установить приложение». Это быстрее, чем каждый раз искать сайт."}</p>
      </div>
      <div class="guide-steps">
        <div class="guide-step static-step">
          <strong>iPhone</strong>
          <span>Safari → Поделиться → На экран Домой.</span>
        </div>
        <div class="guide-step static-step">
          <strong>Android</strong>
          <span>Chrome → меню → Установить приложение.</span>
        </div>
      </div>
    </section>
  `;
}

function parseTriageSections(answer) {
  const text = String(answer || "").trim();
  if (!text) return [];
  const matches = [...text.matchAll(/(?:^|\n)\s*(\d+)[).]\s+([^\n:]+):?/g)];
  if (matches.length < 2) return [{ title: "Рекомендации", body: text }];
  return matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
    return {
      title: `${match[1]}. ${match[2].trim()}`,
      body: text.slice(start, end).trim()
    };
  });
}

function formatTriageAnswer(answer) {
  const sections = parseTriageSections(answer);
  return `
    <div class="triage-answer">
      ${sections.map((section) => `
        <article class="triage-answer-card">
          <h3>${escapeHtml(section.title)}</h3>
          <p>${nl2br(section.body)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

const historyEventLabels = {
  triage: "Разбор здоровья",
  reminder: "Напоминание",
  weight: "Вес",
  profile: "Карточка питомца",
  observation: "Наблюдение",
  vaccination: "Вакцинация"
};

function humanizeUiText(value) {
  return String(value || "")
    .replace(/\btriage\b/gi, "Разбор здоровья")
    .replace(/REMINDER_VACCINATION_CREATED/g, "Создано напоминание: вакцинация")
    .replace(/REMINDER_CREATED/g, "Создано напоминание")
    .replace(/Разбор жалобы/g, "Разбор здоровья")
    .replace(/красные симптомы/g, "опасные признаки")
    .replace(/онлайн-ответ/g, "ответ сервиса");
}

function historyTitle(item) {
  const raw = humanizeUiText(item.title || "");
  if (raw) return raw;
  return historyEventLabels[item.event_type] || "Событие здоровья";
}

function historyEventLabel(item) {
  return historyEventLabels[item.event_type] || humanizeUiText(item.event_type || "Событие");
}

function inferUrgencyMeta(text) {
  const value = String(text || "").toLowerCase();
  if (value.includes("срочно") || value.includes("красн") || value.includes("немедлен") || value.includes("в клинику")) {
    return { label: "Срочно", className: "danger" };
  }
  if (value.includes("консультац") || value.includes("показать") || value.includes("врачу")) {
    return { label: "Нужна консультация", className: "warn" };
  }
  if (value.includes("наблюд") || value.includes("зел")) {
    return { label: "Наблюдение", className: "ok" };
  }
  return { label: "Событие", className: "neutral" };
}

function compactText(value, limit = 170) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trim()}…`;
}

function renderHistoryCard(item) {
  const details = humanizeUiText(item.details || "");
  const meta = inferUrgencyMeta(`${item.title || ""} ${details}`);
  const summary = compactText(details || historyTitle(item));
  return `
    <article class="item-card history-card">
      <div>
        <div class="history-meta">
          <span class="status-dot ${meta.className}">${escapeHtml(meta.label)}</span>
          <span>${escapeHtml(historyEventLabel(item))}</span>
          <span>${escapeHtml(formatDateTime(item.created_at))}</span>
        </div>
        <h3>${escapeHtml(historyTitle(item))}</h3>
        ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
        ${details && details.length > summary.length ? `
          <details class="history-details">
            <summary>Показать полный текст</summary>
            <p>${nl2br(details)}</p>
          </details>
        ` : ""}
      </div>
    </article>
  `;
}

function renderEmptyBlock({ icon = "activity", title, text, action, actionText }) {
  return `
    <div class="empty-state empty-card">
      <div class="empty-icon">${renderAppIcon(icon)}</div>
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(text)}</p>
        ${action ? `<button class="primary-button compact" data-action="${escapeHtml(action)}" type="button">${escapeHtml(actionText || "Продолжить")}</button>` : ""}
      </div>
    </div>
  `;
}

async function loadDueFollowups() {
  try {
    const data = await api("/api/followups/due");
    return data.items || [];
  } catch {
    return [];
  }
}

function renderDueFollowups(items) {
  if (!items.length) return "";
  const cards = items
    .map((item) => {
      const pet = item.pet_name ? `${item.pet_type || "питомец"} — ${item.pet_name}` : "питомец";
      return `
        <article class="item-card followup-card">
          <div>
            <h3>Как питомец чувствует себя сейчас?</h3>
            <p>Недавно вы рассказывали о самочувствии: ${escapeHtml(pet)}.</p>
            <small>Если стало хуже — лучше не ждать и обратиться в клинику.</small>
          </div>
          <div class="inline-actions">
            <button class="secondary-button compact" data-followup-answer="better" data-followup-id="${item.id}" type="button">Стало лучше</button>
            <button class="secondary-button compact" data-followup-answer="same" data-followup-id="${item.id}" type="button">Без изменений</button>
            <button class="secondary-button compact danger-text" data-followup-answer="worse" data-followup-id="${item.id}" type="button">Стало хуже</button>
            <button class="primary-button compact" data-followup-answer="retry" data-followup-id="${item.id}" type="button">Рассказать ещё раз</button>
          </div>
        </article>
      `;
    })
    .join("");
  return `<section class="profile-card due-followups"><h3>Проверить самочувствие</h3><div class="list-stack">${cards}</div></section>`;
}

async function renderHome() {
  await refreshAccountState();
  await refreshPets();
  const dueFollowups = await loadDueFollowups();
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  const petData = mainPet ? await api(`/api/pets/${mainPet.id}`) : null;
  const sub = subscriptionSummary();
  const latestWeight = petData?.weights?.[0] || null;
  const previousWeight = petData?.weights?.[1] || null;
  const weightChange = latestWeight && previousWeight
    ? Number(latestWeight.weight_kg) - Number(previousWeight.weight_kg)
    : null;
  const latestObservation = petData?.observations?.[0] || null;
  const nearestReminder = petData?.reminders?.[0] || null;
  const latestHistory = petData?.history?.[0] || null;
  const observationText = latestObservation ? observationDisplayText(latestObservation) : "Пока нет наблюдений";
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <p class="section-label">Ваш кабинет</p>
        <h2>${mainPet ? `Всё важное о «${escapeHtml(mainPet.pet_name)}»` : "Добавьте питомца — и всё важное будет рядом"}</h2>
        <p>${mainPet ? "Вес, наблюдения, даты и история собраны в одном постоянном контексте." : "Карточка поможет не терять историю, вес и важные даты."}</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="pets" type="button">${renderAppIcon("paw-print")}<span>Питомцы</span></button>
    </div>
    ${mainPet ? `
      <section class="profile-card pet-context-card">
        <div class="card-title-row">
          <div class="card-icon large">${renderAppIcon("paw-print")}</div>
          <div><p class="section-label">Выбранный питомец</p><h3>${escapeHtml(petTitle(mainPet))}</h3>${renderPetBadges(mainPet)}</div>
        </div>
        <div class="pet-context-metrics">
          <div><small>Последний вес</small><strong>${latestWeight ? `${escapeHtml(latestWeight.weight_kg)} кг` : "Не записан"}</strong><span>${weightChange === null ? "Добавьте первую запись" : `${weightChange > 0 ? "+" : ""}${weightChange.toFixed(2)} кг к предыдущей`}</span></div>
          <div><small>Последнее наблюдение</small><strong>${escapeHtml(compactText(observationText, 58))}</strong><span>${latestObservation ? formatDateTime(latestObservation.created_at) : "История начнётся с первой записи"}</span></div>
          <div><small>Ближайшая дата</small><strong>${nearestReminder ? escapeHtml(nearestReminder.title) : "Не добавлена"}</strong><span>${nearestReminder ? escapeHtml(nearestReminder.due_date) : "Прививка, обработка или осмотр"}</span></div>
          <div><small>Последнее действие</small><strong>${latestHistory ? escapeHtml(historyTitle(latestHistory)) : "История пока пустая"}</strong><span>${latestHistory ? formatDateTime(latestHistory.created_at) : "Все события будут по датам"}</span></div>
        </div>
        <div class="inline-actions"><button class="text-button" data-open-pet="${mainPet.id}" type="button">Открыть карточку</button><button class="text-button" data-pet-view="summary" data-pet-id="${mainPet.id}" type="button">Подготовить сводку для врача</button></div>
      </section>
      <section aria-labelledby="quickActionsTitle">
        <div class="section-heading"><p class="section-label">Быстрые действия</p><h3 id="quickActionsTitle">Что добавить в историю</h3></div>
        <div class="pet-action-grid home-service-actions">
          <button class="menu-card" data-pet-view="observations" data-pet-id="${mainPet.id}" type="button">${renderAppIcon("clipboard-list")}<span><strong>Добавить запись</strong><small>Наблюдение или изменение</small></span></button>
          <button class="menu-card" data-pet-view="weight" data-pet-id="${mainPet.id}" type="button">${renderAppIcon("scale")}<span><strong>Записать вес</strong><small>Продолжить динамику</small></span></button>
          <button class="menu-card" data-pet-view="reminders" data-pet-id="${mainPet.id}" type="button">${renderAppIcon("bell")}<span><strong>Добавить дату</strong><small>Прививка, обработка, осмотр</small></span></button>
          <button class="menu-card" data-action="food" type="button">${renderAppIcon("utensils")}<span><strong>Проверить питание</strong><small>Ответ можно сохранить</small></span></button>
          <button class="menu-card" data-pet-view="triage" data-pet-id="${mainPet.id}" type="button">${renderAppIcon("heart-pulse")}<span><strong>Рассказать об изменении</strong><small>Сохранить разбор в историю</small></span></button>
        </div>
      </section>
    ` : `
      <section class="profile-card empty-service-start">
        ${renderEmptyBlock({ icon: "paw-print", title: "Создайте карточку питомца", text: "Для начала достаточно вида и клички." })}
        <button class="primary-button" data-open-onboarding type="button">Добавить питомца</button>
      </section>
    `}
    <article class="profile-card plan-status-card"><p class="section-label">Доступ</p><h3>${escapeHtml(sub.planTitle)}</h3><p>${sub.quotaLeft} из ${sub.quotaTotal} разборов доступно. Данные питомцев и записи не удаляются после окончания Plus.</p><button class="text-button" data-action="subscription" type="button">Условия подписки</button></article>
    ${renderDueFollowups(dueFollowups)}
  `, { scroll: false });
}

function renderMore() {
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Все разделы</h2>
        <p>История здоровья, питание, полезные материалы и настройки.</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="more-menu-grid">
      <button class="menu-card" data-action="history" type="button">${renderAppIcon("history")}<span><strong>История здоровья</strong><small>Все сохранённые события</small></span></button>
      <button class="menu-card" data-action="food" type="button">${renderAppIcon("utensils")}<span><strong>Питание</strong><small>Продукты и готовые блюда</small></span></button>
      <button class="menu-card" data-action="care" type="button">${renderAppIcon("heart-pulse")}<span><strong>Уход и привычки</strong><small>Ежедневная забота</small></span></button>
      <button class="menu-card" data-action="faq" type="button">${renderAppIcon("book-open")}<span><strong>Вопросы и ответы</strong><small>Короткие справочные материалы</small></span></button>
      <button class="menu-card" data-action="observations" type="button">${renderAppIcon("clipboard-list")}<span><strong>Наблюдения</strong><small>Поведение и самочувствие</small></span></button>
      <button class="menu-card" data-action="subscription" type="button">${renderAppIcon("credit-card")}<span><strong>Подписка</strong><small>Тариф и доступные разборы</small></span></button>
      <button class="menu-card" data-action="account" type="button">${renderAppIcon("settings")}<span><strong>Настройки</strong><small>Вход, уведомления и данные</small></span></button>
      <button class="menu-card" data-action="feedback" type="button">${renderAppIcon("mail")}<span><strong>Связаться с нами</strong><small>Вопрос по работе сервиса</small></span></button>
    </div>
  `);
}

function isProviderConnected(provider) {
  return state.externalAccounts.some((account) => account.provider === provider);
}

function providerAccount(provider) {
  return state.externalAccounts.find((account) => account.provider === provider) || null;
}

function telegramSyncReasonText(reason) {
  const reasons = {
    telegram_not_linked: "Telegram ещё не подключён к этому кабинету.",
    telegram_db_not_configured: "Связь с Telegram временно недоступна.",
    telegram_user_not_found: "Связь с Telegram установлена не полностью. Откройте мессенджер и вернитесь сюда.",
    sync_error: "Последняя проверка не завершилась. Обычно помогает открыть раздел ещё раз через минуту."
  };
  return reasons[reason] || "Если данные в Telegram и кабинете отличаются, откройте этот раздел ещё раз или напишите в поддержку.";
}

function renderSyncStatusCard() {
  const telegram = providerAccount("telegram");
  const max = providerAccount("max");
  const sync = state.telegramProfileSync || {};
  const checkedAt = state.lastSyncCheckAt ? formatDateTime(state.lastSyncCheckAt) : "—";
  const telegramConnected = Boolean(telegram);
  const maxConnected = Boolean(max);
  const syncOk = telegramConnected && sync.synced !== false;
  const statusLabel = !telegramConnected ? "Не подключён" : syncOk ? "Данные обновлены" : "Нужно обновить связь";
  const statusClass = !telegramConnected ? "neutral" : syncOk ? "connected" : "warning";
  const detail = !telegramConnected
    ? "Подключите Telegram, чтобы пользоваться одним аккаунтом на сайте и в мессенджере."
    : syncOk
      ? "Питомцы, история и подписка доступны в одном аккаунте."
      : "Откройте настройки ещё раз через минуту. Если связь не восстановится, напишите в поддержку.";
  const imported = syncOk
    ? [
        ["Питомцы", sync.pets_imported, sync.pets_linked],
        ["Напоминания", sync.reminders_imported],
        ["История", sync.history_imported],
        ["Наблюдения", sync.observations_imported],
        ["Вес", sync.measurements_imported]
      ]
        .map(([label, importedCount, linkedCount]) => {
          const total = Number(importedCount || 0) + Number(linkedCount || 0);
          return total ? `<span>${label}: ${total}</span>` : "";
        })
        .filter(Boolean)
        .join("")
    : "";
  return `
    <div class="profile-card">
      <h3>Связанные сервисы</h3>
      <p><span class="status-badge ${statusClass}">${statusLabel}</span></p>
      <p>${escapeHtml(detail)}</p>
      <details class="technical-details">
        <summary>Диагностика подключения</summary>
        <div class="meta-row">
          <span>Telegram: ${telegramConnected ? "подключён" : "не подключён"}</span>
          <span>MAX: ${maxConnected ? "подключён" : "не подключён"}</span>
          <span>Проверено: ${checkedAt}</span>
        </div>
        ${imported ? `<div class="meta-row">${imported}</div>` : ""}
        ${!syncOk && telegramConnected ? `<p>${escapeHtml(telegramSyncReasonText(sync.reason))}</p>` : ""}
      </details>
    </div>
  `;
}

function renderPushCard(push) {
  const supported = pushSupported();
  const enabled = Boolean(push?.config?.enabled);
  const count = Number(push?.status?.count || 0);
  let statusText = "Разрешите напоминания, чтобы не пропустить важную дату или проверку самочувствия.";
  let button = "";
  if (!supported) {
    statusText = "На этом устройстве напоминания недоступны. На iPhone откройте сайт в Safari и добавьте его на экран «Домой».";
  } else if (!enabled) {
    button = `<button class="secondary-button compact" type="button" disabled>Готовится</button>`;
  } else if (count > 0) {
    statusText = "Напоминания включены на этом устройстве.";
    button = `<button class="secondary-button compact" data-action="disable-push" type="button">Отключить на этом устройстве</button>`;
  } else {
    statusText = "Можно включить напоминания на этом устройстве.";
    button = `<button class="secondary-button compact" data-action="enable-push" type="button">Включить уведомления</button>`;
  }
  return `
    <div class="profile-card">
      <h3>Напоминания на этом устройстве</h3>
      <p>${escapeHtml(statusText)}</p>
      ${button ? `<div class="inline-actions">${button}</div>` : ""}
    </div>
  `;
}

async function renderAccountLinks() {
  await refreshAccountState();
  const push = await loadPushStatus();
  const email = state.user?.email || "";
  const telegramConnected = isProviderConnected("telegram");
  const maxConnected = isProviderConnected("max");
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Профиль и настройки</h2>
        <p>Вход, связанные сервисы, напоминания и ваши данные.</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="profile-card">
      <h3>Способы входа</h3>
      <p>${email ? `Электронная почта: ${escapeHtml(maskEmail(email))}` : "Электронная почта пока не подключена."}</p>
      <p>Подключите мессенджер, чтобы входить удобным способом и видеть один кабинет на всех устройствах.</p>
    </div>
    <div class="summary-grid">
        <div class="summary-card">
          <strong>Telegram</strong>
          <span>Статус: ${telegramConnected ? "подключён" : "не подключён"}</span>
          ${telegramConnected
            ? `<span class="status-badge connected">Подключён</span>`
            : `<button class="secondary-button compact" data-link-provider="telegram" type="button">Подключить Telegram</button>`}
        </div>
        <div class="summary-card">
          <strong>MAX</strong>
          <span>Статус: ${maxConnected ? "подключён" : "не подключён"}</span>
          ${maxConnected
            ? `<span class="status-badge connected">Подключён</span>`
            : `<button class="secondary-button compact" data-link-provider="max" type="button">Подключить MAX</button>`}
        </div>
    </div>
    ${renderSyncStatusCard()}
    ${renderPushCard(push)}
    <div class="profile-card">
      <h3>Вход и безопасность</h3>
      <p>Управляйте входами и копией данных кабинета.</p>
      <div class="inline-actions">
        <button class="secondary-button compact" data-action="logout" type="button">Выйти</button>
        <button class="secondary-button compact" data-action="export-account-data" type="button">Скачать мои данные</button>
        <button class="secondary-button compact" data-action="revoke-sessions" type="button">Выйти со всех устройств</button>
        <button class="secondary-button compact danger-text" data-action="show-data-deletion" type="button">Запросить удаление данных</button>
      </div>
      <div id="dataDeletionPanel"></div>
    </div>
    <p class="hint" id="accountLinkHint"></p>
  `);
}

async function enablePushNotifications() {
  setAccountLinkHint("Проверяю, поддерживает ли браузер уведомления...");
  if (!pushSupported()) throw new Error("push_unsupported");
  const config = await loadPushConfig(true);
  if (!config.enabled || !config.public_key) throw new Error("push_not_configured");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("push_permission_denied");
  const registration = await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.public_key)
    });
  }
  await api("/api/push/subscribe", {
    method: "POST",
    body: JSON.stringify(subscription.toJSON())
  });
  setAccountLinkHint("Уведомления подключены для этого устройства.");
  setTimeout(renderAccountLinks, 700);
}

async function disablePushNotifications() {
  setAccountLinkHint("Отключаю уведомления на этом устройстве...");
  if (!pushSupported()) throw new Error("push_unsupported");
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    setAccountLinkHint("В этом браузере активная подписка не найдена.");
    await renderAccountLinks();
    return;
  }
  await api("/api/push/unsubscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint: subscription.endpoint })
  });
  await subscription.unsubscribe().catch(() => false);
  setAccountLinkHint("Уведомления отключены для этого устройства.");
  setTimeout(renderAccountLinks, 700);
}

function setAccountLinkHint(content) {
  const hint = document.querySelector("#accountLinkHint");
  if (!hint) return;
  if (typeof content === "string") {
    hint.textContent = content;
    return;
  }
  hint.innerHTML = "";
  hint.append(content);
}

function renderAccountLinkWaiting(provider, url, loginState) {
  const wrap = document.createElement("span");
  const providerTitle = provider === "telegram" ? "Telegram" : "MAX";
  wrap.append(`${providerTitle} открыт только для подтверждения входа. После подтверждения вернитесь сюда — сайт привяжет способ входа автоматически.`);

  const actions = document.createElement("span");
  actions.className = "hint-actions";
  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `Открыть ${providerTitle}`;
    actions.append(link);
  }
  const checkButton = document.createElement("button");
  checkButton.type = "button";
  checkButton.textContent = "Проверить привязку";
  checkButton.addEventListener("click", () => pollAccountLink(provider, loginState));
  actions.append(checkButton);
  wrap.append(actions);
  setAccountLinkHint(wrap);
}

function openDeferredExternalWindow() {
  const externalWindow = window.open("about:blank", "_blank");
  if (externalWindow) {
    externalWindow.opener = null;
    externalWindow.document.title = "TemichevVet — подтверждение входа";
  }
  return externalWindow;
}

function closeDeferredExternalWindow(externalWindow) {
  if (!externalWindow || externalWindow.closed) return;
  externalWindow.close();
}

function navigateDeferredExternalWindow(externalWindow, url) {
  if (externalWindow && !externalWindow.closed) {
    externalWindow.location.href = url;
    return true;
  }
  return false;
}

async function startProviderLink(provider, externalWindow = openDeferredExternalWindow()) {
  setAccountLinkHint("Готовлю безопасную привязку...");
  try {
    const data = await api(`/api/account/${provider}/start`, { method: "POST", body: "{}" });
    if (!data.enabled || !data.url || !data.state) {
      closeDeferredExternalWindow(externalWindow);
      setAccountLinkHint(data.message || "Этот способ входа пока не настроен.");
      return;
    }
    renderAccountLinkWaiting(provider, data.url, data.state);
    navigateDeferredExternalWindow(externalWindow, data.url);
    pollAccountLink(provider, data.state);
  } catch (error) {
    closeDeferredExternalWindow(externalWindow);
    setAccountLinkHint(readableError(error.message));
  }
}

async function pollAccountLink(provider, loginState, attempt = 0) {
  if (attempt > 60) {
    setAccountLinkHint("Подтверждение не найдено. Попробуйте подключить способ входа ещё раз.");
    return;
  }
  try {
    const data = await api(`/api/auth/${provider}/status?state=${encodeURIComponent(loginState)}`, { method: "GET" });
    if (data.status === "complete") {
      state.token = "";
      localStorage.removeItem("tvv_token");
      await refreshAccountState();
      setAccountLinkHint("Способ входа подключён к этому кабинету.");
      setTimeout(renderAccountLinks, 700);
      return;
    }
    if (data.status === "expired") {
      setAccountLinkHint(data.message || "Код истёк. Попробуйте подключить способ входа ещё раз.");
      return;
    }
    setAccountLinkHint(data.message || "Ожидаем подтверждение...");
  } catch (error) {
    setAccountLinkHint(readableError(error.message));
  }
  setTimeout(() => pollAccountLink(provider, loginState, attempt + 1), 3000);
}

async function downloadAccountData() {
  setAccountLinkHint("Готовлю выгрузку данных...");
  const data = await api("/api/account/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const datePart = new Date().toISOString().slice(0, 10);
  link.href = url;
  link.download = `temichevvet-data-${datePart}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setAccountLinkHint("Выгрузка данных сформирована.");
}

async function revokeAllSessions() {
  if (!confirm("Завершить все активные входы в этот кабинет? После этого нужно будет войти заново.")) return;
  await api("/api/account/sessions/revoke-all", { method: "POST", body: "{}" });
  stopTelegramPolling();
  clearTelegramLogin();
  stopMaxPolling();
  clearMaxLogin();
  clearAccountState();
  setAuthMode(false);
  openAuthDialog();
  emailHint.textContent = "Все сессии завершены. Войдите заново удобным способом.";
}

function renderDataDeletionPanel() {
  const panel = document.querySelector("#dataDeletionPanel");
  if (!panel) return;
  panel.innerHTML = `
    <form class="form-grid deletion-form" id="dataDeletionForm">
      <div class="care-note">
        Удаление затрагивает сайт, PWA и связанные мессенджеры. Чтобы избежать случайного удаления питомцев, истории или подписки, команда сначала проверит запрос.
      </div>
      <label>
        <span>Для подтверждения введите УДАЛИТЬ</span>
        <input name="confirm" autocomplete="off" placeholder="УДАЛИТЬ" />
      </label>
      <label>
        <span>Комментарий, если нужен</span>
        <textarea name="comment" rows="3" placeholder="Например: удалить аккаунт и все связанные данные"></textarea>
      </label>
      <button class="secondary-button danger-text" type="submit">Отправить запрос на удаление</button>
    </form>
  `;
  document.querySelector("#dataDeletionForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await submitDataDeletionRequest(event.currentTarget);
    } catch (error) {
      setAccountLinkHint(readableError(error.message));
    }
  });
}

async function submitDataDeletionRequest(form) {
  const formData = new FormData(form);
  const confirmValue = String(formData.get("confirm") || "");
  const comment = String(formData.get("comment") || "");
  const data = await api("/api/account/deletion-request", {
    method: "POST",
    body: JSON.stringify({ confirm: confirmValue, comment })
  });
  setAccountLinkHint(data.message || "Запрос на удаление данных создан.");
  const panel = document.querySelector("#dataDeletionPanel");
  if (panel) panel.innerHTML = "";
}

async function renderPets() {
  await refreshPets();
  const cards = state.pets.length
    ? state.pets
        .map(
          (pet) => `
            <article class="item-card pet-card">
              <div class="pet-card-main">
                <div class="card-icon">${renderAppIcon("paw-print")}</div>
                <div>
                <h3>${escapeHtml(petTitle(pet))}</h3>
                <p>${pet.is_main ? "Основной питомец" : "История, вес и напоминания"}</p>
                ${renderPetBadges(pet)}
                </div>
              </div>
              <button class="secondary-button compact" data-open-pet="${pet.id}" type="button">Открыть карточку</button>
            </article>
          `
        )
        .join("")
    : renderEmptyBlock({
        icon: "paw-print",
        title: "Добавьте первого питомца",
        text: "Кличка, возраст, вес, история и важные даты будут храниться в одной карточке."
      });

  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Питомцы</h2>
        <p>Все важные данные — отдельно для каждой собаки или кошки.</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="list-stack">${cards}</div>
    <details class="form-disclosure" ${state.pets.length ? "" : "open"}>
      <summary>${renderAppIcon("plus")}<span>Добавить питомца</span></summary>
    <form class="form-grid" id="petCreateForm">
      <label><span>Тип</span><select name="pet_type"><option value="кошка">Кошка</option><option value="собака">Собака</option></select></label>
      <label><span>Кличка</span><input name="pet_name" required placeholder="Например: Лео" /></label>
      <label><span>Порода</span><input name="breed" placeholder="Если знаете: бенгальская, шпиц..." /></label>
      <label><span>Пол</span><select name="sex"><option value="">Не указан</option><option value="м">Самец</option><option value="ж">Самка</option></select></label>
      <label><span>Год рождения</span><input name="birth_year" inputmode="numeric" placeholder="Например: 2019" /></label>
      <label><span>Месяц</span><input name="birth_month" inputmode="numeric" placeholder="Если знаете: 6" /></label>
      <label><span>День</span><input name="birth_day" inputmode="numeric" placeholder="Если знаете: 15" /></label>
      <label><span>Вес, кг</span><input name="weight_kg" inputmode="decimal" placeholder="6.1" /></label>
      <label class="checkbox-row full-row"><input name="is_main" type="checkbox" /> <span>Сделать основным питомцем</span></label>
      <button class="primary-button" type="submit">Сохранить питомца</button>
    </form>
    </details>
  `);

  document.querySelector("#petCreateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    event.currentTarget.dataset.clientRequestId ||= createFlowId();
    const form = new FormData(event.currentTarget);
    const payload = petPayloadFromForm(form);
    payload.client_request_id = event.currentTarget.dataset.clientRequestId;
    try {
      const data = await api("/api/pets", { method: "POST", body: JSON.stringify(payload) });
      state.currentPetId = data.item.id;
      if (data.created) {
        trackMetrikaGoalOnce("pet.created", `pet:${data.item.id}`, {
          ...attributionEventMetadata(),
          pet_type: analyticsPetType(data.item.pet_type || payload.pet_type),
          has_pet: true
        });
      }
      await renderPetCard(data.item.id);
    } catch (error) {
      showError(`Не удалось сохранить питомца: ${readableError(error.message)}`);
    }
  });
}

function petPayloadFromForm(form) {
  const numberOrNull = (name) => {
    const value = String(form.get(name) || "").trim().replace(",", ".");
    return value ? Number(value) : null;
  };
  return {
    pet_type: String(form.get("pet_type") || "кошка"),
    pet_name: String(form.get("pet_name") || "").trim(),
    breed: String(form.get("breed") || "").trim() || null,
    sex: String(form.get("sex") || "").trim() || null,
    birth_year: numberOrNull("birth_year"),
    birth_month: numberOrNull("birth_month"),
    birth_day: numberOrNull("birth_day"),
    birth_precision: numberOrNull("birth_day") ? "day" : numberOrNull("birth_month") ? "month" : numberOrNull("birth_year") ? "year" : null,
    weight_kg: numberOrNull("weight_kg"),
    is_main: form.get("is_main") === "on"
  };
}

async function renderPetCard(petId) {
  state.currentPetId = petId;
  const data = await api(`/api/pets/${petId}`);
  const pet = data.item;
  const history = (data.history || [])
    .slice(0, 5)
    .map((item) => `<li><strong>${escapeHtml(historyTitle(item))}</strong><span>${formatDateTime(item.created_at)}</span></li>`)
    .join("");

  setWorkspace(`
    <div class="workspace-head">
      <div>
        <p class="section-label">Карточка питомца</p>
        <h2>${escapeHtml(petTitle(pet))}</h2>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="pets" type="button">${renderAppIcon("chevron-left")}<span>К списку</span></button>
    </div>
    <section class="profile-card pet-hero-card">
      <div class="card-title-row">
        <div class="card-icon large">${renderAppIcon("paw-print")}</div>
        <div><h3>${escapeHtml(pet.pet_name)}</h3><p>${pet.is_main ? "Основной питомец" : "Карточка здоровья"}</p></div>
      </div>
      <p>Здесь собраны данные, записи и важные события питомца.</p>
      ${renderPetBadges(pet)}
    </section>
    <div class="pet-action-grid">
      <button class="menu-card" data-pet-view="triage" data-pet-id="${pet.id}" type="button">${renderAppIcon("heart-pulse")}<span><strong>Что изменилось?</strong><small>Сохранить разбор в историю</small></span></button>
      <button class="menu-card" data-pet-view="history" data-pet-id="${pet.id}" type="button">${renderAppIcon("history")}<span><strong>История</strong><small>Ответы и события</small></span></button>
      <button class="menu-card" data-pet-view="observations" data-pet-id="${pet.id}" type="button">${renderAppIcon("clipboard-list")}<span><strong>Наблюдения</strong><small>Аппетит и поведение</small></span></button>
      <button class="menu-card" data-pet-view="weight" data-pet-id="${pet.id}" type="button">${renderAppIcon("scale")}<span><strong>Вес</strong><small>Динамика веса</small></span></button>
      <button class="menu-card" data-pet-view="reminders" data-pet-id="${pet.id}" type="button">${renderAppIcon("bell")}<span><strong>Напоминания</strong><small>Важные даты</small></span></button>
      <button class="menu-card" data-pet-view="summary" data-pet-id="${pet.id}" type="button">${renderAppIcon("book-open")}<span><strong>Сводка для врача</strong><small>История по выбранному периоду</small></span></button>
      <button class="menu-card" data-pet-view="edit" data-pet-id="${pet.id}" type="button">${renderAppIcon("settings")}<span><strong>Изменить карточку</strong><small>Основные данные</small></span></button>
    </div>
    <section>
      <h3>Последние события</h3>
      ${history ? `<ul class="event-list">${history}</ul>` : "<p>История пока пустая.</p>"}
    </section>
    <details class="danger-zone">
      <summary>Управление карточкой</summary>
      <div class="inline-actions">
        ${pet.is_main ? "" : `<button class="secondary-button compact" data-set-main="${pet.id}" type="button">Сделать основным</button>`}
        <button class="secondary-button compact danger-text icon-text-button" data-delete-pet="${pet.id}" data-delete-pet-title="${escapeHtml(petTitle(pet))}" data-delete-pet-linked="${pet.external_source ? "1" : "0"}" type="button">${renderAppIcon("trash-2")}<span>Удалить карточку</span></button>
      </div>
    </details>
  `);
}

function confirmPetDeletion(button) {
  const title = button.dataset.deletePetTitle || "карточка питомца";
  const isLinked = button.dataset.deletePetLinked === "1";
  const message = [
    `Удаление карточки: ${title}`,
    "",
    "Будут удалены данные питомца, связанные напоминания, наблюдения, вес и история в веб-кабинете.",
    isLinked ? "Связанная карточка также будет удалена из подключённого мессенджера." : "",
    "",
    "Если вы уверены, введите УДАЛИТЬ. Если передумали, нажмите «Отмена»."
  ].filter(Boolean).join("\n");
  const answer = window.prompt(message);
  if (answer === null) return false;
  const confirmed = String(answer).trim().toUpperCase() === "УДАЛИТЬ";
  if (!confirmed) window.alert("Удаление отменено: для подтверждения нужно ввести УДАЛИТЬ.");
  return confirmed;
}

async function renderPetEdit(petId) {
  const data = await api(`/api/pets/${petId}`);
  const pet = data.item;
  setWorkspace(`
    <div class="workspace-head">
      <h2>Изменить питомца</h2>
      <button class="secondary-button compact icon-text-button" data-open-pet="${pet.id}" type="button">${renderAppIcon("chevron-left")}<span>В карточку</span></button>
    </div>
    <form class="form-grid" id="petEditForm">
      <label><span>Тип</span><select name="pet_type"><option value="кошка" ${pet.pet_type === "кошка" ? "selected" : ""}>Кошка</option><option value="собака" ${pet.pet_type === "собака" ? "selected" : ""}>Собака</option></select></label>
      <label><span>Кличка</span><input name="pet_name" required value="${escapeHtml(pet.pet_name)}" /></label>
      <label><span>Порода</span><input name="breed" value="${escapeHtml(pet.breed || "")}" /></label>
      <label><span>Пол</span><select name="sex"><option value="">Не указан</option><option value="м" ${pet.sex === "м" ? "selected" : ""}>Самец</option><option value="ж" ${pet.sex === "ж" ? "selected" : ""}>Самка</option></select></label>
      <label><span>Год рождения</span><input name="birth_year" inputmode="numeric" value="${escapeHtml(pet.birth_year || "")}" /></label>
      <label><span>Месяц</span><input name="birth_month" inputmode="numeric" value="${escapeHtml(pet.birth_month || "")}" /></label>
      <label><span>День</span><input name="birth_day" inputmode="numeric" value="${escapeHtml(pet.birth_day || "")}" /></label>
      <label><span>Вес, кг</span><input name="weight_kg" inputmode="decimal" value="${escapeHtml(pet.weight_kg || "")}" /></label>
      <button class="primary-button" type="submit">Сохранить изменения</button>
    </form>
  `);
  document.querySelector("#petEditForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = petPayloadFromForm(new FormData(event.currentTarget));
    delete payload.is_main;
    try {
      await api(`/api/pets/${petId}`, { method: "PATCH", body: JSON.stringify(payload) });
      await renderPetCard(petId);
    } catch (error) {
      showError(`Не удалось обновить карточку: ${readableError(error.message)}`);
    }
  });
}

async function renderPetHistory(petId) {
  if (!state.pets.length) await refreshPets();
  const pet = state.pets.find((item) => Number(item.id) === Number(petId));
  const data = await api(`/api/pets/${petId}/history`);
  const items = data.items.length
    ? data.items.map((item) => renderHistoryCard(item)).join("")
    : renderEmptyBlock({
        icon: "history",
        title: "История пока пустая",
        text: "После первого разбора, наблюдения, веса или напоминания события появятся здесь.",
        action: "triage",
        actionText: "Рассказать, что случилось"
      });
  setWorkspace(`
    <div class="workspace-head">
      <div><h2>История здоровья</h2>${pet ? `<p>${escapeHtml(petTitle(pet))}</p>` : ""}</div>
      <button class="secondary-button compact icon-text-button" data-open-pet="${petId}" type="button">${renderAppIcon("chevron-left")}<span>В карточку</span></button>
    </div>
    <div class="list-stack">${items}</div>
  `);
}

const summaryPeriodLabels = { "30": "30 дней", "90": "90 дней", all: "Вся история" };

function renderDoctorSummarySection(title, content, className = "") {
  if (!content) return "";
  return `<section class="doctor-summary-section ${className}"><h3>${escapeHtml(title)}</h3>${content}</section>`;
}

async function renderPetSummary(petId, period = "30") {
  const data = await api(`/api/pets/${petId}/summary?period=${encodeURIComponent(period)}`);
  const pet = data.pet;
  const periodButtons = ["30", "90", "all"].map((value) => {
    const allowed = data.allowed_periods.includes(value);
    return `<button class="${value === data.period ? "primary-button" : "secondary-button"} compact" data-summary-period="${value}" data-pet-id="${petId}" type="button" ${allowed ? "" : "disabled title='Доступно в Plus'"}>${summaryPeriodLabels[value]}${allowed ? "" : " · Plus"}</button>`;
  }).join("");
  const weightRows = (data.weights || []).map((item) => `<tr><td>${formatDateTime(item.created_at)}</td><td>${escapeHtml(item.weight_kg)} кг</td><td>${escapeHtml(item.note || "—")}</td></tr>`).join("");
  const observationItems = (data.observations || []).map((item) => `<li><strong>${escapeHtml(observationTypeLabel(item.obs_type))}</strong><span>${escapeHtml(observationDisplayText(item))}</span><small>${formatDateTime(item.created_at)}</small></li>`).join("");
  const historyItems = (data.history || []).map((item) => `<li><strong>${escapeHtml(historyTitle(item))}</strong><span>${escapeHtml(compactText(humanizeUiText(item.details || ""), 240))}</span><small>${formatDateTime(item.created_at)}</small></li>`).join("");
  const reminderItems = (data.reminders || []).map((item) => `<li><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.due_date)}${item.due_time ? `, ${escapeHtml(item.due_time)}` : ""}</span><small>${escapeHtml(periodicityLabel(item.periodicity || "once"))}</small></li>`).join("");
  const weightChange = data.weight_change_kg === null || data.weight_change_kg === undefined
    ? ""
    : `<p class="summary-weight-change">Изменение к предыдущей записи: <strong>${data.weight_change_kg > 0 ? "+" : ""}${escapeHtml(data.weight_change_kg)} кг</strong></p>`;
  trackMetrikaGoalOnce("summary.viewed", `summary:${petId}:${period}:${new Date().toISOString().slice(0, 10)}`, {
    ...attributionEventMetadata(),
    has_pet: true
  });
  setWorkspace(`
    <div class="workspace-head no-print">
      <div><p class="section-label">Карточка питомца</p><h2>Сводка для врача</h2><p>${escapeHtml(petTitle(pet))}</p></div>
      <button class="secondary-button compact icon-text-button" data-open-pet="${petId}" type="button">${renderAppIcon("chevron-left")}<span>В карточку</span></button>
    </div>
    <div class="summary-periods no-print" aria-label="Период сводки">${periodButtons}</div>
    <article class="doctor-summary-print" id="doctorSummaryPrint">
      <header class="doctor-summary-header">
        <div><p class="section-label">TemichevVet</p><h2>Сводка по истории питомца</h2></div>
        <div><strong>${escapeHtml(pet.pet_name)}</strong><span>${escapeHtml(pet.pet_type)}${pet.breed ? ` · ${escapeHtml(pet.breed)}` : ""}</span></div>
      </header>
      <dl class="doctor-summary-meta">
        <div><dt>Период</dt><dd>${escapeHtml(summaryPeriodLabels[data.period])}</dd></div>
        <div><dt>Дата формирования</dt><dd>${formatDateTime(data.generated_at)}</dd></div>
        ${pet.weight_kg ? `<div><dt>Вес в карточке</dt><dd>${escapeHtml(pet.weight_kg)} кг</dd></div>` : ""}
      </dl>
      ${renderDoctorSummarySection("Динамика веса", weightRows ? `${weightChange}<div class="summary-table-wrap"><table><thead><tr><th>Дата</th><th>Вес</th><th>Заметка</th></tr></thead><tbody>${weightRows}</tbody></table></div>` : "")}
      ${renderDoctorSummarySection("Наблюдения владельца", observationItems ? `<ul class="doctor-summary-list">${observationItems}</ul>` : "")}
      ${renderDoctorSummarySection("Сохранённые события и разборы", historyItems ? `<ul class="doctor-summary-list timeline">${historyItems}</ul>` : "")}
      ${renderDoctorSummarySection("Важные даты и активные напоминания", reminderItems ? `<ul class="doctor-summary-list">${reminderItems}</ul>` : "")}
      ${!weightRows && !observationItems && !historyItems && !reminderItems ? `<div class="notice">За выбранный период записей пока нет.</div>` : ""}
      <footer class="doctor-summary-footer">Сводка составлена из данных владельца и сохранённых событий. Она не содержит нового диагноза и не заменяет осмотр ветеринарного врача.</footer>
    </article>
    <div class="summary-actions no-print">
      ${data.can_export ? `<button class="primary-button" data-print-summary data-pet-id="${petId}" data-summary-period="${data.period}" type="button">Печать или сохранить в PDF</button>` : `<div class="care-note"><strong>Экспорт доступен в Plus.</strong> Сводку за 30 дней можно просматривать бесплатно.</div><button class="secondary-button" data-action="subscription" type="button">Посмотреть Plus</button>`}
    </div>
  `);
}

async function renderPetObservations(petId) {
  if (!state.pets.length) await refreshPets();
  const pet = state.pets.find((item) => Number(item.id) === Number(petId));
  const data = await api(`/api/pets/${petId}/observations`);
  const items = data.items.length
    ? data.items.map((item) => {
        const text = observationDisplayText(item);
        return `<article class="item-card"><div><h3>${escapeHtml(observationTypeLabel(item.obs_type))}</h3>${text ? `<p>${escapeHtml(text)}</p>` : ""}<small>${formatDateTime(item.created_at)}</small></div></article>`;
      }).join("")
    : renderEmptyBlock({
        icon: "clipboard-list",
        title: "Наблюдений пока нет",
        text: "Добавляйте короткие заметки о состоянии, аппетите, активности, стуле или симптомах.",
      });
  setWorkspace(`
    <div class="workspace-head">
      <div><h2>Наблюдения</h2>${pet ? `<p>${escapeHtml(petTitle(pet))}</p>` : ""}</div>
      <button class="secondary-button compact icon-text-button" data-open-pet="${petId}" type="button">${renderAppIcon("chevron-left")}<span>В карточку</span></button>
    </div>
    <div class="care-note">Коротко отмечайте изменения аппетита, активности, туалета или поведения.</div>
    <form class="inline-form" id="observationForm">
      <label><span>Что заметили?</span><input name="text" placeholder="Например: аппетит нормальный, активность ниже обычного" required /></label>
      <button class="primary-button compact" type="submit">Добавить наблюдение</button>
    </form>
    <div class="list-stack">${items}</div>
  `);
  document.querySelector("#observationForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("text") || "");
    try {
      const created = await api(`/api/pets/${petId}/observations`, { method: "POST", body: JSON.stringify({ obs_type: "note", text }) });
      trackServiceGoals(created, `observation:${created.item?.id || petId}`);
      await renderPetObservations(petId);
    } catch (error) {
      showError(`Не удалось добавить наблюдение: ${readableError(error.message)}`);
    }
  });
}

async function renderPetWeights(petId) {
  if (!state.pets.length) await refreshPets();
  const pet = state.pets.find((item) => Number(item.id) === Number(petId));
  const data = await api(`/api/pets/${petId}/weights`);
  const items = data.items.length
    ? data.items.map((item) => `<article class="item-card"><div><h3>${escapeHtml(item.weight_kg)} кг</h3><p>${escapeHtml(item.note || "")}</p><small>${formatDateTime(item.created_at)}</small></div></article>`).join("")
    : renderEmptyBlock({
        icon: "scale",
        title: "Истории веса пока нет",
        text: "Сохраняйте вес периодически, чтобы видеть динамику и быстрее замечать изменения.",
      });
  setWorkspace(`
    <div class="workspace-head">
      <div><h2>Вес</h2>${pet ? `<p>${escapeHtml(petTitle(pet))}</p>` : ""}</div>
      <button class="secondary-button compact icon-text-button" data-open-pet="${petId}" type="button">${renderAppIcon("chevron-left")}<span>В карточку</span></button>
    </div>
    <form class="inline-form" id="weightForm">
      <label><span>Вес, кг</span><input name="weight_kg" inputmode="decimal" placeholder="6,1" required /></label>
      <label><span>Заметка</span><input name="note" placeholder="Например: после смены корма" /></label>
      <button class="primary-button compact" type="submit">Сохранить</button>
    </form>
    <div class="list-stack">${items}</div>
  `);
  document.querySelector("#weightForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const created = await api(`/api/pets/${petId}/weights`, {
        method: "POST",
        body: JSON.stringify({
          weight_kg: Number(String(form.get("weight_kg") || "").replace(",", ".")),
          note: String(form.get("note") || "")
        })
      });
      trackServiceGoals(created, `weight:${created.item?.id || petId}`);
      await renderPetWeights(petId);
    } catch (error) {
      showError(`Не удалось сохранить вес: ${readableError(error.message)}`);
    }
  });
}

async function renderReminders(petId = null) {
  await refreshPets();
  const data = petId ? await api(`/api/pets/${petId}`) : await api("/api/reminders");
  const reminders = petId ? data.reminders || [] : data.items || [];
  const title = petId ? `Напоминания питомца` : "Напоминания";
  const petContext = petId ? data.item || state.pets.find((pet) => Number(pet.id) === Number(petId)) : null;
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  const selectedPetId = petId || mainPet?.id || "";
  const items = reminders.length
    ? reminders
        .map(
          (item) => `
            <article class="item-card">
              <div>
                <h3>${escapeHtml(item.title)}</h3>
                <p>${escapeHtml(item.due_date)} ${escapeHtml(item.due_time || "")}${item.pet_name ? ` · ${escapeHtml(item.pet_name)}` : ""}</p>
                <small>${escapeHtml(periodicityLabel(item.periodicity || "once"))}</small>
              </div>
              <button class="secondary-button compact danger-text" data-delete-reminder="${item.id}" data-return-pet="${petId || ""}" type="button">Отключить</button>
            </article>
          `
        )
        .join("")
    : renderEmptyBlock({
        icon: "bell",
        title: "Напоминаний пока нет",
        text: "Создайте напоминание о вакцинации, обработке от паразитов, осмотре, груминге или своей задаче.",
      });

  setWorkspace(`
    <div class="workspace-head">
      <div><h2>${title}</h2>${petContext ? `<p>${escapeHtml(petTitle(petContext))}</p>` : ""}</div>
      <button class="secondary-button compact icon-text-button" ${petId ? `data-open-pet="${petId}"` : `data-action="home"`} type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="list-stack">${items}</div>
    <details class="form-disclosure" ${reminders.length ? "" : "open"}>
      <summary>${renderAppIcon("plus")}<span>Добавить напоминание</span></summary>
    <form class="form-grid" id="reminderForm">
      <label><span>Питомец</span><select name="pet_id">${petOptions(selectedPetId)}</select></label>
      <label><span>Шаблон</span><select name="reminder_type">${reminderTypes.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label><span>Заголовок</span><input name="title" required value="Вакцинация" placeholder="Вакцинация" /></label>
      <label><span>Дата</span><input name="due_date" type="date" required /></label>
      <label><span>Время</span><input name="due_time" type="time" /></label>
      <label><span>Повтор</span><select name="periodicity">${periodicityOptions.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label class="full-row"><span>Заметка</span><input name="notes" placeholder="Например: купить препарат заранее" /></label>
      <button class="primary-button" type="submit">Сохранить напоминание</button>
    </form>
    </details>
  `);

  const reminderForm = document.querySelector("#reminderForm");
  const reminderTypeSelect = reminderForm.querySelector("[name='reminder_type']");
  const reminderTitleInput = reminderForm.querySelector("[name='title']");
  reminderTypeSelect.addEventListener("change", () => {
    const suggested = reminderDefaultTitles[reminderTypeSelect.value] || "Напоминание";
    if (!reminderTitleInput.value || Object.values(reminderDefaultTitles).includes(reminderTitleInput.value)) {
      reminderTitleInput.value = suggested;
    }
  });

  reminderForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const selectedPetId = String(form.get("pet_id") || "");
    try {
      const created = await api("/api/reminders", {
        method: "POST",
        body: JSON.stringify({
          pet_id: selectedPetId ? Number(selectedPetId) : null,
          reminder_type: String(form.get("reminder_type") || "custom"),
          title: String(form.get("title") || ""),
          due_date: String(form.get("due_date") || ""),
          due_time: String(form.get("due_time") || "") || null,
          periodicity: String(form.get("periodicity") || "once"),
          notes: String(form.get("notes") || "") || null
        })
      });
      trackServiceGoals(created, `reminder:${created.item?.id || selectedPetId}`);
      await renderReminders(petId);
    } catch (error) {
      showError(`Не удалось сохранить напоминание: ${readableError(error.message)}`);
    }
  });
}

async function renderTriage(prefillPetId = null) {
  await refreshPets();
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  const selectedPetId = prefillPetId || state.currentPetId || mainPet?.id || "";
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Что изменилось у питомца?</h2>
        <p>Расскажите, что заметили. Ответ можно сохранить в общей истории питомца.</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="check-urgent-warning">
      TemichevVet не ставит диагноз и не назначает лечение. Если есть тяжёлое дыхание, судороги,
      потеря сознания, кровь, признаки отравления или резкое ухудшение — сразу обращайтесь в клинику.
    </div>
    <form class="form-grid one-column premium-form" id="triageForm">
      <label><span>О ком речь?</span><select name="pet_id"><option value="">Без привязки к карточке</option>${petOptions(selectedPetId)}</select></label>
      <label><span>Что происходит?</span><textarea name="text" placeholder="Например: кошка второй день не ест, прячется и почти не пьёт" required></textarea></label>
      <button class="primary-button" type="submit">Получить и сохранить разбор</button>
    </form>
    <div id="triageResult"></div>
  `);
  document.querySelector("#triageForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const petId = String(form.get("pet_id") || "");
    trackFunnel("triage.submit_click", { has_pet: Boolean(petId) });
    const resultEl = document.querySelector("#triageResult");
    resultEl.innerHTML = `<div class="notice check-loading" role="status" aria-live="polite"><strong>Готовим ответ…</strong><span>Обычно это занимает несколько секунд.</span></div>`;
    try {
      const data = await api("/api/triage", {
        method: "POST",
        body: JSON.stringify({
          pet_id: petId ? Number(petId) : null,
          text: String(form.get("text") || "")
        })
      });
      state.subscription = data.subscription || state.subscription;
      trackServiceGoals(data, `health-check:${data.triage_id || petId || "unlinked"}`);
      resultEl.innerHTML = `
        <div class="result-box ${data.urgency === "red" ? "danger" : ""}" data-triage-answer="${escapeHtml(data.answer)}">
          ${formatTriageAnswer(data.answer)}
          <div class="inline-actions triage-result-actions">
            <button class="secondary-button compact" data-copy-triage-result type="button">Скопировать для врача</button>
          </div>
        </div>
        <div class="care-note">
          Сохраните важные детали для ветеринарного врача.
          ${data.followup ? "Позже напомним проверить самочувствие ещё раз." : ""}
        </div>
        <div class="next-actions">
          ${petId ? `<button class="secondary-button icon-text-button" data-open-pet="${petId}" type="button">${renderAppIcon("paw-print")}<span>Открыть карточку</span></button>` : ""}
          ${petId ? `<button class="secondary-button icon-text-button" data-pet-view="reminders" data-pet-id="${petId}" type="button">${renderAppIcon("bell")}<span>Добавить напоминание</span></button>` : `<button class="secondary-button icon-text-button" data-action="reminders" type="button">${renderAppIcon("bell")}<span>Добавить напоминание</span></button>`}
          ${petId ? `<button class="secondary-button icon-text-button" data-pet-view="history" data-pet-id="${petId}" type="button">${renderAppIcon("history")}<span>История питомца</span></button>` : ""}
          <button class="primary-button" data-action="triage" type="button">Рассказать ещё раз</button>
        </div>
      `;
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger"><strong>Не получилось загрузить ответ</strong><p>${escapeHtml(readableError(error.message))}</p></div>`;
    }
  });
}

async function renderFood() {
  if (!state.pets.length) await refreshPets();
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  const defaultSpecies = mainPet?.pet_type === "собака" ? "dog" : "cat";
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Питание</h2>
        <p>Узнайте, можно ли давать питомцу продукт или готовое блюдо.</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="more" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <form class="form-grid one-column" id="foodForm">
      <label><span>Сохранить для питомца</span><select name="pet_id"><option value="">Выбрать после ответа</option>${petOptions(mainPet?.id || "")}</select></label>
      <label><span>Для кого?</span><select name="species" required><option value="dog" ${defaultSpecies === "dog" ? "selected" : ""}>Собака</option><option value="cat" ${defaultSpecies === "cat" ? "selected" : ""}>Кошка</option></select></label>
      <label><span>Продукт или блюдо</span><input name="query" placeholder="борщ, котлета, виноград, куриная грудка" required /></label>
      <label><span>Состав блюда, если известен</span><input name="ingredients" placeholder="мясо, рис, лук, соль" /></label>
      <div class="care-note">Это общая справочная база для кошек и собак, а не видоспецифичный анализ корма или этикетки. Для готового блюда перечислите известный состав через запятую.</div>
      <button class="primary-button" type="submit">Проверить продукт</button>
    </form>
    <div id="foodResult"></div>
  `);
  document.querySelector("#foodForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const species = String(form.get("species") || "");
    const query = String(form.get("query") || "");
    const ingredients = String(form.get("ingredients") || "");
    const selectedPetId = Number(form.get("pet_id") || 0);
    const resultEl = document.querySelector("#foodResult");
    resultEl.innerHTML = `<p class="hint">Проверяю...</p>`;
    try {
      const data = await api("/api/food/check", {
        method: "POST",
        body: JSON.stringify({
          species,
          query,
          ingredients
        })
      });
      if (data.species !== species) throw new Error("food_species_mismatch");
      storePendingPublicFoodSave({
        save_kind: "food",
        pet_type: species,
        species,
        query,
        ingredients,
        pet_id: selectedPetId || undefined,
        landing_slug: "cabinet-food",
        session_id: getFunnelSessionId(),
        ...attributionEventMetadata(),
        created_at: new Date().toISOString()
      });
      resultEl.innerHTML = `
        <div class="result-box ${data.item && !data.item.allowed ? "danger" : ""}">
          <pre>${escapeHtml(data.message)}</pre>
        </div>
        <div class="next-actions">
          <button class="primary-button" data-auth-food-save type="button">Сохранить в карточку</button>
          <button class="secondary-button" data-action="food" type="button">Проверить ещё продукт</button>
          <button class="secondary-button icon-text-button" data-action="faq" type="button">${renderAppIcon("book-open")}<span>Вопросы и ответы</span></button>
          <button class="secondary-button" data-action="more" type="button">Все разделы</button>
        </div>
      `;
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger"><strong>Не получилось проверить продукт</strong><p>${escapeHtml(readableError(error.message))}</p></div>`;
    }
  });
}

const knowledgeSections = {
  care: {
    title: "Уход и привычки",
    icon: "heart-pulse",
    endpoint: "/api/care",
    intro: "Карточки по уходу, поведению, шерсти, когтям, ушам, зубам, прогулкам и домашней безопасности.",
    label: "Тема ухода",
    placeholder: "когти у кошки, уход за щенком, переезд с питомцем",
    empty: "Карточки по уходу не найдены. Попробуйте другую формулировку."
  },
  faq: {
    title: "Вопросы и ответы",
    icon: "book-open",
    endpoint: "/api/faq",
    intro: "Справочник по частым вопросам: профилактика, тревожные признаки, подготовка к врачу, уход и бытовые ситуации.",
    label: "Что хотите узнать?",
    placeholder: "вакцинация котёнка, обработка от клещей, как подготовиться к врачу",
    empty: "Подходящие ответы не найдены. Попробуйте другую формулировку."
  }
};

function speciesText(values) {
  const list = Array.isArray(values) ? values : [];
  const labels = list
    .map((value) => {
      if (value === "cat") return "кошки";
      if (value === "dog") return "собаки";
      return value;
    })
    .filter(Boolean);
  return labels.length ? labels.join(", ") : "кошки и собаки";
}

function renderKnowledgeMeta(item) {
  const parts = [];
  if (item.category) parts.push(item.category);
  parts.push(speciesText(item.species));
  return `<div class="meta-row">${parts.map((part) => `<span>${escapeHtml(part)}</span>`).join("")}</div>`;
}

function renderFaqItem(item) {
  return `
    <article class="item-card knowledge-card">
      <div>
        <h3>${escapeHtml(item.question || "Вопрос")}</h3>
        ${renderKnowledgeMeta(item)}
        <p>${escapeHtml(item.short_answer || "Краткий ответ пока не заполнен.")}</p>
        ${item.detailed_answer ? `
          <details>
            <summary>Подробный ответ</summary>
            <p>${nl2br(item.detailed_answer)}</p>
          </details>
        ` : ""}
      </div>
    </article>
  `;
}

function renderCareItem(item) {
  const steps = Array.isArray(item.steps) ? item.steps.filter(Boolean) : [];
  return `
    <article class="item-card knowledge-card">
      <div>
        <h3>${escapeHtml(item.title || "Карточка ухода")}</h3>
        ${renderKnowledgeMeta(item)}
        <p>${escapeHtml(item.summary || "Краткое описание пока не заполнено.")}</p>
        ${item.details ? `
          <details>
            <summary>Подробная инструкция</summary>
            <p>${nl2br(item.details)}</p>
            ${steps.length ? `<ol>${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>` : ""}
          </details>
        ` : ""}
        ${item.warning ? `<div class="notice danger compact-note">${escapeHtml(item.warning)}</div>` : ""}
      </div>
    </article>
  `;
}

function renderKnowledgeItems(kind, items, query) {
  const config = knowledgeSections[kind];
  if (!items.length) {
    return `<div class="notice">${escapeHtml(config.empty)}</div>`;
  }
  const title = query ? "Найдено" : kind === "care" ? "Популярные карточки" : "Популярные вопросы";
  const cards = items.map((item) => (kind === "care" ? renderCareItem(item) : renderFaqItem(item))).join("");
  return `
    <div class="knowledge-results">
      <h3>${title}</h3>
      <div class="list-stack">${cards}</div>
    </div>
  `;
}

async function renderKnowledgeSection(kind) {
  const config = knowledgeSections[kind];
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2 class="icon-heading">${renderAppIcon(config.icon)}<span>${config.title}</span></h2>
        <p>${escapeHtml(config.intro)}</p>
      </div>
      <button class="secondary-button compact icon-text-button" data-action="more" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <form class="form-grid one-column" id="knowledgeSearchForm">
      <label>
        <span>${escapeHtml(config.label)}</span>
        <input name="query" placeholder="${escapeHtml(config.placeholder)}" />
      </label>
      <button class="primary-button" type="submit">Найти</button>
    </form>
    <div class="care-note">
      Это справочный раздел. Он не расходует разборы по здоровью и не заменяет очный осмотр ветеринарного врача.
    </div>
    <div id="knowledgeResult"></div>
  `);

  const form = document.querySelector("#knowledgeSearchForm");
  const resultEl = document.querySelector("#knowledgeResult");

  async function loadItems(query = "") {
    resultEl.innerHTML = `<p class="hint">Загружаю...</p>`;
    try {
      const params = new URLSearchParams({ q: query, limit: "8" });
      const data = await api(`${config.endpoint}?${params.toString()}`);
      resultEl.innerHTML = renderKnowledgeItems(kind, data.items || [], query);
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger"><strong>Не получилось загрузить материалы</strong><p>${escapeHtml(readableError(error.message))}</p></div>`;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    await loadItems(String(formData.get("query") || "").trim());
  });

  await loadItems("");
}

function paymentStatusNotice(message, type = "") {
  const noticeType = new Set(["danger", "success", "warning"]).has(type) ? type : "";
  const className = noticeType ? `notice ${noticeType}` : "notice";
  return `<div class="${className}">${escapeHtml(message)}</div>`;
}

async function startPlusPayment() {
  trackFunnel("payment.plus_click");
  const resultEl = document.querySelector("#paymentResult");
  if (resultEl) resultEl.innerHTML = paymentStatusNotice("Создаю защищённую ссылку оплаты...");
  try {
    const data = await api("/api/payments/plus/create", { method: "POST" });
    state.subscription = data.subscription || state.subscription;
    if (data.status === "already_active") {
      renderSubscription(paymentStatusNotice(data.message || "Plus уже активен."));
      return;
    }
    if (!data.confirmation_url || !data.payment_id) {
      throw new Error("payment_confirmation_missing");
    }
    state.lastPlusPaymentId = data.payment_id;
    localStorage.setItem("tvv_last_plus_payment_id", data.payment_id);
    window.location.href = data.confirmation_url;
  } catch (error) {
    if (resultEl) resultEl.innerHTML = paymentStatusNotice(`Не удалось открыть оплату. ${readableError(error.message)}`, "danger");
  }
}

async function checkPlusPaymentStatus(options = {}) {
  const resultEl = document.querySelector("#paymentResult");
  if (resultEl) resultEl.innerHTML = paymentStatusNotice("Проверяю оплату...");
  try {
    const paymentId = state.lastPlusPaymentId || localStorage.getItem("tvv_last_plus_payment_id") || "";
    const path = paymentId
      ? `/api/payments/${encodeURIComponent(paymentId)}/status`
      : "/api/payments/plus/status";
    const data = await api(path);
    state.subscription = data.subscription || state.subscription;
    if (data.status === "succeeded") {
      trackMetrikaGoalOnce("payment.succeeded", `payment:${paymentId || data.payment_id || "latest"}`, {
        ...attributionEventMetadata(),
        provider: "yookassa"
      });
      state.lastPlusPaymentId = "";
      localStorage.removeItem("tvv_last_plus_payment_id");
    }
    if (options.replaceHistory) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    const type = data.status === "canceled" || data.status === "invalid" || data.status === "not_found" ? "danger" : "";
    renderSubscription(paymentStatusNotice(data.message || "Статус платежа обновлён.", type));
  } catch (error) {
    if (options.replaceHistory) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    const message = paymentStatusNotice(`Не удалось проверить оплату. ${readableError(error.message)}`, "danger");
    if (resultEl) resultEl.innerHTML = message;
    else renderSubscription(message);
  }
}

function renderSubscription(statusHtml = "") {
  const sub = state.subscription || {};
  const plan = sub.title || sub.plan || "Free";
  const quotaTotal = Number.isFinite(Number(sub.quota_total)) ? Number(sub.quota_total) : 0;
  const quotaUsed = Number.isFinite(Number(sub.quota_used)) ? Number(sub.quota_used) : 0;
  const quotaLeft = Number.isFinite(Number(sub.quota_left)) ? Number(sub.quota_left) : Math.max(0, quotaTotal - quotaUsed);
  const periodEnd = sub.period_end ? formatDateTime(sub.period_end) : "—";
  const canPay = !sub.plan || sub.plan === "free";
  const telegramConnected = isProviderConnected("telegram");
  setWorkspace(`
    <div class="workspace-head">
      <div><h2>Подписка</h2><p>Текущий тариф и доступные возможности.</p></div>
      <button class="secondary-button compact icon-text-button" data-action="more" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <section class="profile-card subscription-current-card">
      <div class="card-title-row">
        <div class="card-icon large">${renderAppIcon("credit-card")}</div>
        <div><p class="section-label">Ваш тариф</p><h3>${escapeHtml(plan)}</h3></div>
      </div>
      <div class="subscription-usage">
        <strong>${quotaLeft}</strong>
        <span>из ${quotaTotal} разборов доступно</span>
      </div>
      ${sub.plan && sub.plan !== "free" ? `<p><strong>Действует до:</strong> ${escapeHtml(periodEnd)}.</p>` : ""}
      ${telegramConnected || sub.source === "telegram" ? `<p class="hint">Сайт и Telegram используют один аккаунт и одну подписку.</p>` : ""}
      ${canPay ? `
        <button class="primary-button icon-text-button" data-action="pay-plus" type="button">${renderAppIcon("credit-card")}<span>Подключить Plus — 200 ₽</span></button>
      ` : `
        <div class="notice success">Plus активен.</div>
      `}
      <div id="paymentResult">${statusHtml}</div>
    </section>
    <section class="profile-card subscription-benefits-card">
      <h3>Что входит в Plus</h3>
      <ul class="benefit-list">
        <li>до 10 разборов по здоровью в месяц;</li>
        <li>до 3 питомцев в кабинете;</li>
        <li>расширенная история и до 20 активных напоминаний;</li>
        <li>сводка за 30/90 дней или всё время;</li>
        <li>печать и сохранение сводки в PDF.</li>
      </ul>
      <p class="legal-price-note">200 ₽ за 30 дней. Оплата разовая, автосписаний нет.</p>
      <p class="hint">После окончания Plus данные не удаляются. Питомцы и записи сверх Free остаются доступны для чтения.</p>
      ${canPay ? `<button class="text-button" data-action="check-plus-payment" type="button">Проверить статус оплаты</button>` : ""}
    </section>
  `);
}

function renderFeedback() {
  setWorkspace(`
    <div class="workspace-head">
      <h2>Обратная связь</h2>
      <button class="secondary-button compact icon-text-button" data-action="more" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
    </div>
    <div class="notice">
      Это связь с командой проекта TemichevVet, а не с ветеринарным врачом. Не отправляйте сюда симптомы, жалобы и срочные медицинские ситуации.
    </div>
    <form class="form-grid one-column" id="feedbackForm">
      <label><span>Категория</span><select name="category">
        <option value="Ошибка">Ошибка в сервисе</option>
        <option value="Оплата">Оплата или подписка</option>
        <option value="Вход">Вход или привязка мессенджера</option>
        <option value="Идея">Идея по улучшению</option>
        <option value="Другое">Другое</option>
      </select></label>
      <label><span>Сообщение команде</span><textarea name="text" required placeholder="Опишите вопрос по работе сервиса"></textarea></label>
      <button class="primary-button" type="submit">Отправить</button>
    </form>
    <p class="hint" id="feedbackResult"></p>
  `);
  document.querySelector("#feedbackForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const resultEl = document.querySelector("#feedbackResult");
    resultEl.textContent = "Отправляю...";
    try {
      const data = await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          category: String(form.get("category") || ""),
          text: String(form.get("text") || "")
        })
      });
      resultEl.textContent = data.message;
      event.currentTarget.reset();
    } catch (error) {
      resultEl.textContent = `Не удалось отправить сообщение: ${readableError(error.message)}`;
    }
  });
}

async function renderGlobalHistory() {
  await refreshPets();
  if (!state.pets.length) {
    setWorkspace(`
      <div class="workspace-head">
        <h2>История здоровья</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
      </div>
      ${renderEmptyBlock({
        icon: "history",
        title: "Сначала добавьте питомца",
        text: "История хранится по карточкам питомцев, чтобы не смешивать разные обращения.",
        action: "pets",
        actionText: "Добавить питомца"
      })}
    `);
    return;
  }
  const selectedPet = state.pets.find((pet) => Number(pet.id) === Number(state.currentPetId))
    || state.pets.find((pet) => pet.is_main)
    || state.pets[0];
  await renderPetHistory(selectedPet.id);
}

async function renderGlobalObservations() {
  await refreshPets();
  if (!state.pets.length) {
    setWorkspace(`
      <div class="workspace-head">
        <h2>Наблюдения</h2>
        <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>Назад</span></button>
      </div>
      ${renderEmptyBlock({
        icon: "clipboard-list",
        title: "Сначала добавьте питомца",
        text: "Наблюдения лучше вести по конкретной карточке: так видна динамика состояния.",
        action: "pets",
        actionText: "Добавить питомца"
      })}
    `);
    return;
  }
  const selectedPet = state.pets.find((pet) => Number(pet.id) === Number(state.currentPetId))
    || state.pets.find((pet) => pet.is_main)
    || state.pets[0];
  await renderPetObservations(selectedPet.id);
}

async function verifyEmailCode() {
  emailHint.textContent = "Проверяю код...";
  try {
    await api("/api/auth/email/verify", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value, code: codeInput.value })
    });
    state.token = "";
    localStorage.removeItem("tvv_token");
    await refreshAccountState();
    setAuthMode(true);
    trackAuthLoginSuccess("email");
    emailHint.textContent = "";
    if (await completePendingSaveAfterLogin()) return;
    await renderStartupView();
  } catch (error) {
    emailHint.textContent = readableError(error.message);
  }
}

emailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!privacyConsent?.checked) {
    emailHint.textContent = "Перед входом нужно принять соглашение и согласие на обработку персональных данных.";
    privacyConsent?.focus();
    return;
  }
  if (!codeRow.hidden && codeInput.value.trim()) {
    await verifyEmailCode();
    return;
  }
  emailHint.textContent = "Отправляю код...";
  trackFunnel("auth.email_start_click");
  try {
    const data = await api("/api/auth/email/start", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value })
    });
    codeRow.hidden = false;
    emailHint.textContent = data.debug_code ? `Тестовый код: ${data.debug_code}` : data.message;
  } catch (error) {
    emailHint.textContent = readableError(error.message);
  }
});

async function startMessenger(provider, externalWindow = openDeferredExternalWindow()) {
  messengerHint.textContent = "Готовлю вход...";
  try {
    const data = await api(`/api/auth/${provider}/start`, { method: "POST", body: "{}" });
    messengerHint.textContent = data.message;
    if (data.enabled && data.url) {
      if (provider === "telegram" && data.state) {
        saveTelegramLogin(data.state, data.url);
        renderTelegramWaiting(data.url, data.state);
        navigateDeferredExternalWindow(externalWindow, data.url);
        pollTelegramLogin(data.state);
        return;
      }
      if (provider === "max" && data.state) {
        saveMaxLogin(data.state, data.url);
        renderMaxWaiting(data.url, data.state);
        navigateDeferredExternalWindow(externalWindow, data.url);
        pollMaxLogin(data.state);
        return;
      }
      if (!navigateDeferredExternalWindow(externalWindow, data.url)) window.location.href = data.url;
      return;
    }
    closeDeferredExternalWindow(externalWindow);
  } catch (error) {
    closeDeferredExternalWindow(externalWindow);
    messengerHint.textContent = readableError(error.message);
  }
}

function getMaxMiniAppInitData() {
  const webApp = window.WebApp;
  return typeof webApp?.initData === "string" ? webApp.initData.trim() : "";
}

async function tryMaxMiniAppLogin() {
  if (maxMiniAppAuthTried || state.token) return false;
  const initData = getMaxMiniAppInitData();
  if (!initData) return false;
  maxMiniAppAuthTried = true;
  try {
    const data = await api("/api/auth/max/init", {
      method: "POST",
      body: JSON.stringify({ init_data: initData })
    });
    if (data.status === "complete") {
      state.token = "";
      localStorage.removeItem("tvv_token");
      clearMaxLogin();
      await refreshAccountState();
      setAuthMode(true);
      trackAuthLoginSuccess("max");
      if (await completePendingSaveAfterLogin()) return true;
      await renderStartupView();
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

function saveTelegramLogin(loginState, url) {
  state.telegramLoginState = loginState;
  state.telegramLoginUrl = url;
}

function clearTelegramLogin() {
  state.telegramLoginState = "";
  state.telegramLoginUrl = "";
  localStorage.removeItem("tvv_telegram_login_state");
  localStorage.removeItem("tvv_telegram_login_url");
}

function renderTelegramWaiting(url, loginState) {
  messengerHint.innerHTML = "";
  const text = document.createElement("span");
  text.textContent = "Откройте Telegram только для подтверждения входа. После подтверждения вернитесь сюда — сайт завершит вход автоматически.";
  messengerHint.append(text);

  const actions = document.createElement("span");
  actions.className = "hint-actions";

  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Открыть Telegram";
    actions.append(link);
  }

  const checkButton = document.createElement("button");
  checkButton.type = "button";
  checkButton.textContent = "Проверить вход";
  checkButton.addEventListener("click", () => pollTelegramLogin(loginState));
  actions.append(checkButton);
  messengerHint.append(actions);
}

function stopTelegramPolling() {
  if (state.telegramPollTimer) {
    clearTimeout(state.telegramPollTimer);
    state.telegramPollTimer = null;
  }
}

async function pollTelegramLogin(loginState, attempt = 0) {
  stopTelegramPolling();
  if (attempt > 60) {
    messengerHint.textContent = "Telegram-вход не подтвержден. Попробуйте нажать кнопку ещё раз.";
    clearTelegramLogin();
    return;
  }
  try {
    const data = await api(`/api/auth/telegram/status?state=${encodeURIComponent(loginState)}`, { method: "GET" });
    if (data.status === "complete") {
      state.token = "";
      await refreshAccountState();
      localStorage.removeItem("tvv_token");
      clearTelegramLogin();
      messengerHint.textContent = "Telegram-вход подтвержден.";
      setAuthMode(true);
      stopTelegramPolling();
      trackAuthLoginSuccess("telegram");
      if (await completePendingSaveAfterLogin()) return;
      await renderStartupView();
      return;
    }
    if (data.status === "expired") {
      clearTelegramLogin();
      messengerHint.textContent = data.message || "Код входа истек. Нажмите Telegram ещё раз.";
      return;
    }
    renderTelegramWaiting(state.telegramLoginUrl, loginState);
    messengerHint.firstChild.textContent = data.message || "Ожидаем подтверждение в Telegram...";
  } catch (error) {
    renderTelegramWaiting(state.telegramLoginUrl, loginState);
    messengerHint.firstChild.textContent = `Не удалось проверить вход: ${readableError(error.message)}`;
  }
  state.telegramPollTimer = setTimeout(() => pollTelegramLogin(loginState, attempt + 1), 3000);
}

function saveMaxLogin(loginState, url) {
  state.maxLoginState = loginState;
  state.maxLoginUrl = url;
}

function clearMaxLogin() {
  state.maxLoginState = "";
  state.maxLoginUrl = "";
  localStorage.removeItem("tvv_max_login_state");
  localStorage.removeItem("tvv_max_login_url");
}

function renderMaxWaiting(url, loginState) {
  messengerHint.innerHTML = "";
  const text = document.createElement("span");
  text.textContent = "Откройте MAX для подтверждения входа. TemichevVetBot и мини-приложение MAX используют тот же личный кабинет.";
  messengerHint.append(text);

  const actions = document.createElement("span");
  actions.className = "hint-actions";

  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "Открыть MAX";
    actions.append(link);
  }

  const checkButton = document.createElement("button");
  checkButton.type = "button";
  checkButton.textContent = "Проверить вход";
  checkButton.addEventListener("click", () => pollMaxLogin(loginState));
  actions.append(checkButton);
  messengerHint.append(actions);
}

function stopMaxPolling() {
  if (state.maxPollTimer) {
    clearTimeout(state.maxPollTimer);
    state.maxPollTimer = null;
  }
}

async function pollMaxLogin(loginState, attempt = 0) {
  stopMaxPolling();
  if (attempt > 60) {
    messengerHint.textContent = "MAX-вход не подтвержден. Попробуйте нажать кнопку ещё раз.";
    clearMaxLogin();
    return;
  }
  try {
    const data = await api(`/api/auth/max/status?state=${encodeURIComponent(loginState)}`, { method: "GET" });
    if (data.status === "complete") {
      state.token = "";
      await refreshAccountState();
      localStorage.removeItem("tvv_token");
      clearMaxLogin();
      messengerHint.textContent = "MAX-вход подтвержден.";
      setAuthMode(true);
      stopMaxPolling();
      trackAuthLoginSuccess("max");
      if (await completePendingSaveAfterLogin()) return;
      await renderStartupView();
      return;
    }
    if (data.status === "expired") {
      clearMaxLogin();
      messengerHint.textContent = data.message || "Код входа истек. Нажмите MAX ещё раз.";
      return;
    }
    renderMaxWaiting(state.maxLoginUrl, loginState);
    messengerHint.firstChild.textContent = data.message || "Ожидаем подтверждение в MAX...";
  } catch (error) {
    renderMaxWaiting(state.maxLoginUrl, loginState);
    messengerHint.firstChild.textContent = `Не удалось проверить вход: ${readableError(error.message)}`;
  }
  state.maxPollTimer = setTimeout(() => pollMaxLogin(loginState, attempt + 1), 3000);
}

openCheckBtn?.addEventListener("click", () => {
  trackFunnel("landing.primary_cta_click", { target: "hero" });
  openPetOnboarding();
});
petOnboardingCloseBtn?.addEventListener("click", closePetOnboarding);
petOnboardingDialog?.addEventListener("click", (event) => {
  if (event.target === petOnboardingDialog) closePetOnboarding();
});
publicPetOnboardingForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const petType = String(form.get("pet_type") || "").trim();
  const petName = String(form.get("pet_name") || "").trim();
  if (!petType || !petName) {
    if (petOnboardingHint) petOnboardingHint.textContent = "Выберите собаку или кошку и укажите кличку.";
    return;
  }
  const existing = pendingPetCreate();
  storePendingPetCreate({
    pet_type: petType,
    pet_name: petName,
    client_request_id: existing?.client_request_id || createFlowId(),
    created_at: existing?.created_at || new Date().toISOString()
  });
  closePetOnboarding();
  if (state.user) {
    setAuthMode(true);
    await completePendingPetAfterLogin();
    return;
  }
  openAuthDialog({ lead: "После входа карточка питомца создастся автоматически." });
});
openLoginBtn?.addEventListener("click", () => {
  trackFunnel("landing.login_cta_click", { target: "hero" });
  openAuthDialog();
});
authCloseBtn.addEventListener("click", closeAuthDialog);
authDialog.addEventListener("click", (event) => {
  if (event.target === authDialog) closeAuthDialog();
});
legalCloseBtn.addEventListener("click", closeLegalModal);
legalModal.addEventListener("click", (event) => {
  if (event.target === legalModal) closeLegalModal();
});
cookieAcceptBtn.addEventListener("click", () => setCookieConsent("all"));
cookieNecessaryBtn.addEventListener("click", () => setCookieConsent("necessary"));
telegramBtn.addEventListener("click", () => {
  trackFunnel("auth.telegram_start_click");
  startMessenger("telegram");
});
maxBtn.addEventListener("click", () => {
  trackFunnel("auth.max_start_click");
  startMessenger("max");
});

window.addEventListener("focus", () => {
  if (!state.token && state.telegramLoginState) pollTelegramLogin(state.telegramLoginState);
  if (!state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

window.addEventListener("popstate", () => {
  if (!openLegalFromCurrentPath()) closeLegalModal();
  syncAdminPageFromLocation();
});

window.addEventListener("hashchange", () => {
  syncAdminPageFromLocation();
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !state.token && state.telegramLoginState) pollTelegramLogin(state.telegramLoginState);
  if (!document.hidden && !state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

document.addEventListener("click", async (event) => {
  const legalButton = event.target.closest("[data-open-legal]");
  if (legalButton) {
    event.preventDefault();
    const legalType = legalButton.dataset.openLegal;
    if (legalButton.getAttribute("href") && legalPathMap[legalButton.getAttribute("href")]) {
      window.history.pushState({}, "", legalButton.getAttribute("href"));
    }
    openLegalModal(legalType);
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  const openOnboardingButton = event.target.closest("[data-open-onboarding]");
  const openPetButton = event.target.closest("[data-open-pet]");
  const petViewButton = event.target.closest("[data-pet-view]");
  const summaryPeriodButton = event.target.closest("button[data-summary-period]:not([data-print-summary])");
  const printSummaryButton = event.target.closest("[data-print-summary]");
  const saveFoodButton = event.target.closest("[data-auth-food-save]");
  const setMainButton = event.target.closest("[data-set-main]");
  const deletePetButton = event.target.closest("[data-delete-pet]");
  const deleteReminderButton = event.target.closest("[data-delete-reminder]");
  const linkProviderButton = event.target.closest("[data-link-provider]");
  const followupAnswerButton = event.target.closest("[data-followup-answer]");
  const copyTriageButton = event.target.closest("[data-copy-triage-result]");

  try {
    if (openOnboardingButton) {
      openPetOnboarding();
      return;
    }
    if (summaryPeriodButton) {
      await renderPetSummary(Number(summaryPeriodButton.dataset.petId), summaryPeriodButton.dataset.summaryPeriod || "30");
      return;
    }
    if (printSummaryButton) {
      const petId = Number(printSummaryButton.dataset.petId);
      const period = printSummaryButton.dataset.summaryPeriod || "30";
      await api(`/api/pets/${petId}/summary/export?period=${encodeURIComponent(period)}`, { method: "POST", body: "{}" });
      window.print();
      return;
    }
    if (saveFoodButton) {
      saveFoodButton.disabled = true;
      await completePendingPublicFoodAfterLogin();
      return;
    }
    if (copyTriageButton) {
      const resultBox = copyTriageButton.closest("[data-triage-answer]");
      await copyTextToClipboard(resultBox?.dataset.triageAnswer || "");
      const originalText = copyTriageButton.textContent;
      copyTriageButton.textContent = "Скопировано";
      window.setTimeout(() => {
        copyTriageButton.textContent = originalText || "Скопировать для врача";
      }, 1600);
      return;
    }
    if (followupAnswerButton) {
      const followupId = Number(followupAnswerButton.dataset.followupId);
      const answer = followupAnswerButton.dataset.followupAnswer;
      const data = await api(`/api/followups/${followupId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer })
      });
      if (answer === "retry") {
        await renderTriage();
        return;
      }
      setWorkspace(`
        <div class="workspace-head">
          <h2>Контроль состояния</h2>
          <button class="secondary-button compact icon-text-button" data-action="home" type="button">${renderAppIcon("chevron-left")}<span>На главную</span></button>
        </div>
        <div class="notice">${escapeHtml(data.message || "Ответ сохранён.")}</div>
      `);
      return;
    }
    if (linkProviderButton) {
      await startProviderLink(linkProviderButton.dataset.linkProvider);
      return;
    }
    if (openPetButton) {
      setDashboardActiveAction("pets");
      await renderPetCard(Number(openPetButton.dataset.openPet));
      return;
    }
    if (petViewButton) {
      const petId = Number(petViewButton.dataset.petId);
      const view = petViewButton.dataset.petView;
      setDashboardActiveAction(view === "triage" ? "triage" : view === "reminders" ? "reminders" : "pets");
      if (view === "history") await renderPetHistory(petId);
      if (view === "observations") await renderPetObservations(petId);
      if (view === "weight") await renderPetWeights(petId);
      if (view === "reminders") await renderReminders(petId);
      if (view === "triage") await renderTriage(petId);
      if (view === "summary") await renderPetSummary(petId);
      if (view === "edit") await renderPetEdit(petId);
      return;
    }
    if (setMainButton) {
      const petId = Number(setMainButton.dataset.setMain);
      await api(`/api/pets/${petId}/main`, { method: "POST", body: JSON.stringify({ is_main: true }) });
      await renderPetCard(petId);
      return;
    }
    if (deletePetButton) {
      const petId = Number(deletePetButton.dataset.deletePet);
      if (confirmPetDeletion(deletePetButton)) {
        await api(`/api/pets/${petId}`, { method: "DELETE" });
        await renderPets();
      }
      return;
    }
    if (deleteReminderButton) {
      const reminderId = Number(deleteReminderButton.dataset.deleteReminder);
      const returnPet = deleteReminderButton.dataset.returnPet;
      await api(`/api/reminders/${reminderId}`, { method: "DELETE" });
      await renderReminders(returnPet ? Number(returnPet) : null);
      return;
    }
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    setDashboardActiveAction(action);
    if (action === "home") await renderHome();
    if (action === "pets") await renderPets();
    if (action === "triage") await renderTriage();
    if (action === "more") renderMore();
    if (action === "food") await renderFood();
    if (action === "care") await renderKnowledgeSection("care");
    if (action === "faq") await renderKnowledgeSection("faq");
    if (action === "reminders") await renderReminders();
    if (action === "subscription") {
      trackFunnel("subscription.open_click");
      await refreshAccountState();
      renderSubscription();
    }
    if (action === "pay-plus") await startPlusPayment();
    if (action === "check-plus-payment") await checkPlusPaymentStatus();
    if (action === "account") await renderAccountLinks();
    if (action === "enable-push") await enablePushNotifications();
    if (action === "disable-push") await disablePushNotifications();
    if (action === "export-account-data") await downloadAccountData();
    if (action === "revoke-sessions") await revokeAllSessions();
    if (action === "show-data-deletion") renderDataDeletionPanel();
    if (action === "feedback") renderFeedback();
    if (action === "history") await renderGlobalHistory();
    if (action === "observations") await renderGlobalObservations();
    if (action === "logout") await performLogout();
  } catch (error) {
    showError(readableError(error.message));
  }
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  state.deferredInstall = event;
  installBtn.hidden = false;
});

installBtn.addEventListener("click", async () => {
  if (!state.deferredInstall) return;
  state.deferredInstall.prompt();
  await state.deferredInstall.userChoice;
  state.deferredInstall = null;
  installBtn.hidden = true;
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js", { scope: "/" })
    .then(() => navigator.serviceWorker.getRegistrations())
    .then((registrations) => Promise.all(
      registrations
        .filter((registration) => registration.scope.endsWith("/static/"))
        .map((registration) => registration.unregister())
    ))
    .catch(() => {});
}

clearSensitiveMiniAppFragment();
showCookieBannerIfNeeded();
renderPublicCheckLanding();
renderPublicCampaignLanding();
if ((location.pathname.replace(/\/+$/, "") || "/") === "/") {
  trackFunnel("landing.view", { path: "/" });
}
bootstrap();
openLegalFromCurrentPath();
