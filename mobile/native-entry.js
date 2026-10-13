import { CapacitorHttp, registerPlugin } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Clipboard } from '@capacitor/clipboard';
import { Network } from '@capacitor/network';
import { LocalNotifications } from '@capacitor/local-notifications';
import { Filesystem, Directory, Encoding } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
const NativeDocuments = registerPlugin('NativeDocuments');
const NativeReminders = registerPlugin('NativeReminders');
const API_BASE = __TVV_API_BASE__;
const DEBUG_API = __TVV_DEBUG_API__;
const allowedExternalHosts = new Set(['temichevvet.ru', 't.me', 'max.ru', 'yoomoney.ru', 'yookassa.ru']);
let notificationSync = Promise.resolve();
window.TVVNative = {
  debugOrigin: DEBUG_API ? API_BASE : null,
  async fetch(path, options = {}) {
    if (!path.startsWith('/api/')) throw new Error('invalid_api_path');
    const result = await CapacitorHttp.request({
      url: API_BASE + path, method: options.method || 'GET',
      headers: { ...options.headers, 'X-TemichevVet-Client': 'android' },
      data: options.body ? JSON.parse(options.body) : undefined,
      responseType: 'json', connectTimeout: (options.method || 'GET') === 'GET' ? 4000 : 15000, readTimeout: 120000
    });
    return new Response(JSON.stringify(result.data), { status: result.status,
      headers: { 'Content-Type': 'application/json' } });
  },
  async openExternal(value) {
    const url = new URL(value);
    const localTestUrl = DEBUG_API && url.origin === API_BASE;
    if (!['https:', 'mailto:', 'tel:'].includes(url.protocol) && !localTestUrl) throw new Error('invalid_external_url');
    if (url.protocol === 'https:' && !localTestUrl && ![...allowedExternalHosts].some((host) => url.hostname === host || url.hostname.endsWith('.' + host))) {
      throw new Error('invalid_external_host');
    }
    await Browser.open({ url: url.href, toolbarColor: '#1476d4' });
  },
  copyText: (text) => Clipboard.write({ string: text }),
  print: () => NativeDocuments.print(),
  minimize: () => App.minimizeApp(),
  async shareFile(name, text) {
    const safeName = name.replace(/[^\w.-]/g, '_');
    const file = await Filesystem.writeFile({ path: safeName, data: text, directory: Directory.Cache, encoding: Encoding.UTF8 });
    await Share.share({ title: 'TemichevVet', files: [file.uri] });
  },
  async notificationsEnabled() { return localStorage.getItem('tvv_native_notifications_enabled') === '1' && (await LocalNotifications.checkPermissions()).display === 'granted'; },
  async enableNotifications() {
    const granted = (await LocalNotifications.requestPermissions()).display === 'granted';
    if (granted) localStorage.setItem('tvv_native_notifications_enabled', '1');
    return granted;
  },
  syncReminders(items) {
    notificationSync = notificationSync.catch(() => {}).then(async () => {
      if (!await this.notificationsEnabled()) return;
      const pending = await LocalNotifications.getPending();
      if (pending.notifications.length) await LocalNotifications.cancel({ notifications: pending.notifications });
      await NativeReminders.sync({ items });
    });
    return notificationSync;
  },
  async clearReminders() {
    await notificationSync.catch(() => {});
    const pending = await LocalNotifications.getPending();
    if (pending.notifications.length) await LocalNotifications.cancel({ notifications: pending.notifications });
    await NativeReminders.clear();
  }
};

const resume = () => window.dispatchEvent(new CustomEvent('tvv:resume'));
await App.addListener('appStateChange', ({ isActive }) => { if (isActive) resume(); });
await App.addListener('backButton', () => window.dispatchEvent(new CustomEvent('tvv:back')));
function handleAppUrl(url) {
  if (url === 'temichevvet://reminders') {
    localStorage.setItem('tvv_open_reminders', '1');
    resume();
    return;
  }
  if (url !== 'temichevvet://payment-return') return;
  void Browser.close().catch(() => {});
  resume();
}
await App.addListener('appUrlOpen', ({ url }) => handleAppUrl(url));
const launch = await App.getLaunchUrl();
if (launch?.url) handleAppUrl(launch.url);
await Browser.addListener('browserFinished', resume);
await Network.addListener('networkStatusChange', ({ connected }) => {
  const banner = document.querySelector('#mobileConnection');
  if (banner) banner.hidden = connected;
});
await LocalNotifications.addListener('localNotificationActionPerformed', () => {
  document.dispatchEvent(new CustomEvent('tvv:navigate', { detail: 'reminders' }));
});
document.addEventListener('click', (event) => {
  const link = event.target.closest('a[href]');
  if (!link || link.hasAttribute('data-open-legal')) return;
  const url = new URL(link.href);
  if (url.origin === location.origin && url.pathname === '/offer') {
    event.preventDefault(); event.stopImmediatePropagation();
    void window.TVVNative.openExternal(API_BASE + '/offer').catch(() => {
      window.dispatchEvent(new CustomEvent('tvv:external-error'));
    });
    return;
  }
  if (url.origin === location.origin || !['https:', 'mailto:', 'tel:'].includes(url.protocol)) return;
  event.preventDefault(); event.stopImmediatePropagation();
  void window.TVVNative.openExternal(url.href).catch(() => {
    window.dispatchEvent(new CustomEvent('tvv:external-error'));
  });
}, true);
await import('../web/app.js');
