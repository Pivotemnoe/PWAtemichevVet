const state = {
  token: localStorage.getItem("tvv_token") || "",
  telegramLoginState: localStorage.getItem("tvv_telegram_login_state") || "",
  telegramLoginUrl: localStorage.getItem("tvv_telegram_login_url") || "",
  maxLoginState: localStorage.getItem("tvv_max_login_state") || "",
  maxLoginUrl: localStorage.getItem("tvv_max_login_url") || "",
  deferredInstall: null,
  telegramPollTimer: null,
  maxPollTimer: null,
  lastPlusPaymentId: localStorage.getItem("tvv_last_plus_payment_id") || "",
  user: null,
  externalAccounts: [],
  subscription: null,
  pets: [],
  currentPetId: null
};

const LEGAL_UPDATED_AT = "5 июня 2026";
const OPERATOR_EMAIL = "support@temichevvet.ru";

const authView = document.querySelector("#authView");
const dashboardView = document.querySelector("#dashboardView");
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
const logoutBtn = document.querySelector("#logoutBtn");
const installBtn = document.querySelector("#installBtn");
const workspace = document.querySelector("#workspace");
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

const periodicityOptions = [
  ["once", "Один раз"],
  ["daily", "Ежедневно"],
  ["weekly", "Еженедельно"],
  ["monthly", "Ежемесячно"],
  ["every_3_months", "Раз в 3 месяца"],
  ["every_6_months", "Раз в 6 месяцев"],
  ["yearly", "Раз в год"]
];

function setAuthMode(isAuthed) {
  authView.hidden = isAuthed;
  dashboardView.hidden = !isAuthed;
  if (isAuthed) closeAuthDialog();
}

function openAuthDialog() {
  authDialog.hidden = false;
  setTimeout(() => emailInput?.focus(), 0);
}

function closeAuthDialog() {
  if (authDialog) authDialog.hidden = true;
}

function readableError(message) {
  const text = String(message || "");
  const messages = {
    email_not_configured: "Вход по email подключается. Пока используйте Telegram или MAX для подтверждения входа.",
    email_delivery_failed: "Не удалось отправить письмо. Проверьте адрес или попробуйте позже.",
    email_code_too_many_requests: "Код уже отправлен. Подождите около минуты перед повторной отправкой.",
    email_code_hour_limit: "Слишком много кодов на этот email. Попробуйте позже.",
    invalid_code: "Код не подошёл. Проверьте цифры и попробуйте ещё раз.",
    code_attempts_exceeded: "Слишком много неверных попыток. Запросите новый код.",
    code_expired_or_not_found: "Код истёк. Запросите новый код.",
    payment_provider_not_configured: "Оплата в веб-кабинете ещё настраивается. Пока используйте оплату в Telegram-версии.",
    payment_provider_error: "Платёжный сервис временно не ответил. Попробуйте позже.",
    payment_confirmation_missing: "Не удалось получить ссылку оплаты. Попробуйте позже.",
    payment_not_found: "Платёж не найден. Сначала нажмите «Оплатить Plus».",
    payment_verification_failed: "Платёж не прошёл серверную проверку. Напишите в поддержку.",
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
          <li>тексты жалоб и вопросов, которые пользователь вводит для разбора состояния или питания;</li>
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
        <p>TemichevVet предоставляет информационный сервис для владельцев собак и кошек: карточки питомцев, историю, напоминания, проверку жалоб, проверку питания, подписку и синхронизацию входов.</p>
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
          <li>до 10 разборов по здоровью питомца в месяц;</li>
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
        <p>На текущем этапе сторонняя рекламная аналитика не используется. Если она будет подключена, сервис должен обновить этот раздел и запрашивать согласие на необязательные cookie.</p>
      </section>
      <section>
        <h3>Как отказаться</h3>
        <p>Необходимые cookie/localStorage нужны для входа и безопасности. Их можно удалить в настройках браузера, но после этого потребуется войти снова.</p>
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

function showCookieBannerIfNeeded() {
  if (!cookieBanner) return;
  if (!localStorage.getItem("tvv_cookie_consent")) {
    cookieBanner.hidden = false;
  }
}

function setCookieConsent(value) {
  localStorage.setItem("tvv_cookie_consent", JSON.stringify({
    value,
    accepted_at: new Date().toISOString(),
    version: "20260605-legal-support-1"
  }));
  cookieBanner.hidden = true;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function petTitle(pet) {
  const main = pet.is_main ? "⭐ " : "";
  return `${main}${pet.pet_type || "питомец"} — ${pet.pet_name || "без имени"}`;
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

async function bootstrap() {
  const shouldCheckPayment = new URLSearchParams(window.location.search).get("payment") === "plus";
  if (!state.token) {
    setAuthMode(false);
    if (state.telegramLoginState) {
      openAuthDialog();
      renderTelegramWaiting(state.telegramLoginUrl, state.telegramLoginState);
      pollTelegramLogin(state.telegramLoginState);
    }
    if (state.maxLoginState) {
      clearMaxLogin();
    }
    return;
  }
  try {
    const data = await api("/api/me");
    state.user = data.user;
    state.externalAccounts = data.external_accounts || [];
    state.subscription = data.subscription || null;
    setAuthMode(true);
    if (shouldCheckPayment) {
      renderSubscription(`<div class="notice">Вернулись с оплаты. Проверяю статус платежа...</div>`);
      await checkPlusPaymentStatus({ replaceHistory: true });
      return;
    }
    await renderHome();
  } catch {
    localStorage.removeItem("tvv_token");
    state.token = "";
    state.user = null;
    state.externalAccounts = [];
    state.subscription = null;
    setAuthMode(false);
    if (state.telegramLoginState) {
      openAuthDialog();
      renderTelegramWaiting(state.telegramLoginUrl, state.telegramLoginState);
      pollTelegramLogin(state.telegramLoginState);
    }
    if (state.maxLoginState) {
      clearMaxLogin();
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
  state.user = data.user;
  state.externalAccounts = data.external_accounts || [];
  state.subscription = data.subscription || null;
  return data;
}

function petOptions(selectedId = "") {
  if (!state.pets.length) return `<option value="">Сначала добавьте питомца</option>`;
  return state.pets
    .map((pet) => `<option value="${pet.id}" ${String(pet.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(petTitle(pet))}</option>`)
    .join("");
}

function renderPetBadges(pet) {
  const parts = [];
  if (pet.age_text) parts.push(`Возраст: ${pet.age_text}`);
  if (pet.weight_kg) parts.push(`Вес: ${pet.weight_kg} кг`);
  if (pet.breed) parts.push(`Порода: ${pet.breed}`);
  if (pet.sex) parts.push(`Пол: ${pet.sex}`);
  return parts.length ? `<div class="meta-row">${parts.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : "";
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
            <button class="primary-button compact" data-followup-answer="retry" data-followup-id="${item.id}" type="button">Новый разбор</button>
          </div>
        </article>
      `;
    })
    .join("");
  return `<section class="profile-card due-followups"><h3>Нужно проверить динамику</h3><div class="list-stack">${cards}</div></section>`;
}

async function renderHome() {
  await refreshPets();
  const dueFollowups = await loadDueFollowups();
  const petCount = state.pets.length;
  const mainPet = state.pets.find((pet) => pet.is_main) || state.pets[0];
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Личный кабинет владельца</h2>
        <p>Здесь собраны питомцы, история здоровья, наблюдения, вес, напоминания и быстрые проверки питания. Данные привязаны к вашему входу.</p>
      </div>
      <button class="secondary-button compact" data-action="pets" type="button">🐾 Мои питомцы</button>
    </div>
    <div class="visual-strip">
      <img src="/static/assets/logo_temichevvet.jpg" alt="" class="visual-logo" />
      <div>
        <h3>Что можно делать сейчас</h3>
        <p>Карточки питомцев, история здоровья и напоминания доступны с телефона и ноутбука по одной ссылке.</p>
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
        <strong>Email / Telegram / MAX</strong>
        <span>доступ к кабинету</span>
      </div>
    </div>
    <div class="next-actions">
      <button class="primary-button" data-action="triage" type="button">🩺 Разобрать жалобу</button>
      <button class="secondary-button" data-action="reminders" type="button">⏰ Напоминания</button>
      <button class="secondary-button" data-action="food" type="button">🍽️ Питание</button>
      <button class="secondary-button" data-action="care" type="button">🧴 Уход и привычки</button>
      <button class="secondary-button" data-action="faq" type="button">❓ Вопросы и ответы</button>
      <button class="secondary-button" data-action="account" type="button">🔐 Способы входа</button>
    </div>
    ${renderDueFollowups(dueFollowups)}
  `, { scroll: false });
}

function isProviderConnected(provider) {
  return state.externalAccounts.some((account) => account.provider === provider);
}

async function renderAccountLinks() {
  await refreshAccountState();
  const email = state.user?.email || "";
  const telegramConnected = isProviderConnected("telegram");
  const maxConnected = isProviderConnected("max");
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Способы входа</h2>
        <p>Подключите мессенджеры к текущему кабинету, чтобы не создавать второй аккаунт и не разделять питомцев, историю и подписку.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">На главную</button>
    </div>
    <div class="profile-card">
      <h3>Email</h3>
      <p>${email ? `Подключён: ${escapeHtml(email)}` : "Email пока не подключён. Вход по email можно использовать отдельно через окно входа."}</p>
    </div>
    <div class="summary-grid">
      <div class="summary-card">
        <strong>Telegram</strong>
        <span>${telegramConnected ? "подключён" : "можно подключить"}</span>
        <button class="secondary-button compact" data-link-provider="telegram" type="button" ${telegramConnected ? "disabled" : ""}>
          ${telegramConnected ? "Подключён" : "Подключить Telegram"}
        </button>
      </div>
      <div class="summary-card">
        <strong>MAX</strong>
        <span>${maxConnected ? "подключён" : "можно подключить"}</span>
        <button class="secondary-button compact" data-link-provider="max" type="button" ${maxConnected ? "disabled" : ""}>
          ${maxConnected ? "Подключён" : "Подключить MAX"}
        </button>
      </div>
    </div>
    <div class="care-note">
      Мессенджер нужен только для подтверждения личности. После подтверждения вернитесь сюда: сайт сам завершит привязку.
    </div>
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
            <article class="item-card">
              <div>
                <h3>${escapeHtml(petTitle(pet))}</h3>
                ${renderPetBadges(pet)}
              </div>
              <button class="secondary-button compact" data-open-pet="${pet.id}" type="button">Открыть</button>
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
      <label><span>Кличка</span><input name="pet_name" required placeholder="Лео" /></label>
      <label><span>Порода</span><input name="breed" placeholder="Бенгальская" /></label>
      <label><span>Пол</span><select name="sex"><option value="">Не указан</option><option value="м">М</option><option value="ж">Ж</option></select></label>
      <label><span>Год рождения</span><input name="birth_year" inputmode="numeric" placeholder="2019" /></label>
      <label><span>Месяц</span><input name="birth_month" inputmode="numeric" placeholder="6" /></label>
      <label><span>День</span><input name="birth_day" inputmode="numeric" placeholder="15" /></label>
      <label><span>Вес, кг</span><input name="weight_kg" inputmode="decimal" placeholder="6.1" /></label>
      <label class="checkbox-row"><input name="is_main" type="checkbox" /> <span>Сделать основным</span></label>
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
    .map((item) => `<li><strong>${escapeHtml(item.title)}</strong><span>${formatDateTime(item.created_at)}</span></li>`)
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
      <button class="secondary-button" data-pet-view="triage" data-pet-id="${pet.id}" type="button">🩺 Разобрать жалобу</button>
      <button class="secondary-button" data-pet-view="edit" data-pet-id="${pet.id}" type="button">✏️ Изменить</button>
      <button class="secondary-button" data-set-main="${pet.id}" type="button">${pet.is_main ? "⭐ Основной" : "⭐ Сделать основным"}</button>
      <button class="secondary-button danger-text" data-delete-pet="${pet.id}" type="button">🗑 Удалить</button>
    </div>
    <section>
      <h3>Последние события</h3>
      ${history ? `<ul class="event-list">${history}</ul>` : "<p>История пока пустая.</p>"}
    </section>
  `);
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
      <label><span>Пол</span><select name="sex"><option value="">Не указан</option><option value="м" ${pet.sex === "м" ? "selected" : ""}>М</option><option value="ж" ${pet.sex === "ж" ? "selected" : ""}>Ж</option></select></label>
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
    ? data.items.map((item) => `<article class="item-card"><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.details || "")}</p><small>${formatDateTime(item.created_at)}</small></div></article>`).join("")
    : "<p>История пока пустая.</p>";
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
    : "<p>Наблюдений пока нет.</p>";
  setWorkspace(`
    <div class="workspace-head">
      <h2>Наблюдения</h2>
      <button class="secondary-button compact" data-open-pet="${petId}" type="button">⬅️ В карточку</button>
    </div>
    <form class="inline-form" id="observationForm">
      <input name="text" placeholder="Например: аппетит нормальный, активность ниже обычного" required />
      <button class="primary-button compact" type="submit">Добавить</button>
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
    : "<p>Истории веса пока нет.</p>";
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
    : "<p>Напоминаний пока нет.</p>";

  setWorkspace(`
    <div class="workspace-head">
      <h2>${title}</h2>
      <button class="secondary-button compact" ${petId ? `data-open-pet="${petId}"` : `data-action="home"`} type="button">⬅️ Назад</button>
    </div>
    <form class="form-grid" id="reminderForm">
      <h3>Добавить напоминание</h3>
      <label><span>Питомец</span><select name="pet_id"><option value="">Без питомца</option>${petOptions(petId || "")}</select></label>
      <label><span>Шаблон</span><select name="reminder_type">${reminderTypes.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label><span>Заголовок</span><input name="title" required placeholder="Обработка от паразитов" /></label>
      <label><span>Дата</span><input name="due_date" type="date" required /></label>
      <label><span>Время</span><input name="due_time" type="time" /></label>
      <label><span>Повтор</span><select name="periodicity">${periodicityOptions.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
      <label class="full-row"><span>Заметка</span><input name="notes" placeholder="Например: купить препарат заранее" /></label>
      <button class="primary-button" type="submit">Сохранить напоминание</button>
    </form>
    <div class="list-stack">${items}</div>
  `);

  document.querySelector("#reminderForm").addEventListener("submit", async (event) => {
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
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Разобрать жалобу</h2>
        <p>Выберите питомца и опишите, что происходит. Если в тексте есть красные симптомы, веб-версия сразу покажет срочное предупреждение.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <div class="visual-strip compact-visual">
      <img src="/static/assets/triage_banner.jpg" alt="" />
      <div>
        <h3>Проверьте срочность</h3>
        <p>Сначала срабатывают красные симптомы. Это помогает не ждать онлайн-ответ там, где нужна клиника.</p>
      </div>
    </div>
    <form class="form-grid one-column" id="triageForm">
      <label><span>Питомец</span><select name="pet_id"><option value="">Без привязки</option>${petOptions(prefillPetId || state.currentPetId || "")}</select></label>
      <label><span>Что происходит</span><textarea name="text" placeholder="Например: кошка второй день плохо ест, стала вялая..." required></textarea></label>
      <button class="primary-button" type="submit">Проверить состояние</button>
    </form>
    <div id="triageResult"></div>
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
        <div class="result-box ${data.urgency === "red" ? "danger" : ""}">
          <pre>${escapeHtml(data.answer)}</pre>
        </div>
        <div class="care-note">
          Если в ответе есть пункты, которые нужно уточнить, подготовьте их для врача.
          Можно также добавить эти данные в новый разбор — это будет отдельная проверка состояния и спишет ещё один запрос.
          ${data.followup ? "Контроль состояния будет показан в кабинете позже; если Telegram подключён, напоминание также уйдёт туда." : ""}
        </div>
        <div class="next-actions">
          ${petId ? `<button class="secondary-button" data-open-pet="${petId}" type="button">🐾 Открыть карточку</button>` : ""}
          <button class="secondary-button" data-action="reminders" type="button">➕ Добавить напоминание</button>
          <button class="primary-button" data-action="triage" type="button">🩺 Новый разбор</button>
        </div>
      `;
    } catch (error) {
      resultEl.innerHTML = `<div class="notice danger">Ошибка: ${escapeHtml(error.message)}</div>`;
    }
  });
}

async function renderFood() {
  setWorkspace(`
    <div class="workspace-head">
      <div>
        <h2>Питание</h2>
        <p>Проверьте отдельный продукт или готовое блюдо. Если это блюдо, добавьте состав через запятую.</p>
      </div>
      <button class="secondary-button compact" data-action="home" type="button">⬅️ В меню</button>
    </div>
    <form class="form-grid one-column" id="foodForm">
      <label><span>Продукт или блюдо</span><input name="query" placeholder="борщ, котлета, виноград, куриная грудка" required /></label>
      <label><span>Состав блюда, если известен</span><input name="ingredients" placeholder="мясо, рис, лук, соль" /></label>
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
    intro: "Частые вопросы по здоровью, профилактике, тревожным признакам, подготовке к врачу и уходу.",
    label: "Вопрос или тема",
    placeholder: "вакцинация котёнка, понос у собаки, что сказать врачу",
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
      Это справочный раздел. Он не списывает запросы по здоровью и не заменяет разбор жалобы или очный осмотр ветеринарного врача.
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
    <div class="pricing-grid subscription-pricing" aria-label="Тарифы TemichevVet">
      <article class="pricing-card">
        <div>
          <strong>Free</strong>
          <span>Бесплатный старт</span>
        </div>
        <p>Базовый личный кабинет для первых проверок и ведения питомца.</p>
        <ul>
          <li>до 5 разборов по здоровью в первый месяц;</li>
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
          <li>до 10 разборов по здоровью в месяц;</li>
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
    <div class="profile-card">
      <h3>Ваш текущий доступ</h3>
      <p><strong>Тариф:</strong> ${escapeHtml(plan)}</p>
      <p><strong>Использовано разборов:</strong> ${quotaUsed} / ${quotaTotal}. Осталось: ${quotaLeft}.</p>
      <p><strong>Источник подписки:</strong> ${escapeHtml(sourceLabel)}.</p>
      ${sub.plan && sub.plan !== "free" ? `<p><strong>Действует до:</strong> ${escapeHtml(periodEnd)}.</p>` : ""}
      <div class="notice">Если Plus оплачен в Telegram, войдите через Telegram или подключите Telegram в разделе «Способы входа» — кабинет подтянет тот же доступ.</div>
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
      <label><span>Тема</span><input name="category" placeholder="Ошибка, оплата, идея, вопрос по кабинету" /></label>
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
    setWorkspace(`<h2>История здоровья</h2><p>Сначала добавьте питомца.</p><button class="primary-button" data-action="pets" type="button">Добавить питомца</button>`);
    return;
  }
  await renderPetHistory(state.currentPetId || state.pets[0].id);
}

async function renderGlobalObservations() {
  await refreshPets();
  if (!state.pets.length) {
    setWorkspace(`<h2>Наблюдения</h2><p>Сначала добавьте питомца.</p><button class="primary-button" data-action="pets" type="button">Добавить питомца</button>`);
    return;
  }
  await renderPetObservations(state.currentPetId || state.pets[0].id);
}

emailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!privacyConsent?.checked) {
    emailHint.textContent = "Перед входом нужно принять соглашение и согласие на обработку персональных данных.";
    privacyConsent?.focus();
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

verifyCodeBtn.addEventListener("click", async () => {
  emailHint.textContent = "Проверяю код...";
  try {
    const data = await api("/api/auth/email/verify", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value, code: codeInput.value })
    });
    state.token = data.token;
    state.user = data.user;
    state.externalAccounts = [];
    localStorage.setItem("tvv_token", data.token);
    setAuthMode(true);
    emailHint.textContent = "";
    await renderHome();
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
      await renderHome();
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
      await renderHome();
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

logoutBtn.addEventListener("click", async () => {
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
  state.user = null;
  state.externalAccounts = [];
  state.subscription = null;
  setAuthMode(false);
});

window.addEventListener("focus", () => {
  if (!state.token && state.telegramLoginState) pollTelegramLogin(state.telegramLoginState);
  if (!state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !state.token && state.telegramLoginState) pollTelegramLogin(state.telegramLoginState);
  if (!document.hidden && !state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

document.addEventListener("click", async (event) => {
  const legalButton = event.target.closest("[data-open-legal]");
  if (legalButton) {
    event.preventDefault();
    openLegalModal(legalButton.dataset.openLegal);
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

  try {
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
      if (confirm("Удалить карточку питомца и связанную историю?")) {
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
    if (action === "export-account-data") await downloadAccountData();
    if (action === "revoke-sessions") await revokeAllSessions();
    if (action === "show-data-deletion") renderDataDeletionPanel();
    if (action === "feedback") renderFeedback();
    if (action === "history") await renderGlobalHistory();
    if (action === "observations") await renderGlobalObservations();
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
