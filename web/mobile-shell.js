import { petAvatar } from './pet-avatar.js?v=20261013-mobile-14';
import { appMode, native } from './platform.js?v=20261013-mobile-14';

export const APP_TABS = [
  ['home', 'Главная', 'house'], ['pets', 'Питомцы', 'paw-print'],
  ['triage', 'Здоровье', 'heart-pulse'], ['reminders', 'Даты', 'calendar-days'],
  ['more', 'Ещё', 'ellipsis']
];
const icon = (name) => `<span class="app-icon icon-${name}" aria-hidden="true"></span>`;
const titles = Object.fromEntries(APP_TABS.map(([action, label]) => [action, label]));
Object.assign(titles, { history: 'История', observations: 'Наблюдения', food: 'Питание',
  subscription: 'Plus', account: 'Профиль', notifications: 'Уведомления', care: 'Уход', faq: 'Вопросы',
  feedback: 'Обратная связь', install: 'Приложение' });

export function mobileDashboardMarkup() {
  return `<section id="dashboardView" class="dashboard-view mobile-dashboard" hidden>
    <div class="mobile-chrome"><header class="mobile-header">
      <button type="button" class="mobile-back" data-mobile-back aria-label="Назад" hidden>${icon('chevron-left')}</button>
      <img class="mobile-logo" src="/static/assets/app-icon-192.png" width="48" height="48" alt="" />
      <div><span class="mobile-brand">TemichevVet</span><h1 id="mobilePageTitle">Главная</h1></div>
      <button type="button" class="mobile-profile" data-action="account" aria-label="Профиль">${icon('user-round')}</button>
    </header>
    <div id="mobileConnection" class="mobile-connection" role="status" hidden>Нет интернета. Проверьте соединение.<button type="button" data-mobile-retry>Повторить</button></div></div>
    <div id="workspace" class="workspace mobile-workspace" aria-live="polite"></div>
    <nav class="mobile-tabbar" aria-label="Основное меню">
      ${APP_TABS.map(([action, title, name]) => `<button class="app-nav-item${action === 'home' ? ' is-active' : ''}" data-action="${action}" type="button"${action === 'home' ? ' aria-current="page"' : ''}>${icon(name)}<span>${title}</span></button>`).join('')}
    </nav>
  </section>`;
}

export function renderMobileWelcome(escape) {
  return `<section class="mobile-welcome">
    <figure class="mobile-companions-photo"><img src="/static/assets/mobile/companions-v1.webp" alt="Собака и кошка дома" width="1200" height="634" /></figure>
    <h2>Всё важное о питомце</h2><p>Карточка, история здоровья и важные даты — всегда под рукой.</p>
    <button class="primary-button" type="button" data-app-login>Войти или создать аккаунт</button>
    <p class="hint">Уже есть аккаунт? Войдите тем же способом — записи будут здесь.</p>
    <div class="mobile-quick-grid">
      <button type="button" data-action="pets">${icon('paw-print')}<strong>Мои питомцы</strong><span>Карточки и история</span></button>
      <button type="button" data-action="triage"><img src="/static/assets/mobile/health-v1.webp" alt="" /><strong>Самочувствие</strong><span>Сохранить изменения</span></button>
      <button type="button" data-action="food"><img src="/static/assets/mobile/food-v1.webp" alt="" /><strong>Питание</strong><span>Проверить продукт</span></button>
      <button type="button" data-action="reminders"><img src="/static/assets/mobile/dates-v1.webp" alt="" /><strong>Важные даты</strong><span>Прививки и обработки</span></button>
    </div>
    <p class="mobile-medical-note">Сервис не ставит диагноз и не назначает лечение.</p>
    <button class="text-button" type="button" data-open-legal="privacy">${escape('Политика конфиденциальности')}</button>
  </section>`;
}

export function renderMobileHome({ pet, details, followups, escape, date }) {
  const weight = details?.weights?.[0] || (pet?.weight_kg ? { weight_kg: pet.weight_kg } : null);
  const reminders = (details?.reminders || []).filter((r) => !r.is_done && !r.completed)
    .slice().sort((a, b) => String(a.due_date).localeCompare(String(b.due_date))).slice(0, 3);
  return `<section class="mobile-home">
    <figure class="mobile-companions-photo home-photo"><img src="/static/assets/mobile/companions-v1.webp" alt="" width="1200" height="634" /><figcaption><strong>Здоровье питомца</strong><span>В одной истории</span></figcaption></figure>
    <div class="mobile-section-heading"><h2>Мой питомец</h2><button class="text-button" data-action="pets" type="button">Все питомцы</button></div>
    ${pet ? `<button class="mobile-pet-card" type="button" data-open-pet="${Number(pet.id)}">
      <span class="mobile-pet-avatar">${petAvatar(pet)}</span><span><small>${escape(pet.pet_type || '')}</small><strong>${escape(pet.pet_name)}</strong><span>${weight ? `${escape(weight.weight_kg)} кг` : 'Открыть карточку'}</span></span>${icon('chevron-left')}
    </button>` : `<section class="mobile-add-pet"><div class="mobile-welcome-symbol">${icon('paw-print')}</div><h3>Добавьте питомца</h3><p>Начните его историю здоровья.</p><button class="primary-button" type="button" data-action="pets">Добавить питомца</button></section>`}
    <div class="mobile-section-heading"><h2>Быстрые действия</h2></div>
    <div class="mobile-quick-grid">
      ${[['triage', 'health', 'Самочувствие', 'Что изменилось'], ['food', 'food', 'Питание', 'Проверить продукт']].map(([action, image, label, hint]) => `<button type="button" class="illustrated-action" data-action="${action}"><img src="/static/assets/mobile/${image}-v1.webp" alt="" /><strong>${label}</strong><span>${hint}</span></button>`).join('')}
    </div>
    <div class="mobile-shortcuts"><button type="button" data-action="observations">${icon('clipboard-list')}<span>Наблюдение</span></button><button type="button" data-action="history">${icon('history')}<span>История</span></button></div>
    ${followups || ''}
    <div class="mobile-section-heading"><h2>Ближайшие даты</h2><button class="text-button" data-action="reminders" type="button">Все даты</button></div>
    <section class="mobile-dates">${reminders.length ? reminders.map((r) => `<button type="button" data-action="reminders"><span class="mobile-date-icon">${icon('calendar-days')}</span><span><strong>${escape(r.title)}</strong><small>${escape(date(r.due_date))}</small></span>${icon('chevron-left')}</button>`).join('') : `<img class="mobile-dates-art" src="/static/assets/mobile/dates-v1.webp" alt="" /><p>Добавьте прививку, обработку или свою задачу.</p><button class="text-button" data-action="reminders" type="button">Добавить дату</button>`}</section>
    ${mobileDoctorCard()}
  </section>`;
}

export function mobileDoctorCard() {
  return `<section class="mobile-doctor-card"><img src="/static/assets/doctor-konstantin-cat-table-retouched.jpg" alt="Константин Темичев" width="88" height="108" /><div><span>TemichevVet</span><strong>Константин Темичев</strong><p>Ветеринарный врач, кандидат ветеринарных наук</p></div></section>`;
}

export function mobileSectionArt(action) {
  const images = { triage: ['health', 'Здоровье питомца'], food: ['food', 'Питание'], reminders: ['dates', 'Важные даты'] };
  const item = images[action];
  return item ? `<div class="mobile-section-art"><div><span>TemichevVet</span><strong>${item[1]}</strong></div><img src="/static/assets/mobile/${item[0]}-v1.webp" alt="" /></div>` : '';
}

export function initMobileShell({ user, login, navigate, back, retry }) {
  if (!appMode) return;
  document.body.classList.add('is-mobile-app');
  if (native) document.body.classList.add('is-native-app');
  document.addEventListener('click', (event) => {
    const loginButton = event.target.closest('[data-app-login]');
    const backButton = event.target.closest('[data-mobile-back]');
    const retryButton = event.target.closest('[data-mobile-retry]');
    const action = event.target.closest('[data-action]');
    if (loginButton || (!user() && action)) {
      event.preventDefault(); event.stopImmediatePropagation();
      login(action?.dataset.action || 'home');
    } else if (backButton || retryButton) {
      event.preventDefault(); event.stopImmediatePropagation();
      void (backButton ? back() : retry());
    }
  }, true);
  document.addEventListener('tvv:navigate', (event) => navigate(event.detail));
}

export function updateMobileHeader(action, nested = false) {
  if (!appMode) return;
  const title = document.querySelector('#mobilePageTitle');
  if (title) title.textContent = titles[action] || 'Питомец';
  const back = document.querySelector('[data-mobile-back]');
  if (back) back.hidden = !nested && APP_TABS.some(([id]) => id === action);
  const banner = document.querySelector('#mobileConnection');
  if (banner) banner.hidden = navigator.onLine;
}
