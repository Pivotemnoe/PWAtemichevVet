const state = {
  token: localStorage.getItem("tvv_token") || "",
  deferredInstall: null
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

function setAuthMode(isAuthed) {
  authView.hidden = isAuthed;
  dashboardView.hidden = !isAuthed;
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
    return;
  }
  try {
    await api("/api/me");
    setAuthMode(true);
  } catch {
    localStorage.removeItem("tvv_token");
    state.token = "";
    setAuthMode(false);
  }
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
    emailHint.textContent = data.debug_code
      ? `Тестовый код: ${data.debug_code}`
      : data.message;
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
    localStorage.setItem("tvv_token", data.token);
    setAuthMode(true);
    emailHint.textContent = "";
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
      window.location.href = data.url;
    }
  } catch (error) {
    messengerHint.textContent = `Ошибка: ${error.message}`;
  }
}

telegramBtn.addEventListener("click", () => startMessenger("telegram"));
maxBtn.addEventListener("click", () => startMessenger("max"));

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("tvv_token");
  state.token = "";
  setAuthMode(false);
});

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    const action = button.dataset.action;
    if (action === "triage") {
      workspace.innerHTML = `
        <h2>Разбор жалобы</h2>
        <p>Здесь будет сценарий проверки состояния питомца. Пока подключена техническая заготовка API.</p>
        <textarea id="triageText" placeholder="Опишите, что происходит с питомцем"></textarea>
        <button class="primary-button" id="triageSend" type="button">Отправить</button>
        <p class="hint" id="triageResult"></p>
      `;
      document.querySelector("#triageSend").addEventListener("click", async () => {
        const resultEl = document.querySelector("#triageResult");
        resultEl.textContent = "Отправляю...";
        try {
          const data = await api("/api/triage", {
            method: "POST",
            body: JSON.stringify({ text: document.querySelector("#triageText").value })
          });
          resultEl.textContent = data.answer;
        } catch (error) {
          resultEl.textContent = `Ошибка: ${error.message}`;
        }
      });
      return;
    }
    if (action === "pets") {
      const data = await api("/api/pets");
      workspace.innerHTML = `<h2>Мои питомцы</h2><p>${data.message}</p>`;
      return;
    }
    if (action === "food") {
      workspace.innerHTML = `
        <h2>Питание</h2>
        <p>Раздел будет подключён к базе продуктов TemichevVet. В PWA он станет отдельным быстрым инструментом.</p>
      `;
      return;
    }
    if (action === "subscription") {
      workspace.innerHTML = `
        <h2>Подписка</h2>
        <p>Здесь будет экран Free/Plus, YooKassa и история платежей.</p>
        <div class="notice">Сейчас оплата работает в Telegram-боте; веб-оплату подключим отдельным этапом.</div>
      `;
    }
  });
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
