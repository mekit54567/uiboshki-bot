// Ачивки (app/lib/achievements/: catalog, captions, store, ui) и «Рейтинг»
// (screens/rating.dart, widgets/trend_chart.dart).
// Ачивки ловятся по удачным ответам API, как в store.dart: здесь — обёртка
// над Api.get/post (core.js не трогаем), открытие — вместо Ach.unlock из
// shell.js (тот же ключ uib_ach и формат, что у веб-сборки Flutter: id → мс).
"use strict";

// ── Каталог (catalog.dart, captions.dart) ────────────────────────────────

const AC_RANKS = [
  { id: "dawn", title: "Рассвет", pose: "morning", sky: ["#FFE7C2", "#FFB38A", "#F08A6E"], ink: "#5B2A1A", sticker: "#FFD9B0" },
  { id: "noon", title: "Полдень", pose: "day", sky: ["#7CC6FF", "#5BA6F7", "#3D8BF2"], ink: "#FFFFFF", sticker: "#CFE8FF" },
  { id: "dusk", title: "Сумерки", pose: "evening", sky: ["#3B2A6E", "#B24B8F", "#FF9A5A"], ink: "#FFFFFF", sticker: "#FFC7A8" },
  { id: "midnight", title: "Полночь", pose: "night", sky: ["#0A0D2A", "#13173C", "#1A1F4D"], ink: "#FFE9A8", sticker: "#FFE9A8" },
];
function acRank(id) { return AC_RANKS.find((r) => r.id === id) || AC_RANKS[0]; }

// вкладки — как в shell: 0 Сегодня, 1 Неделя, 2 Сдать, 3 Учёба, 4 Ещё
const AC_ACH = [
  ["lesson", "dawn", "Где пара?", "Открыть пару: где она, кто ведёт и что по баллам", [0, "Нажми на пару"]],
  ["week_next", "dawn", "Листаю неделю", "Перелистнуть на следующую неделю", [1, "Смахни неделю влево"]],
  ["goal", "dawn", "Своя цель", "Выбрать цель по предмету: автомат или с экзаменом", [3, "Открой предмет, там карточка «Цель»"]],
  ["sdo", "dawn", "Свой вход в СДО", "Подключить свой вход, чтобы видеть баллы", [3, "Нажми «Подключить СДО»"]],
  ["widget", "dawn", "На столе", "Поставить виджет Капибары на экран телефона", [0, "Зажми пустое место на экране телефона → Виджеты → Капибара"]],
  ["look", "dawn", "По-своему", "Поменять оформление, тему или иконку", [4, "Нажми «Оформление»"]],
  ["ai", "dawn", "Первый вопрос", "Спросить ИИ по лекциям группы", [3, "Нажми «Помощник»"]],
  ["summary", "dawn", "Конспект", "Открыть конспект лекции", [3, "Открой «Файлы» и нажми на лекцию"]],
  ["remind", "dawn", "Будильник на пару", "Настроить напоминание перед парой", [4, "Нажми «Уведомления»"]],
  ["teacher", "dawn", "Знаю препода", "Найти расписание преподавателя", [1, "Нажми на поиск вверху недели"]],
  ["submit", "noon", "Сдано из Капибары", "Сдать работу в СДО прямо из приложения", [2, "Нажми «Сдать» у задания"]],
  ["week5", "noon", "Неделя в кармане", "Заходить в Капибару каждый день с понедельника по пятницу"],
  ["early", "noon", "Заранее", "Сдать работу из приложения за три дня до срока", [2, "Сроки — на вкладке «Сдать»"]],
  ["streak", "noon", "Без пропусков", "Четыре лекции подряд по одному предмету без пропуска", [3, "Посещения — на экране предмета"]],
  ["plus", "noon", "Плюс балл", "Получить новый балл в СДО", [3, "Баллы — на вкладке «Учёба»"]],
  ["found", "noon", "Найдено в лекциях", "Открыть слайд лекции из поиска или из ответа ИИ", [3, "Открой «Файлы» и поищи в тексте лекций"]],
  ["auto", "dusk", "Автомат", "Набрать цель «автомат» по предмету", [3, "Открой предмет, там карточка «Цель»"]],
  ["clean", "dusk", "Чистый лист", "Все работы по предмету зачтены", [3, "Работы — на экране предмета"]],
  ["month", "dusk", "Месяц с Капибарой", "Заходить в Капибару 30 разных дней"],
  ["calm", "dusk", "Ни одного «горит»", "Сдать из приложения три работы подряд не в последний день", [2, "Сроки — на вкладке «Сдать»"]],
  ["t2222", "midnight", "22:22", "Коснуться капибары ровно в 22:22"],
  ["wave", "midnight", "Идеальная волна", "Поймать редкую волну, пока капибара обновляет экран"],
  ["fri13", "midnight", "Пятница, 13-е", "Зайти в Капибару в пятницу, 13-е"],
  ["secret", "midnight", "Тайная фраза", "Услышать от капибары фразу, которая выпадает раз на сотню касаний"],
  ["one_of_us", "midnight", "Один из нас", "Капибара повернулась к тебе: раз на десять тысяч касаний"],
].map(([id, rank, title, how, place]) => ({ id, rank, title, how, place: place ? { tab: place[0], hint: place[1] } : null, secret: rank === "midnight" }));
function acAch(id) { return AC_ACH.find((a) => a.id === id) || null; }

/** Подпись маркером на полароиде; нет своей — название ачивки. */
const AC_CAPTIONS = {
  lesson: "вот где моя пара", week_next: "заглядываю вперёд", goal: "цель есть!", sdo: "СДО теперь тут",
  widget: "капибара на столе", look: "теперь по-моему", ai: "ИИ, выручай", summary: "конспект за минуту",
  remind: "не просплю", teacher: "знаю, где препод", submit: "сдано!", week5: "неделя в кармане",
  early: "сдано заранее!", streak: "ни одной пропущенной", plus: "+ балл", found: "нашлось в лекциях",
  auto: "автомат!", clean: "всё зачтено", month: "месяц вместе", calm: "без паники", t2222: "22:22 — поймано!",
  wave: "волна моя!", fri13: "пятница, 13-е", secret: "тсс… секрет", one_of_us: "капибара обернулась",
};

/** Имя на полароиде (из /me) и адрес бота (из /meta → links.bot). */
let acName = "", acBot = "@UiboshkiBot";
function acSetBot(link) { const m = /t\.me\/(\w+)/.exec(link || ""); if (m) acBot = "@" + m[1]; }

// ── Хранилище (store.dart) ───────────────────────────────────────────────

const AcStore = {
  _got: null,
  _dues: {},
  _listeners: new Set(),
  /** Открытые ачивки: id → мс. */
  get got() {
    if (this._got) return this._got;
    const m = {};
    let raw = Prefs.get("uib_ach");
    try { if (typeof raw === "string") raw = JSON.parse(raw); } catch (e) { raw = null; }
    if (raw && typeof raw === "object") {
      for (const [k, v] of Object.entries(raw)) {
        if (!acAch(k)) continue;
        const t = typeof v === "number" ? v : Date.parse(v);
        if (!isNaN(t)) m[k] = t;
      }
    }
    return (this._got = m);
  },
  set got(m) { this._got = m; this._save(); this._listeners.forEach((f) => { try { f(); } catch (e) {} }); },
  _save() { Prefs.set("uib_ach", JSON.stringify(this._got)); },
  listen(f) { this._listeners.add(f); return () => this._listeners.delete(f); },
  has(id) { return id in this.got; },
  count() { return Object.keys(this.got).length; },
  /** Открыть ачивку; true — новая (плашка, бонус за ранг, на сервер). */
  unlock(id, at = Date.now()) {
    const a = acAch(id);
    if (!a || this.has(id)) return false;
    const when = at instanceof Date ? at.getTime() : at;
    this.got = { ...this.got, [id]: when };
    acShowBanner(a);
    if (typeof PlusBonus !== "undefined") PlusBonus.claim(a.rank).catch(() => {});
    this._send({ [id]: when });
    return true;
  },
  /** Отправить открытые; с сервера — недостающее (с другого телефона), молча. */
  async _send(items) {
    if (!Api.token) return;
    try {
      const r = await _acPost("/achievements", { items });
      const there = r && r.items;
      if (!there || typeof there !== "object") return;
      const m = { ...this.got };
      let changed = false;
      for (const [k, v] of Object.entries(there)) {
        if (!acAch(k) || typeof v !== "number") continue;
        if (m[k] === undefined || v < m[k]) { m[k] = v; changed = true; }
      }
      if (changed) this.got = m;
    } catch (e) { /* нет сети — отправим при следующем заходе */ }
  },
  sync() { return this._send(this.got); },
  /** Заход: дни для «Неделя в кармане», «Месяц с Капибарой», пятница, 13-е. */
  visit(at = now()) {
    const t = msk(at);
    const days = new Set(Prefs.get("uib_ach_days", []) || []);
    if (!days.has(t.iso)) {
      days.add(t.iso);
      const list = [...days].sort();
      Prefs.set("uib_ach_days", list.length > 60 ? list.slice(list.length - 60) : list);
    }
    if (t.wd === 4 && t.d === 13) this.unlock("fri13", at);
    if (days.size >= 30) this.unlock("month", at);
    if (t.wd >= 4) {
      const monday = mondayOf(at);
      if ([0, 1, 2, 3, 4].every((i) => days.has(addDays(monday, i)))) this.unlock("week5", at);
    }
  },
  /** Коснулся капибары на «Сегодня». */
  capyTouched(at = now()) { const t = msk(at); if (t.h === 22 && t.min === 22) this.unlock("t2222", at); },
  /** Удачный ответ API: по пути и ответу — какая ачивка. */
  onApi(method, path, body, result) {
    const p = path.split("?")[0];
    try {
      if (p.startsWith("/summary/") && result && result.summary != null) this.unlock("summary");
      if (method === "GET") {
        if (p === "/deadlines" && result) this._rememberDues(result.items);
        if (p === "/sdo/grades" && result) this._grades(result.courses);
        if (p.startsWith("/sdo/grades/") && result) this._course(result);
        if (p.startsWith("/target/2/")) this.unlock("teacher");
        if (/^\/files\/\d+\/page\//.test(p)) this.unlock("found");
      } else if (method === "POST") {
        if (p === "/sdo/connect") this.unlock("sdo");
        if (p.startsWith("/sdo/goal/")) this.unlock("goal");
        if (p === "/chat") this.unlock("ai");
        if (p === "/notify" && body && body.prefs && typeof body.prefs === "object") {
          const pr = body.prefs;
          if (pr.lessons === true || Object.entries(pr).some(([k, v]) => k.startsWith("remind_") && Number.isInteger(v))) this.unlock("remind");
        }
        if (p === "/sdo/submit" && body) this._submitted(body.deadline_id);
      }
    } catch (e) { /* ачивка — не главное */ }
  },
  _rememberDues(items) {
    if (!Array.isArray(items)) return;
    for (const d of items) if (d && Number.isInteger(d.id) && d.due_date) this._dues[d.id] = String(d.due_date);
  },
  _submitted(id) {
    this.unlock("submit");
    const due = this._dues[id];
    if (!due || !/^\d{4}-\d{2}-\d{2}/.test(due)) return;
    const left = Math.round((Date.parse(due.slice(0, 10) + "T12:00:00Z") - Date.parse(isoDay() + "T12:00:00Z")) / 864e5);
    if (left >= 3) this.unlock("early");
    const calm = left >= 1 ? (+Prefs.get("uib_ach_calm", 0) || 0) + 1 : 0;
    Prefs.set("uib_ach_calm", calm);
    if (calm >= 3) this.unlock("calm");
  },
  _allPassed(c) { return Number.isInteger(c.works_total) && c.works_total > 0 && c.works_passed === c.works_total; },
  _grades(courses) {
    if (!Array.isArray(courses) || !courses.length) return;
    this.unlock("sdo");
    let was = {};
    try { was = JSON.parse(Prefs.get("uib_ach_scores") || "{}") || {}; } catch (e) {}
    const cur = {};
    let plus = false;
    for (const c of courses) {
      if (!c || typeof c.score !== "number") continue;
      const id = String(c.id);
      cur[id] = c.score;
      if (typeof was[id] === "number" && c.score > was[id]) plus = true;
      if (this._allPassed(c)) this.unlock("clean");
    }
    Prefs.set("uib_ach_scores", JSON.stringify(cur));
    if (plus) this.unlock("plus");
  },
  _course(c) {
    const goal = c.goal;
    if (goal && goal.mode === "auto" && goal.status === "done") this.unlock("auto");
    if (this._allPassed(c)) this.unlock("clean");
    const lectures = (c.attendance && Array.isArray(c.attendance.lectures)) ? c.attendance.lectures : [];
    let run = 0;
    for (const l of lectures) {
      const st = l && l.status;
      if (st === "future" || st === "wait") continue; // ещё не известно — серию не рвёт
      run = st === "ok" ? run + 1 : 0;
      if (run >= 4) { this.unlock("streak"); return; }
    }
  },
};

// shell.js: Ach.unlock(id) → сюда; Ach.done — тот же список (id → ISO).
Ach.unlock = (id) => AcStore.unlock(id);
try {
  Object.defineProperty(Ach, "done", { configurable: true, get() {
    const o = {};
    for (const [k, v] of Object.entries(AcStore.got)) o[k] = new Date(v).toISOString();
    return o;
  } });
} catch (e) {}
Ach.capyTouched = (at) => AcStore.capyTouched(at);

// ── Обёртка над Api: ачивки по ответам и «Расписание без входа» (guest.dart) ──
const _acGet = Api.get.bind(Api), _acPost = Api.post.bind(Api);
const _acPut = Api.put.bind(Api), _acDel = Api.del.bind(Api);
const acNeedLogin = () => new ApiError("Войди, чтобы открыть это", 401);
Api.get = async function (path) {
  if (!Api.token && !/^\/(auth\/|meta|legal\/)/.test(path)) {
    // без входа: только публичный поиск и расписание через /guest/…
    if (path === "/pins") return { items: [] };
    if (path.startsWith("/search") || path.startsWith("/target/")) return _acGet("/guest" + path);
    throw acNeedLogin();
  }
  const r = await _acGet(path);
  if (Api.token && !Api.offline) AcStore.onApi("GET", path, null, r);
  return r;
};
Api.post = async function (path, body = {}) {
  if (!Api.token && !path.startsWith("/auth/")) throw acNeedLogin();
  const r = await _acPost(path, body);
  if (Api.token) AcStore.onApi("POST", path, body, r);
  return r;
};
Api.put = function (path, body = {}) { if (!Api.token) return Promise.reject(acNeedLogin()); return _acPut(path, body); };
Api.del = function (path) { if (!Api.token) return Promise.reject(acNeedLogin()); return _acDel(path); };

// ── Заход (shell.dart: _visit, PlusBonus.sendRef): после входа и при возврате ──
async function acVisit() {
  if (!Api.token) return;
  try {
    AcStore.visit(now());
    await AcStore.sync();
    if (typeof PlusBonus !== "undefined") await PlusBonus.checkAll();
  } catch (e) {}
}
(() => {
  const build = Tabs.build.bind(Tabs);
  Tabs.build = function () {
    build();
    acVisit();
    Api.get("/me").then((me) => { acName = String((me && me.first_name) || "").trim(); }).catch(() => {});
    Api.get("/meta").then((m) => acSetBot(m && m.links && m.links.bot)).catch(() => {});
    if (typeof PlusBonus !== "undefined") PlusBonus.sendRef();
  };
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Tabs.screens.length) acVisit(); });
})();

// ── Значок ранга (RankBadge) ─────────────────────────────────────────────

/** Общие фильтр и маски для неба (один раз на страницу). */
function acDefs() {
  if (document.getElementById("ac-defs")) return;
  const d = document.createElement("div");
  d.innerHTML = `<svg id="ac-defs" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <filter id="ac-blur" filterUnits="userSpaceOnUse" x="-60" y="-60" width="220" height="220"><feGaussianBlur stdDeviation="8"/></filter>
    <mask id="ac-moon-b" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100"><rect width="100" height="100" fill="#fff"/><circle cx="68" cy="24" r="11.04" fill="#000"/></mask>
    <mask id="ac-moon-p" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100"><rect width="100" height="100" fill="#fff"/><circle cx="71.5" cy="19.75" r="8.28" fill="#000"/></mask>
  </defs></svg>`;
  document.body.appendChild(d.firstElementChild);
}
/** Повторяемые звёзды на фото (как Random(13) в ui.dart — свой посев). */
function acStars() {
  let s = 13;
  const rnd = () => { s |= 0; s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const out = [];
  for (let i = 0; i < 26; i++) out.push([100 * rnd(), 70 * rnd(), 100 * (0.003 + 0.004 * rnd())]);
  return out;
}
const AC_STARS = acStars();
/** Солнце, закат или луна со звёздами — SVG 100×100 (_drawLight). */
function acLight(rank, badge) {
  const blur = 'filter="url(#ac-blur)"';
  switch (rank) {
    case "dawn": return `<circle cx="50" cy="100" r="30" fill="#FFE1A6" ${blur}/><circle cx="50" cy="100" r="23" fill="#FFF4D6"/>`;
    case "noon": {
      const [x, y, k] = badge ? [75, 23, 13] : [78, 20, 9];
      return `<circle cx="${x}" cy="${y}" r="${k + 4}" fill="#FFF3B0" fill-opacity=".667" ${blur}/><circle cx="${x}" cy="${y}" r="${k}" fill="#FFF3B0"/>`;
    }
    case "dusk": {
      const y = badge ? 72 : 78;
      return `<circle cx="50" cy="${y}" r="26" fill="#FF9A5A" fill-opacity=".6" ${blur}/><circle cx="50" cy="${y}" r="20" fill="#FFCF7A"/>`;
    }
    default: {
      const stars = badge
        ? [[25, 25, 1], [60, 15, 0.7], [18, 60, 0.6], [85, 55, 0.6]].map(([x, y, k]) => `<circle cx="${x}" cy="${y}" r="${1.8 * k}" fill="#fff"/>`).join("")
        : AC_STARS.map(([x, y, r]) => `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${r.toFixed(2)}" fill="#fff"/>`).join("");
      const [x, y, k] = badge ? [74, 27, 12] : [76, 22, 9];
      return stars + `<circle cx="${x}" cy="${y}" r="${k}" fill="#FFE9A8" mask="url(#ac-moon-${badge ? "b" : "p"})"/>`;
    }
  }
}
function acSky(r) { return `linear-gradient(to bottom, ${r.sky[0]}, ${r.sky[1]}, ${r.sky[2]})`; }
/** Круглый значок: небо, свет и капибара; закрытая — серая; закрытая полночная — «?». */
function acBadge(rankId, size = 64, open = true) {
  acDefs();
  const r = acRank(rankId);
  if (!open && r.id === "midnight") {
    return `<span class="ac-badge q" style="width:${size}px;height:${size}px" aria-label="Не открыта"><span style="font-size:${size * 0.4}px">?</span></span>`;
  }
  const c = size * 0.58;
  return `<span class="ac-badge${open ? "" : " off"}" style="width:${size}px;height:${size}px;background:${acSky(r)}" aria-label="${open ? r.title : "Не открыта"}">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none">${acLight(r.id, true)}</svg>
    ${r.id === "midnight" ? `<span class="ac-ring" style="--rw:${size * 0.045}px"></span>` : ""}
    <i class="capy" style="--img:url(/img/capy/${r.pose}.png);width:${c}px;height:${c}px;color:${r.ink};position:absolute;top:${size * 0.3}px;left:${(size - c) / 2}px"></i>
  </span>`;
}

// ── Полароид (Polaroid) ──────────────────────────────────────────────────

function acFilmStamp(ms) {
  const t = msk(new Date(ms)), two = (v) => String(v).padStart(2, "0");
  return `'${two(t.y % 100)} ${two(t.m)} ${two(t.d)} ${two(t.h)}:${two(t.min)}`;
}
function acPolaroid(a, at) {
  const r = acRank(a.rank);
  const caption = AC_CAPTIONS[a.id] || a.title;
  const who = [acName, `${AcStore.count()} из ${AC_ACH.length}`].filter(Boolean).join(" · ");
  return `<div class="ac-pol">
    <div class="ac-pol-card">
      <div class="ac-pol-photo" style="background:${acSky(r)}">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">${acLight(r.id, false)}</svg>
        <i class="capy" style="--img:url(/img/capy/${r.pose}.png);width:170px;height:170px;color:${r.ink};position:absolute;left:51px;top:79px"></i>
        <span class="ac-sticker" style="background:${r.sticker}">${esc(r.title.toUpperCase())}</span>
        <span class="ac-stamp">${esc(acFilmStamp(at))}</span>
      </div>
      <div class="ac-caption" id="polaroid-caption">${esc(caption)}</div>
      <div class="ac-pol-foot"><span class="ell grow">${esc(who)}</span><span>${esc(acBot)}</span></div>
    </div>
    <i class="ac-tape"></i>
  </div>`;
}

/** Полароид картинкой PNG (для «Поделиться»): рисуем то же на canvas ×3. */
async function acPolaroidPng(a, at) {
  const r = acRank(a.rank), K = 3, W = 300;
  try { await Promise.all([document.fonts.load("30px Neucha"), document.fonts.load("800 11px Onest"), document.fonts.load("700 14px Onest")]); } catch (e) {}
  const caption = AC_CAPTIONS[a.id] || a.title;
  const meas = document.createElement("canvas").getContext("2d");
  meas.font = "30px Neucha";
  // подпись до двух строк по ширине
  const words = caption.split(" "), lines = [];
  let line = "";
  for (const w of words) {
    const tr = line ? line + " " + w : w;
    if (meas.measureText(tr).width > 260 && line) { lines.push(line); line = w; } else line = tr;
  }
  if (line) lines.push(line);
  lines.length = Math.min(lines.length, 2);
  const capH = 31.5 * lines.length;
  const H = 10 + 14 + 272 + 10 + capH + 10 + 15 + 16 + 6;
  const cv = document.createElement("canvas");
  cv.width = W * K; cv.height = H * K;
  const g = cv.getContext("2d");
  g.scale(K, K);
  // карточка с тенью
  g.save();
  g.shadowColor = "rgba(0,0,0,.33)"; g.shadowBlur = 30; g.shadowOffsetY = 14;
  g.fillStyle = "#FDFBF6";
  g.beginPath(); g.roundRect(0, 10, W, H - 16, 6); g.fill();
  g.restore();
  // фото: небо, свет, капибара
  const px = 14, py = 24, ps = 272;
  g.save();
  g.beginPath(); g.roundRect(px, py, ps, ps, 3); g.clip();
  const sky = g.createLinearGradient(0, py, 0, py + ps);
  r.sky.forEach((c, i) => sky.addColorStop(i / 2, c));
  g.fillStyle = sky; g.fillRect(px, py, ps, ps);
  const S = ps / 100;
  const circle = (x, y, rad, color, glow = 0) => {
    if (glow) {
      const gr = g.createRadialGradient(px + x * S, py + y * S, 0, px + x * S, py + y * S, (rad + glow * 1.6) * S);
      gr.addColorStop(0, color); gr.addColorStop(Math.max(0, (rad - glow * 1.2) / (rad + glow * 1.6)), color); gr.addColorStop(1, "rgba(0,0,0,0)");
      g.fillStyle = gr;
      g.beginPath(); g.arc(px + x * S, py + y * S, (rad + glow * 1.6) * S, 0, 7); g.fill();
      return;
    }
    g.fillStyle = color; g.beginPath(); g.arc(px + x * S, py + y * S, rad * S, 0, 7); g.fill();
  };
  if (r.id === "dawn") { circle(50, 100, 30, "#FFE1A6", 8); circle(50, 100, 23, "#FFF4D6"); }
  if (r.id === "noon") { circle(78, 20, 13, "rgba(255,243,176,.667)", 8); circle(78, 20, 9, "#FFF3B0"); }
  if (r.id === "dusk") { circle(50, 78, 26, "rgba(255,154,90,.6)", 8); circle(50, 78, 20, "#FFCF7A"); }
  if (r.id === "midnight") {
    AC_STARS.forEach(([x, y, rad]) => circle(x, y, rad, "#fff"));
    const m = document.createElement("canvas"); m.width = ps * K; m.height = ps * K;
    const mg = m.getContext("2d"); mg.scale(K * S, K * S);
    mg.fillStyle = "#FFE9A8"; mg.beginPath(); mg.arc(76, 22, 9, 0, 7); mg.fill();
    mg.globalCompositeOperation = "destination-out"; mg.beginPath(); mg.arc(71.5, 19.75, 8.28, 0, 7); mg.fill();
    g.drawImage(m, px, py, ps, ps);
  }
  try {
    const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = `/img/capy/${r.pose}.png`; });
    const t = document.createElement("canvas"); t.width = 170 * K; t.height = 170 * K;
    const tg = t.getContext("2d");
    const k = Math.min(170 / img.width, 170 / img.height), w = img.width * k, h = img.height * k;
    tg.drawImage(img, (170 - w) / 2 * K, (170 - h) / 2 * K, w * K, h * K);
    tg.globalCompositeOperation = "source-in"; tg.fillStyle = r.ink; tg.fillRect(0, 0, t.width, t.height);
    g.drawImage(t, px + 51, py + 79, 170, 170);
  } catch (e) {}
  // наклейка ранга
  g.save();
  g.translate(px + 10, py + 10); g.rotate(-6 * Math.PI / 180);
  g.font = "800 11px Onest";
  const st = r.title.toUpperCase().split("").join(String.fromCharCode(8202));
  const sw = g.measureText(st).width + 16;
  g.fillStyle = r.sticker; g.beginPath(); g.roundRect(0, 0, sw, 21, 10.5); g.fill();
  g.fillStyle = "#141823"; g.textBaseline = "middle"; g.fillText(st, 8, 11);
  g.restore();
  // дата как на плёнке
  g.font = "700 14px Onest";
  const stamp = acFilmStamp(at), tw = g.measureText(stamp).width + 12 + 1.2 * stamp.length;
  g.fillStyle = "rgba(20,10,5,.55)"; g.beginPath(); g.roundRect(px + ps - 8 - tw, py + ps - 8 - 24, tw, 24, 4); g.fill();
  g.save(); g.shadowColor = "rgba(255,122,26,.6)"; g.shadowBlur = 6; g.fillStyle = "#FF9A3C"; g.textBaseline = "middle";
  let sx = px + ps - 8 - tw + 6;
  for (const ch of stamp) { g.fillText(ch, sx, py + ps - 8 - 12); sx += g.measureText(ch).width + 1.2; }
  g.restore();
  g.restore();
  // подпись маркером
  g.save();
  const cy = py + ps + 10;
  g.translate(px + 6, cy + capH / 2); g.rotate(-3 * Math.PI / 180);
  g.font = "30px Neucha"; g.fillStyle = "#1D3B8F"; g.textBaseline = "middle";
  lines.forEach((l, i) => g.fillText(l, 0, (i - (lines.length - 1) / 2) * 31.5));
  g.restore();
  // кто и бот
  g.font = "12px Onest"; g.fillStyle = "#7D776B"; g.textBaseline = "middle";
  const fy = cy + capH + 10 + 8;
  const bw = g.measureText(acBot).width;
  g.fillText(acBot, W - 18 - bw, fy);
  let who = [acName, `${AcStore.count()} из ${AC_ACH.length}`].filter(Boolean).join(" · ");
  while (who.length > 3 && g.measureText(who).width > W - 36 - bw - 8) who = who.slice(0, -2) + "…";
  g.fillText(who, 18, fy);
  // скотч
  g.save(); g.translate(W / 2, 11); g.rotate(-4 * Math.PI / 180);
  g.shadowColor = "rgba(0,0,0,.13)"; g.shadowBlur = 2; g.shadowOffsetY = 1;
  g.fillStyle = "rgba(243,217,138,.8)"; g.fillRect(-45, -11, 90, 22);
  g.restore();
  return new Promise((ok) => cv.toBlob(ok, "image/png"));
}

/** «Поделиться» полароидом: Web Share с файлом, иначе — скачать картинку. */
async function acSharePolaroid(a, at) {
  const blob = await acPolaroidPng(a, at);
  if (!blob) throw new Error("нет картинки");
  const name = `kapibara-${a.id}.png`;
  const file = new File([blob], name, { type: "image/png" });
  const text = `Ачивка «${a.title}» в Капибаре · ${acBot}`;
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], text }); } catch (e) { if (e.name !== "AbortError") throw e; }
    return;
  }
  const url = URL.createObjectURL(blob), l = document.createElement("a");
  l.href = url; l.download = name; document.body.appendChild(l); l.click(); l.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

// ── Лист ачивки (AchievementSheet) ───────────────────────────────────────

function acShowAchievement(a) {
  const at = AcStore.got[a.id], open = at !== undefined;
  const how = a.secret && !open ? "Секрет. Как получить — не скажу" : a.how;
  const where = a.place && !(a.secret && !open);
  return Sheet.show(`
    ${open ? `<div class="ac-pol-fit"><div class="ac-pol-pad">${acPolaroid(a, at)}</div></div>` : `<div class="ac-center">${acBadge(a.rank, 96, false)}</div>`}
    <div style="height:var(--l)"></div>
    <div class="ttl" style="--sz:24px;text-align:center">${esc(acRank(a.rank).title + " · " + a.title)}</div>
    <div class="bd mut" style="--sz:15px;text-align:center;margin-top:var(--s)">${esc(how)}</div>
    ${open || where ? '<div style="height:var(--xl)"></div>' : ""}
    ${open ? `<button class="btn primary" style="min-height:50px" data-act="share">${icon("ios_share", "", "font-size:20px")}Поделиться</button>` : ""}
    ${where ? `${open ? '<div style="height:var(--s)"></div>' : ""}<button class="${open ? "ac-ob" : "btn primary"}" id="ach-where" style="min-height:50px" data-act="where">Показать где</button>` : ""}`,
  (body, close) => {
    const fit = body.querySelector(".ac-pol-fit");
    if (fit) {
      const k = Math.min(1, fit.clientWidth / 324);
      fit.style.height = `${(fit.firstElementChild.offsetHeight) * k}px`;
      fit.firstElementChild.style.transform = `scale(${k})`;
    }
    on(body, {
      share: async (b) => {
        tick();
        b.disabled = true;
        try { await acSharePolaroid(a, at); } catch (e) { toast("Не получилось поделиться", "error"); }
        b.disabled = false;
      },
      // «Показать где»: закрыть всё до вкладок, открыть нужную и подсказать
      where: () => {
        tick();
        close();
        while (Sheet.open.length) Sheet.closeTop();
        Nav.popAll();
        Tabs.show(a.place.tab);
        toast(a.place.hint);
      },
    });
  });
}

// ── Плашка «Новая ачивка» (UnlockBanner) ─────────────────────────────────

let _acBanner = null;
function acShowBanner(a) {
  if (_acBanner) _acBanner.remove();
  const r = acRank(a.rank);
  const el = document.createElement("div");
  el.className = "ac-banner";
  el.id = "ach-banner";
  el.setAttribute("role", "status");
  el.innerHTML = `<div class="row">${acBadge(a.rank, 44)}
    <div class="grow"><div class="bd mut" style="--sz:12px">Новая ачивка · ${esc(r.title)}</div>
      <div class="bd b7" style="--sz:16px;margin-top:2px">${esc(a.title)}</div></div>
    <span class="bd b7 acc" style="--sz:14px">Посмотреть</span></div>`;
  const toastUp = () => !!(document.getElementById("toast") || {}).firstElementChild;
  const place = () => el.classList.toggle("up", toastUp());
  place();
  const t = setInterval(place, 250);
  const gone = () => { clearInterval(t); clearTimeout(life); if (_acBanner === el) _acBanner = null; el.classList.add("out"); setTimeout(() => el.remove(), 320); };
  const life = setTimeout(gone, 5200 - 320);
  el.addEventListener("click", () => { gone(); acShowAchievement(a); });
  let y0 = null;
  el.addEventListener("touchstart", (e) => { y0 = e.touches[0].clientY; }, { passive: true });
  el.addEventListener("touchend", (e) => { if (y0 !== null && Math.abs(e.changedTouches[0].clientY - y0) > 20) gone(); y0 = null; });
  document.body.appendChild(el);
  _acBanner = el;
}

// ── Экран «Ачивки» и строка в «Ещё» ──────────────────────────────────────

function acBar(value) { return `<div class="progress" style="height:6px;border-radius:4px"><i style="width:${Math.min(100, value * 100)}%;border-radius:4px"></i></div>`; }

window.openAchievements = function openAchievements() {
  tick();
  Nav.push((body) => {
    const draw = () => {
      const got = AcStore.got, n = Object.keys(got).length;
      const cols = body.clientWidth - 36 >= 520 ? 5 : body.clientWidth - 36 >= 300 ? 3 : 2;
      body.innerHTML = backRow() + screenTitle("Ачивки", { sub: `${n} из ${AC_ACH.length}` })
        + `<div style="padding:0 var(--xl)">${acBar(n / AC_ACH.length)}</div>`
        + AC_RANKS.map((r) => {
          const list = AC_ACH.filter((a) => a.rank === r.id), have = list.filter((a) => a.id in got).length;
          return `<div style="padding:var(--xl) var(--l) 0">
            <div class="row" style="padding:0 var(--s)">${acBadge(r.id, 30)}<div class="ttl grow" style="--sz:22px">${esc(r.title)}</div>
              <span class="bd mut" style="--sz:14px">${have} из ${list.length}</span></div>
            ${r.id === "midnight" ? `<div class="bd mut" style="--sz:13px;padding:var(--xs) var(--s) 0">Секретные: как получить, видно, когда найдёшь</div>` : ""}
            <div class="ac-grid" style="--cols:${cols};margin-top:var(--m)">${list.map((a) => {
              const open = a.id in got;
              return `<button class="tile ac-tile" id="ach-${a.id}" data-act="ach" data-id="${a.id}" aria-label="${esc(a.title)}, ${open ? "открыта" : "не открыта"}">
                ${acBadge(a.rank, 56, open)}<div class="bd b6 clamp2" style="--sz:12.5px;margin-top:var(--s);color:var(--${open ? "text" : "muted"})">${esc(a.title)}</div></button>`;
            }).join("")}</div></div>`;
        }).join("") + '<div style="height:var(--xxl)"></div>';
    };
    draw();
    on(body, { ach: (b) => { tick(); acShowAchievement(acAch(b.dataset.id)); } });
    return AcStore.listen(draw);
  });
};

/** Строка «Ачивки · N из 25» в «Ещё» (AchievementsRow): el — контейнер. */
window.mountAchievementsRow = function mountAchievementsRow(el) {
  const draw = () => {
    const got = AcStore.got, n = Object.keys(got).length;
    const last = Object.entries(got).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([id]) => acAch(id));
    const w = 36 + 18 * Math.max(0, last.length - 1);
    el.innerHTML = `<button class="tile" id="more-achievements" data-act="ac-ach"><div class="row">
      <span class="ac-stack" style="width:${w}px">${last.length ? last.slice().reverse().map((a, i) =>
        `<span class="ac-ringed" style="left:${18 * (last.length - 1 - i)}px">${acBadge(a.rank, 36)}</span>`).join("") : acBadge("dawn", 36, false)}</span>
      <div class="grow"><div class="row" style="gap:0"><span class="bd b7 grow" style="--sz:15px">Ачивки</span>
        <span class="bd mut" style="--sz:13px">${n} из ${AC_ACH.length}</span></div>
        <div style="height:6px"></div>${acBar(n / AC_ACH.length)}</div>
      ${icon("chevron_right", "", "color:var(--muted)")}</div></button>`;
  };
  draw();
  const off = AcStore.listen(() => { if (!el.isConnected) { off(); return; } draw(); });
  el.addEventListener("click", (e) => { if (e.target.closest('[data-act="ac-ach"]')) openAchievements(); });
};

// ── «Рейтинг» (screens/rating.dart) ─────────────────────────────────────

const acXp = (v) => String(Math.trunc(+v || 0));
const AC_PARTS = [["brs", "Баллы БРС"], ["submit", "Сданные работы"], ["early", "Сдано заранее"], ["ach", "Ачивки"], ["file", "Файлы для группы"]];
const acParts = (m) => AC_PARTS.map(([k, t]) => [t, (m && typeof m[k] === "number") ? m[k] : 0]);

function acRulesText(r) {
  const n = Math.trunc(r.min_people ?? 3);
  return `Опыт — за то, что видно в СДО: ${r.brs ?? 1} за каждый балл БРС, ${r.submit ?? 15} за сданную работу и ещё ${r.early ?? 10}, если сдал за сутки до срока; от ${r.ach_min ?? 3} до ${r.ach_max ?? 25} за ачивку (чем выше ранг, тем больше) и ${r.file ?? 2} за файл, который ты выложил группе. Галочка «сделал» опыта не даёт. Опыт группы — сумма опыта её людей; в рейтинг группа попадает, когда опыт есть хотя бы у ${n} ${plural(n, "человека", "человек", "человек")}.`;
}

/** Из чего опыт: «название — полоса — число» (PartsBars). */
function acPartsBars(parts) {
  const top = Math.max(0, ...parts.map((p) => p[1])), sum = parts.reduce((m, p) => m + p[1], 0);
  return parts.map(([t, v]) => `<div style="padding:6px 0"><div class="row" style="gap:0"><span class="bd grow" style="--sz:14px">${esc(t)}</span>
      ${sum > 0 && v > 0 ? `<span class="bd mut" style="--sz:12.5px">${Math.round(v * 100 / sum)}%&nbsp;&nbsp;</span>` : ""}<span class="num" style="--sz:15px">${Math.trunc(v)}</span></div>
    <div class="progress" style="height:6px;margin-top:6px"><i style="width:${top > 0 ? Math.max(0, Math.min(1, v / top)) * 100 : 0}%"></i></div></div>`).join("");
}

/** Место группы двумя крупными цифрами (_GroupCard). */
function acGroupCard(g) {
  const place = g.place, need = Math.trunc(g.need || 0);
  if (place == null) {
    return `<div class="tile" id="rating-wait"><div class="row">${icon("hourglass_empty", "", "color:var(--muted)")}<div class="bd mut grow" style="--sz:14px">${need > 0
      ? `Группа попадёт в рейтинг, когда опыт появится ещё у ${need} ${plural(need, "человека", "человек", "человек")}. Опыт дают сданные работы и баллы БРС.`
      : "Рейтинг пересчитывается раз в несколько минут — загляни чуть позже."}</div></div></div>`;
  }
  const cell = (id, value, of, where) => `<div class="grow" id="${id}"><div class="num" style="--sz:40px">${value == null ? "—" : esc(value)}</div>
    <div class="bd b6" style="--sz:13.5px;margin-top:6px">${esc(where)}</div>
    ${of != null ? `<div class="bd mut" style="--sz:13px">из ${esc(of)} ${plural(Math.trunc(of), "группы", "групп", "групп")}</div>` : ""}</div>`;
  const people = Math.trunc(g.people || 0);
  return `<div class="tile"><div class="row" style="align-items:flex-start;gap:var(--l)">
      ${g.institute ? cell("rating-inst", g.place_inst, g.groups_inst, `место в ${g.institute}`) : ""}
      ${cell("rating-all", place, g.groups_all, "место в университете")}</div>
    <div class="divider" style="margin:var(--m) 0"></div>
    <div class="bd mut" style="--sz:14px">У группы ${acXp(g.xp)} опыта · с опытом ${people} ${plural(people, "человек", "человека", "человек")}</div></div>`;
}

/** Ширина текста подписи оси (11px Onest). */
function acTextW(text, font = "11px Onest") {
  const c = acTextW.c || (acTextW.c = document.createElement("canvas").getContext("2d"));
  c.font = font;
  return c.measureText(text).width;
}
const acScale = (values, invert) => {
  const known = values.filter((v) => typeof v === "number");
  if (!known.length) return { lo: 0, hi: 1, ticks: [] };
  let hi = Math.max(...known);
  const lo = invert ? 1 : 0;
  if (hi - lo < 1) hi = lo + 1;
  const top = Math.round(hi);
  let ticks;
  if (invert && top <= 6) { ticks = []; for (let v = 1; v <= top; v++) ticks.push(v); }
  else ticks = [...new Set([Math.round(lo), Math.round((lo + hi) / 2), top])];
  return { lo, hi, ticks };
};

/** График по неделям (TrendChart): палец — черта и подпись «неделя · значение». */
function acTrend(el, values, labels, invert, format) {
  const n = values.length;
  const lastIdx = () => { for (let i = n - 1; i >= 0; i--) if (values[i] != null) return i; return null; };
  const sc = acScale(values, invert);
  const gutter = sc.ticks.length ? Math.max(...sc.ticks.map((t) => acTextW(String(t)))) + 8 : 0;
  const Hh = 132, pad = 6;
  let hover = null;
  el.innerHTML = `<div class="ac-tr-head"></div><div style="height:var(--s)"></div><div class="ac-tr-plot"></div><div style="height:6px"></div>
    ${n > 1 ? `<div class="row" style="gap:0"><span style="width:${gutter}px;flex:none"></span><span class="bd mut grow" style="--sz:11.5px">${esc(labels[0])}</span><span class="bd mut" style="--sz:11.5px">сейчас</span></div>` : ""}`;
  const head = el.querySelector(".ac-tr-head"), plot = el.querySelector(".ac-tr-plot");
  const delta = (i) => {
    if (invert || i === 0) return "";
    const a = values[i], b = values[i - 1];
    if (a == null || b == null || a === b) return "";
    const d = Math.trunc(a - b);
    return ` · ${d > 0 ? "+" : "−"}${Math.abs(d)} за неделю`;
  };
  const draw = () => {
    const W = plot.clientWidth || 300, plotW = W - gutter;
    const x = (i) => gutter + (n === 1 ? plotW / 2 : i * plotW / (n - 1));
    const y = (v) => { const t = (v - sc.lo) / (sc.hi - sc.lo), h = Hh - pad * 2; return invert ? pad + t * h : Hh - pad - t * h; };
    const shown = hover ?? lastIdx();
    head.innerHTML = shown == null ? "" : `<span class="bd b7" style="--sz:14px">${esc(format(values[shown]))}</span><span class="bd mut" style="--sz:12.5px">&nbsp;&nbsp;${esc(shown === n - 1 ? "сейчас" : "неделя с " + labels[shown])}${esc(delta(shown))}</span>`;
    let s = "";
    for (const v of sc.ticks) {
      const ty = y(v);
      s += `<line x1="${gutter}" y1="${ty}" x2="${W}" y2="${ty}" stroke="var(--line)" stroke-width="1"/>
        <text x="${gutter - 8}" y="${ty}" text-anchor="end" dominant-baseline="central" font-family="Onest" font-size="11" fill="var(--muted)">${v}</text>`;
    }
    if (n && values.some((v) => v != null)) {
      const runs = [];
      for (let i = 0; i < n; i++) {
        if (values[i] == null) continue;
        if (!runs.length || runs[runs.length - 1][runs[runs.length - 1].length - 1] !== i - 1) runs.push([i]); else runs[runs.length - 1].push(i);
      }
      for (const run of runs) {
        const d = run.map((i, k) => `${k ? "L" : "M"}${x(i).toFixed(1)} ${y(values[i]).toFixed(1)}`).join(" ");
        if (!invert && run.length > 1) s += `<path d="${d} L${x(run[run.length - 1]).toFixed(1)} ${Hh} L${x(run[0]).toFixed(1)} ${Hh} Z" fill="url(#ac-tr-fill)"/>`;
        s += `<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
      }
      const dot = (i, r) => `<circle cx="${x(i)}" cy="${y(values[i])}" r="${r + 2}" fill="var(--card-solid)"/><circle cx="${x(i)}" cy="${y(values[i])}" r="${r}" fill="var(--accent)"/>`;
      if (invert) for (let i = 0; i < n; i++) if (values[i] != null) s += dot(i, 3);
      if (hover != null) {
        s += `<line x1="${x(hover)}" y1="0" x2="${x(hover)}" y2="${Hh}" stroke="var(--line)" stroke-width="1.5"/>`;
        if (values[hover] != null) s += dot(hover, 5);
      } else { const l = lastIdx(); if (l != null) s += dot(l, 5); }
    }
    plot.innerHTML = `<svg width="${W}" height="${Hh}" style="display:block;overflow:visible;touch-action:none"><defs><linearGradient id="ac-tr-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".28"/><stop offset="1" stop-color="var(--accent)" stop-opacity=".02"/></linearGradient></defs>${s}</svg>`;
  };
  const touch = (e) => {
    if (!n) return;
    const W = plot.clientWidth, bx = plot.getBoundingClientRect().left;
    const i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - bx - gutter) / (W - gutter) * (n - 1))));
    if (i !== hover) { hover = i; draw(); }
  };
  let down = false;
  plot.addEventListener("pointerdown", (e) => { down = true; try { plot.setPointerCapture(e.pointerId); } catch (_) {} touch(e); });
  plot.addEventListener("pointermove", (e) => { if (down) touch(e); });
  const up = () => { down = false; if (hover !== null) { hover = null; draw(); } };
  plot.addEventListener("pointerup", up);
  plot.addEventListener("pointercancel", up);
  requestAnimationFrame(draw);
}

/** «Как росла группа» и «Из чего опыт группы» — пока у группы есть опыт. */
function acGroupCharts(g) {
  const history = Array.isArray(g.history) ? g.history : [];
  if (!((g.xp || 0) > 0)) return "";
  return (history.length > 1 ? section("Как росла группа") + `<div class="hx"><div class="tile ac-growth" id="rating-growth"></div></div>` : "")
    + section("Из чего опыт группы") + `<div class="hx"><div class="tile" id="rating-parts" style="padding:var(--s) var(--l)">${acPartsBars(acParts(g.parts))}</div></div>`;
}
/** Опыт или место по неделям — переключатель над одним графиком (_Growth). */
function acMountGrowth(root, g) {
  const el = root.querySelector(".ac-growth");
  if (!el) return;
  const h = g.history, inst = g.institute || "";
  const has = (k) => h.some((w) => w[k] != null);
  const modes = [["xp", "Опыт", ""]];
  if (inst && has("place_inst")) modes.push(["place_inst", `В ${inst}`, `в ${inst}`]);
  if (has("place")) modes.push(["place", "В вузе", "в вузе"]);
  let mode = "xp";
  const draw = () => {
    const m = modes.find((x) => x[0] === mode) || modes[0];
    const place = mode !== "xp";
    el.innerHTML = (modes.length > 1 ? `<div class="ac-wrap" style="gap:var(--s)">${modes.map(([k, t]) =>
      `<button class="ac-chip${k === mode ? " on" : ""}" data-m="${k}" id="rating-growth-${k === "xp" ? "xp" : k === "place" ? "place_all" : "place"}">${esc(t)}</button>`).join("")}</div><div style="height:var(--m)"></div>` : "")
      + '<div class="ac-trend"></div>';
    acTrend(el.querySelector(".ac-trend"), h.map((w) => (place ? (w[mode] ?? null) : (w.xp ?? 0))), h.map((w) => String(w.week ?? "")), place,
      (v) => (place ? `${Math.trunc(v)} место ${m[2]}` : `${Math.trunc(v)} опыта`));
  };
  el.addEventListener("click", (e) => { const b = e.target.closest(".ac-chip"); if (b) { tick(); mode = b.dataset.m; draw(); } });
  draw();
}

/** Топ групп (_Board): место, название, опыт; своя — акцентом. */
function acBoard(rows, placeKey) {
  return `<div class="hx"><div class="tile p0">${rows.map((r, i) => {
    const mine = r.mine === true;
    return `${i ? '<div class="divider"></div>' : ""}<button class="row ac-brow" data-act="group" data-id="${r.id ?? ""}" data-name="${esc(r.name || "")}" id="rating-group-${r.id}-${placeKey}">
      <span class="num" style="--sz:17px;width:32px;flex:none;color:var(--${mine ? "accent" : "muted"})">${esc(r[placeKey] ?? "")}</span>
      <span class="bd grow" style="--sz:15px;font-weight:${mine ? 700 : 500};color:var(--${mine ? "accent" : "text"})">${esc(r.name || "")}</span>
      <span class="num" style="--sz:15px;color:var(--muted)">${acXp(r.xp)}</span>${icon("chevron_right", "", "font-size:18px;color:var(--muted);margin-left:4px")}</button>`;
  }).join("")}</div></div>`;
}

function acSwitch(onState, id) { return `<button class="ac-sw${onState ? " on" : ""}" id="${id}" role="switch" aria-checked="${onState}" data-act="${id}"><i></i></button>`; }

/** Строка листом (inputSheet) — с переносами в пояснении. */
function acInputSheet({ title, text, hint = "", initial = "", action = "Сохранить" }) {
  return Sheet.show(`<div class="ttl" style="--sz:24px">${esc(title)}</div>
    <div class="bd mut" style="--sz:15px;margin-top:8px;white-space:pre-line">${esc(text)}</div>
    <div style="height:var(--l)"></div><input class="field" type="text" placeholder="${esc(hint)}" value="${esc(initial)}">
    <div style="height:var(--l)"></div><button class="btn primary" data-act="ok">${esc(action)}</button>`,
  (body, close) => {
    const f = body.querySelector(".field");
    setTimeout(() => f.focus(), 300);
    on(body, { ok: () => close(f.value) });
    f.addEventListener("keydown", (e) => { if (e.key === "Enter") close(f.value); });
  }).then((v) => (typeof v === "string" ? v : null));
}

/** Экран «Рейтинг». → Promise, когда экран закрыт (строка в «Ещё» обновится). */
window.openRating = function openRating() {
  tick();
  return new Promise((resolve) => {
    Nav.push((body) => {
      let me = {};
      const save = async (b) => {
        tick();
        try { await Api.put("/rating/me", b); } catch (e) { toast(errorText(e), "error"); return; }
        reload();
      };
      const reload = acLoad(body, "/rating", (d) => {
        const g = d.group || {}, inst = d.institute_top || [], all = d.university_top || [], people = d.people || [];
        me = d.me || {};
        const show = me.show === true, sAll = me.show_all === true;
        const toggle = (title, sub, onS, id) => `<div class="row" style="padding:var(--m) var(--s) var(--m) var(--l)">
          <div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div><div class="bd mut" style="--sz:12.5px">${esc(sub)}</div></div>${acSwitch(onS, id)}</div>`;
        body.innerHTML = backRow() + screenTitle("Рейтинг", { sub: g.name || "" })
          + `<div class="hx">${acGroupCard(g)}</div>` + acGroupCharts(g)
          + (inst.length ? section(g.institute_name ? g.institute_name : "Институт") + acBoard(inst, "place_inst") : "")
          + (all.length ? section("Весь университет") + acBoard(all, "place") : "")
          + section("Моя группа") + `<div class="hx"><div class="tile p0">
            ${toggle("Показывать меня группе", show ? "группа видит твой ник и опыт (он считается из баллов СДО и сдач)"
              : "включишь — группа увидит твой ник и опыт (он считается из баллов СДО и сдач)", show, "rating-show")}
            <div class="divider"></div>
            ${toggle("Показывать меня всем", sAll ? `все пользователи Капибары видят тебя как «${me.public_nick ?? "Капибара №…"}» и твой опыт`
              : "по отдельному согласию: все увидят твой ник (или «Капибара №…», не имя) и опыт", sAll, "rating-show_all")}
            <div class="divider"></div>
            <button class="row ac-brow" id="rating-nick" data-act="nick"><span class="bd b6" style="--sz:15px">Ник</span>
              <span class="bd mut grow ell" style="--sz:15px;text-align:right">${esc(me.nick || "")}</span>${icon("chevron_right", "", "color:var(--muted)")}</button>
            ${people.map((r) => `<div class="divider"></div><div class="row" style="padding:var(--m) var(--l)">
              <div class="grow"><span class="bd" style="--sz:15px;font-weight:${r.me === true ? 700 : 500}">${esc(r.nick || "")}</span>${r.me === true && r.hidden === true
                ? `<span class="bd mut" style="--sz:12.5px">&nbsp;&nbsp;· видишь только ты</span>` : ""}</div>
              <span class="num" style="--sz:15px;color:var(--muted)">${acXp(r.xp)}</span></div>`).join("")}
          </div></div>`
          + section("Мой опыт") + `<div class="hx"><div class="tile" id="rating-mine" style="padding:var(--s) var(--l) var(--m)">
            ${acPartsBars(acParts(me))}<div style="height:var(--s)"></div><div class="divider"></div>
            <div class="row" style="margin-top:var(--m)"><span class="bd b7 grow" style="--sz:15px">Всего</span><span class="num acc" style="--sz:20px">${acXp(me.total)}</span></div></div></div>`
          + `<div class="bd mut" style="--sz:13px;padding:var(--m) var(--xl) 0">${esc(acRulesText(d.rules || {}))}</div><div style="height:var(--xxl)"></div>`;
        acMountGrowth(body, g);
      });
      on(body, {
        group: (b) => { if (b.dataset.id) { tick(); openGroupRating(+b.dataset.id, b.dataset.name); } },
        "rating-show": () => save({ show: me.show !== true }),
        "rating-show_all": async () => {
          if (me.show_all === true) { save({ show_all: false }); return; }
          tick();
          let doc;
          try { doc = await Api.get("/legal/rating_all"); } catch (e) { toast(errorText(e), "error"); return; }
          const version = await acShowAllSheet(doc, me.public_nick ?? null);
          if (version != null) save({ show_all: true, consent: version });
        },
        nick: async () => {
          tick();
          const v = await acInputSheet({ title: "Ник в рейтинге",
            text: "Можно: 2–24 знака — буквы, цифры, пробел, точка, дефис и _. Слово «капибара» в своём нике тоже можно: «Капибара на паре».\nНельзя: мат и оскорбления, а ещё выдавать себя за сервис, МИРЭА или старост — «Капибара», «Капибара МИРЭА», «Админ», «Поддержка», «Староста».\nНик видит твоя группа, если включишь «Показывать меня группе», и все — если «Показывать меня всем». Пустое поле — имя и первая буква фамилии: так тебя видит только группа, остальные — «Капибара №…».",
            hint: me.nick || "", initial: me.custom_nick === true ? me.nick || "" : "" });
          if (v != null) save({ nick: v });
        },
      });
      return () => resolve();
    });
  });
};

/** Группа из рейтинга по нажатию (GroupRatingScreen). */
window.openGroupRating = function openGroupRating(id, name = "") {
  Nav.push((body) => {
    acLoad(body, `/rating/group/${id}`, (g) => {
      const people = g.people_list || [], hidden = Math.trunc(g.hidden || 0), member = g.member === true, inst = g.institute_name || "";
      body.innerHTML = backRow() + screenTitle(g.name || name, { sub: inst })
        + `<div class="hx">${acGroupCard(g)}</div>` + acGroupCharts(g)
        + section("Люди") + `<div class="hx"><div class="tile p0" id="rating-group-people">
          ${people.map((p, i) => `${i ? '<div class="divider"></div>' : ""}<div class="row" style="padding:var(--m) var(--l)">
            <span class="bd grow" style="--sz:15px;font-weight:${p.me === true ? 700 : 500}">${esc(p.nick || "")}</span>
            <span class="num" style="--sz:15px;color:var(--muted)">${acXp(p.xp)}</span></div>`).join("")}
          ${people.length && hidden > 0 ? '<div class="divider"></div>' : ""}
          ${!people.length || hidden > 0 ? `<div class="bd mut" style="--sz:14px;padding:var(--l)">${!people.length
            ? (member ? "Пока никто не включил «Показывать меня группе»." : "Пока никто из группы не включил «Показывать меня всем».")
            : `Ещё ${hidden} ${plural(hidden, "человек", "человека", "человек")} с опытом не показывают себя.`}</div>` : ""}
        </div></div><div style="height:var(--xxl)"></div>`;
      acMountGrowth(body, g);
    });
  });
};

/** Отдельное согласие на показ всем (ShowAllSheet). → версия текста или null. */
function acShowAllSheet(d, seenAs) {
  let agree = false;
  return Sheet.show(`<div class="ac-sa-list">
      <div class="ttl" style="--sz:24px">${esc(d.title || "")}</div>
      <div class="bd mut" style="--sz:12.5px;margin-top:var(--xs)">Версия ${esc(d.version)} от ${esc(d.date)}</div>
      <div class="ac-seen"><span class="bd mut" style="--sz:14px">Все увидят тебя как <b style="color:var(--text)">${esc(seenAs ?? "Капибара №…")}</b>${seenAs == null ? " — номер случайный, дадим при включении" : ""}</span></div>
      <div class="bd" style="--sz:14px">${esc(d.lead_short ?? d.lead ?? "")}</div>
      ${(d.sections || []).filter((s) => s.sheet === true || d.lead_short == null).map((s) => `<div class="bd b7 mut" style="--sz:13px;margin-top:var(--m)">${esc(s.title)}</div>
        <div style="margin-top:var(--xs)">${(s.blocks || []).map((b) => b.ul ? b.ul.map((it) => `<div class="bd" style="--sz:14px;margin-bottom:var(--xs)">• ${esc(it)}</div>`).join("")
          : `<div class="bd" style="--sz:14px;margin-bottom:var(--xs)">${esc(b.p)}</div>`).join("")}</div>`).join("")}
      ${d.lead_short != null ? `<button class="bd ac-link" id="rating-all-full" style="--sz:14px;margin-top:var(--s);padding:var(--xs) 0;text-align:left" data-act="full">Полный текст согласия — кто оператор, срок, как отозвать</button>` : ""}
    </div>
    <div class="ac-sa-foot">
      <div class="ac-check" role="checkbox" aria-checked="false" id="rating-all-agree" data-act="agree">
        <span class="ac-box"></span><span class="bd" style="--sz:14px">Даю <a class="ac-link" data-act="full">согласие на показ ника и опыта всем пользователям Капибары</a></span></div>
      <div style="height:var(--m)"></div>
      <button class="btn primary" id="rating-all-on" style="min-height:50px" data-act="ok" disabled>Включить</button>
      <button class="btn text" style="min-height:46px" data-act="no"><span class="bd mut" style="--sz:15px">Отмена</span></button>
    </div>`,
  (body, close, sh) => {
    sh.classList.add("ac-sa");
    const box = body.querySelector(".ac-box"), ok = body.querySelector('[data-act="ok"]'), chk = body.querySelector(".ac-check");
    on(body, {
      full: () => openLegal("rating_all"),
      agree: () => { tick(); agree = !agree; box.classList.toggle("on", agree); box.innerHTML = agree ? icon("check") : ""; chk.setAttribute("aria-checked", agree); ok.disabled = !agree; },
      ok: () => { if (agree) close(String(d.version)); },
      no: () => close(null),
    });
  }).then((v) => (typeof v === "string" ? v : null));
}

/** Строка «Рейтинг» в «Ещё» (RatingRow): el — контейнер; после экрана — заново. */
window.mountRatingRow = function mountRatingRow(el) {
  const line = (d) => {
    const g = d && d.group;
    if (!g || g.place == null) return "места групп в институте и вузе";
    return g.institute && g.place_inst != null ? `${g.place_inst} место в ${g.institute} · ${g.place} в вузе` : `${g.place} место в вузе`;
  };
  const draw = (d) => {
    el.innerHTML = `<button class="tile" id="more-rating" data-act="ac-rating"><div class="row">${icon("leaderboard", "o", "color:var(--accent)")}
      <div class="grow"><div class="bd b7" style="--sz:15px">Рейтинг</div><div class="bd mut" style="--sz:13px">${esc(line(d))}</div></div>
      ${icon("chevron_right", "", "color:var(--muted)")}</div></button>`;
  };
  const load = () => Api.get("/rating").then(draw, () => draw(null));
  draw(null);
  load();
  el.addEventListener("click", async (e) => {
    if (!e.target.closest('[data-act="ac-rating"]')) return;
    await openRating();
    if (el.isConnected) load();
  });
};
