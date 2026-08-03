const CACHE_NAME = "temichevvet-pwa-20260803-check-progress-2";
const APP_SHELL = [
  "/",
  "/check",
  "/check/cat-not-eating",
  "/check/dog-vomiting",
  "/check/urination",
  "/check/poisoning",
  "/check/general",
  "/static/styles.css?v=20260803-check-progress-2",
  "/static/app.js?v=20260803-check-progress-2",
  "/static/manifest.webmanifest?v=20260627-ios-icon-1",
  "/static/assets/app-icon-192.png?v=20260627-ios-icon-1",
  "/static/assets/app-icon-512.png?v=20260627-ios-icon-1",
  "/static/assets/apple-touch-icon-20260627.png",
  "/static/assets/apple-touch-icon.png?v=20260627-ios-icon-1",
  "/apple-touch-icon.png?v=20260627-ios-icon-1",
  "/apple-touch-icon-precomposed.png?v=20260627-ios-icon-1",
  "/static/assets/logo_temichevvet.jpg",
  "/static/assets/hero_pets.jpg",
  "/static/assets/check-ad-general.png",
  "/static/assets/check-ad-cat.png",
  "/static/assets/check-ad-dog.png",
  "/static/assets/subscription_banner.jpg",
  "/static/assets/onb_step1_add_pet.jpg"
];

const PRIVATE_PATH_PREFIXES = [
  "/api/",
  "/admin",
  "/app",
  "/auth/",
  "/review-login"
];

function isPrivateRequest(url) {
  return PRIVATE_PATH_PREFIXES.some((prefix) => url.pathname === prefix || url.pathname.startsWith(prefix))
    || url.searchParams.has("payment")
    || url.searchParams.has("review")
    || url.searchParams.has("token");
}

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.allSettled(APP_SHELL.map((url) => cache.add(url)))
    )
  );
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
  if (isPrivateRequest(url)) {
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok && url.pathname === "/" && !url.search) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put("/", copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { title: "TemichevVet", body: event.data ? event.data.text() : "" };
  }
  const title = payload.title || "TemichevVet";
  const options = {
    body: payload.body || "Оцените состояние питомца в личном кабинете.",
    icon: "/static/assets/app-icon-192.png",
    badge: "/static/assets/app-icon-192.png",
    data: { url: payload.url || "/app" }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/app";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
