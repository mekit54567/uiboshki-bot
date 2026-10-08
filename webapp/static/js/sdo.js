// СДО → Баллы: предметы семестра, предмет подробно, «Текущий контроль» — часть WebApp.
// Файлы подключаются по порядку и делят глобальную область видимости.

let sdoData = null;            // /api/sdo/grades
let sdoCourse = null;          // /api/sdo/grades/{id}
let sdoView = "sdo";           // sdo → subject → tk
let tkFilter = "all";
// Номер последнего открытия предмета: ответ старого запроса не затирает
// предмет, открытый после него (иначе «Сдать» и отметка лекции уходили в чужой курс).
let sdoCourseReq = 0;

// Цвет категории БРС — по названию (названия берутся из журнала курса)
function catColor(name) {
  const n = (name || "").toLowerCase();
  if (n.includes("текущ")) return "var(--s-tk)";
  if (n.includes("посещ")) return "var(--s-pos)";
  if (n.includes("семестр") || n.includes("экзам") || n.includes("промежут")) return "var(--s-sk)";
  if (n.includes("труд")) return "var(--s-td)";
  if (n.includes("достиж")) return "var(--s-dost)";
  return "var(--s-dop)";
}

function fmtNum(x) {
  return (Math.round(x * 10) / 10).toString().replace(".", ",");
}

// Что уже есть: «закрыт» у экзамена было непонятно — что закрыто? Пишем
// оценку, которая уже набрана (дизайн-ревью, п. 7).
function gotText(c) {
  if (c.kind === "credit") return "зачёт уже есть";
  const got = c.marks.filter(m => c.score >= m.at);
  return got.length ? "«" + escapeHtml(got[got.length - 1].label) + "» уже есть" : "";
}

// «зачёт» — без кавычек, оценки — в «ёлочках»
function markWord(label) {
  return label === "зачёт" ? "зачёт" : "«" + escapeHtml(label) + "»";
}

function needText(c) {
  // своя цель (sdo_goal.py) — «до «4» ещё 12» вместо ближайшей «3»
  const own = sdoData && sdoData.goals ? sdoData.goals[c.id] : null;
  const goal = own && c.marks.find(m => m.label === own);
  if (goal) {
    return c.score >= goal.at ? icon("check", "inl") + markWord(goal.label) + " уже есть"
      : (goal.label === "зачёт" ? "до зачёта" : "до «" + escapeHtml(goal.label) + "»") + " ещё <b>" + fmtNum(goal.at - c.score) + "</b>";
  }
  if (c.closed && !c.need) return icon("check", "inl") + gotText(c);
  if (c.closed) return icon("check", "inl") + gotText(c) + " · до «" + escapeHtml(c.need_label) + "» ещё <b>" + fmtNum(c.need) + "</b>";
  return (c.kind === "credit" ? "до зачёта" : "до «" + escapeHtml(c.need_label) + "»") + " ещё <b>" + fmtNum(c.need) + "</b>";
}

// Легенда — только те цвета, что реально есть в полосках: раньше было три
// подписи на пять цветов (трудовая и достижения без подписи, дизайн-ревью, п. 4)
const LEGEND = [["var(--s-tk)", "работы"], ["var(--s-pos)", "посещения"], ["var(--s-sk)", "экзамен/зачёт"],
  ["var(--s-td)", "трудовая деятельность"], ["var(--s-dost)", "достижения"], ["var(--s-dop)", "доп. баллы"]];

function legendHtml(list) {
  const used = new Set();
  list.forEach(c => c.categories.forEach(k => { if (k.score > 0) used.add(catColor(k.name)); }));
  const items = LEGEND.filter(([color]) => used.has(color));
  return items.length ? '<div class="legend">' + items.map(([color, label]) => '<span><i style="background:' + color + '"></i>' + label + '</span>').join("") + '</div>' : "";
}

// Полоска суммы: доли категорий от 130 и пороги
function scoreBar(c, cls) {
  const seg = c.categories.filter(k => k.score > 0)
    .map(k => '<i style="width:' + Math.min(100, k.score / c.max * 100).toFixed(1) + '%;background:' + catColor(k.name) + '"></i>').join("");
  const ticks = c.marks.map(m => '<span class="tk" style="left:' + (m.at / c.max * 100).toFixed(1) + '%"></span>').join("");
  return '<span class="sbar ' + (cls || "") + '">' + seg + ticks + '</span>';
}

function zachRow(c) {
  const pct = c.works_total ? Math.round(c.works_passed / c.works_total * 100) : 0;
  const ok = pct >= c.pass_share * 100;
  return '<div class="zach' + (ok ? " ok" : "") + '"><span>' + icon("checkCircle", "inl") + ' Зачтено работ <b>' + c.works_passed + ' из ' + c.works_total + '</b></span>' +
    '<span class="zb"><i style="width:' + pct + '%"></i><em style="left:' + c.pass_share * 100 + '%"></em></span><b>' + pct + '%</b></div>';
}

// Что даёт свой вход в СДО (дизайн-ревью, п. 19): без входа экран не пустой,
// а объясняет, зачем подключаться. Тексты — по тому, что бот реально умеет.
const SDO_PERKS = [
  ["cap", "Баллы по каждому предмету и сколько осталось до зачёта или «3»"],
  ["checkCircle", "Какие работы текущего контроля зачтены, а какие нет"],
  ["upload", "Сдача работ прямо отсюда — до 3 файлов за раз"],
  ["bell", "Бот напишет, когда появятся новые баллы"],
];

function sdoNeedConnect(box, text) {
  // «вход устарел» и «не подключён» — один экран, отличается заголовок и кнопка
  const expired = /устарел/.test(text);
  box.innerHTML = '<div class="card sdo-empty"><div class="big">' + icon("cap", "xl acc") + '</div><b>' + escapeHtml(text.replace(/:\s*вкладка.*$/, "")) + '</b>' +
    '<p class="sheet-hint">Баллы и задания у каждого свои — их видно только со своим входом в СДО.</p>' +
    '<div class="sdo-perks">' + SDO_PERKS.map(([ic, t]) => '<div class="sdo-perk"><span class="sec-ic">' + icon(ic) + '</span><span>' + t + '</span></div>').join("") + '</div>' +
    '<button class="primary" onclick="openSdoSheet()">' + (expired ? "Подключить заново" : "Подключить СДО") + '</button></div>';
}

function showSdoView(name) {
  sdoView = name;
  switchTab(name);
  window.scrollTo(0, 0);
  if (tg && tg.BackButton) {
    tg.BackButton.offClick(sdoBack);
    if (name !== "sdo") { tg.BackButton.onClick(sdoBack); tg.BackButton.show(); }
  }
}

function sdoBack() {
  haptic();
  if (sdoView === "task") showSdoView("tk");
  else if (sdoView === "tk" || sdoView === "pos") {
    showSdoView("subject");
    // ТК мог открыться с пары на главной, минуя экран предмета, — там старый или пустой предмет
    if (sdoCourse) renderSubject();
  } else showSdoView("sdo");
}

// ── Список предметов ──────────────────────────────────────────────────────

async function openSdo(fresh) {
  showSdoView("sdo");
  const box = document.getElementById("sdo-list");
  if (!sdoData || fresh) box.innerHTML = '<div class="skel" style="height:118px"></div><div class="skel" style="height:110px"></div><div class="skel" style="height:110px"></div>';
  else renderSdoList();
  try {
    sdoData = await api("/api/sdo/grades" + (fresh ? "?fresh=1" : ""));
    renderSdoList();
  } catch (e) {
    if (/подключи/.test(e.message)) sdoNeedConnect(box, e.message[0].toUpperCase() + e.message.slice(1));
    else if (!sdoData) box.innerHTML = capyError(e.message);
  }
}

// баллов на автомат хватает, а зачтённых работ < 75 % — чего не хватает (иначе "")
function autoWorksText(c) {
  return c.closed && c.works_need ? "зачесть ещё " + c.works_need + " " + plural(c.works_need, "работу", "работы", "работ") : "";
}

// Сводка семестра: сколько предметов идут на автомат (зачёт/«3» и ≥ 75 % работ)
// и какой ближе всего — одна на hero экрана СДО и плитку «Баллы СДО» на главной.
function sdoSummary(list) {
  const auto = c => c.auto !== undefined ? c.auto : c.closed;   // старый кэш без auto — как раньше
  return {
    // «на автомат»: баллов на зачёт/«3» и зачтено ≥ 75 % работ (sdo_grades.summarize → auto)
    closed: list.filter(c => auto(c)).length, total: list.length,
    near: list.filter(c => !auto(c)).sort((a, b) => (a.closed ? 0 : a.need) - (b.closed ? 0 : b.need))[0] || null,
  };
}

// Короткое имя предмета для плитки: без меток семестра и скобок, до max знаков по словам.
function shortCourse(title, max) {
  max = max || 28;
  const t = (title || "").replace(/\[[^\]]*\]|\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max + 1).replace(/\s+\S*$/, "");
  return (cut.length >= max / 2 ? cut : t.slice(0, max)).replace(/[\s,.:;—-]+$/, "") + "…";
}

// Журнал для фоновых загрузок (баллы у пар, плитка на главной): один запрос на всех.
let sdoGradesReq = null;

function fetchSdoGrades() {
  if (!sdoGradesReq) {
    sdoGradesReq = api("/api/sdo/grades").then(d => (sdoData = d), e => { sdoGradesReq = null; throw e; });
  }
  return sdoGradesReq;
}

function renderSdoList() {
  const box = document.getElementById("sdo-list");
  const list = sdoData.courses;
  const ago = Math.max(0, Math.round((Date.now() / 1000 - sdoData.updated) / 60));
  document.getElementById("sdo-updated").textContent = ago < 1 ? "обновлено только что" : "обновлено " + ago + " мин назад";
  updateSdoTile(sdoData);         // плитка «Баллы СДО» на главной — те же цифры (дизайн-ревью, п. 12)
  if (!list.length) { box.innerHTML = '<div class="empty">В СДО пока нет журналов с баллами за этот семестр</div>'; return; }
  const { closed, near } = sdoSummary(list);
  box.innerHTML =
    '<div class="sc-sum"><div class="e">На автомат: зачёт или «3» и ≥ 75 % работ</div>' +
      '<div class="b">' + closed + ' из ' + list.length + ' ' + plural(list.length, "предмета", "предметов", "предметов") + '</div>' +
      '<div class="m">' + (near ? "ближе всего: " + escapeHtml(near.title) + " — " + (autoWorksText(near) || needText(near).replace(/<\/?b>/g, "")) : "все предметы закрыты " + icon("party", "mood")) + '</div>' +
      // деления — шкала: закрытые заполняются слева, а не там, где стоит карточка
      '<div class="pips">' + list.map((c, i) => '<i class="' + (i < closed ? "on" : "") + '"></i>').join("") + '</div></div>' +
    legendHtml(list) +
    list.map(c =>
      '<div class="sc-card tap" onclick="openSubject(' + c.id + ')"><div class="sc-top"><div class="t"><span class="sc-kind ' + (c.kind === "credit" ? "za" : "ex") + '">' +
        (c.kind === "credit" ? "ЗАЧ" : "ЭКЗ") + '</span><br>' + escapeHtml(c.title) + '</div>' +
        '<div class="n">' + fmtNum(c.score) + '<span class="of"> / ' + fmtNum(c.max) + '</span></div></div>' +
        scoreBar(c) + '<div class="sc-foot"><span>' + needText(c) + '</span>' + (c.final ? '<span>' + escapeHtml(c.final) + '</span>' : '') + '</div>' +
        (c.works_total ? zachRow(c) : '') + '</div>').join("");
}

// ── С пары на главной — сразу в её текущий контроль ──────────────────────
// Название пары в расписании и курса в СДО пишут по-разному (скобки, метка
// семестра, сокращения) — сравниваем по словам; лучший курс, если совпало
// не меньше 60% слов пары.

function courseWords(t) {
  return (t || "").toLowerCase().replace(/ё/g, "е").replace(/\[[^\]]*\]|\([^)]*\)/g, " ")
    .split(/[^a-zа-я0-9]+/).filter(w => w.length > 2);
}

function matchCourse(title, courses) {
  const want = courseWords(title);
  if (!want.length) return null;
  let best = null, bestScore = 0;
  courses.forEach(c => {
    const have = new Set(courseWords(c.title));
    const hit = want.filter(w => have.has(w)).length;
    const score = hit / Math.max(want.length, have.size);
    if (score > bestScore) { best = c; bestScore = score; }
  });
  return bestScore >= 0.6 ? best : null;
}

// Баллы у пар в «Эта неделя»: «12/40» у предмета, который нашёлся в СДО.
// Журнал грузится один раз и только если вход в СДО подключён.
let scoresTried = false;

function lessonScore(title) {
  if (!sdoData || !sdoData.courses) return "";
  const c = matchCourse(title, sdoData.courses);
  if (!c) return "";
  return ' <span class="l-score' + (c.closed ? " ok" : "") + '" title="баллы в СДО">' + fmtNum(c.score) + '/' + fmtNum(c.max) + '</span>';
}

async function loadLessonScores() {
  if (sdoData || scoresTried) return;
  scoresTried = true;
  const st = typeof loadSdoStatus === "function" ? (sdoState && sdoState.state !== "off" ? sdoState : await loadSdoStatus()) : null;
  if (!st || st.state !== "ok") return;
  try { await fetchSdoGrades(); } catch (e) { return; }
  rerenderSelectedDay();
}

async function openLessonSdo(title) {
  // Сразу экран «Текущий контроль» (сначала скелетон), без промежуточного
  // экрана предмета: данные сводки уже есть, подробности догружаются тихо.
  haptic();
  const req = ++sdoCourseReq;
  const box = document.getElementById("tk-body");
  if (!sdoData) {
    sdoCourse = null;
    document.getElementById("tk-back").innerHTML = icon("back") + " Предмет";
    box.innerHTML = '<div class="skel" style="height:150px"></div><div class="skel" style="height:300px;margin-top:10px"></div>';
    showSdoView("tk");
    try { sdoData = await api("/api/sdo/grades"); }
    catch (e) {
      if (req !== sdoCourseReq) return;                         // уже открыли другое
      if (/подключи/.test(e.message)) { openSdo(); return; }   // покажет «Подключить СДО»
      showSdoView("sdo"); showToast("СДО не ответил: " + e.message); return;
    }
    if (req !== sdoCourseReq) return;
  }
  const c = matchCourse(title, sdoData.courses);
  if (!c) { if (sdoView === "tk") showSdoView("sdo"); showToast("В СДО нет журнала с баллами по этому предмету"); return; }
  if (!c.works_total) { openSubject(c.id); return; }
  sdoCourse = Object.assign({ id: c.id }, c);
  if (sdoView === "tk") {
    document.getElementById("tk-back").innerHTML = icon("back") + " " + escapeHtml(c.title);
    tkFilter = "all"; renderTk();
  } else openTk();
  try {
    const full = await api("/api/sdo/grades/" + c.id);
    if (req !== sdoCourseReq) return;
    sdoCourse = full;
    if (sdoView === "tk") renderTk();
    else if (sdoView === "subject") renderSubject();
  } catch (e) {}
}

// ── Предмет подробно ──────────────────────────────────────────────────────

async function openSubject(id) {
  haptic();
  const req = ++sdoCourseReq;
  const base = sdoData && sdoData.courses.find(c => c.id === id);
  sdoCourse = base ? Object.assign({ id: id }, base) : null;
  showSdoView("subject");
  if (sdoCourse) renderSubject();
  else document.getElementById("subject-body").innerHTML = '<div class="skel" style="height:300px"></div>';
  try {
    const full = await api("/api/sdo/grades/" + id);
    if (req !== sdoCourseReq) return;                    // пока ждали, открыли другой предмет
    sdoCourse = full;
    if (sdoView !== "sdo") { renderSubject(); if (sdoView === "tk") renderTk(); if (sdoView === "pos") renderPos(); }
  } catch (e) {
    if (req !== sdoCourseReq) return;
    if (!base) document.getElementById("subject-body").innerHTML = capyError(e.message);
  }
}

function renderSubject() {
  const c = sdoCourse;
  const marks = c.marks.map(m => '<span class="gm' + (c.score >= m.at ? " got" : "") + '" style="left:' + (m.at / c.max * 100).toFixed(1) + '%">' +
    '<b>' + (m.label === "зачёт" ? icon("check") : escapeHtml(m.label)) + '</b><em>' + (m.label === "зачёт" ? "зачёт · " : "") + m.at + '</em></span>').join("");
  const seg = c.categories.filter(k => k.score > 0)
    .map(k => '<i style="width:' + Math.min(100, k.score / c.max * 100).toFixed(1) + '%;background:' + catColor(k.name) + '"></i>').join("");
  const rows = c.categories.map((k, i) => {
    const pos = !k.tk && /посещ/i.test(k.name) && c.attendance;
    const go = (k.tk && c.works_total) || pos;
    // посещаемость — обычная строка с баллами; лекции — по нажатию, на экране «Посещения»
    const share = k.max ? k.score / k.max : 0;
    return '<div class="cat-row' + (go ? ' go' : '') + '"' + (go ? ' onclick="' + (pos ? 'openPos()' : 'openTk()') + '"' : '') + '>' +
      '<span class="d" style="background:' + catColor(k.name) + '"></span><span class="nm">' + escapeHtml(k.name) + '</span>' +
      '<span class="mb"><i style="width:' + Math.min(100, share * 100).toFixed(1) + '%;background:' + catColor(k.name) + '"></i></span>' +
      '<span class="v">' + fmtNum(k.score) + '<small>/' + fmtNum(k.max) + '</small></span>' +
      '<span class="chev">' + (go ? '›' : '') + '</span></div>';
  }).join("");
  document.getElementById("subject-body").innerHTML =
    '<h2 class="section" style="margin-top:6px"><span>' + escapeHtml(c.title) + '</span><span class="stat">' + (c.kind === "credit" ? "ЗАЧ" : "ЭКЗ") + '</span></h2>' +
    '<div class="card"><div class="sd-head"><span class="n">' + fmtNum(c.score) + '</span><span class="of">из ' + fmtNum(c.max) + '</span>' +
      '<div class="st">' + (c.final ? escapeHtml(c.final) : (c.kind === "credit" ? "зачёт" : "экзамен")) + '<b' + (c.closed ? ' class="ok"' : '') + '>' + needText(c).replace(/<\/?b>/g, "") + '</b></div></div>' +
      '<div class="gbar"><div class="gtrack">' + seg + '</div>' + marks + '</div>' +
      '<div class="cats">' + rows + '</div>' + (c.works_total ? zachRow(c) : '') + '</div>' + goalCard(c) + historyCard(c);
}

// ── Цель по предмету (sdo_goal.py) ────────────────────────────────────────
// Без дат и расписания: что нужно, чтобы дойти до зачёта, «3», «4» или «5»,
// — сколько баллов не хватает, откуда их взять и хватает ли зачтённых работ
// (правило БРС: ≥ 75 %, иначе экзамена по БРС не будет).

const GOAL_LOOK = {
  done: ["ok", g => markWord(g.label) + " есть"], ok: ["ok", () => "дойдёшь"],
  tight: ["warn", () => "впритык"], no: ["bad", () => "не хватит"],
};

function goalCard(c) {
  const g = c.goal;
  if (!g) return "";
  const look = GOAL_LOOK[g.status] || GOAL_LOOK.ok;
  const tk = g.tk;
  const line = (ic, html, tap) => '<div class="gl' + (tap ? ' go" onclick="' + tap : '') + '">' + icon(ic, "inl") + '<span>' + html + '</span>' + (tap ? '<span class="chev">›</span>' : '') + '</div>';
  const lines = [];
  lines.push(g.need ? line("medal", "до " + markWord(g.label) + " не хватает <b>" + fmtNum(g.need) + "</b>")
    : line("check", markWord(g.label) + " по баллам уже набрано"));
  if (g.open_count) lines.push(line("upload", "работы: открыто " + g.open_count + " · до <b>+" + fmtNum(g.open_points) + "</b>", "openTk('todo')"));
  if (g.attendance_left) lines.push(line("users", "посещения лекций: до <b>+" + fmtNum(g.attendance_left) + "</b>", c.attendance ? "openPos()" : ""));
  if (tk.total) {
    lines.push(line("checkCircle", "зачтено " + tk.passed + " из " + tk.total + " · нужно " + tk.need +
      (tk.left ? " → из " + tk.open + " открытых зачесть <b>" + tk.left + "</b>" : " " + icon("check", "inl"))));
  }
  if (g.need && g.status !== "done") lines.push(line("sparkle", "если сдать всё и ходить на лекции — до <b>" + fmtNum(g.best) + "</b>"));
  if (g.lost_count) lines.push(line("warning", "ниже порога или срок прошёл: " + g.lost_count + " " + plural(g.lost_count, "работа", "работы", "работ") +
    " — не считаю, " + plural(g.lost_count, "пригодится", "пригодятся", "пригодятся") + ", если дадут пересдать"));
  if (g.skip) {
    const after = GOAL_LOOK[g.skip.status] || GOAL_LOOK.ok;
    lines.push(line("clock", "пропущу лекцию " + escapeHtml(humanDate(g.skip.date).split(" · ")[0]) + ": −" + fmtNum(g.skip.value) +
      " → <b class=\"" + after[0] + "\">" + (g.skip.status === g.status ? "ничего не изменится" : after[1](g)) + "</b>"));
  }
  const why = g.status !== "no" ? "" : '<p class="gc-why">' + (!tk.reachable
    ? "Открытых работ меньше, чем нужно зачесть: без пересдачи экзамена по БРС не будет."
    : "Даже если сдать всё и ходить на все лекции, будет " + fmtNum(g.best) + " — меньше " + fmtNum(g.at) + ". Можно выбрать цель ниже.") + '</p>';
  return '<div class="card goal-card"><div class="gc-head"><b>Цель</b><span class="gc-pill ' + look[0] + '">' + look[1](g) + '</span></div>' +
    '<div class="gc-opts">' + g.marks.map(m => '<button class="' + (m === g.label ? "on" : "") + '" onclick="setGoal(' + escapeHtml(JSON.stringify(m)) + ')">' + markWord(m) + '</button>').join("") + '</div>' +
    '<div class="gc-lines">' + lines.join("") + '</div>' + why + '</div>';
}

async function setGoal(label) {
  const c = sdoCourse;
  if (!c || !c.goal || c.goal.label === label) return;
  haptic();
  try {
    c.goal = await api("/api/sdo/goal/" + c.id, { method: "POST", body: JSON.stringify({ label: label }) });
  } catch (e) { showToast(e.message); return; }
  if (sdoData) { sdoData.goals = sdoData.goals || {}; sdoData.goals[c.id] = label; }
  haptic("success");
  if (sdoView === "subject") renderSubject();
}

// График «как росли баллы» (sdo_history.py: точка в день, когда смотришь баллы).
// Шкала — не 0…130, а по ближайшему порогу (histScale), иначе рост 10→30
// лежит внизу и не виден. Линии и заливка — в SVG, текст и точка — HTML
// поверх (preserveAspectRatio="none" растягивал бы буквы и круг).
function historyCard(c) {
  const h = c.history;
  if (!h || !h.points || !h.points.length) return "";
  const pts = h.points, d = h.week_delta;
  const delta = d === null || d === undefined ? "" :
    '<span class="hist-delta' + (d > 0 ? " up" : "") + '">' + (d > 0 ? "+" : "") + fmtNum(d) + ' за неделю</span>';
  if (pts.length < 2) {
    return '<div class="card hist"><div class="hist-head"><b>Как растут баллы</b>' + delta + '</div>' +
      '<p class="sheet-hint">График появится, когда наберётся история: бот запоминает сумму раз в день, когда ты смотришь баллы.</p></div>';
  }
  const sc = histScale(pts.map(p => p[1]), c.marks, c.max);
  // координаты — в процентах блока графика: и у SVG (viewBox 100×100), и у подписей
  const t0 = Date.parse(pts[0][0]), t1 = Date.parse(pts[pts.length - 1][0]);
  const x = t => t1 === t0 ? 100 : (Date.parse(t) - t0) / (t1 - t0) * 100;
  const y = v => 100 - (Math.min(sc.hi, Math.max(sc.lo, v)) - sc.lo) / (sc.hi - sc.lo) * 100;
  const xy = pts.map(p => [x(p[0]), y(p[1])]);
  const line = xy.map(p => p[0].toFixed(2) + "," + p[1].toFixed(2)).join(" ");
  const last = pts[pts.length - 1], lx = xy[xy.length - 1][0], ly = xy[xy.length - 1][1];
  const valBelow = ly < 26;                     // точка у самого верха — значение под ней
  // высота линии графика в точке px — чтобы подписи порогов не налезали на неё
  const yAt = px => {
    for (let i = 1; i < xy.length; i++) {
      if (px <= xy[i][0]) {
        const a = xy[i - 1], b = xy[i], k = b[0] === a[0] ? 1 : (px - a[0]) / (b[0] - a[0]);
        return a[1] + (b[1] - a[1]) * k;
      }
    }
    return ly;
  };
  const LH = 14;                                // высота подписи, % высоты графика
  const busy = (x0, x1, y0, y1) => {
    for (let px = x0; px <= x1; px += 2) { const v = yAt(px); if (v >= y0 - 5 && v <= y1 + 5) return true; }
    return x1 > 80 && (valBelow ? y1 > ly && y0 < ly + 24 : y1 > ly - 24 && y0 < ly);   // значение у последней точки
  };
  // пороги в шкале — пунктир с подписью «зачёт · 40» / «на «4» · 60» там, где свободно
  const lines = sc.marks.map(m => '<line x1="0" x2="100" y1="' + y(m.at).toFixed(2) + '" y2="' + y(m.at).toFixed(2) + '" class="hist-mark"/>').join("");
  const labels = sc.marks.map(m => {
    const my = y(m.at), text = (m.label === "зачёт" ? "зачёт" : "на «" + m.label + "»") + " · " + fmtNum(m.at);
    const w = text.length * 2.3 + 4;            // ширина подписи в % (≈ 6px на букву при ширине ~290px)
    const spots = [["l", "up", 0, w, my - LH, my], ["r", "up", 100 - w, 100, my - LH, my],
                   ["l", "dn", 0, w, my, my + LH], ["r", "dn", 100 - w, 100, my, my + LH]];
    const s = spots.find(p => !busy(p[2], p[3], p[4], p[5])) || spots[0];
    return '<span class="hist-lbl ' + s[0] + ' ' + s[1] + (m.at === sc.goal ? ' goal' : '') +
      '" style="top:' + my.toFixed(2) + '%">' + escapeHtml(text) + '</span>';
  }).join("");
  // края оси — «26 сен» и «сегодня», без голых «26.09» (дизайн-ревью, п. 15)
  const fmtDay = iso => { const p = iso.split("-"); return +p[2] + " " + MONTHS_SHORT[+p[1] - 1]; };
  return '<div class="card hist"><div class="hist-head"><b>Как растут баллы</b>' + delta + '</div>' +
    '<div class="hist-plot">' +
      '<span class="hist-y top">' + fmtNum(sc.hi) + '</span><span class="hist-y bot">' + fmtNum(sc.lo) + '</span>' +
      '<svg viewBox="0 0 100 100" class="hist-svg" preserveAspectRatio="none">' +
        '<defs><linearGradient id="hist-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="hist-g0"/><stop offset="1" class="hist-g1"/></linearGradient></defs>' +
        '<line x1="0" x2="100" y1="0" y2="0" class="hist-grid"/><line x1="0" x2="100" y1="100" y2="100" class="hist-grid"/>' + lines +
        '<polygon points="0,100 ' + line + ' 100,100" class="hist-area" fill="url(#hist-fill)"/>' +
        '<polyline points="' + line + '" class="hist-line"/></svg>' +
      labels +
      '<span class="hist-dot" style="left:' + lx.toFixed(2) + '%;top:' + ly.toFixed(2) + '%"></span>' +
      '<span class="hist-val' + (valBelow ? ' dn' : '') + '" style="top:' + ly.toFixed(2) + '%">' + fmtNum(last[1]) + '</span>' +
    '</div>' +
    '<div class="hist-axis"><span>' + fmtDay(pts[0][0]) + '</span><span>' + humanDate(last[0]) + '</span></div></div>';
}

// Шкала графика баллов (дизайн-ревью, п. 17): верх — ближайший порог выше
// максимума истории с небольшим запасом, а если все пороги пройдены — максимум
// БРС (130). Низ — 0, а если все точки высоко (выше середины) — чуть ниже
// минимума, круглым числом; ось подписана, так что это честно.
// → {lo, hi, goal: порог-цель или null, marks: пороги, попавшие в шкалу}.
function histScale(values, marks, max) {
  max = max || 130;
  marks = marks || [];
  const vmax = Math.max.apply(null, values), vmin = Math.min.apply(null, values);
  const above = marks.map(m => m.at).filter(a => a > vmax).sort((a, b) => a - b);
  const goal = above.length ? above[0] : null;
  let hi = goal === null ? max : Math.min(max, Math.ceil((goal + Math.max(5, goal * 0.2)) / 5) * 5);
  hi = Math.max(hi, Math.ceil(vmax));
  let lo = 0;
  if (vmin > hi / 2) lo = Math.max(0, Math.floor((vmin - Math.max(5, (hi - vmin) / 2)) / 10) * 10);
  return { lo: lo, hi: hi, goal: goal, marks: marks.filter(m => m.at > lo && m.at < hi) };
}

// ── Текущий контроль ──────────────────────────────────────────────────────

const WORK_LOOK = {
  ok: ["check", "зачтено"], low: ["cross", "ниже порога"], wait: ["clock", "сдано · ждёт оценки"],
  todo: ["upload", "можно сдавать"], offline: ["classroom", "сдаётся на занятии"], soon: ["lock", "ещё закрыто"],
  late: ["clock", "срок прошёл · ждём оценку"], miss: ["warning", "срок прошёл"], none: ["", ""],
};

function openTk(filter) {
  haptic();
  tkFilter = filter || "all";        // из «Цели» — сразу «Сдать»
  document.getElementById("tk-back").innerHTML = icon("back") + " " + escapeHtml(sdoCourse ? sdoCourse.title : "Предмет");
  showSdoView("tk");
  renderTk();
}

async function refreshTk() {
  if (!sdoCourse) return;
  const req = sdoCourseReq;
  try {
    const full = await api("/api/sdo/grades/" + sdoCourse.id);
    if (req !== sdoCourseReq) return;
    sdoCourse = full;
    if (sdoView === "tk") renderTk();
    if (sdoView === "subject") renderSubject();
  } catch (e) {}
}

// «среда, 15 октября 2026, 23:59» → «15 октября, 23:59»
function shortDate(t) {
  return escapeHtml((t || "").replace(/^[а-яё]+,\s*/i, "").replace(/\s\d{4}(,|$)/, "$1"));
}

function workMeta(w) {
  // у теста — «Ограничение по времени» со страницы СДО: сразу видно, сколько он займёт
  const tl = w.time_limit ? " · " + (w.time_limit % 60 ? w.time_limit + " мин" : w.time_limit / 60 + " ч") + " на тест" : "";
  if (w.status === "soon" && w.opens) return "откроется " + shortDate(w.opens) + tl;
  if ((w.status === "todo" || w.status === "miss") && w.due) return "до " + shortDate(w.due) + (w.status === "miss" ? " · срок прошёл" : tl);
  if (w.status === "late" && w.due) return "срок был " + shortDate(w.due) + " · ждём оценку";
  return (WORK_LOOK[w.status] || WORK_LOOK.none)[1] || escapeHtml(w.kind);
}

function renderTk() {
  const c = sdoCourse;
  const box = document.getElementById("tk-body");
  if (!c.works || !c.works.length) { box.innerHTML = capyEmpty("Работ в текущем контроле пока нет", "Как только преподаватель их добавит — появятся тут"); return; }
  const detailed = !!c.works[0].status;   // страницы заданий уже подгружены
  const works = c.works.map(w => Object.assign({}, w, { status: w.status || (w.grade != null ? (w.passed ? "ok" : "low") : "none") }));
  const tk = c.categories.find(k => k.tk) || { score: works.reduce((a, w) => a + (w.grade || 0), 0), max: works.reduce((a, w) => a + (w.max || 0), 0) };
  const need = Math.ceil(works.length * c.pass_share);
  const passed = works.filter(w => w.status === "ok").length;
  const todo = works.filter(w => w.status === "todo").length;
  const graded = works.filter(w => w.grade != null).length;
  const shown = works.filter(w => tkFilter === "all" || (tkFilter === "todo" ? w.status === "todo" : w.grade != null));
  const sq = s => ({ ok: "g", low: "r", wait: "b", late: "b" })[s] || "";
  box.innerHTML =
    '<h2 class="section" style="margin-top:6px"><span>Текущий контроль</span></h2>' +
    '<div class="card"><div class="sd-head"><span class="n">' + fmtNum(tk.score) + '</span><span class="of">из ' + fmtNum(tk.max) + '</span>' +
      '<div class="st">зачтено<b' + (passed >= need ? ' class="ok"' : '') + '>' + passed + ' из ' + works.length + ' · нужно ' + need + '</b></div></div>' +
      '<div class="tkbar">' + works.map(w => '<i class="' + sq(w.status) + '"></i>').join("") + '</div>' +
      '<div class="tklegend"><span><i class="g"></i>зачтено</span><span><i class="r"></i>ниже порога</span><span><i class="b"></i>ждёт оценки</span><span><i></i>впереди</span></div></div>' +
    '<div class="chips-row tk-chips">' +
      [["all", "Все · " + works.length], ["todo", "Сдать · " + todo], ["graded", "Оценено · " + graded]]
        .map(([k, t]) => '<button class="' + (tkFilter === k ? "active" : "") + '" onclick="tkFilter=\'' + k + '\'; renderTk()">' + t + '</button>').join("") + '</div>' +
    (detailed ? '' : '<p class="sheet-hint">' + icon("clock", "inl") + ' Подгружаю сроки и статусы заданий…</p>') +
    '<div class="card pad">' + (shown.length ? shown.map(w => {
      const look = WORK_LOOK[w.status] || WORK_LOOK.none;
      const i = works.indexOf(works.find(x => x.cmid === w.cmid));
      return '<div class="wrow ' + w.status + '" onclick="tapWork(' + i + ')"><span class="wi">' + (look[0] ? icon(look[0]) : "") + '</span>' +
        '<span class="wn">' + escapeHtml(w.name) + '<small>' + workMeta(w) + '</small></span>' +
        '<span class="ws"><b>' + (w.grade != null ? fmtNum(w.grade) : "—") + '</b>/' + fmtNum(w.max || 0) +
        (w.pass_mark != null ? '<small>зачёт ' + fmtNum(w.pass_mark) + '</small>' : '') + '</span><span class="chev">›</span></div>';
    }).join("") : '<div class="empty">Тут пусто</div>') + '</div>';
}

// ── Посещения (attendance.py) ─────────────────────────────────────────────
// Пульс МИРЭА сервер бота не пускает, поэтому посещения лекций — из баллов
// за посещаемость в СДО: они делятся поровну на лекции семестра (практики не
// в счёт), уважительный пропуск выбывает из деления. Какие лекции засчитаны —
// по приросту баллов в истории.

// [значок, подпись, цвет в полоске]; значки — как в журнале: «+», «Н», «У»
const POS_LOOK = {
  ok: ["+", "был", "g"], excused: ["У", "уважительная причина", "y"], miss: ["Н", "не был", "r"],
  wait: ["", "ждём отметку", "b"], before: ["?", "отметь сам", "q"], future: ["", "впереди", ""],
};

function openPos() {
  haptic();
  document.getElementById("pos-back").innerHTML = icon("back") + " " + escapeHtml(sdoCourse ? sdoCourse.title : "Предмет");
  showSdoView("pos");
  renderPos();
}

function lectureWord(n) {             // «2 лекции», «5 лекций»
  const d = n % 10, h = n % 100;
  return d === 1 && h !== 11 ? "лекция" : d >= 2 && d <= 4 && (h < 12 || h > 14) ? "лекции" : "лекций";
}

function lectureGen(n) {              // «из 1 лекции», «из 2 лекций»
  return n % 10 === 1 && n % 100 !== 11 ? "лекции" : "лекций";
}

function renderPos() {
  const a = sdoCourse && sdoCourse.attendance;
  const box = document.getElementById("pos-body");
  if (!a) { box.innerHTML = capyEmpty("Посещения не посчитать", "У предмета нет строки «Посещаемость» или его нет в расписании", "sad"); return; }
  const head = '<h2 class="section" style="margin-top:6px"><span>Посещения</span><span class="stat">лекции</span></h2>';
  if (!a.ok) {
    box.innerHTML = head + '<div class="card"><div class="sd-head"><span class="n">' + fmtNum(a.score) + '</span><span class="of">из ' + fmtNum(a.max) + '</span>' +
      '<div class="st">лекций<b>' + a.past + ' из ' + a.total + ' прошло</b></div></div>' +
      '<p class="sheet-hint">' + icon("warning", "inl") + ' ' + escapeHtml(a.why[0].toUpperCase() + a.why.slice(1)) + '. Посчитать, какие лекции засчитаны, не выйдет.</p></div>';
    return;
  }
  const L = a.lectures;
  const has = st => L.some(x => x.status === st);
  const legend = ["ok", "excused", "miss", "wait", "before", "future"].filter(has)
    .map(st => '<span><i class="' + POS_LOOK[st][2] + '"></i>' + POS_LOOK[st][1] + '</span>').join("");
  const fmtDay = iso => { const p = iso.split("-"); return +p[2] + " " + MONTHS_SHORT[+p[1] - 1]; };
  const lines = [];
  lines.push(icon("checkCircle", "inl") + ' Посещено <b>' + a.attended + ' из ' + a.past + '</b> ' + (a.past % 10 === 1 && a.past % 100 !== 11 ? "прошедшей" : "прошедших") + ' ' + lectureGen(a.past) +
    (a.excused ? ' · по уважительной причине <b>' + a.excused + '</b>' : ''));
  if (a.waiting) lines.push(icon("clock", "inl") + ' ' + a.waiting + ' ' + lectureWord(a.waiting) + ' — ждём, пока преподаватель поставит отметку');
  if (a.left) lines.push(icon("calendar", "inl") + ' Впереди ' + a.left + ' ' + lectureWord(a.left) + ' — ещё до <b>' + fmtNum(a.can_get) + '</b> ' + (a.can_get === 1 ? "балла" : "баллов"));
  if (a.before) {
    const b = a.before, open = b.left_ok || b.left_excused;
    lines.push(icon("edit", "inl") + ' До ' + fmtDay(b.day) + ' бот баллы не записывал: из ' + b.past + ' ' + lectureGen(b.past) +
      ' по баллам посещено ' + b.attended + (b.excused ? ', по уважительной ' + b.excused : '') + '. ' +
      (open ? 'Отметь сам, на каких был: осталось <b>+' + b.left_ok + '</b>' + (b.left_excused ? ' и <b>У ' + b.left_excused + '</b>' : '') +
       ' — нажми на лекцию со знаком «?».' : 'Отмечено — на остальных «Н». Нажми на свою отметку, чтобы снять.'));
  }
  box.innerHTML = head +
    '<div class="card"><div class="sd-head"><span class="n">' + a.attended + '</span><span class="of">из ' + a.total + ' ' + lectureGen(a.total) + '</span>' +
      '<div class="st">баллы<b>' + fmtNum(a.score) + ' из ' + fmtNum(a.max) + ' · ' + fmtNum(a.unit) + ' за лекцию</b></div></div>' +
      '<div class="tkbar">' + L.map(x => '<i class="' + POS_LOOK[x.status][2] + '"></i>').join("") + '</div>' +
      '<div class="tklegend">' + legend + '</div>' +
      '<div class="pos-lines">' + lines.map(t => '<div>' + t + '</div>').join("") + '</div></div>' +
    '<div class="card pad">' + L.map(x => {
      const look = POS_LOOK[x.status];
      // свои отметки — только у лекций до начала истории (знак «?» или уже свой)
      const editable = x.status === "before" || x.manual || (x.status === "miss" && a.before && L.some(y => y.manual) && x.date <= a.before.day);
      const sign = x.status === "wait" ? icon("clock") : look[0];
      return '<div class="wrow ' + x.status + (editable ? ' edit' : '') + '"' + (editable ? ' onclick="markLecture(\'' + x.date + '\')"' : '') + '>' +
        '<span class="wi">' + sign + '</span>' +
        '<span class="wn">Лекция ' + x.n + '<small>' + humanDate(x.date) + ' · ' + look[1] + (x.manual ? ' · твоя отметка' : '') + '</small></span>' +
        '<span class="ws">' + (x.status === "ok" ? '<b>+' + fmtNum(a.unit) + '</b>' : '') + '</span></div>';
    }).join("") + '</div>';
}

// Своя отметка у лекции до начала истории: «?» → «+» (если плюсики ещё
// остались по баллам) → «У» (если есть ушки) → снять. Сервер проверяет то же.
async function markLecture(day) {
  const a = sdoCourse.attendance, x = a.lectures.find(l => l.date === day);
  if (!x) return;
  haptic();
  const b = a.before || { left_ok: 0, left_excused: 0, excused: 0 };
  let next = null;
  if (x.manual && x.status === "ok") next = b.excused && b.left_excused ? "excused" : null;
  else if (x.manual) next = null;
  else if (b.left_ok) next = "ok";
  else if (b.left_excused) next = "excused";
  else { showToast("По баллам посещено " + b.attended + " — сначала сними плюсик с другой лекции"); return; }
  const c = sdoCourse;
  try {
    c.attendance = await api("/api/sdo/attendance/" + c.id, { method: "POST", body: JSON.stringify({ day: day, mark: next }) });
    if (sdoCourse === c) renderPos();
  } catch (e) {
    showToast(e.message);
  }
}

function tapWork(i) {
  const w = sdoCourse.works[i];
  if (!w) return;
  if (w.module === "assign" || w.module === "quiz") openTask(w);   // тест — экран с попытками, пройти — на сайте
  else openLink(w.url);
}

// ── Задание: описание, файлы преподавателя, сдача ─────────────────────────

let sdoTask = null;
let sdoTaskReq = 0;          // как sdoCourseReq: ответ по старому заданию не рисуется на новом

async function openTask(w) {
  haptic();
  const req = ++sdoTaskReq;
  sdoTask = null;
  showSdoView("task");
  const box = document.getElementById("task-body");
  box.innerHTML = '<h2 class="section" style="margin-top:6px"><span>' + escapeHtml(w.name) + '</span></h2>' +
    '<div class="skel" style="height:120px"></div><div class="skel" style="height:160px"></div>';
  try {
    const t = await api("/api/sdo/task/" + w.cmid + (w.module === "quiz" ? "?module=quiz" : ""));
    if (req !== sdoTaskReq) return;                      // уже открыли другое задание — «Сдать» не в чужой cmid
    sdoTask = Object.assign(t, { work: w, loaded: Date.now() });
    if (sdoView === "task") renderTask();
  } catch (e) {
    if (req !== sdoTaskReq) return;
    box.innerHTML = capyError(e.message,
      '<button class="link-btn" onclick="openLink(' + escapeHtml(JSON.stringify(w.url)) + ')">Открыть в СДО</button>');
  }
}

const TASK_TAG = { ok: ["ok", icon("check", "inl") + "зачтено"], low: ["bad", "ниже порога"], wait: ["", icon("clock", "inl") + "ждёт оценки"], todo: ["warn", ""],
  offline: ["", icon("classroom", "inl") + "сдаётся на занятии"], soon: ["", icon("lock", "inl") + "ещё закрыто"], miss: ["bad", "срок прошёл"],
  late: ["", icon("clock", "inl") + "ждём оценку"] };

function renderTask() {
  const t = sdoTask, w = t.work;
  const tag = TASK_TAG[w.status] || ["", ""];
  const remain = w.status === "todo" && t.remaining ? icon("clock", "inl") + escapeHtml(t.remaining.replace(/ осталось$/, "")) : tag[1];
  const fileRow = (f, i, mine) => '<div class="t-file"><span class="ic">' + fileIconFor(f.name) + '</span>' +
    '<span class="nm">' + escapeHtml(f.name) + '</span>' +
    '<button class="dlb" onclick="downloadSdoFile(' + i + ', ' + mine + ', this)" aria-label="Скачать">' + icon("download") + '</button></div>';
  document.getElementById("task-body").innerHTML =
    '<h2 class="section" style="margin-top:6px"><span>' + escapeHtml(t.title || w.name) + '</span>' +
      '<span class="stat">до ' + fmtNum(w.max || 0) + (w.pass_mark != null ? ' · зачёт от ' + fmtNum(w.pass_mark) : '') + '</span></h2>' +
    '<div class="card">' +
      (t.due ? '<div class="t-due"><div><div class="eyebrow">Срок сдачи</div><b>' + shortDate(t.due) + '</b></div>' +
        (remain ? '<span class="t-tag ' + tag[0] + '">' + remain + '</span>' : '') + '</div>' : '') +
      '<div class="t-tags">' + (w.status === "ok" || w.status === "low" ? '<span class="t-tag">Оценено</span>' :
        (t.status ? '<span class="t-tag">' + escapeHtml(humanStatus(t.status)) + '</span>' : '')) +
        '<span class="t-tag">' + (w.grade != null ? "Оценка " + fmtNum(w.grade) + " / " + fmtNum(w.max) : "Не оценено") + '</span></div>' +
      // кто и когда поставил оценку (блок «Отзыв» в СДО)
      (t.graded_by ? '<p class="sheet-hint">Оценил(а): ' + escapeHtml(t.graded_by) + (t.graded_at ? " · " + shortDate(t.graded_at) : "") + '</p>' : '') +
      (t.description ? '<p class="t-desc">' + escapeHtml(t.description).replace(/\n/g, "<br>") + '</p>' : '') + '</div>' +
    (t.feedback ? '<h2 class="section">Комментарий преподавателя</h2><div class="card"><p class="t-desc">' +
      escapeHtml(t.feedback).replace(/\n/g, "<br>") + '</p></div>' : '') +
    (t.quiz ? quizCard(t, w) : '') +
    (t.files.length ? '<h2 class="section">Файлы задания' + (t.files.length > 1 ? '<button class="link-btn" onclick="downloadAllSdo(this)">' + icon("download", "inl") + ' Скачать все · ' + t.files.length + '</button>' : '') + '</h2>' +
      '<div class="card pad">' + t.files.map((f, i) => fileRow(f, i, false)).join("") + '</div>' : '') +
    (t.mine.length ? '<h2 class="section">Мой ответ</h2><div class="card pad">' + t.mine.map((f, i) => fileRow(f, i, true)).join("") + '</div>' : '') +
    (t.can_submit ? '<button class="primary t-go" onclick="submitFromTask()">' + icon("upload") + ' ' + (t.mine.length ? "Сдать ещё / заменить" : "Сдать работу") +
      (t.limit > 1 ? ' · до ' + t.limit + ' ' + plural(t.limit, "файла", "файлов", "файлов") : '') + '</button>' :
      (w.status === "offline" ? '<p class="sheet-hint" style="text-align:center">Эту работу сдают на занятии, не через СДО.</p>' : '')) +
    (t.quiz && t.open_now ? '' : '<button class="ghost" onclick="openLink(' + escapeHtml(JSON.stringify(t.url)) + ')">Открыть в СДО</button>');
}

// Тест (разведка СДО 07.10): открыт ли, попытки, лучший результат, проходная.
// Пройти можно только на сайте — кнопка ведёт туда.
function quizCard(t, w) {
  const used = t.attempts.length;
  const state = t.open_now ? "Тест открыт — можно проходить"
    : t.no_more ? "Попыток больше нет"
    : t.unavailable || w.status === "soon" ? "Ещё не открыт" + (t.opens ? " · откроется " + shortDate(t.opens) : "")
    : "Сейчас пройти нельзя";
  const line = (ic, html) => '<p class="t-desc">' + icon(ic, "inl") + " " + html + '</p>';
  return '<h2 class="section">Тест</h2><div class="card">' +
    line(t.open_now ? "check" : "lock", "<b>" + escapeHtml(state) + "</b>") +
    line("upload", "Попытки: " + (t.attempts_allowed ? "использовано " + used + " из " + t.attempts_allowed : used + " · без ограничения")) +
    (t.best ? line("checkCircle", "Лучший результат: <b>" + escapeHtml(t.best.replace("/", " из ")) + "</b>") : "") +
    (t.pass_text ? line("warning", "Проходная: " + escapeHtml(t.pass_text)) : "") +
    (t.time_limit ? line("clock", "На попытку: " + (t.time_limit % 60 ? t.time_limit + " мин" : t.time_limit / 60 + " ч")) : "") +
    t.attempts.map((a, i) => line("check", "Попытка " + (i + 1) + ": " + escapeHtml(a.grade || a.state) + (a.finished ? " · " + shortDate(a.finished) : ""))).join("") +
    '</div>' +
    (t.open_now ? '<button class="primary t-go" onclick="openLink(' + escapeHtml(JSON.stringify(t.url)) + ')">' + icon("upload") + ' Пройти тест в СДО</button>' : '');
}

// Статус ответа — по-человечески, а не сырым текстом Moodle (дизайн-ревью, п. 7)
const MOODLE_STATUS = [[/не представлен|нет ответа|no attempt/i, "Ещё не сдано"], [/черновик|draft/i, "Черновик — не отправлен"],
  [/отправлено для оценивания|submitted for grading/i, "Сдано, ждёт оценки"], [/вне сайта/i, "Сдаётся на занятии"]];

function humanStatus(s) {
  const hit = MOODLE_STATUS.find(([re]) => re.test(s || ""));
  return hit ? hit[1] : s;
}

function submitFromTask() {
  const t = sdoTask;
  openSubmit(0, { cmid: t.cmid, subject: t.title || t.work.name, description: t.url, limit: t.limit,
    due_text: (sdoCourse ? sdoCourse.title : "") + (t.due ? " · до " + shortDate(t.due) : "") });
}

// 📥 — Telegram.WebApp.downloadFile (Bot API 8.0): на iPhone «Сохранить в
// Файлы», на Android — в Загрузки. Файл бот берёт из СДО входом студента.
function sdoDownload(f) {
  return new Promise(resolve => {
    if (!(tg && tg.downloadFile && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0"))) { openLink(f.dl); return resolve(false); }
    try { tg.downloadFile({ url: f.dl, file_name: f.name }, ok => resolve(!!ok)); }
    catch (e) { openLink(f.dl); resolve(false); }
  });
}

// ссылки на файлы живут 10 минут — экран открыт дольше, берём свежие
async function freshTask() {
  if (Date.now() - sdoTask.loaded < 9 * 60000) return;
  const old = sdoTask;
  try {
    const t = await api("/api/sdo/task/" + old.cmid);
    if (sdoTask === old) sdoTask = Object.assign(t, { work: old.work, loaded: Date.now() });
  } catch (e) {}
}

async function downloadSdoFile(i, mine, btn) {
  await freshTask();
  const f = (mine ? sdoTask.mine : sdoTask.files)[i];
  if (btn) btn.classList.add("sending");
  if (await sdoDownload(f)) haptic("success");
  if (btn) btn.classList.remove("sending");
}

// «Скачать все» — по очереди: Telegram спрашивает про каждый файл, архивом не умеет
async function downloadAllSdo(btn) {
  btn.disabled = true;
  await freshTask();
  let n = 0;
  for (const f of sdoTask.files) { if (await sdoDownload(f)) n++; }
  btn.disabled = false;
  if (n) showToast("📥 Скачано: " + n + " из " + sdoTask.files.length);
}
