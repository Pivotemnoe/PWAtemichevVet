import { CapacitorHttp, registerPlugin } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Clipboard } from '@capacitor/clipboard';
import { Network } from '@capacitor/network';
import { LocalNotifications } from '@capacitor/local-notifications';
import { Filesystem, Directory, Encoding } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import { syncIOSReminders } from './ios-reminders.js';

const NativeDocuments = registerPlugin('NativeDocuments');
const NativeReminders = registerPlugin('NativeReminders');
const API_BASE = __TVV_API_BASE__;
const DEBUG_API = __TVV_DEBUG_API__;
const allowedHosts = new Set(['temichevvet.ru', 't.me', 'max.ru', 'yoomoney.ru', 'yookassa.ru']);
const planKey = 'tvv_ios_reminder_plan';
let notificationSync = Promise.resolve();

window.TVVNative = {
  platform: 'ios',
  debugOrigin: DEBUG_API ? API_BASE : null,
  async fetch(path, options = {}) {
    if (!path.startsWith('/api/')) throw new Error('invalid_api_path');
    const method = (options.method || 'GET').toUpperCase();
    const analysis = method === 'POST'
      && ['/api/triage', '/api/check/preview', '/api/food/check'].includes(path.split('?')[0]);
    // Capacitor iOS uses connectTimeout as the entire URLRequest timeout,
    // taking precedence over readTimeout. AI responses need the full wait.
    const timeout = analysis ? 120000 : method === 'GET' ? 4000 : 15000;
    const result = await CapacitorHttp.request({
      url: API_BASE + path, method,
      // In Capacitor iOS 8.5.3 this also creates a dedicated URLSession, rather
      // than the shared session/pool used concurrently by analytics and login.
      // Our JSON API has fixed paths and must not redirect to another origin.
      disableRedirects: true,
      headers: { ...options.headers, 'X-TemichevVet-Client': 'ios' },
      data: options.body ? JSON.parse(options.body) : undefined,
      responseType: 'json', connectTimeout: timeout, readTimeout: timeout,
    });
    return new Response(JSON.stringify(result.data), { status: result.status,
      headers: { 'Content-Type': 'application/json' } });
  },
  async openExternal(value) {
    const url = new URL(value);
    if (['mailto:', 'tel:'].includes(url.protocol)) return NativeDocuments.openExternal({ url: url.href });
    const localTestUrl = DEBUG_API && url.origin === API_BASE;
    if (url.protocol !== 'https:' && !localTestUrl) throw new Error('invalid_external_url');
    if (!localTestUrl && ![...allowedHosts].some((host) => url.hostname === host || url.hostname.endsWith('.' + host))) {
      throw new Error('invalid_external_host');
    }
    await Browser.open({ url: url.href, toolbarColor: '#1476d4' });
  },
  copyText: (text) => Clipboard.write({ string: text }),
  print: () => NativeDocuments.print(),
  // iOS has no Android-style hardware back action or programmatic minimize API.
  minimize: async () => {},
  async shareFile(name, text) {
    const safeName = name.replace(/[^\w.-]/g, '_');
    const file = await Filesystem.writeFile({ path: safeName, data: text,
      directory: Directory.Cache, encoding: Encoding.UTF8 });
    await Share.share({ title: 'TemichevVet', files: [file.uri] });
  },
  async notificationsEnabled() {
    return localStorage.getItem('tvv_native_notifications_enabled') === '1'
      && (await LocalNotifications.checkPermissions()).display === 'granted';
  },
  async enableNotifications() {
    const granted = (await LocalNotifications.requestPermissions()).display === 'granted';
    if (granted) localStorage.setItem('tvv_native_notifications_enabled', '1');
    return granted;
  },
  reminderPlanInfo() {
    try { return JSON.parse(localStorage.getItem(planKey) || 'null'); }
    catch { return null; }
  },
  syncReminders(items) {
    notificationSync = notificationSync.catch(() => {}).then(async () => {
      if (!await this.notificationsEnabled()) return;
      try {
        const info = await syncIOSReminders(NativeReminders, items);
        localStorage.setItem(planKey, JSON.stringify(info));
      } catch (error) {
        const previous = this.reminderPlanInfo();
        localStorage.setItem(planKey, JSON.stringify({ ...previous, updateFailed: true }));
        throw error;
      }
    });
    return notificationSync;
  },
  clearReminders() {
    notificationSync = notificationSync.catch(() => {}).then(async () => {
      await NativeReminders.clear();
      localStorage.removeItem(planKey);
    });
    return notificationSync;
  },
};

const resume = () => window.dispatchEvent(new CustomEvent('tvv:resume'));
function handleAppUrl(value) {
  let url;
  try { url = new URL(value); } catch { return; }
  if (url.protocol !== 'temichevvet:' && !(DEBUG_API && url.protocol === 'temichevvet-qa:')) return;
  if (url.pathname && url.pathname !== '/') return;
  if (url.host === 'reminders') {
    localStorage.setItem('tvv_open_reminders', '1');
    resume();
  } else if (url.host === 'payment-return') {
    void Browser.close().catch(() => {});
    resume();
  }
}
await App.addListener('appStateChange', ({ isActive }) => { if (isActive) resume(); });
await App.addListener('appUrlOpen', ({ url }) => handleAppUrl(url));
const launch = await App.getLaunchUrl();
if (launch?.url) handleAppUrl(launch.url);
const notificationLaunch = await NativeReminders.consumeLaunch();
if (notificationLaunch.openReminders) localStorage.setItem('tvv_open_reminders', '1');
await Browser.addListener('browserFinished', resume);
await Network.addListener('networkStatusChange', ({ connected }) => {
  const banner = document.querySelector('#mobileConnection');
  if (banner) banner.hidden = connected;
});
await LocalNotifications.addListener('localNotificationActionPerformed', ({ notification }) => {
  if (!notification.extra?.tvvPetReminder) return;
  localStorage.setItem('tvv_open_reminders', '1');
  resume();
});
document.addEventListener('click', (event) => {
  const link = event.target.closest('a[href]');
  if (!link || link.hasAttribute('data-open-legal')) return;
  const url = new URL(link.href);
  const legalPage = url.origin === location.origin && ['/offer', '/privacy', '/terms', '/contacts'].includes(url.pathname);
  if (!legalPage && (url.origin === location.origin || !['https:', 'mailto:', 'tel:'].includes(url.protocol))) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  void window.TVVNative.openExternal(legalPage ? API_BASE + url.pathname : url.href).catch(() => {
    window.dispatchEvent(new CustomEvent('tvv:external-error'));
  });
}, true);
await import('../web/app.js');
