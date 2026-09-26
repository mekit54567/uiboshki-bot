// Поиск расписания: группы, преподаватели, аудитории, закреплённые — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Поиск расписания: преподаватель / группа / аудитория ──────────────────

const TARGET_KIND = { 1: ["👥", "Группа"], 2: ["👤", "Преподаватель"], 3: ["🚪", "Аудитория"] };
let targetType = 0;
let targetTimer = null;
let targetSeq = 0;

document.querySelectorAll("#target-types button").forEach(b => b.addEventListener("click", () => {
  targetType = Number(b.dataset.type);
  document.querySelectorAll("#target-types button").forEach(x => x.classList.toggle("active", x === b));
  haptic();
  searchTargets(document.getElementById("target-search").value);
}));

document.getElementById("target-search").addEventListener("input", (e) => {
  clearTimeout(targetTimer);
  targetTimer = setTimeout(() => searchTargets(e.target.value), 250);
});

function targetItem(t) {
  const kind = TARGET_KIND[t.type] || ["📅", ""];
  return '<div class="target-item" onclick="openTarget(' + t.type + ',' + t.id + ',' + escapeHtml(JSON.stringify(t.title)) + ')">' +
    '<span class="ic">' + kind[0] + '</span>' +
    '<div style="min-width:0"><div class="tt">' + escapeHtml(t.title) + '</div><div class="ts">' + kind[1] +
    (t.hint ? ' · ' + escapeHtml(t.hint) : '') + '</div></div>' +
    '<span class="go">›</span></div>';
}

async function searchTargets(q) {
  const list = document.getElementById("target-list");
  q = (q || "").trim();
  document.getElementById("target-recent").style.display = q ? "none" : "block";
  if (q.length < 2) { list.innerHTML = ""; renderRecent(); return; }
  const seq = ++targetSeq;
  list.innerHTML = '<div class="empty">Ищу…</div>';
  try {
    const data = await api("/api/search?q=" + encodeURIComponent(q) + "&type=" + targetType);
    if (seq !== targetSeq) return;  // пришёл ответ на старый запрос — пользователь уже печатает дальше
    if (!data.items.length) {
      list.innerHTML = '<div class="empty">' + (data.ready
        ? "Ничего не нашлось"
        : "Справочник ещё собирается (первый запуск, около получаса) — попробуй чуть позже") + '</div>';
      return;
    }
    list.innerHTML = data.items.map(targetItem).join("");
  } catch (e) {
    if (seq === targetSeq) list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
}

function recentTargets() {
  try { return JSON.parse(localStorage.getItem("recentTargets") || "[]"); } catch (e) { return []; }
}

function rememberTarget(t) {
  try {
    const rest = recentTargets().filter(x => !(x.type === t.type && x.id === t.id));
    localStorage.setItem("recentTargets", JSON.stringify([t].concat(rest).slice(0, 6)));
  } catch (e) {}
}

// Закреплённые — на сервере (видны с любого устройства), недавние — на
// этом устройстве. Закреплённые сверху и в «Недавних» не повторяются.
let pinnedTargets = [];

async function loadPins() {
  try { pinnedTargets = (await api("/api/pins")).items; } catch (e) {}
}

function isPinned(type, id) {
  return pinnedTargets.some(p => p.type === type && p.id === id);
}

function renderRecent() {
  const box = document.getElementById("target-recent");
  const recents = recentTargets().filter(t => !isPinned(t.type, t.id));
  let html = "";
  if (pinnedTargets.length) {
    html += '<p class="recent-title">📌 Закреплённые</p><div class="list">' + pinnedTargets.map(targetItem).join("") + '</div>';
  }
  if (recents.length) {
    html += '<p class="recent-title"' + (pinnedTargets.length ? ' style="margin-top:18px"' : '') + '>Недавние</p>' +
      '<div class="list">' + recents.map(targetItem).join("") + '</div>';
  }
  box.innerHTML = html ||
    '<div class="empty">Начни вводить фамилию преподавателя, номер группы или аудитории — например «Морозов» или «УИБО-03». Нужное можно закрепить 📌</div>';
}

// Экран расписания группы / преподавателя / аудитории — как главная:
// недели листаются, под днями точки пар, пары карточками. Сервер отдаёт
// сразу 8 недель, так что листать — без запросов.
const DAY_SHORT7 = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const DAY_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
let targetCurrent = null;   // {type, id, title}
let targetData = null;
let targetWeekIdx = 0;
let targetSelected = null;  // ISO-дата выбранного дня

function setPinButton(on) {
  const btn = document.getElementById("target-pin");
  btn.classList.toggle("on", on);
  btn.setAttribute("aria-label", on ? "Открепить" : "Закрепить");
}

async function openTarget(type, id, title) {
  haptic();
  rememberTarget({ type: type, id: id, title: title });
  targetCurrent = { type: type, id: id, title: title };
  targetData = null;
  const kind = TARGET_KIND[type] || ["📅", ""];
  document.getElementById("search-pane").style.display = "none";
  document.getElementById("target-view").style.display = "block";
  document.getElementById("target-ic").textContent = kind[0];
  document.getElementById("target-kind").textContent = kind[1];
  document.getElementById("target-title").textContent = title;
  setPinButton(isPinned(type, id));
  document.getElementById("tw-label").textContent = "Эта неделя";
  document.getElementById("tw-num").textContent = "";
  document.getElementById("target-days").innerHTML = "";
  document.getElementById("target-lessons").innerHTML =
    '<div class="skel" style="height:64px"></div><div class="skel" style="height:64px"></div>';
  window.scrollTo(0, 0);
  if (tg && tg.BackButton) { tg.BackButton.offClick(closeTarget); tg.BackButton.onClick(closeTarget); tg.BackButton.show(); }
  try {
    const data = await api("/api/target/" + type + "/" + id);
    if (!targetCurrent || targetCurrent.type !== type || targetCurrent.id !== id) return;  // уже ушли с экрана
    targetData = data;
    targetWeekIdx = 0;
    if (data.pinned !== isPinned(type, id)) {   // сервер главнее: закрепили с другого устройства
      pinnedTargets = pinnedTargets.filter(p => !(p.type === type && p.id === id));
      if (data.pinned) pinnedTargets.push({ type: type, id: id, title: title });
    }
    setPinButton(data.pinned);
    openNextLessonDay();
    renderTargetWeek();
  } catch (e) {
    document.getElementById("target-lessons").innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
}

// Сегодня, а если сегодня пар уже нет — ближайший день этой недели с парами
// (обычно ищут «когда он в универе»); на других неделях — первый день с парами.
function defaultTargetDay(week) {
  const days = week.days;
  const t = days.findIndex(d => d.date === targetData.today);
  for (let j = Math.max(t, 0); j < days.length; j++) if (days[j].lessons.length) return days[j].date;
  return (t >= 0 ? days[t] : days[0]).date;
}

// При открытии — ближайший день с парами начиная с сегодня, хоть на
// следующей неделе (в субботу вечером «когда он в универе» — это уже
// понедельник/вторник); если пар впереди нет вовсе — сегодня.
function openNextLessonDay() {
  targetWeekIdx = 0;
  targetSelected = targetData.today;
  for (let w = 0; w < targetData.weeks.length; w++) {
    const day = targetData.weeks[w].days.find(d => d.date >= targetData.today && d.lessons.length);
    if (day) { targetWeekIdx = w; targetSelected = day.date; return; }
  }
}

function lessonKinds(lessons) {
  const kinds = [];
  lessons.forEach(l => { for (let i = 0; i < (l.pairs || 1); i++) kinds.push(l.kind); });
  return kinds;
}

function renderTargetWeek() {
  const week = targetData.weeks[targetWeekIdx];
  document.getElementById("tw-label").textContent = weekLabel(new Date(week.monday + "T12:00:00"), targetWeekIdx);
  document.getElementById("tw-num").textContent = week.week ? "· " + week.week + " неделя" : "";
  document.getElementById("tw-prev").disabled = targetWeekIdx <= 0;
  document.getElementById("tw-next").disabled = targetWeekIdx >= targetData.weeks.length - 1;
  const box = document.getElementById("target-days");
  box.innerHTML = "";
  week.days.forEach((day, i) => {
    if (i === 6 && !day.lessons.length) return;   // воскресенье — только если в этот день есть пары
    const b = document.createElement("button");
    b.innerHTML = DAY_SHORT7[i] + "<b>" + Number(day.date.slice(8)) + '</b><span class="dots">' + dotsHtml(lessonKinds(day.lessons)) + "</span>";
    b.classList.toggle("today", day.date === targetData.today);
    b.classList.toggle("active", day.date === targetSelected);
    b.onclick = () => { targetSelected = day.date; haptic(); renderTargetWeek(); };
    box.appendChild(b);
  });
  const day = week.days.find(d => d.date === targetSelected) || week.days[0];
  const idx = week.days.indexOf(day);
  document.getElementById("target-lessons").innerHTML = day.lessons.length
    ? day.lessons.map(l => lessonRow(l, !!l.status)).join("")
    : '<div class="empty">' + DAY_FULL[idx] + " — пар нет 🎉</div>";
}

function shiftTargetWeek(delta) {
  if (!targetData) return;
  const next = Math.min(targetData.weeks.length - 1, Math.max(0, targetWeekIdx + delta));
  if (next === targetWeekIdx) return;
  targetWeekIdx = next;
  targetSelected = defaultTargetDay(targetData.weeks[next]);
  haptic();
  renderTargetWeek();
}

async function togglePin() {
  if (!targetCurrent) return;
  const t = targetCurrent;
  const on = isPinned(t.type, t.id);
  const btn = document.getElementById("target-pin");
  btn.disabled = true;
  try {
    const path = "/api/pins/" + t.type + "/" + t.id;
    if (on) await api(path, { method: "DELETE" });
    else await api(path, { method: "PUT", body: JSON.stringify({ title: t.title }) });
    pinnedTargets = pinnedTargets.filter(p => !(p.type === t.type && p.id === t.id));
    if (!on) pinnedTargets.push({ type: t.type, id: t.id, title: t.title });
    setPinButton(!on);
    haptic("success");
    showToast(on ? "Откреплено" : "📌 Закреплено — будет сверху в поиске");
  } catch (e) {
    alert("Не получилось: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

function closeTarget() {
  targetCurrent = null;
  document.getElementById("target-view").style.display = "none";
  document.getElementById("search-pane").style.display = "block";
  if (tg && tg.BackButton) { tg.BackButton.offClick(closeTarget); tg.BackButton.hide(); }
  renderRecent();
}
