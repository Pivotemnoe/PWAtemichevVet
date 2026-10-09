let pendingToken = "";
let device = "";
try {
  const u = new URL(window.location.href);
  const token = u.searchParams.get("retention") || "";
  if (/^\d+\.[a-f0-9]{64}$/.test(token)) {
    sessionStorage.setItem("tvv_retention_link", token);
    u.searchParams.delete("retention");
    window.history.replaceState(null, "", u.pathname + u.search + u.hash);
  }
  pendingToken = sessionStorage.getItem("tvv_retention_link") || "";
  device = localStorage.getItem("tvv_retention_device") || crypto.randomUUID();
  localStorage.setItem("tvv_retention_device", device);
} catch {}

export async function retentionActivity(api, { token = false, kind = "" } = {}) {
  if (document.visibilityState === "hidden") return null;
  try {
    const data = await api("/api/retention/activity", {
      method: "POST",
      body: JSON.stringify({
        token: token ? pendingToken : "",
        installed: Boolean(window.matchMedia?.("(display-mode: standalone)")?.matches || navigator.standalone),
        device: device || "unknown", kind
      })
    });
    if (token && data.target) {
      pendingToken = "";
      try { sessionStorage.removeItem("tvv_retention_link"); } catch {}
    }
    return data.target || null;
  } catch { return null; }
}

export async function currentDevicePush(status) {
  try {
    const registration = await navigator.serviceWorker.getRegistration("/");
    const sub = await registration?.pushManager?.getSubscription();
    if (!sub || !crypto.subtle) return false;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sub.endpoint));
    const hash = [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
    return (status.items || []).some((x) => x.endpoint_hash === hash);
  } catch { return false; }
}

export async function notificationSettings(api, setWorkspace, escapeHtml) {
  const p = await api("/api/retention/preferences");
  setWorkspace(`
    <div class="workspace-head"><div><h2>Сообщения и напоминания</h2>
    <p>Выберите, куда удобнее получать сообщения TemichevVet.</p></div>
    <button class="secondary-button compact" data-action="account">Назад</button></div>
    <section class="profile-card">
    <form id="retentionPreferencesForm" class="form-grid">
      <label>Канал<select name="channel">${p.channels.map((c) =>
        `<option value="${c}" ${p.channel === c ? "selected" : ""}>${c === "max" ? "MAX" : "Почта"}</option>`).join("")}</select></label>
      <label class="checkbox-row"><input type="checkbox" name="service_enabled" ${p.service_enabled ? "checked" : ""}>
        Напоминания о сохранённых датах и вопросы после оценки состояния</label>
      <label class="checkbox-row"><input type="checkbox" name="weekly_enabled" ${p.weekly_enabled ? "checked" : ""}>
        Полезные предложения — не чаще раза в неделю</label>
      <p class="hint">Недельная серия пока готовится. Этот выбор сохранится для её запуска.</p>
      <label>Часовой пояс<input name="timezone" value="${escapeHtml(p.timezone)}" required></label>
      <button class="primary-button" type="submit" ${p.channels.length ? "" : "disabled"}>Сохранить</button>
      <p id="retentionPreferencesHint" class="hint" role="status"></p>
    </form>
    ${p.channels.length ? "" : '<p>Подключите почту или MAX в профиле, чтобы получать сообщения.</p>'}
    </section>`);
  const form = document.querySelector("#retentionPreferencesForm");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const hint = document.querySelector("#retentionPreferencesHint");
    try {
      await api("/api/retention/preferences", { method: "POST", body: JSON.stringify({
        channel: form.elements.channel.value,
        service_enabled: form.elements.service_enabled.checked,
        weekly_enabled: form.elements.weekly_enabled.checked,
        timezone: form.elements.timezone.value.trim()
      }) });
      hint.textContent = "Настройки сохранены.";
    } catch { hint.textContent = "Не удалось сохранить. Проверьте канал и часовой пояс."; }
  });
}

const scenarioNames = {
  billing_renewal: "Перед продлением Plus", billing_success: "Оплата Plus",
  billing_failed: "Неудачная оплата Plus", billing_canceled: "Отмена автопродления",
  first_pet: "Первый питомец", first_record: "Первая запись",
  history: "История здоровья", followup: "Самочувствие после оценки",
  date: "Важная дата", install: "Установка приложения"
};
const statusNames = {
  queued: "Ожидает отправки", sending: "Отправляется",
  accepted: "Принято почтой / MAX", failed: "Ошибка",
  unknown: "Результат неизвестен", skipped: "Нет доступного канала", cancelled: "Отменено"
};
const reasonNames = {
  subscription_changed: "Условия подписки изменились — напоминание отменено",
  channel_unavailable: "Канал недоступен", disabled: "Сообщения отключены",
  account_merged: "Аккаунты объединены — повтор отменён",
  weekly_disabled: "Недельные предложения отключены", expired: "Срок сообщения истёк",
  followup_completed: "Вопрос уже закрыт или уведомление отправлено",
  followup_expired: "Оценка состояния устарела", date_changed: "Дата изменена или закрыта",
  user_returned: "Пользователь уже вернулся", first_record_saved: "Запись уже сохранена",
  pet_added: "Питомец уже добавлен", pwa_already_launched: "Приложение уже открывали",
  weekly_limit: "Действует недельный интервал", worker_interrupted: "Отправка прервана — повтор отключён",
  http_400: "MAX отклонил запрос", http_401: "MAX: ошибка доступа",
  http_403: "MAX: диалог недоступен", http_404: "MAX: диалог не найден",
  http_429: "MAX: ограничение частоты", SMTPRecipientsRefused: "Почта отклонила адрес",
  SMTPAuthenticationError: "Ошибка доступа к почте"
};

export function retentionAdmin(data, h) {
  const r = data.retention || {};
  const w = r.windows?.["30"] || {};
  const s = r.windows?.["7"] || {};
  const cols = [
    { key: "label", label: "Группа" }, { key: "eligible_users", label: "Пользователи" },
    { key: "queued", label: "В очереди" }, { key: "accepted", label: "Принято каналом" },
    { key: "failed", label: "Ошибки" }, { key: "unknown", label: "Неизвестно" },
    { key: "returned_users", label: "Вернулись по кнопке" },
    { key: "action_users", label: "Полезное действие" }, { key: "paid_users", label: "Оплатили" }
  ];
  const cuts = (rows, channel = false) => (rows || []).map((x) => ({
    ...x, label: channel ? (x.name === "email" ? "Почта" : x.name === "max" ? "MAX" : "Нет канала")
      : (scenarioNames[x.name] || x.name)
  }));
  return `
    ${h.head("Сообщения и возвраты", "Одна первая отправка. Общие предложения — не чаще одного в неделю.")}
    <p>Доставка: ${r.enabled ? "включена" : "выключена"}. Недельная серия: ${r.series_enabled ? "включена" : "подготовлена, ещё не запущена"}.</p>
    ${h.table("Регистрация и первый шаг · одни и те же аккаунты", r.registration || [], [
      { key: "period", label: "Созданы за" }, { key: "registered", label: "Регистрации" },
      { key: "first_login", label: "Первый вход" }, { key: "first_record", label: "Первая полезная запись" },
      { key: "without_pet", label: "Пока без питомца" }, { key: "paid", label: "Оплатили" }
    ])}
    <div class="summary-grid admin-summary">
      ${h.metric("Подобрано пользователей · 30 дней", w.eligible_users || 0)}
      ${h.metric("Сообщений в очереди", w.queued || 0)}
      ${h.metric("Принято почтой / MAX", w.accepted || 0, `${w.accepted_users || 0} пользователей`)}
      ${h.metric("Вернулись по кнопке", w.returned_users || 0, w.return_percent == null ? "Процент появится после отправок" : `${w.return_percent}% получателей`)}
      ${h.metric("Сохранили запись", w.record_users || 0)}
      ${h.metric("Ответили о самочувствии", w.answer_users || 0)}
      ${h.metric("Открыли Plus", w.plus_users || 0)}
      ${h.metric("Оплатили после перехода", w.paid_users || 0)}
      ${h.metric("Ошибки отправки", w.failed || 0)}
      ${h.metric("Результат неизвестен", w.unknown || 0)}
      ${h.metric("Отменено / нет канала", (w.cancelled || 0) + (w.skipped || 0))}
      ${h.metric("Отключили сообщения", w.unsubscribed_users || 0)}
    </div>
    <p class="hint">«Принято каналом» — ответ сервера почты или MAX, без подтверждения прочтения.
    «Вернулись по кнопке» — открыли сервис и вошли в свой аккаунт по ссылке сообщения.
    Действия связаны с последним таким переходом в течение 7 дней после отправки; это связь событий, а не доказательство причинного эффекта.</p>
    ${h.table("По каналам · отправки за 30 дней", cuts(w.by_channel, true), cols)}
    ${h.table("По сценариям · отправки за 30 дней", cuts(w.by_scenario), cols)}
    ${h.table("Последние 7 дней", [
      { name: "Принято каналом", value: s.accepted || 0 },
      { name: "Вернулись по кнопке", value: s.returned_users || 0 },
      { name: "Сохранили запись", value: s.record_users || 0 },
      { name: "Ответили о самочувствии", value: s.answer_users || 0 },
      { name: "Оплатили", value: s.paid_users || 0 }
    ], [{ key: "name", label: "Показатель" }, { key: "value", label: "Количество" }])}
    ${h.head("Приложение на телефоне", "Показ инструкции, выбор установки и запуск PWA считаются отдельно.")}
    <div class="summary-grid admin-summary">
      ${h.metric("Увидели предложение", w.install_shown_users || 0)}
      ${h.metric("Открыли инструкцию", w.install_instruction_users || 0)}
      ${h.metric("Приняли установку в браузере", w.install_accepted_users || 0)}
      ${h.metric("Открыли PWA", w.all_pwa_users || 0)}
      ${h.metric("Подключили push", w.all_push_users || 0)}
      ${h.metric("Открыли PWA после сообщения", w.pwa_users || 0)}
    </div>
    <p class="hint">Ручная установка на iPhone подтверждается последующим запуском PWA.
    Установка не означает разрешение уведомлений. Показатели выше — пользователи за 30 дней.</p>
    ${h.table("Возврат после регистрации", r.cohorts || [], [
      { key: "day", label: "Период" }, { key: "eligible", label: "Измеряемая когорта" },
      { key: "returned", label: "Вернулись" }, { key: "percent", label: "%" }
    ])}
    <p class="hint">D1/D7/D30 — новый сеанс в соответствующие сутки после регистрации.
    В знаменатель входят только аккаунты с измеренным первым сеансом и полностью прошедшим окном.
    Новое измерение началось с этой версии; исторические пропуски не считаются нулевыми возвратами.</p>
    ${h.table("Причины отмен и ошибок", (r.reasons || []).map((x) => ({
      ...x, status: statusNames[x.status] || x.status, reason: reasonNames[x.reason] || x.reason
    })), [{ key: "status", label: "Статус" }, { key: "reason", label: "Причина" }, { key: "count", label: "Сообщения" }])}
    ${h.table("Последние сообщения", (r.recent || []).map((x) => ({
      ...x, scenario: scenarioNames[x.scenario] || x.scenario,
      channel: x.channel === "email" ? "Почта" : x.channel === "max" ? "MAX" : "—",
      status: statusNames[x.status] || x.status, reason: reasonNames[x.reason] || x.reason || "—"
    })), [
      { key: "id", label: "ID" }, { key: "user_id", label: "Пользователь" },
      { key: "scenario", label: "Сценарий" }, { key: "channel", label: "Канал" },
      { key: "status", label: "Статус" }, { key: "reason", label: "Причина" },
      { key: "due_at", label: "Отправить", render: (x) => h.date(x.due_at) },
      { key: "sent_at", label: "Отправлено", render: (x) => h.date(x.sent_at) }
    ])}
  `;
}
