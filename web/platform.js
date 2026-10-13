// Browser/PWA defaults; the Android entrypoint supplies the native implementation.
export const native = Boolean(window.TVVNative);
export const appMode = native || Boolean(navigator.standalone)
  || Boolean(window.matchMedia?.('(display-mode: standalone)').matches)
  || location.pathname === '/mobile' || new URLSearchParams(location.search).get('mobile') === '1';

export function appFetch(path, options = {}) {
  return native ? window.TVVNative.fetch(path, options) : fetch(path, options);
}

export function openExternal(url) {
  const target = new URL(url, 'https://temichevvet.ru');
  const localPreview = !native && ['localhost', '127.0.0.1', '10.0.2.2'].includes(location.hostname)
    && target.origin === location.origin;
  if (!['https:', 'mailto:', 'tel:'].includes(target.protocol)
    && !localPreview && !(native && target.origin === window.TVVNative.debugOrigin)) throw new Error('invalid_external_url');
  if (native) return window.TVVNative.openExternal(target.href);
  location.href = target.href;
}

export async function confirmPayment() {
  const dialog = document.querySelector('#paymentRedirectDialog');
  if (!dialog) throw new Error('payment_dialog_missing');
  return new Promise((resolve) => {
    const finish = (confirmed) => { dialog.close(); resolve(confirmed); };
    dialog.querySelector('[data-payment-continue]').onclick = () => finish(true);
    dialog.querySelector('[data-payment-cancel]').onclick = () => finish(false);
    dialog.oncancel = (event) => { event.preventDefault(); finish(false); };
    dialog.showModal();
  });
}

export function markPaymentPending() {
  localStorage.setItem('tvv_payment_return_pending', '1');
}

export function clearPaymentPending() {
  localStorage.removeItem('tvv_payment_return_pending');
}

export function paymentPending() {
  return localStorage.getItem('tvv_payment_return_pending') === '1';
}
