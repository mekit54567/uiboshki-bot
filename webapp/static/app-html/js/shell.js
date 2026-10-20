// Оболочка (screens/shell.dart): пять вкладок и меню-капсула. Вкладка из
// ссылки пуша — /app?tab=week|deadlines|study|more. Экраны вкладок —
// Screens.today/week/deadlines/study/more (js/screens/*.js): mount(body, screen)
// рисует, onShow() — при каждом возврате на вкладку.
"use strict";

const Screens = window.Screens || (window.Screens = {});

const TABS = [
  { id: "today", icon: "schedule", label: "Сегодня" },
  { id: "week", icon: "calendar_today", label: "Неделя" },
  { id: "deadlines", icon: "bookmark_border", label: "Сдать" },
  { id: "study", icon: "school", variant: "o", label: "Учёба" },
  { id: "more", icon: "more_horiz", label: "Ещё" },
];
function tabByName(name) {
  return { week: 1, deadlines: 2, sdo: 3, study: 3, more: 4 }[name] ?? 0;
}

const Tabs = {
  index: 0,
  screens: [],
  current() { return this.screens[this.index]; },
  build() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    this.screens = TABS.map((t) => {
      const s = Nav.make();
      s.dataset.tab = t.id;
      s.style.display = "none";
      app.appendChild(s);
      return s;
    });
    const bar = document.getElementById("tabbar");
    bar.className = "";
    bar.innerHTML = `<nav class="capsule" role="tablist">${TABS.map((t, i) =>
      `<button class="slot" role="tab" data-i="${i}" aria-label="${t.label}">${icon(t.icon, t.variant || "")}<span class="lbl">${t.label}</span></button>`).join("")}</nav>`;
    bar.addEventListener("click", (e) => {
      const b = e.target.closest(".slot");
      if (!b) return;
      const i = +b.dataset.i;
      if (i === this.index) { this.current().scroller.scrollTo({ top: 0, behavior: "smooth" }); return; }
      tick();
      this.show(i);
    });
    this.show(tabByName(new URLSearchParams(location.search).get("tab")));
  },
  show(i) {
    this.index = i;
    this.screens.forEach((s, k) => (s.style.display = k === i ? "" : "none"));
    document.querySelectorAll("#tabbar .slot").forEach((b, k) => {
      b.classList.toggle("on", k === i);
      b.setAttribute("aria-selected", k === i ? "true" : "false");
    });
    const s = this.screens[i], scr = Screens[TABS[i].id];
    this.setHidden(false);
    if (!s.mounted && scr) {
      s.mounted = true;
      try { s.cleanup = scr.mount(s.body, s) || null; }
      catch (e) { console.error(e); s.body.innerHTML = notice("Не открылось", errorText(e), { pose: "sad" }); }
      this._watch(s);
    } else if (scr && scr.onShow) scr.onShow(s.body, s);
    if (i === 4) Ach.unlock("more");
  },
  /** В длинном списке (новый дизайн) капсула уезжает вниз, пока читаешь дальше. */
  _watch(s) {
    let last = 0;
    s.scroller.addEventListener("scroll", () => {
      if (!Theme.design2) return;
      const y = s.scroller.scrollTop, max = s.scroller.scrollHeight - s.scroller.clientHeight;
      if (s.quietUntil && Date.now() < s.quietUntil) { last = y; return; }  // прокрутила программа, не человек
      if (y < 40 || y >= max - 4) this.setHidden(false);
      else if (y > last + 6) this.setHidden(true);
      else if (y < last - 6) this.setHidden(false);
      last = y;
    }, { passive: true });
  },
  setHidden(h) { document.getElementById("tabbar").classList.toggle("hidden", h); },
  setVisible(v) { document.getElementById("tabbar").classList.toggle("off", !v); },
  /** Сменилась группа или вид — экраны вкладок строятся заново. */
  rebuild() {
    this.screens.forEach((s) => { if (typeof s.cleanup === "function") s.cleanup(); s.mounted = false; s.body.innerHTML = ""; });
    this.show(this.index);
  },
};

// Ачивки ловит приложение (achievements/store.dart), сервер их помнит
// (/api/achievements). Здесь — тот же список открытых, без анимации открытия.
const Ach = {
  get done() { return Prefs.get("uib_ach", {}) || {}; },
  unlock(id) {
    const d = this.done;
    if (d[id]) return;
    d[id] = new Date().toISOString();
    Prefs.set("uib_ach", d);
    Api.post("/achievements", { items: { [id]: d[id] } }).catch(() => {});
  },
};

// ── Запуск ──
async function start() {
  // вход прежней PWA (до веб-сборки Flutter) — ключ без приставки
  try {
    const old = localStorage.getItem("uib_token");
    if (old && !Api.token) Api.token = old;
    localStorage.removeItem("uib_token");
  } catch (e) {}
  // оболочка без сети и пуши — service worker; в Telegram он не нужен
  if ("serviceWorker" in navigator && !(window.Telegram && Telegram.WebApp && Telegram.WebApp.initData)) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  }
  Theme.apply();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => Theme.apply());
  setInterval(() => { if (Prefs.get("uib_theme") === "sunset") Theme.apply(); }, 60000);
  Api.onUnauthorized = () => logout(true);
  // сервер мог выключить новый дизайн (DESIGN2=0) — узнаём при запуске
  Api.get("/meta").then((m) => {
    const on = !(m && m.features && m.features.design2 === false);
    if (on !== Theme.design2) { Theme.design2 = on; Prefs.set("uib_design2", on); Theme.apply(); if (Api.token) Tabs.rebuild(); }
  }).catch(() => {});
  if (Api.token) { Tabs.build(); afterStart(); }
  else showLogin();
}
function showLogin() {
  const app = document.getElementById("app");
  app.innerHTML = "";
  Tabs.setVisible(false);
  const s = Nav.make();
  app.appendChild(s);
  if (Screens.login) Screens.login.mount(s.body, s, () => { Tabs.setVisible(true); Tabs.build(); afterStart(); });
}
/** После входа (shell.dart: _ensureGroup, _maybeTour): удаление данных,
 * согласие на ПД, группа новому человеку, приглашение, знакомство. */
async function afterStart() {
  let me;
  try { me = await Api.get("/me"); } catch (e) { return; } // нет сети — экраны сами скажут
  if (!me) return;
  if (me.erasing && typeof me.erasing === "object") {
    await confirmSheet({ title: "Данные удаляются", text: String(me.erasing.text || ""), action: "Понятно", cancel: "Закрыть" });
    return logout(true);
  }
  if (me.consent_needed === true && window.openConsent) {
    const blocked = me.consent_blocked === true;
    const ok = await openConsent({ required: blocked });
    if (ok === false || (blocked && ok !== true)) return logout(true);
    if (blocked) Tabs.rebuild(); // до согласия API закрыт — экраны загрузить заново
  }
  if (me.group == null && window.openGroupPick) {
    const g = await openGroupPick({ required: true });
    if (g) Tabs.rebuild();
  }
  if (window.sendRef) sendRef().catch(() => {});
  if (window.maybeTour) await maybeTour();
}

async function logout(expired = false) {
  if (!expired) { try { await Api.post("/auth/logout"); } catch (e) {} }
  Api.token = null;
  Api.clearCache();
  Nav.stack.forEach((s) => s.remove());
  Nav.stack = [];
  showLogin();
  if (expired) toast("Вход устарел — войди снова", "info");
}
document.addEventListener("DOMContentLoaded", start);
