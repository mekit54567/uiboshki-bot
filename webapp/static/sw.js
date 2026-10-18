// Service worker приложения вне Telegram (этап 2: PWA). В Telegram не
// регистрируется (core.js) — там своё кэширование и обновления.
//  • оболочка (страница, стили, скрипты с ?v=хэш) — из кэша, обновляется сама:
//    у файлов с меткой версии адрес меняется при каждом выпуске;
//  • данные GET /api/… — сначала сеть (до 5 с), нет сети — последний ответ:
//    расписание и дедлайны видно и в метро;
//  • остальное (POST, вход, ИИ) — только сеть.
const SHELL = "uib-shell-v1", DATA = "uib-data-v1";
const OFFLINE_API = /^\/api\/(today|day|week|deadlines|me|homework|notes|files|subjects|notify)\b/;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(["/app"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(k => k !== SHELL && k !== DATA).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("message", e => {
  if (e.data === "logout") e.waitUntil(caches.delete(DATA));   // вышел — чужих данных на телефоне не оставляем
});

// Файлы приложения (/app/…, веб-сборка Flutter): свежие из сети, медленно или
// без сети — из кэша; в кэше ещё нет (первый запуск) — ждём сеть сколько надо:
// canvaskit большой, на 3G за 4 с не успевает.
async function freshFirst(req, cacheName, ms) {
  const cache = await caches.open(cacheName);
  const net = fetch(req).then(resp => {
    if (resp.ok) cache.put(req, resp.clone());
    return resp;
  });
  try {
    return await Promise.race([net, timeout(ms)]);
  } catch (e) {
    return (await cache.match(req)) || net;
  }
}

function timeout(ms) { return new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms)); }

async function networkFirst(req, cacheName, ms) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await Promise.race([fetch(req), timeout(ms)]);
    if (resp.ok) cache.put(req, resp.clone());
    return resp;
  } catch (e) {
    const hit = await cache.match(req);
    if (hit) return hit;
    throw e;
  }
}

self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/app" || url.pathname === "/app/" || url.pathname === "/" || url.pathname === "/index.html") {
    e.respondWith(networkFirst(new Request("/app"), SHELL, 4000));
  } else if (url.pathname.startsWith("/app/")) {
    e.respondWith(freshFirst(req, SHELL, 4000));
  } else if (url.search.includes("v=") && /\.(js|css)$/.test(url.pathname) || url.pathname.startsWith("/pwa/")) {
    e.respondWith(caches.open(SHELL).then(c => c.match(req).then(hit => hit || fetch(req).then(resp => {
      if (resp.ok) c.put(req, resp.clone());
      return resp;
    }))));
  } else if (OFFLINE_API.test(url.pathname)) {
    e.respondWith(networkFirst(req, DATA, 5000));
  }
});

// Пуши (этап 2 (г), delivery.py → webpush.py): уведомление на экране и
// переход в нужное место приложения по нажатию.
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Капибара", {
    body: d.body || "", tag: d.tag || "uib", icon: "/pwa/icon-192.png", badge: "/pwa/icon-192.png",
    data: { url: d.url || "/app" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/app";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    const open = list.find(c => new URL(c.url).pathname === "/app");
    return open ? open.navigate(url).then(c => c && c.focus()) : self.clients.openWindow(url);
  }));
});
