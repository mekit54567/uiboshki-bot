// Ядро PWA на HTML (Никита 19.10): то же приложение, что на iPhone (app/,
// Flutter), только страницей — быстрее в Safari, без чёрной полосы снизу.
// Здесь: настройки (те же ключи, что у Flutter-версии в localStorage — вход и
// вид переезжают сами), запросы к /api/v1, время, тема и шрифт, экраны и
// переходы, листы снизу, всплывашки, иконки и капибары.
"use strict";

// ── Настройки: shared_preferences в вебе — localStorage «flutter.<имя>» = JSON ──
const Prefs = {
  get(name, fallback = null) {
    try {
      const v = localStorage.getItem("flutter." + name);
      return v === null ? fallback : JSON.parse(v);
    } catch (e) { return fallback; }
  },
  set(name, value) {
    try {
      if (value === null || value === undefined) localStorage.removeItem("flutter." + name);
      else localStorage.setItem("flutter." + name, JSON.stringify(value));
    } catch (e) {}
  },
};

// ── Время: на стенде — ?now=2026-10-08T10:07:00+03:00 (как --dart-define=NOW) ──
const _nowShift = (() => {
  const q = new URLSearchParams(location.search).get("now");
  const t = q ? Date.parse(q) : NaN;
  return isNaN(t) ? 0 : t - Date.now();
})();
function now() { return new Date(Date.now() + _nowShift); }
const MSK = 3 * 3600 * 1000;
/** Дата-время по Москве как «наивный» объект {y,m,d,h,min,wd} — экраны считают по МСК. */
function msk(date = now()) {
  const t = new Date(date.getTime() + MSK);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate(), h: t.getUTCHours(), min: t.getUTCMinutes(),
           wd: (t.getUTCDay() + 6) % 7, iso: t.toISOString().slice(0, 10) };
}
function isoDay(date = now()) { return msk(date).iso; }
function hm(date) { const t = msk(date); return String(t.h).padStart(2, "0") + ":" + String(t.min).padStart(2, "0"); }
const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"];
const WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

// ── Мелочи ──
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}
function tick() { try { navigator.vibrate && navigator.vibrate(4); } catch (e) {} }
/** Иконка Material: icon("schedule") — Round, icon("school", "o") — Outlined. */
function icon(name, variant = "", style = "") {
  return `<span class="mi ${variant}" aria-hidden="true"${style ? ` style="${style}"` : ""}>${name}</span>`;
}
const CAPY = ["angry", "day", "evening", "joy", "morning", "night", "sad", "splash", "surf"];
/** Капибара-силуэт (CapyImage): цвет — currentColor или color. */
function capy(pose, size, color = "") {
  return `<i class="capy" style="--img:url(/img/capy/${pose}.png);width:${size}px;height:${size}px${color ? ";color:" + color : ""}"></i>`;
}
/** Слово через дефис не рвётся (FitWords.glue). */
function glue(text) { return String(text).replace(/(\S)-(?=\S)/g, "$1-⁠"); }
/** Кегль заголовка по длине (titleSize). */
function titleSize(text, base) {
  const n = String(text).length;
  return n > 60 ? base * 0.62 : n > 40 ? base * 0.72 : n > 26 ? base * 0.86 : base;
}

// ── Цвет предмета (subjectColor / AppStyle.ink) ──
function subjectIndex(title) {
  let h = 0;
  const s = String(title).toLowerCase();
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) & 0x7fffffff;
  return h % 8;
}
function subjectColor(title) { return `var(--t-subject-${subjectIndex(title)})`; }
/** Цвет предмета для текста и заливок: в светлых темах нового дизайна — темнее. */
function ink(title) {
  return Theme.darkInk ? `var(--t-subject-ink-${subjectIndex(title)})` : subjectColor(title);
}

// ── Запросы к серверу ──
class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}
const Api = {
  get token() { return Prefs.get("uib_token"); },
  set token(v) { Prefs.set("uib_token", v); },
  onUnauthorized: null,
  /** Без сети — последний удачный ответ GET (как Api.get в app/lib/api/api.dart). */
  offline: false,
  async _req(method, path, body, timeout = 8000) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeout);
    const headers = { "Content-Type": "application/json" };
    if (this.token) headers.Authorization = "Bearer " + this.token;
    // с экрана «Домой» — своё хранилище и свой вход: в «Устройствах» — «Ярлык», не Safari
    if (matchMedia("(display-mode: standalone)").matches || navigator.standalone) headers["X-Client"] = "home";
    let r;
    try {
      r = await fetch("/api/v1" + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal });
    } catch (e) {
      throw new ApiError(e.name === "AbortError" ? "Сервер не ответил — проверь интернет" : "Нет связи с сервером — проверь интернет");
    } finally { clearTimeout(timer); }
    if (r.status === 401 && !path.startsWith("/auth/")) {
      if (this.onUnauthorized) this.onUnauthorized();
      throw new ApiError("Вход устарел — войди снова", 401);
    }
    let data = null;
    const text = await r.text();
    if (text) {
      try { data = JSON.parse(text); }
      catch (e) { throw new ApiError("Сервер сейчас не в духе — попробуй чуть позже", r.status); }
    }
    if (r.status >= 400) {
      const d = data && data.detail;
      if (typeof d === "string") throw new ApiError(d, r.status);
      throw new ApiError(r.status >= 500 ? "Сервер сейчас не в духе — попробуй чуть позже" : `Не получилось (ошибка ${r.status}) — попробуй ещё раз.`, r.status);
    }
    return data;
  },
  async get(path) {
    try {
      const data = await this._req("GET", path);
      try { localStorage.setItem("uib_cache:" + path, JSON.stringify(data)); } catch (e) {}
      this.offline = false;
      return data;
    } catch (e) {
      if (e.status) throw e;
      const c = this.cached(path);
      if (c !== undefined) { this.offline = true; return c; }
      throw e;
    }
  },
  /** Последний запомненный ответ GET (undefined — нет): экран рисуется сразу. */
  cached(path) {
    try {
      const v = localStorage.getItem("uib_cache:" + path);
      return v === null ? undefined : JSON.parse(v);
    } catch (e) { return undefined; }
  },
  // 15 с: на iPhone после возврата из другого приложения запрос может повиснуть
  // на мёртвом соединении — лучше оборвать и повторить (Никита 20.10: вход и VK
  // «не нажимались»). Долгие (ответ ИИ, конспект, сдача файла) передают своё время.
  post(path, body = {}, timeout = 15000) { return this._req("POST", path, body, timeout); },
  put(path, body = {}) { return this._req("PUT", path, body); },
  patch(path, body = {}) { return this._req("PATCH", path, body); },
  del(path) { return this._req("DELETE", path); },
  clearCache() {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && (k.startsWith("uib_cache:") || k.startsWith("flutter.uib_cache:"))) localStorage.removeItem(k); // и чаты помощника
      }
    } catch (e) {}
  },
};
function errorText(e) { return e && e.message ? e.message : "Что-то пошло не так — попробуй ещё раз."; }

// ── Тема и шрифт («Оформление», theme/look.dart) ──
const Theme = {
  design2: Prefs.get("uib_design2", true) !== false,
  dark: false,
  get darkInk() { return this.design2 && !this.dark; },
  pick() {
    const choice = this.design2 ? (Prefs.get("uib_theme") || "system") : ((Prefs.get("uib_theme") === "sunset" ? "system" : Prefs.get("uib_theme")) || "system");
    let dark, dusk = 0;
    if (choice === "light") dark = false;
    else if (choice === "dark") dark = true;
    else if (choice === "sunset") ({ dark, dusk } = sunsetPhase(now()));
    else dark = matchMedia("(prefers-color-scheme: dark)").matches;
    return { choice, dark, dusk };
  },
  apply() {
    const { dark, dusk } = this.pick();
    this.dark = dark;
    const look = this.design2 ? Look.load() : Look.classic;
    const name = dark ? (look.dark === "library" ? "library" : "depth") : (look.light === "campus" ? "campus" : "notebook");
    const root = document.documentElement;
    root.dataset.appTheme = name;
    root.dataset.dark = dark ? "1" : "0";
    root.dataset.paper = !dark && name === "notebook" ? look.paper : "smooth";
    root.dataset.card = look.card;
    root.style.filter = "";
    root.style.setProperty("--dusk", String(dusk));
    let font = Prefs.get("uib_font") || "book";
    if (!this.design2 && (font === "hand" || font === "wide")) font = "book";
    root.dataset.font = font;
    const f = { book: ["SourceSerif", 500, 1, -0.03, "SourceSerif", 500, 1, -0.05],
                strict: ["Onest", 700, 1, -0.03, "Onest", 800, 1, -0.05],
                hand: ["Neucha", 400, 1.08, 0, "Onest", 800, 1, -0.05],
                wide: ["Unbounded", 500, 0.8, 0, "Unbounded", 500, 0.85, -0.02] }[font] || [];
    const vars = ["--f-head", "--head-w", "--head-k", "--head-ls", "--f-num", "--num-w", "--num-k", "--num-ls"];
    vars.forEach((v, i) => root.style.setProperty(v, f[i]));
    // фон под вырезом и строкой состояния — цвет темы
    const bg = getComputedStyle(root).getPropertyValue("--t-bg").trim();
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta && bg) meta.setAttribute("content", bg);
    if (dusk > 0) document.body.style.setProperty("filter", `brightness(${1 - 0.1 * dusk})`);
    else document.body.style.removeProperty("filter");
  },
};
const Look = {
  classic: { light: "notebook", dark: "depth", paper: "smooth", card: "tint", day: "cards", cheer: "quiet", icon: "classic" },
  load() {
    const c = this.classic;
    return { light: Prefs.get("uib_look_light", c.light), dark: Prefs.get("uib_look_dark", c.dark),
             paper: Prefs.get("uib_look_paper", c.paper), card: Prefs.get("uib_look_card", c.card),
             day: Prefs.get("uib_look_day", c.day), cheer: Prefs.get("uib_look_cheer", c.cheer),
             icon: Prefs.get("uib_look_icon", c.icon) };
  },
  save(l) { for (const k of ["light", "dark", "paper", "card", "day", "cheer", "icon"]) Prefs.set("uib_look_" + k, l[k]); },
};
/** Восход и закат в Москве (moscowSun) и фаза «по закату» (sunsetPhase). */
function moscowSun(d) {
  const lat = 55.7558, lon = 37.6173, t = msk(d);
  const day = Date.UTC(t.y, t.m - 1, t.d);
  const n = Math.round((day - Date.UTC(t.y, 0, 1)) / 864e5) + 1;
  const g = 2 * Math.PI / 365 * (n - 1);
  const eqt = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g)
    - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  const latR = lat * Math.PI / 180;
  const cosH = Math.cos(90.833 * Math.PI / 180) / (Math.cos(latR) * Math.cos(decl)) - Math.tan(latR) * Math.tan(decl);
  const ha = Math.acos(Math.max(-1, Math.min(1, cosH))) * 180 / Math.PI;
  const at = (minUtc) => new Date(day + minUtc * 60000);
  return { rise: at(720 - 4 * (lon + ha) - eqt), set: at(720 - 4 * (lon - ha) - eqt) };
}
function sunsetPhase(t) {
  const sun = moscowSun(t);
  if (t < sun.rise || t >= sun.set) return { dark: true, dusk: 0 };
  const left = (sun.set - t) / 60000;
  return { dark: false, dusk: left >= 60 ? 0 : (60 - left) / 60 };
}

// ── Экраны и переходы (Navigator) ──
// Вкладки — корневые экраны (живут всё время), поверх — стек открытых экранов.
const Nav = {
  stack: [],
  root: null,
  /** Новый экран: render(scrollEl, screen) рисует содержимое; tint — подсветка фона цветом предмета. */
  make({ tint = "", cls = "" } = {}) {
    const s = document.createElement("section");
    s.className = "screen " + cls;
    s.innerHTML = `<div class="bg"${tint ? ` style="--tint:${tint}"` : ""}></div><div class="scroll"><div class="wrap"></div></div>`;
    s.body = s.querySelector(".wrap");
    s.scroller = s.querySelector(".scroll");
    return s;
  },
  /** Открыть экран поверх: render(body, screen) → необязательно cleanup. */
  push(render, opts = {}) {
    tick();
    const s = this.make(opts);
    const app = document.getElementById("app");
    const under = this.top();
    app.appendChild(s);
    this.stack.push(s);
    Tabs.setVisible(false);
    s.classList.add("enter");
    if (under) { under.classList.add("under"); setTimeout(() => under.classList.remove("under"), 340); }
    setTimeout(() => s.classList.remove("enter"), 340);
    try { history.pushState({ depth: this.stack.length }, ""); } catch (e) {}
    s.cleanup = render(s.body, s) || null;
    return s;
  },
  top() { return this.stack[this.stack.length - 1] || Tabs.current(); },
  /** Закрыть верхний экран (кнопка «назад», свайп от края, «назад» браузера). */
  pop(fromHistory = false) {
    const s = this.stack.pop();
    if (!s) return;
    // назад по истории — только если эту запись добавили мы: иначе history.back()
    // уводил со страницы (Никита 20.10: после свайпа — чёрный экран)
    if (!fromHistory && history.state && history.state.depth) { this._skip = true; try { history.back(); } catch (e) {} }
    const under = this.top();
    if (typeof s.cleanup === "function") s.cleanup();
    s.classList.add("leave");
    if (under) { under.classList.add("back"); setTimeout(() => under.classList.remove("back"), 300); }
    setTimeout(() => s.remove(), 290);
    if (!this.stack.length) Tabs.setVisible(true);
    if (under && under.onShow) under.onShow();
  },
  popAll() { while (this.stack.length) this.pop(); },
};
window.addEventListener("popstate", () => {
  if (Nav._skip) { Nav._skip = false; return; }
  if (Sheet.open.length) { Sheet.closeTop(); return; }
  if (Nav.stack.length) Nav.pop(true);
});
// свайп от левого края — «назад», как в приложении на iPhone. Только с экрана
// «Домой»: в Safari у края свой жест «назад» — вместе с нашим экран закрывался
// дважды и уходил со страницы (Никита 20.10)
const STANDALONE = navigator.standalone === true || matchMedia("(display-mode: standalone)").matches;
(() => {
  if (!STANDALONE) return;
  let x0 = null, y0 = 0, s = null;
  document.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    if (t.clientX < 24 && Nav.stack.length && !Sheet.open.length) { x0 = t.clientX; y0 = t.clientY; s = Nav.top(); }
  }, { passive: true });
  document.addEventListener("touchmove", (e) => {
    if (x0 === null) return;
    const t = e.touches[0], dx = Math.max(0, t.clientX - x0);
    if (Math.abs(t.clientY - y0) > 40 && dx < 30) { x0 = null; s.style.transform = ""; return; }
    s.style.transform = `translateX(${dx}px)`;
  }, { passive: true });
  document.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    x0 = null;
    if (dx > innerWidth * 0.3) { s.style.transform = ""; Nav.pop(); }
    else { s.style.transition = "transform .2s"; s.style.transform = ""; setTimeout(() => (s.style.transition = ""), 220); }
  });
})();

/** Кнопка «назад» сверху экрана (BackRow). */
function backRow(extra = "") {
  return `<div class="backrow"><button data-act="back" aria-label="Назад">${icon("arrow_back_ios_new")}</button>${extra}</div>`;
}
/** Заголовок экрана (ScreenTitle): sub — строка под названием, trailing — справа. */
function screenTitle(title, { sub = "", trailing = "", lead = "", size = 34 } = {}) {
  const t = `<div class="row" style="align-items:flex-end"><div class="grow">
    <div class="ttl" style="--sz:${titleSize(title, size)}px">${esc(glue(title))}</div>
    ${sub ? `<div class="bd mut" style="--sz:15px;margin-top:4px">${esc(sub)}</div>` : ""}
    <div class="bar" style="width:34px;height:3px;border-radius:2px;background:var(--accent);margin-top:10px"></div>
  </div>${trailing}</div>`;
  return `<div style="padding:var(--l) var(--xl) var(--m)">${lead ? lead + '<div style="height:6px"></div>' : ""}${t}</div>`;
}
function section(text) { return `<div class="section eyebrow">${esc(text)}</div>`; }
/** Пусто или ошибка (Notice): pose — капибара, retry — data-act кнопки. */
function notice(title, text, { pose = "", retry = "", retryLabel = "Ещё раз" } = {}) {
  // «Пусто, всё хорошо» — капибара выглядывает снизу справа из-за края карточки (CapyPeek)
  if (pose && pose !== "sad") {
    const size = 84, shown = size * 0.8, h = msk(now()).h, night = h >= 23 || h < 5;
    return `<div class="hx"><div class="tile" style="padding:0;position:relative;min-height:${shown + 30}px">
      <div style="padding:var(--l) calc(${size}px + var(--l)) var(--l) var(--l)">
        <div class="bd b6" style="--sz:17px">${esc(title)}</div>
        <div class="bd mut" style="--sz:14px;margin-top:4px">${esc(text)}</div>
        ${retry ? `<button class="btn text" style="width:auto;padding:0;justify-content:flex-start;margin-top:var(--m)" data-act="${retry}">${esc(retryLabel)}</button>` : ""}</div>
      <button class="peek" aria-hidden="true" tabindex="-1" style="width:${size + 18}px;height:${shown + 26}px" onclick="tick();this.classList.toggle('turned')">
        <span class="peek-rise" style="top:26px">${capy(night ? "night" : pose, size, "var(--accent)")}</span>
        ${night ? '<b class="peek-z" style="font-size:11px">z</b><b class="peek-z" style="font-size:14px;animation-delay:-1.2s">z</b>' : ""}</button>
    </div></div>`;
  }
  return `<div class="hx"><div class="tile row" style="align-items:center">
    ${pose ? `<span class="mut">${capy(pose, 72)}</span>` : ""}
    <div class="grow"><div class="bd b6" style="--sz:17px">${esc(title)}</div>
    <div class="bd mut" style="--sz:14px;margin-top:4px">${esc(text)}</div>
    ${retry ? `<button class="btn text" style="width:auto;padding:0;justify-content:flex-start" data-act="${retry}">${esc(retryLabel)}</button>` : ""}</div>
  </div></div>`;
}
/** Первая загрузка экрана — капибара со сценой (CapyLoading, js/capy_scenes.js). */
function spinner() { return typeof capyLoading === "function" ? capyLoading() : smallSpinner(); }
/** Маленькая крутилка — где в приложении CircularProgressIndicator (поиск). */
function smallSpinner() { return '<div class="spinner"></div>'; }
/** Кольцо баллов (ScoreRing). */
function ring(value, color, inner, size = 64, stroke = 6) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value || 0));
  return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${stroke}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${c * v} ${c}"/></svg><span style="position:relative">${inner}</span></div>`;
}

/** Действия по data-act внутри элемента: on(el, {back(){…}, open(btn){…}}). */
function on(el, handlers) {
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-act]");
    if (!b || !el.contains(b)) return;
    const act = b.dataset.act;
    if (act === "back" && !handlers.back) { Nav.pop(); return; }
    const fn = handlers[act];
    if (fn) { e.preventDefault(); fn(b, e); }
  });
}

// ── Листы снизу (appSheet / confirmSheet / inputSheet) ──
const Sheet = {
  open: [],
  /** show(html, mount) → Promise со значением close(value). mount(body, close) вешает обработчики. */
  show(html, mount) {
    return new Promise((resolve) => {
      const w = document.createElement("div");
      w.className = "sheet-wrap";
      w.innerHTML = `<div class="sheet-dim"></div><div class="sheet" role="dialog"><div class="grip"></div><div class="body">${html}</div></div>`;
      document.body.appendChild(w);
      const close = (value) => {
        if (w.closed) return;
        w.closed = true;
        this.open = this.open.filter((x) => x !== w);
        w.classList.add("out");
        setTimeout(() => w.remove(), 220);
        resolve(value);
      };
      w.close = close;
      w.querySelector(".sheet-dim").addEventListener("click", () => close(undefined));
      // смахнуть вниз за верх листа — закрыть
      const sh = w.querySelector(".sheet");
      let y0 = null;
      sh.addEventListener("touchstart", (e) => { if (sh.scrollTop <= 0) y0 = e.touches[0].clientY; }, { passive: true });
      sh.addEventListener("touchmove", (e) => {
        if (y0 === null) return;
        const dy = e.touches[0].clientY - y0;
        if (dy > 0) sh.style.transform = `translateY(${dy}px)`;
      }, { passive: true });
      sh.addEventListener("touchend", (e) => {
        if (y0 === null) return;
        const dy = e.changedTouches[0].clientY - y0;
        y0 = null;
        sh.style.transform = "";
        if (dy > 110) close(undefined);
      });
      this.open.push(w);
      if (mount) mount(w.querySelector(".body"), close, sh);
    });
  },
  closeTop() { const w = this.open[this.open.length - 1]; if (w) w.close(undefined); },
};
/** «Точно?» — заголовок, пояснение, главная кнопка и «Отмена». → true/false. */
async function confirmSheet({ title, text = "", action, cancel = "Отмена", danger = false }) {
  const v = await Sheet.show(`
    <div class="ttl" style="--sz:24px">${esc(title)}</div>
    ${text ? `<div class="bd mut" style="--sz:15px;margin-top:8px">${esc(text)}</div>` : ""}
    <div style="height:var(--xl)"></div>
    <button class="btn ${danger ? "danger" : "primary"}" data-act="ok">${esc(action)}</button>
    <button class="btn text" data-act="no">${esc(cancel)}</button>`,
  (body, close) => on(body, { ok: () => close(true), no: () => close(false) }));
  return v === true;
}
/** Строка листом снизу. → текст или null. */
async function inputSheet({ title, text = "", hint = "", initial = "", action = "Сохранить", type = "text", multiline = false }) {
  const v = await Sheet.show(`
    <div class="ttl" style="--sz:24px">${esc(title)}</div>
    ${text ? `<div class="bd mut" style="--sz:15px;margin-top:8px">${esc(text)}</div>` : ""}
    <div style="height:var(--l)"></div>
    ${multiline ? `<textarea class="field" placeholder="${esc(hint)}">${esc(initial)}</textarea>`
                : `<input class="field" type="${type}" placeholder="${esc(hint)}" value="${esc(initial)}">`}
    <div style="height:var(--l)"></div>
    <button class="btn primary" data-act="ok">${esc(action)}</button>`,
  (body, close) => {
    const f = body.querySelector(".field");
    setTimeout(() => f.focus(), 300);
    on(body, { ok: () => close(f.value) });
    if (!multiline) f.addEventListener("keydown", (e) => { if (e.key === "Enter") close(f.value); });
  });
  return typeof v === "string" ? v : null;
}

// ── Всплывашка (toast): kind — info | done | error ──
let _toastTimer = 0;
function toast(text, kind = "info") {
  const box = document.getElementById("toast");
  if (!box) return;
  const ic = { error: "error_outline", done: "check_circle", info: "info" }[kind] || "info";
  box.innerHTML = `<div class="toast ${kind}">${icon(ic)}<div class="bd grow" style="--sz:15px">${esc(text)}</div></div>`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    const t = box.firstElementChild;
    if (t) { t.classList.add("out"); setTimeout(() => t.remove(), 200); }
  }, kind === "error" ? 4200 : 3000);
}

/** Открыть ссылку: внутри PWA — в браузере, не уходя из приложения. */
function openLink(url) { window.open(url, "_blank", "noopener"); }
