import assert from 'node:assert/strict';
import { test } from 'node:test';

test('app mode has native request isolation and refuses unsafe external protocols', async () => {
  global.window = { TVVNative: { fetch: async (path) => ({ path }) } };
  Object.defineProperty(globalThis, 'navigator', { value: { standalone: false }, configurable: true });
  global.location = { pathname: '/', search: '', href: 'https://localhost/' };
  const platform = await import('../web/platform.js');
  assert.equal(platform.appMode, true);
  assert.deepEqual(await platform.appFetch('/api/me'), { path: '/api/me' });
  assert.throws(() => platform.openExternal('javascript:alert(1)'), /invalid_external_url/);
  assert.throws(() => platform.openExternal('http://untrusted.example'), /invalid_external_url/);
});

test('local PWA fixture navigation is limited to the same loopback origin', async () => {
  global.window = {};
  global.location = { hostname: '127.0.0.1', origin: 'http://127.0.0.1:8096', pathname: '/mobile', search: '', href: 'http://127.0.0.1:8096/mobile' };
  const platform = await import('../web/platform.js?browser-fixture');
  platform.openExternal('http://127.0.0.1:8096/mobile/qa-checkout/test');
  assert.equal(global.location.href, 'http://127.0.0.1:8096/mobile/qa-checkout/test');
  assert.throws(() => platform.openExternal('http://other.example'), /invalid_external_url/);
  assert.throws(() => platform.openExternal('http://127.0.0.1:9000'), /invalid_external_url/);
});
