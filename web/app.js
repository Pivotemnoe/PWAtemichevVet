const state = {
  token: localStorage.getItem("tvv_token") || "",
  adminToken: localStorage.getItem("tvv_admin_token") || "",
  telegramLoginState: localStorage.getItem("tvv_telegram_login_state") || "",
  telegramLoginUrl: localStorage.getItem("tvv_telegram_login_url") || "",
  maxLoginState: localStorage.getItem("tvv_max_login_state") || "",
  maxLoginUrl: localStorage.getItem("tvv_max_login_url") || "",
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
const startupAction = (() => {
  const action = new URLSearchParams(window.location.search).get("action") || "";
  return ["triage", "pets", "reminders"].includes(action) ? action : "";
})();

const authView = document.querySelector("#authView");
const mainView = document.querySelector("main");
const dashboardTemplate = document.querySelector("#dashboardTemplate");
const adminTemplate = document.querySelector("#adminTemplate");
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
const openAuthBtn = document.querySelector("#openAuthBtn");
const authDialog = document.querySelector("#authDialog");
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
let logoutBtn = document.querySelector("#logoutBtn");
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

function ensureDashboardView() {
  if (dashboardView && document.body.contains(dashboardView)) return dashboardView;
  const dashboardNode = dashboardTemplate?.content?.firstElementChild?.cloneNode(true);
  if (!dashboardNode || !mainView) return null;
  mainView.append(dashboardNode);
  dashboardView = document.querySelector("#dashboardView");
  logoutBtn = document.querySelector("#logoutBtn");
  workspace = document.querySelector("#workspace");
  logoutBtn?.addEventListener("click", performLogout);
  return dashboardView;
}

function removeDashboardView() {
  if (dashboardView && document.body.contains(dashboardView)) dashboardView.remove();
  dashboardView = null;
  logoutBtn = null;
  workspace = null;
}

function ensureAdminView() {
  if (adminView && document.body.contains(adminView)) return adminView;
  const adminNode = adminTemplate?.content?.firstElementChild?.cloneNode(true);
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

function openAuthDialog() {
  authDialog.hidden = false;
  setTimeout(() => emailInput?.focus(), 0);
}

function closeAuthDialog() {
  if (authDialog) authDialog.hidden = true;
}

async function performLogout() {
  if (state.token) {
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
    } catch {
      // Local logout still needs to happen even if the session is already expired.
    }
  }
  stopTelegramPolling();
  clearTelegramLogin();
  stopMaxPolling();
  clearMaxLogin();
  localStorage.removeItem("tvv_token");
  state.token = "";
  clearAccountState();
  setAuthMode(false);
}

function readableError(message) {
  const text = String(message || "");
  const messages = {
    email_not_configured: "Вход по email временно недоступен. Попробуйте позже или используйте Telegram/MAX для подтверждения входа.",
    email_delivery_failed: "Не удалось отправить письмо. Проверьте адрес или попробуйте позже.",
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
    push_not_configured: "PWA-уведомления временно недоступны. Основные функции кабинета работают без них.",
    push_unsupported: "Этот браузер не поддерживает PWA-уведомления.",
    push_permission_denied: "Браузер не дал разрешение на уведомления.",
    rate_limited: "Слишком много запросов. Подождите немного и попробуйте снова.",
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
          <li>тексты симптомов и вопросов, которые пользователь вводит для проверки состояния или питания;</li>
          <li>данные подписки, лимитов и платежных событий без хранения полных реквизитов банковской карты;</li>
          <li>технические данные: IP-адрес, время запроса, ошибки, данные сессии, cookie/localStorage, записи безопасности.</li>
        </ul>
      </section>
      <section>
        <h3>4. Цели обработки</h3>
        <ul>
          <li>создание и защита личного кабинета;</li>
          <li>ведение карточек питомцев, истории, наблюдений, веса и напоминаний;</li>
          <li>оценка срочности ситуации и подготовка понятных рекомендаций владельцу;</li>
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
        <p>TemichevVet предоставляет информационный сервис для владельцев собак и кошек: карточки питомцев, историю, напоминания, проверку симптомов, проверку питания, подписку и синхронизацию входов.</p>
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
          <li>до 10 проверок по здоровью питомца в месяц;</li>
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
        <p>Сервис помогает быстрее сориентироваться по срочности ситуации, сохранить историю и подготовить понятные шаги. Он не ставит диагноз, не назначает лечение, не подбирает дозировки лекарств и не заменяет очный осмотр ветеринарного врача.</p>
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
}

function closeLegalModal() {
  legalModal.hidden = true;
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
    version: "20260613-errorcopy-1"
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

function loadMetrika() {
  if (metrikaLoaded || typeof window === "undefined") return;
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
    url: location.href,
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
  const main = pet.is_main ? "⭐ " : "";
  return `${main}${formatPetSpecies(pet.pet_type)} — ${pet.pet_name || "без имени"}`;
}

function observationTypeLabel(value) {
  const labels = {
    note: "Заметка",
    appetite: "Аппетит",
    activity: "Активность",
    stool: "Стул",
    symptom: "Симптом"
  };
  return labels[value] || value || "Заметка";
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
  setWorkspace(`<div class="notice danger">${escapeHtml(message)}</div>`);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(path, { ...options, headers });
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
  if (state.adminToken) {
    headers.Authorization = `Bearer ${state.adminToken}`;
  }
  const response = await fetch(path, { ...options, headers });
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
      const data = await adminApi("/api/admin/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: adminUsernameInput.value,
          password: adminPasswordInput.value
        })
      });
      state.adminToken = data.token;
      localStorage.setItem("tvv_admin_token", data.token);
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
    if (state.adminToken) {
      try {
        await adminApi("/api/admin/auth/logout", { method: "POST", body: "{}" });
      } catch {
        // Local admin logout still needs to happen if the server session has expired.
      }
    }
    localStorage.removeItem("tvv_admin_token");
    state.adminToken = "";
    setAdminMode(false);
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
    ["llm.", "LLM-разбор", "Событие проверки симптомов через модель или LLM-шлюз."],
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

function renderAdminMetric(label, value, hint = "") {
  return `
    <div class="summary-card admin-metric">
      <strong>${adminCell(value)}</strong>
      <span>${escapeHtml(label)}</span>
      ${hint ? `<small>${escapeHtml(hint)}</small>` : ""}
    </div>
  `;
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

function renderAdminDashboard(data, system = null) {
  const overview = data.overview || {};
  const checks = system?.checks || {};
  const statusHelp = system?.status_help || {};
  const events1h = system?.events_1h || {};
  const events24h = system?.events_24h || {};
  const integrationEvents = system?.integration_events_24h || [];
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
    <div class="admin-generated">Обновлено: ${formatDateTime(data.generated_at)}</div>
    <div class="summary-grid admin-summary">
      ${renderAdminMetric("Пользователей", overview.users_total, `+${overview.users_today || 0} сегодня`)}
      ${renderAdminMetric("Питомцев", overview.pets_total)}
      ${renderAdminMetric("Активный Plus", overview.active_plus)}
      ${renderAdminMetric("Платежей за 30 дней", overview.paid_payments_30d, `${overview.revenue_30d_rub || 0} ₽`)}
      ${renderAdminMetric("Проверок за 24 часа", overview.triage_24h)}
      ${renderAdminMetric("Токенов за 30 дней", overview.tokens_30d)}
      ${renderAdminMetric("Активных напоминаний", overview.active_reminders)}
      ${renderAdminMetric("Событий защиты 24ч", overview.security_events_24h, `${overview.security_warnings_24h || 0} предупреждений / ${overview.security_errors_24h || 0} ошибок`)}
    </div>
    <section class="admin-section">
      <h2>Системный статус</h2>
      <p class="admin-explain">Статусы ниже показывают, какие интеграции подключены именно на этом сервере. «Не подключено» не означает взлом или потерю данных: функция просто не будет доступна, пока не добавлены нужные ключи или секреты. Критично только если «Проблема» у базы.</p>
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
      <p class="admin-explain">«События с ошибкой» — это не всегда взлом. Сюда попадают неверные коды входа, истёкшие сессии, частые запросы, попытки открыть чужие данные и технические ошибки API. Смотрите «Журнал безопасности»: там видно тип события, канал и время, но без лишнего медицинского текста.</p>
      <div class="admin-error-grid">
        ${renderAdminMetric("API/сервер за 1ч", events1h.server_5xx ?? "—", "Если 0, сайт сейчас отвечает; число за 24ч может быть старой историей после перезапуска.")}
        ${renderAdminMetric("API/сервер за 24ч", events24h.server_5xx ?? "—", "5xx: серверная ошибка или временная недоступность API.")}
        ${renderAdminMetric("Оплата за 24ч", events24h.payment_errors ?? "—", "Сбои создания/проверки платежа YooKassa.")}
        ${renderAdminMetric("LLM за 24ч", events24h.llm_errors ?? "—", "Сбои проверки симптомов через модель или шлюз OpenAI.")}
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
    ${renderAdminTable("Последние пользователи", data.recent_users || [], [
      { key: "id", label: "ID" },
      { key: "email", label: "Email" },
      { key: "providers", label: "Входы" },
      { key: "plan", label: "Тариф" },
      { key: "pets_count", label: "Питомцы" },
      { key: "triage_count", label: "Проверки" },
      { key: "created_at", label: "Создан", render: (row) => formatDateTime(row.created_at) }
    ])}
    ${renderAdminTable("Последние проверки без медицинского текста", data.recent_triage || [], [
      { key: "id", label: "ID" },
      { key: "user_id", label: "User" },
      { key: "pet_name", label: "Питомец", render: (row) => adminCell(row.pet_name ? `${row.pet_type || "питомец"} — ${row.pet_name}` : "—") },
      { key: "urgency_level", label: "Срочность" },
      { key: "total_tokens", label: "Токены" },
      { key: "model", label: "Модель" },
      { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
    ])}
    ${renderAdminTable("Обратная связь", data.recent_feedback || [], [
      { key: "id", label: "ID" },
      { key: "email", label: "Пользователь" },
      { key: "category", label: "Категория" },
      { key: "preview", label: "Кратко" },
      { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
    ])}
    ${renderAdminTable("Журнал безопасности", data.recent_audit || [], [
      { key: "id", label: "ID" },
      { key: "event_type", label: "Событие", render: renderAuditEventCell },
      { key: "status", label: "Статус", render: (row) => adminCell(adminStatusLabel(row.status)) },
      { key: "help", label: "Пояснение", render: renderAuditHelpCell },
      { key: "actor", label: "Кто" },
      { key: "user_id", label: "User" },
      { key: "provider", label: "Канал" },
      { key: "created_at", label: "Дата", render: (row) => formatDateTime(row.created_at) }
    ])}
  `;
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
  setAdminMode(Boolean(state.adminToken));
  if (!state.adminToken) {
    setTimeout(() => adminPasswordInput?.focus(), 0);
    return;
  }
  try {
    await loadAdminDashboard();
  } catch (error) {
    localStorage.removeItem("tvv_admin_token");
    state.adminToken = "";
    setAdminMode(false);
    setAdminHint(adminReadableError(error.message), true);
  }
}

function clearStartupAction() {
  if (!startupAction) return;
  const url = new URL(window.location.href);
  url.searchParams.delete("action");
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

async function renderStartupView() {
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
  await renderHome();
}

function applyAccountState(data) {
  state.user = data.user || null;
  state.externalAccounts = data.external_accounts || [];
  state.subscription = data.subscription || null;
  state.telegramProfileSync = data.telegram_profile_sync || null;
  state.lastSyncCheckAt = new Date().toISOString();
}

function clearAccountState() {
  state.user = null;
  state.externalAccounts = [];
  state.subscription = null;
  state.telegramProfileSync = null;
  state.lastSyncCheckAt = "";
}

async function bootstrap() {
  if (isAdminRoute) {
    await bootstrapAdmin();
    return;
  }
  const shouldCheckPayment = new URLSearchParams(window.location.search).get("payment") === "plus";
  if (!state.token) {
    try {
      const data = await api("/api/me");
      applyAccountState(data);
      setAuthMode(true);
      if (shouldCheckPayment) {
        renderSubscription(`<div class="notice">Вернулись с оплаты. Проверяю статус платежа...</div>`);
        await checkPlusPaymentStatus({ replaceHistory: true });
        return;
      }
      await renderStartupView();
      return;
    } catch {
      clearAccountState();
    }
    setAuthMode(false);
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
    await renderStartupView();
  } catch {
    localStorage.removeItem("tvv_token");
    state.token = "";
    clearAccountState();
    setAuthMode(false);
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
      message: "Не удалось получить настройки PWA-уведомлений."
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
  if (state.user?.email) labels.push("Email");
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
          <span>${hasPets ? "Возраст, вес и основной питомец уже помогают проверке." : "Так проверки, вес и напоминания будут храниться в одном месте."}</span>
        </button>
        <button class="guide-step" data-action="triage" type="button">
          <strong>2. Проверьте симптомы</strong>
          <span>Опишите симптомы простыми словами, чтобы получить уровень срочности.</span>
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
  if (matches.length < 2) return [{ title: "Разбор состояния", body: text }];
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
  triage: "Проверка симптомов",
  reminder: "Напоминание",
  weight: "Вес",
  profile: "Карточка питомца",
  observation: "Наблюдение",
  vaccination: "Вакцинация"
};

function humanizeUiText(value) {
  return String(value || "")
    .replace(/\btriage\b/gi, "Проверка симптомов")
    .replace(/REMINDER_VACCINATION_CREATED/g, "Создано напоминание: вакцинация")
    .replace(/REMINDER_CREATED/g, "Создано напоминание")
    .replace(/Разбор жалобы/g, "Проверка симптомов")
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

function renderEmptyBlock({ icon = "ℹ️", title, text, action, actionText }) {
  return `
    <div class="empty-state empty-card">
      <div class="empty-icon">${icon}</div>
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(text)}</p>
        ${action ? `<button class="primary-button compact" data-action="${action}" type="button">${escapeHtml(actionText || "Продолжить")}</button>` : ""}
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
            <h3>Контроль состояния</h3>
            <p>Вы разбирали состояние: ${escapeHtml(pet)}. Как питомец чувствует себя сейчас?</p>
            <small>Если стало хуже — лучше не ждать и обратиться в клинику.</small>
          </div>
          <div class="inline-actions">
            <button class="secondary-button compact" data-followup-answer="better" data-followup-id="${item.id}" type="button">Стало лучше</button>
            <button class="secondary-button compact" data-followup-answer="same" data-followup-id="${item.id}" type="button">Без изменений</button>
            <button class="secondary-button compact danger-text" data-followup-answer="worse" data-followup-id="${item.id}" type="button">Стало хуже</button>
            <button class="primary-button compact" data-followup-answer="retry" data-followup-id="${item.id}" type="button">Новая проверка</button>
          </div>
        </article>
      `;
    })
    .join("");
  return `<section class="profile-card due-followups"><h3>Нужно проверить динамику</h3><div class="list-stack">${cards}</div></section>`;
}

async function renderHome() {
  await refreshAccountState();
  await refreshPets();
  const dueFollowups = await loadDueFollowups();
  const petCount = state.pets.length;
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  const sub = subscriptionSummary();
  const providerLabels = connectedProviderLabels();
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Личный кабинет TemichevVet</h2>
        <p>Питомцы, проверки симптомов, история, наблюдения, вес, напоминания и подписка собраны в одном месте.</p>
      </div>
      <button class="secondary-button compact" data-action="pets" type="button">🐾 Мои питомцы</button>
    </div>
    <div class="visual-strip">
      <img src="/static/assets/logo_temichevvet.jpg" alt="" class="visual-logo" />
      <div>
        <h3>Личный кабинет открыт</h3>
        <p>Карточки питомцев, история здоровья, питание, FAQ и напоминания доступны с телефона и ноутбука по одной ссылке.</p>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card">
        <strong>${petCount}</strong>
        <span>питомцев</span>
      </div>
      <div class="summary-card">
        <strong>${mainPet ? escapeHtml(mainPet.pet_name) : "—"}</strong>
        <span>основной питомец</span>
      </div>
      <div class="summary-card">
        <strong>${escapeHtml(sub.planTitle)}</strong>
        <span>${sub.quotaLeft} из ${sub.quotaTotal} проверок доступно</span>
      </div>
      <div class="summary-card">
        <strong>${escapeHtml(providerLabels)}</strong>
        <span>способы входа</span>
      </div>
      <div class="summary-card">
        <strong>${escapeHtml(sub.source)}</strong>
        <span>источник подписки</span>
      </div>
      <div class="summary-card">
        <strong>${dueFollowups.length}</strong>
        <span>проверок в обработке</span>
      </div>
    </div>
    ${renderHomeGuide(Boolean(petCount))}
    ${renderPwaInstallGuide()}
    <div class="next-actions">
      <button class="primary-button" data-action="triage" type="button">🩺 Проверить симптомы</button>
      <button class="secondary-button" data-action="pets" type="button">🐾 Мои питомцы</button>
      <button class="secondary-button" data-action="reminders" type="button">⏰ Напоминания</button>
      <button class="secondary-button" data-action="history" type="button">📜 История здоровья</button>
      <button class="secondary-button" data-action="food" type="button">🍽️ Питание</button>
      <button class="secondary-button" data-action="care" type="button">🧴 Уход и привычки</button>
      <button class="secondary-button" data-action="faq" type="button">❓ Вопросы и ответы</button>
    </div>
    <div class="secondary-menu-row inline">
      <button class="secondary-button compact" data-action="more" type="button">☰ Ещё: питание, FAQ, подписка и настройки</button>
    </div>
    ${renderDueFollowups(dueFollowups)}
  `, { scroll: false });
}

function renderMore() {
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Ещё</h2>
        <p>Дополнительные разделы сервиса: справка, питание, подписка, входы и связь с командой.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <div class="detail-grid more-grid">
      <button class="secondary-button" data-action="food" type="button">🍽️ Питание</button>
      <button class="secondary-button" data-action="care" type="button">🧴 Уход и привычки</button>
      <button class="secondary-button" data-action="faq" type="button">❓ Вопросы и ответы</button>
      <button class="secondary-button" data-action="observations" type="button">📊 Наблюдения</button>
      <button class="secondary-button" data-action="subscription" type="button">💳 Подписка</button>
      <button class="secondary-button" data-action="account" type="button">🔐 Способы входа</button>
      <button class="secondary-button" data-action="feedback" type="button">✉️ Обратная связь</button>
      <button class="secondary-button danger-text" data-action="logout" type="button">Выйти</button>
    </div>
    <div class="care-note">
      Питание, уход и вопросы-ответы не расходуют лимит проверок симптомов. Для срочной ситуации используйте «Проверить симптомы».
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
    telegram_db_not_configured: "Синхронизация Telegram временно недоступна на сервере.",
    telegram_user_not_found: "Telegram подключён, но профиль бота пока не найден.",
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
  const statusLabel = !telegramConnected ? "Telegram не подключён" : syncOk ? "Синхронизация штатная" : "Нужна проверка";
  const statusClass = !telegramConnected ? "neutral" : syncOk ? "connected" : "warning";
  const detail = !telegramConnected
    ? "Подключите Telegram, если хотите видеть питомцев, историю и Plus из Telegram-бота в этом кабинете."
    : syncOk
      ? "При открытии кабинета сервис проверяет Telegram-данные и подтягивает доступные питомцы, историю, наблюдения и подписку."
      : telegramSyncReasonText(sync.reason);
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
      <h3>Статус синхронизации</h3>
      <div class="meta-row">
        <span>Telegram: ${telegramConnected ? "подключён" : "не подключён"}</span>
        <span>MAX: ${maxConnected ? "подключён" : "не подключён"}</span>
        <span>Последняя проверка: ${checkedAt}</span>
      </div>
      <p><span class="status-badge ${statusClass}">${statusLabel}</span></p>
      <p>${escapeHtml(detail)}</p>
      ${imported ? `<div class="meta-row">${imported}</div>` : ""}
    </div>
  `;
}

function renderPushCard(push) {
  const supported = pushSupported();
  const enabled = Boolean(push?.config?.enabled);
  const count = Number(push?.status?.count || 0);
  const serverMessage = push?.config?.message || "";
  let statusText = serverMessage || "PWA-уведомления используются для контрольных напоминаний после разбора.";
  let button = "";
  if (!supported) {
    statusText = "Этот браузер не поддерживает PWA-уведомления. На iPhone используйте Safari и установите сайт на экран «Домой».";
  } else if (!enabled) {
    button = `<button class="secondary-button compact" type="button" disabled>Готовится</button>`;
  } else if (count > 0) {
    statusText = `Подключено устройств: ${count}. Уведомления помогут напомнить о контрольном вопросе после разбора.`;
    button = `<button class="secondary-button compact" data-action="disable-push" type="button">Отключить на этом устройстве</button>`;
  } else {
    statusText = "Можно включить уведомления на этом устройстве: сервис напомнит проверить состояние питомца после разбора.";
    button = `<button class="secondary-button compact" data-action="enable-push" type="button">Включить уведомления</button>`;
  }
  return `
    <div class="profile-card">
      <h3>Уведомления PWA</h3>
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
        <h2>Способы входа</h2>
        <p>Подключите мессенджеры к текущему кабинету, чтобы не создавать второй аккаунт и не разделять питомцев, историю и подписку.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <div class="profile-card">
      <h3>Email</h3>
      <p>${email ? `Статус: подключён · ${escapeHtml(maskEmail(email))}` : "Email пока не подключён. Вход по email можно использовать отдельно через окно входа."}</p>
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
    <div class="care-note">
      Мессенджер нужен только для подтверждения личности. После подтверждения вернитесь сюда: сайт сам завершит привязку.
    </div>
    ${renderPushCard(push)}
    <div class="profile-card">
      <h3>Безопасность и данные</h3>
      <p>Здесь можно завершить активные входы, скачать данные кабинета или оставить запрос на удаление персональных данных.</p>
      <div class="inline-actions">
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

async function startProviderLink(provider) {
  setAccountLinkHint("Готовлю безопасную привязку...");
  try {
    const data = await api(`/api/account/${provider}/start`, { method: "POST", body: "{}" });
    if (!data.enabled || !data.url || !data.state) {
      setAccountLinkHint(data.message || "Этот способ входа пока не настроен.");
      return;
    }
    renderAccountLinkWaiting(provider, data.url, data.state);
    window.open(data.url, "_blank", "noopener");
    pollAccountLink(provider, data.state);
  } catch (error) {
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
    if (data.status === "complete" && data.token) {
      state.token = data.token;
      localStorage.setItem("tvv_token", data.token);
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
  localStorage.removeItem("tvv_token");
  state.token = "";
  state.user = null;
  state.externalAccounts = [];
  state.subscription = null;
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
              <div>
                <h3>${escapeHtml(petTitle(pet))}</h3>
                <p>${pet.is_main ? "Основной питомец для быстрых проверок." : "Карточка питомца: история, вес, наблюдения и напоминания."}</p>
                ${renderPetBadges(pet)}
              </div>
              <button class="secondary-button compact" data-open-pet="${pet.id}" type="button">Открыть карточку</button>
            </article>
          `
        )
        .join("")
    : `
      <div class="empty-state">
        <img src="/static/assets/onb_step1_add_pet.jpg" alt="" />
        <p>Питомцев пока нет. Создайте первую карточку, чтобы сохранять историю и напоминания.</p>
      </div>
    `;

  setWorkspace(`
    <div class="workspace-head">
      <h2>Мои питомцы</h2>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ Назад</button>
    </div>
    <div class="list-stack">${cards}</div>
    <form class="form-grid" id="petCreateForm">
      <h3>Добавить питомца</h3>
      <label><span>Тип</span><select name="pet_type"><option value="кошка">Кошка</option><option value="собака">Собака</option></select></label>
      <label><span>Кличка</span><input name="pet_name" required placeholder="Например: Лео" /></label>
      <label><span>Порода</span><input name="breed" placeholder="Если знаете: бенгальская, шпиц..." /></label>
      <label><span>Пол</span><select name="sex"><option value="">Не указан</option><option value="м">Самец</option><option value="ж">Самка</option></select></label>
      <label><span>Год рождения</span><input name="birth_year" inputmode="numeric" placeholder="Например: 2019" /></label>
      <label><span>Месяц</span><input name="birth_month" inputmode="numeric" placeholder="Если знаете: 6" /></label>
      <label><span>День</span><input name="birth_day" inputmode="numeric" placeholder="Если знаете: 15" /></label>
      <label><span>Вес, кг</span><input name="weight_kg" inputmode="decimal" placeholder="6.1" /></label>
      <label class="checkbox-row full-row"><input name="is_main" type="checkbox" /> <span>Сделать основным: он будет выбран первым в проверках и напоминаниях.</span></label>
      <button class="primary-button" type="submit">Сохранить питомца</button>
    </form>
  `);

  document.querySelector("#petCreateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = petPayloadFromForm(form);
    try {
      const data = await api("/api/pets", { method: "POST", body: JSON.stringify(payload) });
      state.currentPetId = data.item.id;
      await renderPetCard(data.item.id);
    } catch (error) {
      showError(`Не удалось сохранить питомца: ${error.message}`);
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
        <h2>Карточка питомца</h2>
        <p>${escapeHtml(petTitle(pet))}</p>
      </div>
      <button class="secondary-button compact" data-action="pets" type="button">⬅️ К списку</button>
    </div>
    <section class="profile-card">
      <h3>Что важно сейчас</h3>
      <p>${escapeHtml(data.summary.what_now)}</p>
      ${renderPetBadges(pet)}
    </section>
    <div class="detail-grid">
      <button class="secondary-button" data-pet-view="history" data-pet-id="${pet.id}" type="button">📜 Вся история</button>
      <button class="secondary-button" data-pet-view="observations" data-pet-id="${pet.id}" type="button">📊 Наблюдения</button>
      <button class="secondary-button" data-pet-view="weight" data-pet-id="${pet.id}" type="button">⚖️ Вес</button>
      <button class="secondary-button" data-pet-view="reminders" data-pet-id="${pet.id}" type="button">⏰ Напоминания</button>
      <button class="secondary-button" data-pet-view="triage" data-pet-id="${pet.id}" type="button">🩺 Проверить симптомы</button>
      <button class="secondary-button" data-pet-view="edit" data-pet-id="${pet.id}" type="button">✏️ Изменить</button>
      <button class="secondary-button" data-set-main="${pet.id}" type="button">${pet.is_main ? "⭐ Основной" : "⭐ Сделать основным"}</button>
      <button class="secondary-button danger-text" data-delete-pet="${pet.id}" data-delete-pet-title="${escapeHtml(petTitle(pet))}" data-delete-pet-linked="${pet.external_source ? "1" : "0"}" type="button">🗑 Удалить</button>
    </div>
    <section>
      <h3>Последние события</h3>
      ${history ? `<ul class="event-list">${history}</ul>` : "<p>История пока пустая.</p>"}
    </section>
  `);
}

function confirmPetDeletion(button) {
  const title = button.dataset.deletePetTitle || "карточка питомца";
  const isLinked = button.dataset.deletePetLinked === "1";
  const message = [
    `Удаление карточки: ${title}`,
    "",
    "Будут удалены данные питомца, связанные напоминания, наблюдения, вес и история в веб-кабинете.",
    isLinked ? "Карточка связана с мессенджером: удаление также уйдёт в очередь синхронизации." : "",
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
      <button class="secondary-button compact" data-open-pet="${pet.id}" type="button">⬅️ В карточку</button>
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
      showError(`Не удалось обновить карточку: ${error.message}`);
    }
  });
}

async function renderPetHistory(petId) {
  const data = await api(`/api/pets/${petId}/history`);
  const items = data.items.length
    ? data.items.map((item) => renderHistoryCard(item)).join("")
    : renderEmptyBlock({
        icon: "📜",
        title: "История пока пустая",
        text: "После первой проверки, наблюдения, веса или напоминания события появятся здесь.",
        action: "triage",
        actionText: "Проверить симптомы"
      });
  setWorkspace(`
    <div class="workspace-head">
      <h2>История здоровья</h2>
      <button class="secondary-button compact" data-open-pet="${petId}" type="button">⬅️ В карточку</button>
    </div>
    <div class="list-stack">${items}</div>
  `);
}

async function renderPetObservations(petId) {
  const data = await api(`/api/pets/${petId}/observations`);
  const items = data.items.length
    ? data.items.map((item) => `<article class="item-card"><div><h3>${escapeHtml(observationTypeLabel(item.obs_type))}</h3><p>${escapeHtml(item.payload?.text || "")}</p><small>${formatDateTime(item.created_at)}</small></div></article>`).join("")
    : renderEmptyBlock({
        icon: "📊",
        title: "Наблюдений пока нет",
        text: "Добавляйте короткие заметки о состоянии, аппетите, активности, стуле или симптомах.",
      });
  setWorkspace(`
    <div class="workspace-head">
      <h2>Наблюдения</h2>
      <button class="secondary-button compact" data-open-pet="${petId}" type="button">⬅️ В карточку</button>
    </div>
    <div class="care-note">Наблюдения — это ваши короткие заметки: аппетит, активность, стул, весомые изменения поведения. Проверки симптомов хранятся в «Истории здоровья».</div>
    <form class="inline-form" id="observationForm">
      <input name="text" placeholder="Например: аппетит нормальный, активность ниже обычного" required />
      <button class="primary-button compact" type="submit">Добавить наблюдение</button>
    </form>
    <div class="list-stack">${items}</div>
  `);
  document.querySelector("#observationForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("text") || "");
    try {
      await api(`/api/pets/${petId}/observations`, { method: "POST", body: JSON.stringify({ obs_type: "note", text }) });
      await renderPetObservations(petId);
    } catch (error) {
      showError(`Не удалось добавить наблюдение: ${error.message}`);
    }
  });
}

async function renderPetWeights(petId) {
  const data = await api(`/api/pets/${petId}/weights`);
  const items = data.items.length
    ? data.items.map((item) => `<article class="item-card"><div><h3>${escapeHtml(item.weight_kg)} кг</h3><p>${escapeHtml(item.note || "")}</p><small>${formatDateTime(item.created_at)}</small></div></article>`).join("")
    : renderEmptyBlock({
        icon: "⚖️",
        title: "Истории веса пока нет",
        text: "Сохраняйте вес периодически, чтобы видеть динамику и быстрее замечать изменения.",
      });
  setWorkspace(`
    <div class="workspace-head">
      <h2>Вес</h2>
      <button class="secondary-button compact" data-open-pet="${petId}" type="button">⬅️ В карточку</button>
    </div>
    <form class="inline-form" id="weightForm">
      <input name="weight_kg" inputmode="decimal" placeholder="6.1" required />
      <input name="note" placeholder="Заметка, если нужна" />
      <button class="primary-button compact" type="submit">Сохранить</button>
    </form>
    <div class="list-stack">${items}</div>
  `);
  document.querySelector("#weightForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api(`/api/pets/${petId}/weights`, {
        method: "POST",
        body: JSON.stringify({
          weight_kg: Number(String(form.get("weight_kg") || "").replace(",", ".")),
          note: String(form.get("note") || "")
        })
      });
      await renderPetWeights(petId);
    } catch (error) {
      showError(`Не удалось сохранить вес: ${error.message}`);
    }
  });
}

async function renderReminders(petId = null) {
  await refreshPets();
  const data = petId ? await api(`/api/pets/${petId}`) : await api("/api/reminders");
  const reminders = petId ? data.reminders || [] : data.items || [];
  const title = petId ? `Напоминания питомца` : "Напоминания";
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
                <small>${escapeHtml(item.periodicity || "once")}</small>
              </div>
              <button class="secondary-button compact danger-text" data-delete-reminder="${item.id}" data-return-pet="${petId || ""}" type="button">Отключить</button>
            </article>
          `
        )
        .join("")
    : renderEmptyBlock({
        icon: "⏰",
        title: "Напоминаний пока нет",
        text: "Создайте напоминание о вакцинации, обработке от паразитов, осмотре, груминге или своей задаче.",
      });

  setWorkspace(`
    <div class="workspace-head">
      <h2>${title}</h2>
      <button class="secondary-button compact" ${petId ? `data-open-pet="${petId}"` : `data-action="home"`} type="button">⬅️ Назад</button>
    </div>
    <form class="form-grid" id="reminderForm">
      <h3>Добавить напоминание</h3>
      <label><span>Питомец</span><select name="pet_id">${petOptions(selectedPetId)}</select></label>
      <label><span>Шаблон</span><select name="reminder_type">${reminderTypes.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label><span>Заголовок</span><input name="title" required value="Вакцинация" placeholder="Вакцинация" /></label>
      <label><span>Дата</span><input name="due_date" type="date" required /></label>
      <label><span>Время</span><input name="due_time" type="time" /></label>
      <label><span>Повтор</span><select name="periodicity">${periodicityOptions.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label class="full-row"><span>Заметка</span><input name="notes" placeholder="Например: купить препарат заранее" /></label>
      <button class="primary-button" type="submit">Сохранить напоминание</button>
    </form>
    <div class="list-stack">${items}</div>
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
      await api("/api/reminders", {
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
      await renderReminders(petId);
    } catch (error) {
      showError(`Не удалось сохранить напоминание: ${error.message}`);
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
        <h2>Проверить симптомы</h2>
        <p>Выберите питомца и опишите, что происходит. Если в тексте есть опасные признаки, сервис сразу покажет срочное предупреждение.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <div class="care-note">
      TemichevVet не ставит диагноз и не назначает лечение. Если есть тяжёлое дыхание, судороги,
      потеря сознания, кровь, признаки отравления или резкое ухудшение — сразу обращайтесь в клинику.
    </div>
    <form class="form-grid one-column" id="triageForm">
      <label><span>Питомец</span><select name="pet_id"><option value="">Без привязки</option>${petOptions(selectedPetId)}</select></label>
      <label><span>Что происходит</span><textarea name="text" placeholder="Например: кошка не ест второй день, вялая, была рвота после еды" required></textarea></label>
      <button class="primary-button" type="submit">Оценить срочность</button>
    </form>
    <div id="triageResult"></div>
    <div class="visual-strip compact-visual">
      <img src="/static/assets/hero_pets.jpg" alt="" />
      <div>
        <h3>Как работает проверка</h3>
        <p>Сначала срабатывают опасные признаки. Это помогает не ждать ответ сервиса там, где нужна клиника.</p>
      </div>
    </div>
  `);
  document.querySelector("#triageForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const petId = String(form.get("pet_id") || "");
    const resultEl = document.querySelector("#triageResult");
    resultEl.innerHTML = `<p class="hint">Проверяю...</p>`;
    try {
      const data = await api("/api/triage", {
        method: "POST",
        body: JSON.stringify({
          pet_id: petId ? Number(petId) : null,
          text: String(form.get("text") || "")
        })
      });
      state.subscription = data.subscription || state.subscription;
      resultEl.innerHTML = `
        <div class="result-box ${data.urgency === "red" ? "danger" : ""}" data-triage-answer="${escapeHtml(data.answer)}">
          ${formatTriageAnswer(data.answer)}
          <div class="inline-actions triage-result-actions">
            <button class="secondary-button compact" data-copy-triage-result type="button">Скопировать для врача</button>
          </div>
        </div>
        <div class="care-note">
          Если в ответе есть уточняющие вопросы, не обязательно отвечать здесь сразу.
          Подготовьте эти данные для ветеринарного врача или добавьте их в новую проверку, если хотите уточнить состояние.
          Новая проверка будет отдельной оценкой срочности и спишет ещё один запрос.
          ${data.followup ? "Контроль состояния будет показан в кабинете позже; если Telegram подключён, напоминание также уйдёт туда." : ""}
        </div>
        <div class="next-actions">
          ${petId ? `<button class="secondary-button" data-open-pet="${petId}" type="button">🐾 Открыть карточку</button>` : ""}
          ${petId ? `<button class="secondary-button" data-pet-view="reminders" data-pet-id="${petId}" type="button">⏰ Добавить напоминание</button>` : `<button class="secondary-button" data-action="reminders" type="button">⏰ Добавить напоминание</button>`}
          ${petId ? `<button class="secondary-button" data-pet-view="history" data-pet-id="${petId}" type="button">📜 История питомца</button>` : ""}
          <button class="primary-button" data-action="triage" type="button">🩺 Уточнить новой проверкой</button>
        </div>
      `;
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger">Ошибка: ${escapeHtml(error.message)}</div>`;
    }
  });
}

async function renderFood() {
  await refreshPets();
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Питание</h2>
        <p>Проверьте отдельный продукт или готовое блюдо. Если это блюдо, лучше указать состав через запятую.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <form class="form-grid one-column" id="foodForm">
      <label><span>Для кого проверяем?</span><select name="food_target">
        <option value="">Не указывать</option>
        ${state.pets.map((pet) => `<option value="pet:${pet.id}" ${mainPet && pet.id === mainPet.id ? "selected" : ""}>${escapeHtml(petTitle(pet))}</option>`).join("")}
        <option value="cat">Кошка</option>
        <option value="dog">Собака</option>
      </select></label>
      <label><span>Продукт или блюдо</span><input name="query" placeholder="борщ, котлета, виноград, куриная грудка" required /></label>
      <label><span>Состав блюда, если известен</span><input name="ingredients" placeholder="мясо, рис, лук, соль" /></label>
      <div class="care-note">Если блюда нет в базе, укажите ингредиенты. Например: “харчо: говядина, рис, томат, чеснок, специи”. Для отдельного продукта достаточно названия.</div>
      <button class="primary-button" type="submit">Проверить</button>
    </form>
    <div id="foodResult"></div>
  `);
  document.querySelector("#foodForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const resultEl = document.querySelector("#foodResult");
    resultEl.innerHTML = `<p class="hint">Проверяю...</p>`;
    try {
      const data = await api("/api/food/check", {
        method: "POST",
        body: JSON.stringify({
          query: String(form.get("query") || ""),
          ingredients: String(form.get("ingredients") || "")
        })
      });
      resultEl.innerHTML = `
        <div class="result-box ${data.item && !data.item.allowed ? "danger" : ""}">
          <pre>${escapeHtml(data.message)}</pre>
        </div>
        <div class="next-actions">
          <button class="secondary-button" data-action="food" type="button">Проверить ещё продукт</button>
          <button class="secondary-button" data-action="faq" type="button">❓ Вопросы и ответы</button>
          <button class="secondary-button" data-action="home" type="button">⬅️ В меню</button>
        </div>
      `;
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger">Ошибка: ${escapeHtml(error.message)}</div>`;
    }
  });
}

const knowledgeSections = {
  care: {
    title: "Уход и привычки",
    icon: "🧴",
    endpoint: "/api/care",
    intro: "Карточки по уходу, поведению, шерсти, когтям, ушам, зубам, прогулкам и домашней безопасности.",
    label: "Тема ухода",
    placeholder: "когти у кошки, уход за щенком, переезд с питомцем",
    empty: "Карточки по уходу не найдены. Попробуйте другую формулировку."
  },
  faq: {
    title: "Вопросы и ответы",
    icon: "❓",
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
        <h2>${config.icon} ${config.title}</h2>
        <p>${escapeHtml(config.intro)}</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <form class="form-grid one-column" id="knowledgeSearchForm">
      <label>
        <span>${escapeHtml(config.label)}</span>
        <input name="query" placeholder="${escapeHtml(config.placeholder)}" />
      </label>
      <button class="primary-button" type="submit">Найти</button>
    </form>
    <div class="care-note">
      Это справочный раздел. Он не списывает запросы по здоровью и не заменяет проверку симптомов или очный осмотр ветеринарного врача.
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
      resultEl.innerHTML = `<div class="notice danger">Ошибка: ${escapeHtml(readableError(error.message))}</div>`;
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
  const className = type ? `notice ${type}` : "notice";
  return `<div class="${className}">${escapeHtml(message)}</div>`;
}

async function startPlusPayment() {
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
    if (resultEl) resultEl.innerHTML = paymentStatusNotice(`Ошибка: ${readableError(error.message)}`, "danger");
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
    const message = paymentStatusNotice(`Ошибка: ${readableError(error.message)}`, "danger");
    if (resultEl) resultEl.innerHTML = message;
    else renderSubscription(message);
  }
}

function renderSubscription(statusHtml = "") {
  const sub = state.subscription || {};
  const sourceLabel = sub.source === "telegram" ? "Telegram" : "PWA";
  const plan = sub.title || sub.plan || "Free";
  const quotaTotal = Number.isFinite(Number(sub.quota_total)) ? Number(sub.quota_total) : 0;
  const quotaUsed = Number.isFinite(Number(sub.quota_used)) ? Number(sub.quota_used) : 0;
  const quotaLeft = Number.isFinite(Number(sub.quota_left)) ? Number(sub.quota_left) : Math.max(0, quotaTotal - quotaUsed);
  const periodEnd = sub.period_end ? formatDateTime(sub.period_end) : "—";
  const canPay = !sub.plan || sub.plan === "free";
  const telegramConnected = isProviderConnected("telegram");
  setWorkspace(`
    <div class="workspace-head">
      <h2>Подписка</h2>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <div class="visual-strip compact-visual">
      <img src="/static/assets/subscription_banner.jpg" alt="" />
      <div>
        <h3>Plus в веб-кабинете</h3>
        <p>Расширенные лимиты, история по питомцам и больше активных напоминаний. Автосписаний не будет.</p>
      </div>
    </div>
    <div class="profile-card">
      <h3>Ваш текущий доступ</h3>
      <p><strong>Тариф:</strong> ${escapeHtml(plan)}</p>
      <p><strong>Использовано проверок:</strong> ${quotaUsed} / ${quotaTotal}. Осталось: ${quotaLeft}.</p>
      <p><strong>Источник подписки:</strong> ${escapeHtml(sourceLabel)}.</p>
      ${sub.plan && sub.plan !== "free" ? `<p><strong>Действует до:</strong> ${escapeHtml(periodEnd)}.</p>` : ""}
      ${telegramConnected || sourceLabel === "Telegram" ? `
        <div class="notice">Telegram подключён: сайт и Telegram используют один аккаунт, историю и подписку.</div>
      ` : `
        <div class="notice">Если Plus был оплачен в Telegram, подключите Telegram в разделе «Способы входа» — кабинет подтянет тот же доступ.</div>
      `}
      ${canPay ? `
        <div class="next-actions payment-actions">
          <button class="primary-button" data-action="pay-plus" type="button">💳 Оплатить Plus — 200 ₽</button>
          <button class="secondary-button" data-action="check-plus-payment" type="button">Проверить оплату</button>
        </div>
        <p class="hint">Plus оплачивается разово на 30 дней. Автосписаний нет. После окончания срока кабинет вернётся на Free.</p>
      ` : `
        <div class="notice">Plus активен. Повторная оплата сейчас не нужна.</div>
      `}
      <div id="paymentResult">${statusHtml}</div>
    </div>
    <div class="pricing-grid subscription-pricing" aria-label="Тарифы TemichevVet">
      <article class="pricing-card">
        <div>
          <strong>Free</strong>
          <span>Бесплатный старт</span>
        </div>
        <p>Базовый личный кабинет для первых проверок и ведения питомца.</p>
        <ul>
          <li>до 5 проверок по здоровью в первый месяц;</li>
          <li>карточка питомца, история, наблюдения и вес;</li>
          <li>базовый доступ к материалам и проверке питания.</li>
        </ul>
      </article>
      <article class="pricing-card featured">
        <div>
          <strong>Plus</strong>
          <span>200 ₽ за 30 дней</span>
        </div>
        <p>Расширенный доступ для регулярного контроля состояния питомца.</p>
        <ul>
          <li>до 10 проверок по здоровью в месяц;</li>
          <li>расширенная история по питомцам;</li>
          <li>до 20 активных напоминаний;</li>
          <li>до 3 питомцев в личном кабинете.</li>
        </ul>
      </article>
    </div>
    <p class="legal-price-note">
      Plus оплачивается разово на 30 дней. Автосписаний нет. После окончания срока кабинет
      возвращается на Free, если Plus не продлить.
    </p>
  `);
}

function renderFeedback() {
  setWorkspace(`
    <div class="workspace-head">
      <h2>Обратная связь</h2>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
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
      resultEl.textContent = `Ошибка: ${error.message}`;
    }
  });
}

async function renderGlobalHistory() {
  await refreshPets();
  if (!state.pets.length) {
    setWorkspace(`
      <div class="workspace-head">
        <h2>История здоровья</h2>
        <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
      </div>
      ${renderEmptyBlock({
        icon: "📜",
        title: "Сначала добавьте питомца",
        text: "История хранится по карточкам питомцев, чтобы не смешивать разные обращения.",
        action: "pets",
        actionText: "Добавить питомца"
      })}
    `);
    return;
  }
  await renderPetHistory(state.currentPetId || state.pets[0].id);
}

async function renderGlobalObservations() {
  await refreshPets();
  if (!state.pets.length) {
    setWorkspace(`
      <div class="workspace-head">
        <h2>Наблюдения</h2>
        <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
      </div>
      ${renderEmptyBlock({
        icon: "📊",
        title: "Сначала добавьте питомца",
        text: "Наблюдения лучше вести по конкретной карточке: так видна динамика состояния.",
        action: "pets",
        actionText: "Добавить питомца"
      })}
    `);
    return;
  }
  await renderPetObservations(state.currentPetId || state.pets[0].id);
}

async function verifyEmailCode() {
  emailHint.textContent = "Проверяю код...";
  try {
    const data = await api("/api/auth/email/verify", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value, code: codeInput.value })
    });
    state.token = data.token;
    localStorage.setItem("tvv_token", data.token);
    await refreshAccountState();
    setAuthMode(true);
    emailHint.textContent = "";
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

async function startMessenger(provider) {
  messengerHint.textContent = "Готовлю вход...";
  try {
    const data = await api(`/api/auth/${provider}/start`, { method: "POST", body: "{}" });
    messengerHint.textContent = data.message;
    if (data.enabled && data.url) {
      if (provider === "telegram" && data.state) {
        saveTelegramLogin(data.state, data.url);
        renderTelegramWaiting(data.url, data.state);
        window.open(data.url, "_blank", "noopener");
        pollTelegramLogin(data.state);
        return;
      }
      if (provider === "max" && data.state) {
        saveMaxLogin(data.state, data.url);
        renderMaxWaiting(data.url, data.state);
        window.open(data.url, "_blank", "noopener");
        pollMaxLogin(data.state);
        return;
      }
      window.location.href = data.url;
    }
  } catch (error) {
    messengerHint.textContent = `Ошибка: ${error.message}`;
  }
}

function saveTelegramLogin(loginState, url) {
  state.telegramLoginState = loginState;
  state.telegramLoginUrl = url;
  localStorage.setItem("tvv_telegram_login_state", loginState);
  localStorage.setItem("tvv_telegram_login_url", url);
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
    if (data.status === "complete" && data.token) {
      state.token = data.token;
      state.user = data.user;
      await refreshAccountState();
      localStorage.setItem("tvv_token", data.token);
      clearTelegramLogin();
      messengerHint.textContent = "Telegram-вход подтвержден.";
      setAuthMode(true);
      stopTelegramPolling();
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
    messengerHint.firstChild.textContent = `Ошибка проверки: ${error.message}`;
  }
  state.telegramPollTimer = setTimeout(() => pollTelegramLogin(loginState, attempt + 1), 3000);
}

function saveMaxLogin(loginState, url) {
  state.maxLoginState = loginState;
  state.maxLoginUrl = url;
  localStorage.setItem("tvv_max_login_state", loginState);
  localStorage.setItem("tvv_max_login_url", url);
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
  text.textContent = "Откройте MAX только для подтверждения входа. После подтверждения вернитесь сюда — сайт завершит вход автоматически.";
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
    if (data.status === "complete" && data.token) {
      state.token = data.token;
      state.user = data.user;
      await refreshAccountState();
      localStorage.setItem("tvv_token", data.token);
      clearMaxLogin();
      messengerHint.textContent = "MAX-вход подтвержден.";
      setAuthMode(true);
      stopMaxPolling();
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
    messengerHint.firstChild.textContent = `Ошибка проверки: ${error.message}`;
  }
  state.maxPollTimer = setTimeout(() => pollMaxLogin(loginState, attempt + 1), 3000);
}

openAuthBtn.addEventListener("click", openAuthDialog);
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
telegramBtn.addEventListener("click", () => startMessenger("telegram"));
maxBtn.addEventListener("click", () => startMessenger("max"));

logoutBtn?.addEventListener("click", performLogout);

window.addEventListener("focus", () => {
  if (!state.token && state.telegramLoginState) pollTelegramLogin(state.telegramLoginState);
  if (!state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

window.addEventListener("popstate", () => {
  if (!openLegalFromCurrentPath()) closeLegalModal();
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
  const openPetButton = event.target.closest("[data-open-pet]");
  const petViewButton = event.target.closest("[data-pet-view]");
  const setMainButton = event.target.closest("[data-set-main]");
  const deletePetButton = event.target.closest("[data-delete-pet]");
  const deleteReminderButton = event.target.closest("[data-delete-reminder]");
  const linkProviderButton = event.target.closest("[data-link-provider]");
  const followupAnswerButton = event.target.closest("[data-followup-answer]");
  const copyTriageButton = event.target.closest("[data-copy-triage-result]");

  try {
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
          <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
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
      await renderPetCard(Number(openPetButton.dataset.openPet));
      return;
    }
    if (petViewButton) {
      const petId = Number(petViewButton.dataset.petId);
      const view = petViewButton.dataset.petView;
      if (view === "history") await renderPetHistory(petId);
      if (view === "observations") await renderPetObservations(petId);
      if (view === "weight") await renderPetWeights(petId);
      if (view === "reminders") await renderReminders(petId);
      if (view === "triage") await renderTriage(petId);
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
    if (action === "home") await renderHome();
    if (action === "pets") await renderPets();
    if (action === "triage") await renderTriage();
    if (action === "more") renderMore();
    if (action === "food") await renderFood();
    if (action === "care") await renderKnowledgeSection("care");
    if (action === "faq") await renderKnowledgeSection("faq");
    if (action === "reminders") await renderReminders();
    if (action === "subscription") {
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
    showError(`Ошибка: ${readableError(error.message)}`);
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
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
}

showCookieBannerIfNeeded();
bootstrap();
openLegalFromCurrentPath();
