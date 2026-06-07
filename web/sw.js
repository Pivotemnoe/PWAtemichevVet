const CACHE_NAME = "temichevvet-pwa-p0-security-1";
const APP_SHELL = [
  "/",
  "/static/styles.css?v=20260607-p0-security-1",
  "/static/app.js?v=20260607-p0-security-1",
  "/static/manifest.webmanifest",
  "/static/assets/icon.svg",
  "/static/assets/logo_temichevvet.jpg",
  "/static/assets/triage_banner.jpg",
  "/static/assets/subscription_banner.jpg",
  "/static/assets/onb_step1_add_pet.jpg"
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
