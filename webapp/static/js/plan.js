// Автопилот — часть WebApp: план «что сделать и когда» в окнах между парами
// (сервер: autopilot.py, CP-SAT). Экран «План» (☰ Ещё → План), карточка и
// дела между парами на «Сегодня», листы «Сделал», «Что если» и настройки.
// Файлы подключаются по порядку и делят глобальную область видимости.

let planData = null;
let planBusy = false;
let planItem = null;          // открытое дело в листе
const PLAN_SNAP = "plan-snap-v1";
const PLAN_DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function readPlanSnap() {
  try { return JSON.parse(localStorage.getItem(PLAN_SNAP) || "null"); } catch (e) { return null; }
}

function savePlanSnap() {
  try { localStorage.setItem(PLAN_SNAP, JSON.stringify(planData)); } catch (e) {}
}

function planHours(min) {
  if (!min) return "0 мин";
  const h = Math.floor(min / 60), m = min % 60;
  return (h ? h + " ч" : "") + (h && m ? " " : "") + (m ? m + " мин" : "");
}

function planPts(x) {
  return String(Math.round(x * 10) / 10).replace(".", ",");
}

function goalWord(label) {
  return label === "зачёт" ? "зачёт" : "«" + label + "»";
}

function planHm(iso) { return String(iso).slice(11, 16); }
function planDay(iso) { return String(iso).slice(0, 10); }
function planToday() { return todayData && todayData.date ? todayData.date : isoDate(new Date()); }

// ── загрузка ──────────────────────────────────────────────────────────────

async function loadPlan(fresh) {
  if (planBusy) return planData;
  planBusy = true;
  try {
    planData = await api("/api/plan" + (fresh ? "?fresh=1" : ""));
    savePlanSnap();
  } catch (e) {
    if (!planData) planData = { error: e.message };
  } finally {
    planBusy = false;
  }
  renderPlanHome();
  if (document.getElementById("view-plan").classList.contains("active")) renderPlan();
  return planData;
}

// Главная: карточка «План на сегодня» и дела между парами. Сначала из
// снимка (план тяжёлый — решатель и СДО), потом свежий.
function initPlanHome() {
  if (!planData) planData = readPlanSnap();
  renderPlanHome();
  loadPlan(false);
}

function todayItems() {
  if (!planData || !planData.items) return [];
  const day = planToday();
  return planData.items.filter(i => planDay(i.start) === day);
}

function planSlot(i) {
  const due = i.due ? "срок " + humanDate(planDay(i.due)).split(" · ")[0] : "";
  const meta = [i.subject, due, "~" + planHours(i.minutes)].filter(Boolean).map(escapeHtml).join(" · ");
  return '<div class="plan-slot" onclick="openPlanItem(\'' + escapeHtml(i.key) + '\')">' +
    '<div class="l-time"><b>' + planHm(i.start) + '</b><span>' + planHm(i.end) + '</span></div>' +
    '<div class="ps-body"><div class="t">' + escapeHtml(i.title) + '</div><div class="m">' + meta + '</div></div>' +
    (i.points ? '<div class="gain">+' + planPts(i.points) + '</div>' : '') + '</div>';
}

function planSummary() {
  const cs = (planData && planData.courses) || [];
  const risk = cs.filter(c => c.status === "risk");
  if (!cs.length) return planData && planData.sdo === "ok" ? "" : "подключи СДО — план учтёт баллы";
  if (risk.length) return "не хватает: " + risk.map(c => escapeHtml(c.title)).slice(0, 2).join(", ");
  return "по плану цели по всем " + cs.length + " " + plural(cs.length, "предмету", "предметам", "предметам") + " ✓";
}

function renderPlanHome() {
  const box = document.getElementById("plan-card");
  if (!box) return;
  if (!planData || planData.error || !planData.ok) { box.innerHTML = ""; return; }
  const items = todayItems();
  const next = (planData.items || []).find(i => planDay(i.start) > planToday());
  if (!items.length && !next && !(planData.courses || []).length) { box.innerHTML = ""; return; }
  const min = items.reduce((a, i) => a + i.minutes, 0);
  const big = items.length ? items.length + " " + plural(items.length, "дело", "дела", "дел") + " · " + planHours(min)
    : "сегодня свободно";
  const sub = items.length ? planSummary() : (next ? "дальше: " + escapeHtml(next.title) + " · " + humanDate(planDay(next.start)) : planSummary());
  box.innerHTML = '<div class="plan-hero tap" onclick="openPlan()"><div class="k">' + icon("route", "inl") + ' План на сегодня · автопилот</div>' +
    '<div class="big">' + big + '</div><div class="s">' + sub + '</div></div>';
  if (typeof refreshStatuses === "function" && todayData) refreshStatuses();
}

// ── экран «План» ──────────────────────────────────────────────────────────

function openPlan() {
  haptic();
  switchTab("plan");
  window.scrollTo(0, 0);
  if (!planData) planData = readPlanSnap();
  renderPlan();
  const age = planData && planData.updated ? Date.now() / 1000 - planData.updated : 1e9;
  if (age > 15 * 60) loadPlan(false);
}

const PLAN_STATUS = {
  done: ["ok", c => goalWord(c.goal_label) + " есть"],
  ok: ["ok", c => goalWord(c.goal_label) + " в плане"],
  tight: ["warn", c => goalWord(c.goal_label) + " впритык"],
  risk: ["bad", c => c.tk_short ? "мало работ" : "−" + planPts(c.short)],
};

function planWeek() {
  const days = planData.days || [];
  const top = Math.max(60, ...days.map(d => d.minutes));       // самый загруженный день — во всю высоту
  return '<div class="plan-week">' + days.map((d, n) => {
    const wd = (new Date(isoDays(d.date) * 86400000).getUTCDay() + 6) % 7;
    const h = Math.round(64 * d.minutes / top);
    return '<div class="' + (n === 0 ? "today" : "") + '"><em>' + (d.minutes ? planHours(d.minutes).replace(" мин", "м").replace(" ч", "ч") : "") + '</em>' +
      '<i class="' + (d.minutes ? "" : "lo") + '" style="height:' + Math.max(4, h) + 'px"></i>' + PLAN_DAY_NAMES[wd] + '</div>';
  }).join("") + '</div>';
}

function planChips() {
  const p = planData.prefs || {};
  const light = (p.light_weekdays || []).map(d => PLAN_DAY_NAMES[d].toLowerCase()).join(", ");
  const goals = (planData.courses || []).filter(c => (p.goals || {})[c.key]).map(c => "цель " + goalWord(c.goal_label) + ": " + c.title);
  return '<div class="plan-chips" onclick="openPlanPrefs()">' +
    ['не позже ' + p.day_end, 'до ' + planHours(p.max_day_min) + ' в день', light ? light + " — легко" : "", ...goals]
      .filter(Boolean).map(t => '<span>' + escapeHtml(t) + '</span>').join("") +
    '<span class="edit">' + icon("gear", "inl") + ' настроить</span></div>';
}

function renderPlan() {
  const box = document.getElementById("plan-body");
  if (!planData) { box.innerHTML = '<div class="skel" style="height:170px"></div><div class="skel" style="height:220px"></div>'; return; }
  if (planData.error) {
    box.innerHTML = '<div class="empty">План не загрузился: ' + escapeHtml(planData.error) + '<br><br><button class="link-btn" onclick="loadPlan(true)">Ещё раз</button></div>';
    return;
  }
  if (!planData.ok) {
    box.innerHTML = '<div class="empty">Не получилось сложить план — попробуй пересчитать<br><br><button class="link-btn" onclick="loadPlan(true)">Пересчитать</button></div>';
    return;
  }
  const cs = planData.courses || [];
  const fine = cs.filter(c => c.status !== "risk").length;
  const total = (planData.items || []).reduce((a, i) => a + i.minutes, 0);
  let html = '<div class="card">';
  if (cs.length) {
    html += '<div class="sd-head"><span class="n">' + fine + '</span><span class="of">из ' + cs.length + ' ' + plural(cs.length, "предмета", "предметов", "предметов") + '</span>' +
      '<div class="st">по плану на 2 недели<b class="' + (fine === cs.length ? "ok" : "") + '">' + (fine === cs.length ? "цели в плане" : "есть риск") + '</b></div></div>';
  } else {
    html += '<div class="sd-head"><span class="n">' + (planData.items || []).length + '</span><span class="of">' +
      plural((planData.items || []).length, "дело", "дела", "дел") + ' в плане</span><div class="st">на 2 недели<b class="ok">' + planHours(total) + '</b></div></div>';
  }
  html += planWeek() + planChips() + '</div>';

  if (planData.sdo !== "ok") {
    const why = planData.sdo === "expired" ? "Вход в СДО устарел — подключи заново, и план учтёт баллы и работы текущего контроля."
      : planData.sdo === "down" ? "СДО сейчас не отвечает — план пока только по дедлайнам."
      : "Подключи СДО — план учтёт баллы, работы текущего контроля и посещения.";
    html += '<div class="note-card tap" onclick="openSdoSheet()">' + icon("cap", "inl") + escapeHtml(why) + '</div>';
  }

  if (cs.length) {
    html += '<h2 class="section"><span>Предметы</span><span class="stat">сейчас → по плану</span></h2><div class="card pad">' +
      cs.map((c, n) => {
        const look = PLAN_STATUS[c.status] || PLAN_STATUS.ok;
        const parts = [planPts(c.score) + " → " + planPts(c.projected)];
        if (c.planned) parts.push("работы +" + planPts(c.planned));
        if (c.attendance_left) parts.push("лекции +" + planPts(c.attendance_left));
        if (c.tk_need) parts.push("зачесть ещё " + c.tk_need);
        return '<div class="goal tap" onclick="openPlanCourse(' + n + ')"><span class="nm">' + escapeHtml(c.title) +
          '<small>' + escapeHtml(parts.join(" · ")) + '</small></span><span class="pill ' + look[0] + '">' + escapeHtml(look[1](c)) + '</span></div>';
      }).join("") + '</div>';
  }

  const items = planData.items || [];
  html += '<h2 class="section"><span>Дела</span><span class="stat">' + (items.length ? planHours(total) : "") + '</span></h2>';
  if (!items.length) {
    html += capyEmpty("Делать нечего", "все работы и дедлайны на две недели закрыты");
  } else {
    let day = "";
    html += '<div class="lessons">';
    items.forEach(i => {
      const d = planDay(i.start);
      if (d !== day) {
        day = d;
        html += '<div class="plan-dayhead">' + escapeHtml(humanDate(d)) + '</div>';
      }
      html += planSlot(i);
    });
    html += '</div>';
  }
  const un = planData.unplanned || [];
  if (un.length) {
    html += '<h2 class="section"><span>Не влезло</span><span class="stat">окон до срока не хватило</span></h2><div class="card pad">' +
      un.map(u => '<div class="goal"><span class="nm">' + escapeHtml(u.title) + '<small>' +
        escapeHtml([u.subject, u.due ? "срок " + humanDate(planDay(u.due)) : ""].filter(Boolean).join(" · ")) +
        '</small></span>' + (u.points ? '<span class="pill warn">+' + planPts(u.points) + '</span>' : '') + '</div>').join("") + '</div>';
  }
  const at = planData.updated ? new Date(planData.updated * 1000) : null;
  html += '<p class="plan-foot">' + (at ? "пересчитан в " + String(at.getHours()).padStart(2, "0") + ":" + String(at.getMinutes()).padStart(2, "0") + " · " : "") +
    (planData.took != null ? String(planData.took).replace(".", ",") + " с · " : "") +
    '<button class="link-btn" onclick="replan(this)">' + icon("refresh", "inl") + ' Пересчитать</button></p>';
  box.innerHTML = html;
}

async function replan(btn) {
  if (btn) btn.disabled = true;
  await loadPlan(true);
  haptic("success");
}

// ── дело: «Сделал» и сколько заняло ──────────────────────────────────────

function openPlanItem(key) {
  haptic();
  planItem = (planData.items || []).find(i => i.key === key);
  if (!planItem) return;
  renderPlanItem(false);
  document.getElementById("plan-sheet").classList.add("open");
}

function renderPlanItem(asking) {
  const i = planItem;
  const lines = [
    icon("clock", "inl") + humanDate(planDay(i.start)) + " · " + planHm(i.start) + "–" + planHm(i.end) + " (~" + planHours(i.minutes) + ")",
    i.due ? icon("deadlines", "inl") + "срок: " + escapeHtml(humanDate(planDay(i.due), { time: planHm(i.due) })) : "",
    i.points ? icon("medal", "inl") + "+" + planPts(i.points) + " " + plural(Math.round(i.points), "балл", "балла", "баллов") + " к предмету" : "",
  ].filter(Boolean);
  let html = '<h3>' + escapeHtml(i.title) + '</h3>' + (i.subject ? '<p class="hint" style="margin:-8px 0 10px">' + escapeHtml(i.subject) + '</p>' : '') +
    '<div class="pos-lines">' + lines.map(l => '<div>' + l + '</div>').join("") + '</div>';
  if (!asking) {
    html += '<div class="plan-btns">' + (i.url ? '<button class="ghost" onclick="openLink(' + escapeHtml(JSON.stringify(i.url)) + ')">' + icon("link", "inl") + ' Открыть в СДО</button>' : '') +
      '<button class="primary" onclick="renderPlanItem(true)">' + icon("check", "inl") + ' Сделал</button></div>';
  } else {
    const opts = [[30, "30 мин"], [60, "1 ч"], [120, "2 ч"], [180, "3 ч+"]];
    html += '<div class="plan-ask"><b>Сколько это заняло?</b><p class="hint">по ответам план учится, сколько тебе нужно на похожие работы</p>' +
      '<div class="plan-opt">' + opts.map(([m, t]) => '<button onclick="planDone(' + m + ')">' + t + '</button>').join("") + '</div>' +
      '<button class="link-btn" onclick="planDone(null)">Не помню</button></div>';
  }
  document.getElementById("plan-sheet-body").innerHTML = html;
}

async function planDone(minutes) {
  const i = planItem;
  try {
    await api("/api/plan/done", { method: "POST", body: JSON.stringify({ key: i.key, kind: i.kind, planned: i.minutes, minutes: minutes }) });
  } catch (e) { showToast("Не вышло: " + e.message); return; }
  haptic("success");
  closeSheet("plan-sheet");
  planData.items = planData.items.filter(x => x.key !== i.key);
  renderPlanHome();
  if (document.getElementById("view-plan").classList.contains("active")) renderPlan();
  showToast("Готово — пересчитываю план");
  loadPlan(true);
}

// ── предмет: «что если пропущу лекцию» ───────────────────────────────────

function openPlanCourse(n) {
  haptic();
  const c = planData.courses[n];
  const lect = (planData.lectures || {})[c.key] || [];
  const need = Math.max(0, c.goal - c.score);
  let html = '<h3>' + escapeHtml(c.title) + '</h3><div class="pos-lines">' +
    '<div>' + icon("medal", "inl") + 'сейчас ' + planPts(c.score) + ', цель ' + goalWord(c.goal_label) + ' — от ' + planPts(c.goal) + (need ? ' (ещё ' + planPts(need) + ')' : '') + '</div>' +
    (c.planned ? '<div>' + icon("route", "inl") + 'работы в плане: +' + planPts(c.planned) + '</div>' : '') +
    (c.attendance_left ? '<div>' + icon("users", "inl") + 'если ходить на лекции: +' + planPts(c.attendance_left) + '</div>' : '') +
    (c.tk_need ? '<div>' + icon("checkCircle", "inl") + 'для допуска зачесть ещё ' + c.tk_need + ' ' + plural(c.tk_need, "работу", "работы", "работ") + ' текущего контроля</div>' : '') +
    '</div>';
  if (lect.length) {
    html += '<div class="plan-ask"><b>Что если пропущу лекцию?</b><div class="plan-opt">' +
      lect.map(l => '<button onclick="planWhatIf(this,' + n + ',\'' + l.date + '\')">' + escapeHtml(humanDate(l.date).split(" · ")[0]) + '</button>').join("") +
      '</div><div id="plan-whatif"></div></div>';
  }
  if ((c.marks || []).length > 1) {
    html += '<div class="plan-ask"><b>Цель по предмету</b><div class="plan-opt">' +
      c.marks.map(m => '<button class="' + (m === c.goal_label ? "on" : "") + '" onclick="setPlanGoal(' + n + ',\'' + escapeHtml(m) + '\')">' + escapeHtml(goalWord(m)) + '</button>').join("") + '</div></div>';
  }
  document.getElementById("plan-sheet-body").innerHTML = html;
  document.getElementById("plan-sheet").classList.add("open");
}

async function planWhatIf(btn, n, date) {
  const c = planData.courses[n];
  btn.parentNode.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === btn));
  const out = document.getElementById("plan-whatif");
  out.innerHTML = '<div class="skel" style="height:80px;margin-top:10px"></div>';
  let r;
  try {
    r = await api("/api/plan/whatif", { method: "POST", body: JSON.stringify({ course: c.key, date: date }) });
  } catch (e) { out.innerHTML = '<p class="hint">' + escapeHtml(e.message) + '</p>'; return; }
  const after = r.course || {};
  const rows = ['<div><span class="pill bad">−' + planPts(r.lost) + '</span><span>баллов за посещаемость — лекция стоит столько</span></div>'];
  if (r.added && r.added.length) {
    rows.push('<div><span class="pill warn">+' + planHours(r.minutes_more) + '</span><span>чтобы добрать, план добавит: ' +
      r.added.map(i => escapeHtml(i.title) + " (" + humanDate(planDay(i.start)).split(" · ")[0] + ")").join(", ") + '</span></div>');
  }
  rows.push(after.status === "risk"
    ? '<div><span class="pill bad">!</span><span>' + escapeHtml(goalWord(after.goal_label)) + ' окажется под угрозой — не хватит ' + planPts(after.short || 0) + '</span></div>'
    : '<div><span class="pill ok">' + icon("check", "inl") + '</span><span>' + escapeHtml(goalWord(after.goal_label)) + ' всё равно в плане' + (after.status === "tight" ? " — но впритык" : "") + '</span></div>');
  out.innerHTML = '<div class="plan-diff">' + rows.join("") + '</div>';
}

async function setPlanGoal(n, label) {
  const c = planData.courses[n];
  const goals = {};
  goals[c.key] = label;
  try { await api("/api/plan/prefs", { method: "POST", body: JSON.stringify({ goals: goals }) }); }
  catch (e) { showToast("Не вышло: " + e.message); return; }
  haptic("success");
  closeSheet("plan-sheet");
  planData = Object.assign(planData, { updated: 0 });
  showToast("Цель — " + goalWord(label) + ", пересчитываю");
  loadPlan(true);
}

// ── настройки ─────────────────────────────────────────────────────────────

let planPrefsDraft = null;

function openPlanPrefs() {
  haptic();
  planPrefsDraft = JSON.parse(JSON.stringify(planData.prefs));
  renderPlanPrefs();
  document.getElementById("plan-sheet").classList.add("open");
}

function renderPlanPrefs() {
  const p = planPrefsDraft;
  const row = (title, key, opts, fmt) => '<div class="plan-ask"><b>' + title + '</b><div class="plan-opt">' +
    opts.map(v => '<button class="' + (p[key] === v ? "on" : "") + '" onclick="planPref(\'' + key + '\',' + JSON.stringify(v).replace(/"/g, "&quot;") + ')">' + fmt(v) + '</button>').join("") + '</div></div>';
  document.getElementById("plan-sheet-body").innerHTML = '<h3>Как планировать</h3>' +
    row("Начинать не раньше", "day_start", ["08:00", "09:00", "10:00", "12:00"], v => v) +
    row("Заканчивать не позже", "day_end", ["21:00", "22:00", "23:00", "23:45"], v => v) +
    row("Не больше в день", "max_day_min", [60, 120, 180, 240], v => planHours(v)) +
    '<div class="plan-ask"><b>Лёгкие дни</b><p class="hint">в эти дни — не больше ' + planHours(p.light_max_min) + '</p><div class="nt-days">' +
    PLAN_DAY_NAMES.map((d, i) => '<button class="' + (p.light_weekdays.includes(i) ? "on" : "") + (i >= 5 ? " we" : "") + '" onclick="planLightDay(' + i + ')">' + d + '</button>').join("") +
    '</div></div><button class="primary" style="margin-top:16px" onclick="savePlanPrefs()">Сохранить и пересчитать</button>';
}

function planPref(key, v) {
  planPrefsDraft[key] = v;
  haptic();
  renderPlanPrefs();
}

function planLightDay(i) {
  const d = planPrefsDraft.light_weekdays;
  planPrefsDraft.light_weekdays = d.includes(i) ? d.filter(x => x !== i) : d.concat([i]).sort();
  haptic();
  renderPlanPrefs();
}

async function savePlanPrefs() {
  const p = planPrefsDraft;
  try {
    await api("/api/plan/prefs", { method: "POST", body: JSON.stringify({
      day_start: p.day_start, day_end: p.day_end, max_day_min: p.max_day_min, light_weekdays: p.light_weekdays }) });
  } catch (e) { showToast("Не вышло: " + e.message); return; }
  haptic("success");
  closeSheet("plan-sheet");
  planData.prefs = p;
  renderPlan();
  loadPlan(true);
}
