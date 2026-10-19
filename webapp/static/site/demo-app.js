// Демо на сайте /about — само приложение Капибары (веб-сборка Flutter, как на
// iPhone и в PWA), а не прежний Mini App (Никита 19.10). Подключается первым
// скриптом в <head> страницы /about/demo (webapp/routes/site.py). Здесь только:
//   • время как в записанных данных — четверг, 8 октября, 10:05 МСК, и дальше
//     идёт само (Dart берёт DateTime.now() из Date.now());
//   • свой localStorage в памяти: вход «demo» и пройденное знакомство. Сайт и
//     PWA /app — один адрес, настоящий localStorage трогать нельзя: демо
//     выкинуло бы человека из его входа в /app;
//   • без service worker и пушей;
//   • отступы под вырез телефона на сайте (window.uibInsets);
//   • ответы /api/v1/… из site/demo.json — тестовые данные стенда, ничьих
//     настоящих данных там нет; чего в записи нет — по форме настоящих ответов
//     (как в app/robot/lib.js). Поиск расписания — настоящий (/about/api/…).
(function () {
  const REC_NOW = 1791443100000;
  const RealDate = Date;
  const shift = REC_NOW - RealDate.now();
  function DemoDate(...a) {
    if (!(this instanceof DemoDate)) return new RealDate(RealDate.now() + shift).toString();
    return a.length ? new RealDate(...a) : new RealDate(RealDate.now() + shift);
  }
  DemoDate.prototype = RealDate.prototype;
  DemoDate.now = () => RealDate.now() + shift;
  DemoDate.UTC = RealDate.UTC;
  DemoDate.parse = RealDate.parse;
  window.Date = DemoDate;

  const mem = new Map([
    ["flutter.uib_token", JSON.stringify("demo")],
    ["flutter.uib_toured", "true"],
  ]);
  const storage = {
    get length() { return mem.size; },
    key: (i) => [...mem.keys()][i] ?? null,
    getItem: (k) => (mem.has(String(k)) ? mem.get(String(k)) : null),
    setItem: (k, v) => { mem.set(String(k), String(v)); },
    removeItem: (k) => { mem.delete(String(k)); },
    clear: () => mem.clear(),
  };
  try { Object.defineProperty(window, "localStorage", { configurable: true, get: () => storage }); } catch (e) {}

  if (navigator.serviceWorker) {
    try { navigator.serviceWorker.register = () => Promise.reject(new Error("демо")); } catch (e) {}
  }
  const insets = () => "44,0,24,0";
  try { Object.defineProperty(window, "uibInsets", { configurable: true, get: () => insets, set: () => {} }); } catch (e) {}
  // сайт прячет «Открываем приложение…», когда Flutter нарисовал первый кадр
  window.addEventListener("flutter-first-frame", () => {
    try { window.parent.postMessage("uib-demo-ready", location.origin); } catch (e) {}
  });

  const realFetch = window.fetch.bind(window);
  const fixtures = realFetch("/site/demo.json").then((r) => r.json()).then((d) => d.fx);
  const reply = (body, status) => new Response(JSON.stringify(body), {
    status: status || 200, headers: { "Content-Type": "application/json; charset=utf-8" } });
  const nope = () => reply({ detail: "В демо это не работает — открой Капибару в Telegram или на uiboshki.ru/app" }, 403);

  const extra = {
    "GET /api/meta": { api: 1, server: "demo", min_client: { web: "0.0.0", android: "0.0.0", ios: "0.0.0" },
      login: ["telegram"], features: { groups: true, sessions: true, offline: true, design2: true },
      links: { bot: "https://t.me/UiboshkiBot", channel: "", contact: "", sdo_guide: "" } },
    "GET /api/auth/sessions": { items: [
      { id: 1, device: "Капибара · iPhone", created_at: "2026-10-01 12:00:00", last_seen: "2026-10-08 10:05:00", current: true },
    ] },
    "GET /api/auth/identities": { items: [], available: [], telegram: true },
    "GET /api/auth/providers": { items: [] },
    "GET /api/sdo/submit-rules": { accepted: [".pdf", ".docx"], labels: ["Документ PDF", "Документ Word"], maxfiles: 3, maxbytes: 20971520 },
  };
  function fallback(p) {
    if (p === "/api/day") return { lessons: [] };
    if (p === "/api/week") return { week: null, days: [] };
    if (p === "/api/notes") return { items: [] };
    if (p === "/api/lecture-search") return { ready: true, items: [] };
    if (p === "/api/achievements") return { items: {} };
    if (p === "/api/groups/search") return { items: [{ id: 4928, name: "УИБО-03-24" }] };
    return undefined;
  }

  window.fetch = async function (input, init) {
    const u = new URL(typeof input === "string" ? input : input.url, location.href);
    if (!u.pathname.startsWith("/api/")) return realFetch(input, init);
    const p = u.pathname.replace(/^\/api\/v1\//, "/api/");
    const method = ((init && init.method) || (typeof input === "object" && input.method) || "GET").toUpperCase();
    // поиск расписания любой группы, преподавателя, аудитории — настоящий
    if (method === "GET" && (p === "/api/search" || p.startsWith("/api/target/"))) {
      return realFetch("/about" + p + u.search);
    }
    const fx = await fixtures;
    if (method === "GET") {
      let hit = fx["GET " + p + u.search];
      if (hit === undefined) hit = fx["GET " + p];
      if (hit === undefined) hit = extra["GET " + p];
      if (hit === undefined) hit = fallback(p);
      return hit !== undefined ? reply(hit) : nope();
    }
    let body = {};
    try { body = JSON.parse((init && init.body) || "{}"); } catch (e) {}
    if (p.startsWith("/api/sdo/goal/")) {
      const hit = fx["POST " + p + "|" + (body.label || "")];
      return hit ? reply(hit) : nope();
    }
    if (p === "/api/chat") {
      await new Promise((r) => setTimeout(r, 1400));          // «думает», как настоящий
      return reply(fx["POST /api/chat"]);
    }
    if (p === "/api/notify") return reply(fx["GET /api/notify"]);
    return nope();                                            // сдача работ, загрузка, удаление — только по-настоящему
  };
})();
