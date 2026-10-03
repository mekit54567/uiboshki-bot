// Главная: сегодня, неделя, точки пар — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Сегодня ───────────────────────────────────────────────────────────────

let todayData = null;

function greetingFor(hour) {
  if (hour >= 5 && hour < 12) return "Доброе утро";
  if (hour >= 12 && hour < 17) return "Добрый день";
  if (hour >= 17 && hour < 23) return "Добрый вечер";
  return "Доброй ночи";
}

function humanMinutes(min) {
  min = Math.max(0, Math.round(min));
  if (min < 60) return min + " мин";
  const h = Math.floor(min / 60), m = min % 60;
  return h + " ч" + (m ? " " + m + " мин" : "");
}

// Цвет типа пары — один и тот же у точек под днями и в карточке пары.
const KIND_COLORS = {
  "лекция": "#a78bfa", "практика": "#4fc3f7", "лабораторная": "#34d399",
  "сам. работа": "#f28b82", "доп. занятие": "#fbbf24",
  "экзамен": "#ff6363", "зачёт": "#ff6363", "консультация": "#ff9f6e",
  "курсовой проект": "#ff9f6e", "курсовая работа": "#ff9f6e",
};

function kindDot(kind) {
  return '<i class="kd" style="background:' + (KIND_COLORS[kind] || "var(--hint)") + '"></i>';
}

function lessonMeta(l) {
  const rest = [l.room ? icon("place", "inl") + escapeHtml(l.room) : "", escapeHtml(l.teacher || "")].filter(Boolean);
  return (l.kind ? kindDot(l.kind) + escapeHtml(l.kind) + (rest.length ? " · " : "") : "") + rest.join(" · ");
}

// tap — пара своей группы в «Эта неделя»: нажал → её текущий контроль в СДО
// (openLessonSdo). В «Сегодня» — нет: там случайно тыкают, листая.
function lessonRow(l, withStatus, tap) {
  const cls = (withStatus && l.status ? " " + l.status : "") + (tap ? " tap" : "");
  const now = withStatus && l.status === "now" ? '<div class="l-now">● идёт сейчас</div>' : "";
  const pairs = l.pairs > 1 ? " · " + l.pairs + " пары подряд" : "";
  return '<div class="lesson' + cls + '"' + (tap ? ' data-t="' + escapeHtml(l.title) + '" onclick="openLessonSdo(this.dataset.t)"' : '') + '>' +
    '<div class="l-time"><b>' + escapeHtml(l.start) + '</b><span>' + escapeHtml(l.end) + '</span></div>' +
    '<div class="l-body"><div class="l-title">' + escapeHtml(l.title) + (tap ? lessonScore(l.title) : '') + '</div>' +
    '<div class="l-meta">' + lessonMeta(l) + escapeHtml(pairs) + '</div>' +
    (l.groups ? '<div class="l-groups">' + icon("users", "inl") + escapeHtml(l.groups) + '</div>' : '') + now + '</div>' +
    '<div class="l-num">' + escapeHtml(String(l.num)) + '</div></div>';
}

// «Сегодня»: пары и дела автопилота (plan.js) одним списком, по времени
function lessonsWithPlan(lessons) {
  const rows = lessons.map(l => ({ at: l.start, html: lessonRow(l, true) }));
  if (typeof todayItems === "function") todayItems().forEach(i => rows.push({ at: planHm(i.start), html: planSlot(i) }));
  rows.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
  return rows.map(r => r.html).join("");
}

// Статусы и отсчёт пересчитываются на клиенте раз в 30 с — главная
// «живая», даже если WebApp долго открыт.
function refreshStatuses() {
  if (!todayData) return;
  const now = Date.now();
  todayData.lessons.forEach(l => {
    if (!l.start_iso) return;
    const s = Date.parse(l.start_iso), e = Date.parse(l.end_iso || l.start_iso);
    l.status = now >= e ? "past" : (now >= s ? "now" : "later");
  });
  renderHero();
  // Пар нет — об этом уже крупно говорит карточка сверху, пустой блок
  // «Сегодня · пар нет» под ней только оставлял дыру (живой тест).
  // дела автопилота на сегодня — между парами, по времени (plan.js)
  const planned = typeof todayItems === "function" ? todayItems().length : 0;
  const noPairs = !todayData.lessons.length && todayData.schedule_ok && !planned;
  const pairs = todayData.lessons.reduce((a, l) => a + (l.pairs || 1), 0);
  document.getElementById("today-count").textContent = [pairs ? pairs + " " + plural(pairs, "пара", "пары", "пар") : "",
    planned ? planned + " " + plural(planned, "дело", "дела", "дел") : ""].filter(Boolean).join(" · ");
  document.getElementById("today-head").style.display = noPairs ? "none" : "";
  document.getElementById("today-lessons").style.display = noPairs ? "none" : "";
  document.getElementById("today-lessons").innerHTML = todayData.lessons.length || planned
    ? lessonsWithPlan(todayData.lessons)
    : '<div class="empty">Расписание сейчас не загрузилось</div>';
}

function renderHero() {
  const hero = document.getElementById("hero");
  const d = todayData, now = Date.now();
  const cur = d.lessons.find(l => l.status === "now");
  const next = d.lessons.find(l => l.status === "later");
  hero.className = "hero";
  if (cur) {
    const s = Date.parse(cur.start_iso), e = Date.parse(cur.end_iso);
    const pct = Math.min(100, Math.max(0, (now - s) / (e - s) * 100));
    hero.innerHTML = '<div class="h-eyebrow">Идёт сейчас · до ' + escapeHtml(cur.end) + '</div>' +
      '<div class="h-big">ещё ' + humanMinutes((e - now) / 60000) + '</div>' +
      '<div class="h-title">' + escapeHtml(cur.title) + '</div><div class="h-meta">' + lessonMeta(cur) + '</div>' +
      '<div class="h-bar"><i style="width:' + pct.toFixed(1) + '%"></i></div>';
  } else if (next) {
    hero.innerHTML = '<div class="h-eyebrow">Следующая пара · ' + escapeHtml(next.start) + '</div>' +
      '<div class="h-big">через ' + humanMinutes((Date.parse(next.start_iso) - now) / 60000) + '</div>' +
      '<div class="h-title">' + escapeHtml(next.title) + '</div><div class="h-meta">' + lessonMeta(next) + '</div>';
  } else {
    hero.className = "hero calm";
    const t = d.tomorrow_first;
    const head = (d.lessons.length ? "На сегодня всё " : "Сегодня пар нет ") + icon("party", "mood");
    hero.innerHTML = '<div class="h-eyebrow">' + head + '</div>' + (t
      ? '<div class="h-big">завтра в ' + escapeHtml(t.start) + '</div><div class="h-title">' + escapeHtml(t.title) +
        '</div><div class="h-meta">' + lessonMeta(t) + '</div>'
      : '<div class="h-big">отдыхай</div><div class="h-meta">завтра тоже без пар</div>');
  }
}

// Ближайший дедлайн на карточке: «чт, 8 окт · через 6 дн.» (дизайн-ревью, п. 15)
function dueText(item) {
  if (item.days < 0) return "просрочен";
  return humanDate(item.due_date, { time: item.due_time });   // «сегодня» — по телефону: сводка может быть из кэша
}

// Мгновенный старт: последняя сводка «сегодня» и точки недели лежат в памяти
// телефона — главная рисуется сразу, свежие данные приходят следом и
// перерисовывают её. Сохранённое показываем только за этот же день.
const HOME_SNAP_KEY = "home.snap";

function readHomeSnap() {
  try {
    const snap = JSON.parse(localStorage.getItem(HOME_SNAP_KEY) || "null");
    return snap && snap.today && snap.today.date === isoDate(new Date()) ? snap : null;
  } catch (e) { return null; }
}

function saveHomeSnap() {
  if (!todayData) return;
  try {
    const week = {};
    Object.keys(weekCache).slice(-2).forEach(k => week[k] = weekCache[k]);
    localStorage.setItem(HOME_SNAP_KEY, JSON.stringify({ today: todayData, week: week }));
  } catch (e) {}
}

function setGreeting(name) {
  const hour = new Date().getHours();
  document.getElementById("greeting").innerHTML = escapeHtml(greetingFor(hour) + (name ? ", " + name : "")) + " " + icon("wave", "mood wave");
}

function showBadge(id, html) {
  const el = document.getElementById(id);
  el.innerHTML = html || "";
  el.style.display = html ? (id === "weather" ? "inline-block" : "inline-flex") : "none";
  // погода, корпус и «МИРЭА не отвечает» — одной строкой с прокруткой вбок,
  // а не столбиком над парами (дизайн-ревью, п. 10)
  const row = document.getElementById("pill-row");
  row.style.display = ["weather", "campus", "stale"].some(i => document.getElementById(i).style.display !== "none") ? "" : "none";
  row.onscroll = pillRowEdge;
  requestAnimationFrame(pillRowEdge);
}

// Затухание справа — только пока есть что листать: в конце последняя плашка видна целиком
function pillRowEdge() {
  const row = document.getElementById("pill-row");
  row.classList.toggle("at-end", row.scrollLeft + row.clientWidth >= row.scrollWidth - 2);
}

function renderToday() {
  document.getElementById("subtitle").textContent = todayData.weekday + ", " + todayData.label + " · " + GROUP_NAME;
  showBadge("weather", todayData.weather ? escapeHtml(todayData.weather) : "");
  // зеркало МИРЭА лежит — расписание сохранённое
  showBadge("stale", todayData.stale ? icon("warning") + " МИРЭА не отвечает · данные от " + escapeHtml(todayData.stale) : "");
  // пары не в своём корпусе — заметно, до первой пары («сегодня МП-1»)
  const campus = (todayData.campus || "").replace(/^Сегодня пары на (.+?) — не на .+$/, "сегодня $1");
  showBadge("campus", campus ? icon("place") + " " + escapeHtml(campus) : "");
  refreshStatuses();     // и число пар (с делами автопилота) в заголовке
  const dl = todayData.deadlines;
  document.getElementById("today-deadline-count").textContent = dl.active;
  document.getElementById("today-deadline-next").innerHTML = dl.soon.length
    ? escapeHtml(dl.soon[0].subject.slice(0, 40) + " · " + dueText(dl.soon[0])) : "ничего не горит " + icon("party", "mood");
  document.getElementById("today-notes").innerHTML = todayData.notes.map(x =>
    '<div class="note-card">' + icon("pin", "inl") + (x.subject ? "<b>" + escapeHtml(x.subject) + ":</b> " : "") + escapeHtml(x.text) + '</div>').join("");
}

let chipsDate = null;   // за какой «сегодня» нарисована полоска дней

async function loadToday() {
  // имя — сразу из Telegram, /api/me (вход и статистика) — параллельно
  const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  setGreeting(user ? user.first_name : "");
  let shown = false;
  if (!todayData) {
    const snap = readHomeSnap();
    if (snap) {
      todayData = snap.today;
      Object.keys(snap.week || {}).forEach(k => { if (!weekCache[k]) weekCache[k] = snap.week[k]; });
      renderToday();
      renderDayChips();
      shown = true;
    }
  }
  const me = api("/api/me").then(m => { setGreeting(m.first_name); return true; }, () => false);
  try {
    todayData = await api("/api/today");
    renderToday();
    saveHomeSnap();
  } catch (e) {
    if (!(await me) && !shown) {
      document.getElementById("subtitle").textContent = "Не удалось авторизоваться: " + e.message;
      return;
    }
    if (shown) { showToast("Нет связи — показываю сохранённое"); return; }
    const hero = document.getElementById("hero");
    hero.className = "hero calm";
    hero.innerHTML = '<div class="h-eyebrow">Расписание</div><div class="h-title">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
    document.getElementById("today-lessons").innerHTML = "";
  }
  if (chipsDate !== (todayData && todayData.date)) renderDayChips();
  else rerenderToday();
}

// Свежие данные пришли, а полоска дней уже стоит на сегодня — перерисовать
// только сегодняшние пары (без нового запроса).
function rerenderToday() {
  const active = document.querySelector("#daychips button.active");
  if (active && todayData && active.dataset.date === todayData.date) renderDay(document.getElementById("day-lessons"), todayData);
}

function plural(n, one, few, many) {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return one;
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
  return many;
}

setInterval(refreshStatuses, 30000);

// ── Плитка «Баллы СДО» (дизайн-ревью, п. 12) ──────────────────────────────
// Вместо плитки «Поиск» (он и так во вкладке внизу): сколько предметов уже
// закрыто на «3»/зачёт и какой ближе всего — те же цифры, что в hero экрана
// СДО (sdo.js: sdoSummary). Журнал грузится после главной и не держит её;
// последнее значение запоминается и показывается сразу при следующем входе.
const SDO_TILE_KEY = "home.sdoTile";

function tileFromGrades(data) {
  const s = sdoSummary((data && data.courses) || []);
  return { state: "ok", closed: s.closed, total: s.total,
    near: s.near ? shortCourse(s.near.title) : "", need: s.near ? s.near.need : 0 };
}

function renderSdoTile(t) {
  const big = document.getElementById("home-sdo-big"), sub = document.getElementById("home-sdo-sub");
  if (!t) {                                   // ещё ни разу не загрузилось
    big.innerHTML = '<span class="skel"></span>'; sub.textContent = "…";
  } else if (t.state === "off") {
    big.innerHTML = icon("cap", "lg"); sub.textContent = "Подключи СДО — увидишь баллы и сколько до зачёта";
  } else if (t.state === "error") {
    big.innerHTML = icon("cap", "lg"); sub.textContent = "нажми, чтобы открыть";
  } else if (!t.total) {
    big.textContent = "—"; sub.textContent = "журналов с баллами пока нет";
  } else {
    big.textContent = t.closed + " из " + t.total;
    sub.innerHTML = t.near ? "ближе всего: " + escapeHtml(t.near) + ", ещё&nbsp;" + fmtNum(t.need) : "все закрыты " + icon("party", "mood");
  }
}

function updateSdoTile(data) {
  const t = data && data.state ? data : tileFromGrades(data);
  renderSdoTile(t);
  try { localStorage.setItem(SDO_TILE_KEY, JSON.stringify(t)); } catch (e) {}
}

function readSdoTile() {
  try { return JSON.parse(localStorage.getItem(SDO_TILE_KEY) || "null"); } catch (e) { return null; }
}

async function loadSdoTile() {
  const saved = readSdoTile();
  try {
    updateSdoTile(await fetchSdoGrades());
  } catch (e) {
    if (/подключи/.test(e.message)) updateSdoTile({ state: "off" });
    else if (!saved || saved.state === "off") renderSdoTile({ state: "error" });   // сеть — тихо, со старым
  }
}

// ── Неделя: выбор дня ─────────────────────────────────────────────────────

const DAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

function isoDate(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

// Неделю можно листать стрелками: на прошлую и на несколько вперёд —
// раньше чипы заканчивались субботой, и глянуть следующий понедельник было
// нельзя (живой тест с телефона).
let weekOffset = 0;
const WEEK_MIN = -1, WEEK_MAX = 8;

function shiftWeek(delta) {
  weekOffset = Math.min(WEEK_MAX, Math.max(WEEK_MIN, weekOffset + delta));
  haptic();
  renderDayChips();
}

// Свайп влево/вправо по дням недели — то же, что стрелки.
(function () {
  let x0 = null, y0 = null;
  document.addEventListener("touchstart", e => {
    if (!e.target.closest || !e.target.closest("#daychips, #day-lessons")) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener("touchend", e => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > 1.5 * Math.abs(dy)) {
      shiftWeek(dx < 0 ? 1 : -1);
      const chips = document.getElementById("daychips");
      if (chips) { chips.classList.remove("swipe-l", "swipe-r"); void chips.offsetWidth; chips.classList.add(dx < 0 ? "swipe-l" : "swipe-r"); }
    }
  }, { passive: true });
})();

function weekLabel(monday, offset) {
  if (offset === 0) return "Эта неделя";
  if (offset === 1) return "Следующая неделя";
  if (offset === -1) return "Прошлая неделя";
  const saturday = new Date(monday); saturday.setDate(monday.getDate() + 5);
  return monday.getDate() + " " + MONTHS_SHORT[monday.getMonth()] + " – " + saturday.getDate() + " " + MONTHS_SHORT[saturday.getMonth()];
}

function dotsHtml(kinds) {
  return kinds.slice(0, 7).map(k => '<i style="background:' + (KIND_COLORS[k] || "var(--hint)") + '"></i>').join("");
}

function renderDayChips() {
  chipsDate = todayData ? todayData.date : null;
  const base = todayData ? new Date(todayData.date + "T12:00:00") : new Date();
  const wd = (base.getDay() + 6) % 7;             // 0 = понедельник
  const monday = new Date(base);
  monday.setDate(base.getDate() - wd + (wd === 6 ? 7 : 0) + weekOffset * 7);  // в воскресенье — следующая неделя
  document.getElementById("wk-label").textContent = weekLabel(monday, weekOffset);
  document.getElementById("wk-prev").disabled = weekOffset <= WEEK_MIN;
  document.getElementById("wk-next").disabled = weekOffset >= WEEK_MAX;
  const box = document.getElementById("daychips");
  box.innerHTML = "";
  let selected = null;
  for (let i = 0; i < 6; i++) {
    const d = new Date(monday); d.setDate(monday.getDate() + i);
    const b = document.createElement("button");
    const iso = isoDate(d);
    b.innerHTML = DAY_SHORT[i] + "<b>" + d.getDate() + '</b><span class="dots"></span>';
    b.dataset.date = iso;
    if (todayData && iso === todayData.date) { b.classList.add("today"); selected = b; }
    b.onclick = () => selectDay(b);
    box.appendChild(b);
  }
  selectDay(selected || box.children[0], true);
  loadWeekDots(isoDate(monday));
}

// Точки под днями (по одной на пару, цвет — тип) и номер учебной недели,
// как в официальном приложении МИРЭА. Неделя грузится одним запросом и
// кэшируется: листать туда-обратно — мгновенно.
const weekCache = {};

async function loadWeekDots(mondayIso) {
  const numEl = document.getElementById("wk-num");
  numEl.textContent = "";
  let data = weekCache[mondayIso];
  if (!data) {
    try { data = weekCache[mondayIso] = await api("/api/week?start=" + mondayIso); saveHomeSnap(); }
    catch (e) { return; }  // без точек полоска дней всё равно работает
  }
  if (!document.querySelector('#daychips button[data-date="' + mondayIso + '"]')) return;  // уже листнули дальше
  numEl.textContent = data.week ? "· " + data.week + " неделя" : "";
  data.days.forEach(day => {
    const box = document.querySelector('#daychips button[data-date="' + day.date + '"] .dots');
    if (!box) return;
    box.innerHTML = dotsHtml(day.dots);
  });
}

// Пары дня кэшируются: переключать дни туда-обратно — мгновенно. Пока
// грузится, список держит прежнюю высоту, чтобы страница не прыгала вверх;
// тап по дню прокручивает к полоске дней — видны все пары дня сразу
// (живой тест: на каждый день приходилось заново листать вниз).
const dayCache = {};

function scrollToWeek() {
  const head = document.getElementById("wk-label").closest("h2");
  const safe = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--safe-top")) || 0;
  const top = head.getBoundingClientRect().top + window.scrollY - safe - 8;
  if (Math.abs(window.scrollY - top) > 4) window.scrollTo({ top: top, behavior: "smooth" });
}

// Баллы СДО у пар «Эта неделя» (sdo.js: lessonScore) приходят позже пар:
// как загрузились — перерисовываем выбранный день.
function rerenderSelectedDay() {
  const list = document.getElementById("day-lessons");
  if (list && lastDayData) renderDay(list, lastDayData);
}

let lastDayData = null;

function renderDay(list, data) {
  lastDayData = data;
  list.innerHTML = data.lessons.length
    ? data.lessons.map(l => lessonRow(l, !!l.status, true)).join("")
    : capyEmpty(data.weekday + " — пар нет", "Отдыхай или догоняй дедлайны");
}

async function selectDay(btn, silent) {
  document.querySelectorAll("#daychips button").forEach(b => b.classList.toggle("active", b === btn));
  if (!silent) haptic();
  const list = document.getElementById("day-lessons");
  const date = btn.dataset.date;
  const today = todayData && date === todayData.date;   // у сегодняшнего дня статусы пар меняются — без кэша
  if (today) {
    renderDay(list, todayData);                          // те же пары, что в /api/today, — без запроса
  } else if (dayCache[date]) {
    renderDay(list, dayCache[date]);
  } else {
    list.style.minHeight = list.offsetHeight + "px";
    list.innerHTML = '<div class="skel" style="height:64px"></div>';
    try {
      const data = await api("/api/day?date=" + date);
      if (!today) dayCache[date] = data;
      if (btn.classList.contains("active")) renderDay(list, data);
    } catch (e) {
      list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
    }
    list.style.minHeight = "";
  }
  if (!silent) scrollToWeek();
  loadLessonScores();
}

// «На экран Домой» (Telegram 8.0+, Bot API addToHomeScreen): ярлык WebApp на
// рабочем столе телефона — открывается сразу приложением.
// Карточка сверху — только если Telegram точно знает, что ярлыка нет
// («missed»); ✕ её прячет. Тихая ссылка внизу «Сегодня» остаётся для тех, кто
// закрыл карточку случайно, и для iPhone, где статус «unknown» — ярлык там
// мог уже быть, и карточка у них висела зря (живой тест).
const HOME_ADD_KEY = "homeAdd.hidden";

function initHomeAdd() {
  if (!(tg && tg.checkHomeScreenStatus && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0"))) return;
  let hidden = false;
  try { hidden = !!localStorage.getItem(HOME_ADD_KEY); } catch (e) {}
  try {
    tg.checkHomeScreenStatus(status => {
      if (status === "missed" && !hidden) document.getElementById("home-add").style.display = "flex";
      else if (status === "missed" || status === "unknown") document.getElementById("home-link").style.display = "block";
    });
    tg.onEvent("homeScreenAdded", () => {
      document.getElementById("home-add").style.display = "none";
      document.getElementById("home-link").style.display = "none";
      haptic("success");
      showToast("📲 Готово — ярлык на экране «Домой»");
    });
  } catch (e) {}
}

function addToHome() {
  haptic();
  try { tg.addToHomeScreen(); } catch (e) { showToast("Telegram не дал добавить — обнови приложение"); }
}

function hideHomeAdd() {
  haptic();
  document.getElementById("home-add").style.display = "none";
  document.getElementById("home-link").style.display = "block";
  try { localStorage.setItem(HOME_ADD_KEY, "1"); } catch (e) {}
}


// Предметы по выбору (военная кафедра): пары скрыты, пока человек не
// скажет «хожу». Спрашиваем карточкой на главной — кто ходит, сразу видит,
// что про него не забыли. Поменять ответ — только командой /optional в боте
// (ссылка на главной лишь мешала остальным).
let optionalState = { pending: [], answers: {} };

async function initOptional() {
  try { optionalState = await api("/api/optional"); } catch (e) { return; }
  renderOptional();
}

function renderOptional() {
  const ask = document.getElementById("optional-ask");
  ask.innerHTML = optionalState.pending.map((s, i) =>
    '<div class="opt-card"><div class="txt"><b>' + icon("medal", "inl") + escapeHtml(s) + '</b>Ходишь? Если нет — уберём эти пары из твоего расписания.</div>' +
    '<div class="btns"><button onclick="answerOptional(' + i + ', true, true)">Хожу</button>' +
    '<button class="no" onclick="answerOptional(' + i + ', false, true)">Не хожу</button></div></div>').join("");
}

async function answerOptional(i, attend, fromPending) {
  const subject = fromPending ? optionalState.pending[i] : Object.keys(optionalState.answers)[i];
  if (!subject) return;
  haptic("success");
  try {
    await api("/api/optional", { method: "POST", body: JSON.stringify({ subject: subject, attend: attend }) });
  } catch (e) { showToast("Не сохранилось: " + e.message); return; }
  optionalState.pending = optionalState.pending.filter(s => s !== subject);
  optionalState.answers[subject] = attend;
  renderOptional();
  showToast(attend ? "🎖 Пары «" + subject + "» будут в расписании" : "Убрал «" + subject + "» из расписания");
  Object.keys(weekCache).forEach(k => delete weekCache[k]);
  Object.keys(dayCache).forEach(k => delete dayCache[k]);
  loadToday();
}
