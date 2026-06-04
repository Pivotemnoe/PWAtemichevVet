const state = {
  token: localStorage.getItem("tvv_token") || "",
  maxLoginState: localStorage.getItem("tvv_max_login_state") || "",
  maxLoginUrl: localStorage.getItem("tvv_max_login_url") || "",
  deferredInstall: null,
  maxPollTimer: null,
  user: null,
  pets: [],
  currentPetId: null
};

const authView = document.querySelector("#authView");
const dashboardView = document.querySelector("#dashboardView");
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
  if (!state.token) {
    setAuthMode(false);
    if (state.maxLoginState) {
      clearMaxLogin();
    }
    return;
  }
  try {
    const data = await api("/api/me");
    state.user = data.user;
    setAuthMode(true);
    await renderHome();
  } catch {
    localStorage.removeItem("tvv_token");
    state.token = "";
    state.user = null;
    setAuthMode(false);
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

async function renderHome() {
  await refreshPets();
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
        <strong>MAX / Email</strong>
        <span>доступ к кабинету</span>
      </div>
    </div>
    <div class="next-actions">
      <button class="primary-button" data-action="triage" type="button">🩺 Разобрать жалобу</button>
      <button class="secondary-button" data-action="reminders" type="button">⏰ Напоминания</button>
      <button class="secondary-button" data-action="food" type="button">🍽️ Питание</button>
    </div>
  `, { scroll: false });
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
      resultEl.innerHTML = `
        <div class="result-box ${data.urgency === "red" ? "danger" : ""}">
          <pre>${escapeHtml(data.answer)}</pre>
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

function renderSubscription() {
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
      <h3>Оплата через сайт</h3>
      <p>Оплату Plus подключим отдельным защищённым потоком: создание платежа на сервере, проверка суммы, статуса оплаты и принадлежности платежа пользователю.</p>
      <div class="notice">До включения web-оплаты кабинет не выдаёт Plus сам. Это защита от обхода тарифов.</div>
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
  emailHint.textContent = "Отправляю код...";
  try {
    const data = await api("/api/auth/email/start", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value })
    });
    codeRow.hidden = false;
    emailHint.textContent = data.debug_code ? `Тестовый код: ${data.debug_code}` : data.message;
  } catch (error) {
    emailHint.textContent = `Ошибка: ${error.message}`;
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
    localStorage.setItem("tvv_token", data.token);
    setAuthMode(true);
    emailHint.textContent = "";
    await renderHome();
  } catch (error) {
    emailHint.textContent = `Ошибка: ${error.message}`;
  }
});

async function startMessenger(provider) {
  messengerHint.textContent = "Готовлю вход...";
  try {
    const data = await api(`/api/auth/${provider}/start`, { method: "POST", body: "{}" });
    messengerHint.textContent = data.message;
    if (data.enabled && data.url) {
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
  text.textContent = "Откройте MAX, запустите бота там, затем вернитесь сюда. PWA проверит вход автоматически.";
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

maxBtn.addEventListener("click", () => {
  messengerHint.textContent = "MAX-бот TemichevVet в разработке. Пока используйте вход по email или рабочий Telegram-бот.";
});

logoutBtn.addEventListener("click", () => {
  stopMaxPolling();
  clearMaxLogin();
  localStorage.removeItem("tvv_token");
  state.token = "";
  state.user = null;
  setAuthMode(false);
});

window.addEventListener("focus", () => {
  if (!state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !state.token && state.maxLoginState) pollMaxLogin(state.maxLoginState);
});

document.addEventListener("click", async (event) => {
  const actionButton = event.target.closest("[data-action]");
  const openPetButton = event.target.closest("[data-open-pet]");
  const petViewButton = event.target.closest("[data-pet-view]");
  const setMainButton = event.target.closest("[data-set-main]");
  const deletePetButton = event.target.closest("[data-delete-pet]");
  const deleteReminderButton = event.target.closest("[data-delete-reminder]");

  try {
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
    if (action === "reminders") await renderReminders();
    if (action === "subscription") renderSubscription();
    if (action === "feedback") renderFeedback();
    if (action === "history") await renderGlobalHistory();
    if (action === "observations") await renderGlobalObservations();
  } catch (error) {
    showError(`Ошибка: ${error.message}`);
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

bootstrap();
