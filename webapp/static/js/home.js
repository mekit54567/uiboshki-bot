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
  const rest = [l.room ? "📍 " + l.room : "", l.teacher].filter(Boolean).map(escapeHtml);
  return (l.kind ? kindDot(l.kind) + escapeHtml(l.kind) + (rest.length ? " · " : "") : "") + rest.join(" · ");
}

function lessonRow(l, withStatus) {
  const cls = withStatus && l.status ? " " + l.status : "";
  const now = withStatus && l.status === "now" ? '<div class="l-now">● идёт сейчас</div>' : "";
  const pairs = l.pairs > 1 ? " · " + l.pairs + " пары подряд" : "";
  return '<div class="lesson' + cls + '">' +
    '<div class="l-time"><b>' + escapeHtml(l.start) + '</b><span>' + escapeHtml(l.end) + '</span></div>' +
    '<div class="l-body"><div class="l-title">' + escapeHtml(l.title) + '</div>' +
    '<div class="l-meta">' + lessonMeta(l) + escapeHtml(pairs) + '</div>' +
    (l.groups ? '<div class="l-groups">👥 ' + escapeHtml(l.groups) + '</div>' : '') + now + '</div>' +
    '<div class="l-num">' + escapeHtml(String(l.num)) + '</div></div>';
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
  document.getElementById("today-lessons").innerHTML = todayData.lessons.length
    ? todayData.lessons.map(l => lessonRow(l, true)).join("")
    : '<div class="empty">' + (todayData.schedule_ok ? "Сегодня пар нет 🎉" : "Расписание сейчас не загрузилось") + '</div>';
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
    const head = d.lessons.length ? "На сегодня всё 🎉" : "Сегодня пар нет 🎉";
    hero.innerHTML = '<div class="h-eyebrow">' + head + '</div>' + (t
      ? '<div class="h-big">завтра в ' + escapeHtml(t.start) + '</div><div class="h-title">' + escapeHtml(t.title) +
        '</div><div class="h-meta">' + lessonMeta(t) + '</div>'
      : '<div class="h-big">отдыхай</div><div class="h-meta">завтра тоже без пар</div>');
  }
}

function dueText(days) {
  if (days < 0) return "просрочен";
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  return "через " + days + " дн.";
}

async function loadToday() {
  try {
    const me = await api("/api/me");
    const hour = new Date().getHours();
    document.getElementById("greeting").textContent = greetingFor(hour) + (me.first_name ? ", " + me.first_name : "") + " 👋";
  } catch (e) {
    document.getElementById("subtitle").textContent = "Не удалось авторизоваться: " + e.message;
    return;
  }
  try {
    todayData = await api("/api/today");
    document.getElementById("subtitle").textContent = todayData.weekday + ", " + todayData.label + " · УИБО-03-24";
    if (todayData.weather) {
      const w = document.getElementById("weather");
      w.textContent = todayData.weather; w.style.display = "inline-block";
    }
    const n = todayData.lessons.reduce((a, l) => a + (l.pairs || 1), 0);
    document.getElementById("today-count").textContent = n ? n + " " + plural(n, "пара", "пары", "пар") : "";
    refreshStatuses();
    const dl = todayData.deadlines;
    document.getElementById("today-deadline-count").textContent = dl.active;
    document.getElementById("today-deadline-next").textContent = dl.soon.length
      ? dl.soon[0].subject.slice(0, 40) + " · " + dueText(dl.soon[0].days) : "ничего не горит 🎉";
    document.getElementById("today-notes").innerHTML = todayData.notes.map(x =>
      '<div class="note-card">📌 ' + (x.subject ? "<b>" + escapeHtml(x.subject) + ":</b> " : "") + escapeHtml(x.text) + '</div>').join("");
  } catch (e) {
    const hero = document.getElementById("hero");
    hero.className = "hero calm";
    hero.innerHTML = '<div class="h-eyebrow">Расписание</div><div class="h-title">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
    document.getElementById("today-lessons").innerHTML = "";
  }
  renderDayChips();
}

function plural(n, one, few, many) {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return one;
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
  return many;
}

setInterval(refreshStatuses, 30000);

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
const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function shiftWeek(delta) {
  weekOffset = Math.min(WEEK_MAX, Math.max(WEEK_MIN, weekOffset + delta));
  haptic();
  renderDayChips();
}

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
    try { data = weekCache[mondayIso] = await api("/api/week?start=" + mondayIso); }
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

async function selectDay(btn, silent) {
  document.querySelectorAll("#daychips button").forEach(b => b.classList.toggle("active", b === btn));
  if (!silent) haptic();
  const list = document.getElementById("day-lessons");
  list.innerHTML = '<div class="skel" style="height:64px"></div>';
  try {
    const data = await api("/api/day?date=" + btn.dataset.date);
    if (btn.classList.contains("active")) {
      list.innerHTML = data.lessons.length
        ? data.lessons.map(l => lessonRow(l, !!l.status)).join("")
        : '<div class="empty">' + data.weekday + ' — пар нет 🎉</div>';
    }
  } catch (e) {
    list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
}
