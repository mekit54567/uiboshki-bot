// Дедлайны и ДЗ — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Дедлайны ──────────────────────────────────────────────────────────────

function daysUntil(iso) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((new Date(iso + "T00:00:00") - today) / 86400000);
}

function dueBadge(item) {
  if (item.done) return '<span class="chip ok">' + icon("check") + ' готово</span>';
  const days = daysUntil(item.due_date);
  const cls = days <= 0 ? "danger" : (days <= 3 ? "warn" : "ok");
  // Срок по-человечески: «чт, 8 окт · через 6 дн.» вместо «8.10» (дизайн-ревью, п. 15).
  // Просрочено вчера — как раньше «просрочено · 18:00», давно — «пн, 28 сен · 4 дн. назад».
  const label = days === -1 ? "просрочено" + (item.due_time ? " · " + item.due_time : "")
    : humanDate(item.due_date, { time: item.due_time });
  return '<span class="chip ' + cls + '">' + escapeHtml(label) + '</span>';
}

// Сегмент вкладки: "dl" — дедлайны, "hw" — доска ДЗ
function setDlSeg(seg) {
  document.querySelectorAll("#dl-seg button").forEach(x => x.classList.toggle("active", x.dataset.seg === seg));
  const hw = seg === "hw";
  document.getElementById("seg-dl").style.display = hw ? "none" : "block";
  document.getElementById("seg-hw").style.display = hw ? "block" : "none";
  document.getElementById("fab-add").style.display = hw ? "none" : "block";
  if (hw) loadHomework();
}

document.querySelectorAll("#dl-seg button").forEach(b => b.addEventListener("click", () => {
  setDlSeg(b.dataset.seg);
  haptic();
}));

// Из меню «Ещё»: сразу нужный сегмент (дизайн-ревью, п. 18) — плитки «Дедлайны» и «ДЗ»
function openDeadlinesSeg(seg) {
  switchTab("deadlines");
  setDlSeg(seg);
}

function openHomework() { openDeadlinesSeg("hw"); }

async function loadDeadlines() {
  const list = document.getElementById("deadline-list");
  try {
    const data = await api("/api/deadlines?include_done=true");
    const stat = data.stats;
    document.getElementById("deadline-stat").textContent =
      stat.active + " активных" + (stat.overdue ? " · " + stat.overdue + " просрочено" : "");
    if (!data.items.length) {
      list.innerHTML = capyEmpty("Дедлайнов нет — можно выдохнуть", "Свой можно добавить кнопкой ＋");
      return;
    }
    const groups = { overdue: [], week: [], later: [], done: [] };
    data.items.forEach(it => {
      const days = daysUntil(it.due_date);
      if (it.done) groups.done.push(it);
      else if (days < 0) groups.overdue.push(it);
      else if (days <= 7) groups.week.push(it);
      else groups.later.push(it);
    });
    const block = (title, items, cls) => items.length
      ? '<p class="group-title ' + (cls || "") + '">' + title + ' · ' + items.length + '</p><div class="list">' + items.map(renderDeadline).join("") + '</div>'
      : "";
    list.innerHTML =
      block("Просрочено", groups.overdue, "danger") +
      block("На этой неделе", groups.week) +
      block("Позже", groups.later) +
      // «нажми, чтобы вернуть» читалось как «нажми на заголовок» — вернуть можно
      // кнопкой у самой задачи (дизайн-ревью, п. 8)
      (groups.done.length ? '<details class="done-group"><summary><p class="group-title">Выполнено · ' + groups.done.length +
        ' ' + icon("chevron", "done-chev") + '</p></summary><div class="list">' +
        groups.done.map(renderDeadline).join("") + '</div></details>' : "");
  } catch (e) {
    list.innerHTML = capyError(e.message);
  }
}

let deadlineIndex = {};

function renderDeadline(item) {
  deadlineIndex[item.id] = item;
  const desc = item.description || "";
  const isLink = /^https?:\/\//.test(desc);
  const actions = [];
  if (item.done) actions.push('<button onclick="event.stopPropagation(); toggleDeadline(' + item.id + ', false)">' + icon("undo") + ' Вернуть в активные</button>');
  if (item.can_submit && !item.done) actions.push('<button class="submit" onclick="event.stopPropagation(); openSubmit(' + item.id + ')">' + icon("upload") + ' Сдать</button>');
  if (!item.done) actions.push('<button onclick="event.stopPropagation(); openRemind(' + item.id + ')">' + icon("bell") + ' Напомнить</button>');
  if (isLink) actions.push('<a href="#" onclick="event.stopPropagation(); openLink(' + escapeHtml(JSON.stringify(desc)) + '); return false;">' + icon("link") + ' Задание</a>');
  if (item.can_edit) actions.push('<button onclick="event.stopPropagation(); openAddSheet(' + item.id + ')">' + icon("edit") + ' Изменить</button>');
  if (item.can_edit) actions.push('<button class="del" onclick="event.stopPropagation(); deleteDeadline(' + item.id + ')">' + icon("trash") + ' Удалить</button>');
  return (
    '<div class="deadline-card ' + (item.done ? "done" : "") + '" onclick="toggleDeadline(' + item.id + ', ' + (!item.done) + ')">' +
      '<div class="checkbox ' + (item.done ? "checked" : "") + '">' + (item.done ? icon("check") : "") + '</div>' +
      '<div class="dl-body">' +
        '<p class="dl-title">' + escapeHtml(item.subject) + '</p>' +
        (desc && !isLink ? '<p class="dl-desc">' + escapeHtml(desc) + '</p>' : '') +
        '<div class="dl-meta">' + dueBadge(item) + (item.personal ? '<span class="chip">' + icon("user") + ' личный</span>' : '') +
          (item.reminders || []).map(r => '<span class="chip remind">' + icon("bell") + ' ' + escapeHtml(r.label) + '</span>').join("") + '</div>' +
        (actions.length ? '<div class="dl-actions">' + actions.join("") + '</div>' : '') +
      '</div>' +
    '</div>'
  );
}

// ── Своё напоминание о дедлайне (deadline_reminders.py) ──────────────────

let remindItem = null;

function openRemind(id) {
  haptic();
  remindItem = deadlineIndex[id];
  renderRemind();
  document.getElementById("remind-sheet").classList.add("open");
}

function renderRemind() {
  const it = remindItem;
  const list = (it.reminders || []).map(r =>
    '<div class="rm-row">' + icon("bell") + '<span>' + escapeHtml(r.label) + '</span>' +
    '<button onclick="deleteRemind(' + escapeHtml(JSON.stringify(r.at)) + ')" aria-label="убрать">' + icon("cross") + '</button></div>').join("");
  document.getElementById("remind-body").innerHTML =
    '<h3>Напомнить</h3><p class="sheet-hint">' + escapeHtml(it.subject) + ' — ' + dueBadge(it).replace(/<[^>]+>/g, "") + '</p>' +
    (list ? '<div class="rm-list">' + list + '</div>' : '') +
    '<div class="nt-mins rm-presets">' +
      '<button onclick="addRemind({preset:\'1d\'})">за день</button>' +
      '<button onclick="addRemind({preset:\'3h\'})">за 3 часа</button>' +
      '<button onclick="addRemind({preset:\'1h\'})">за час</button></div>' +
    '<div class="nt-custom"><input type="datetime-local" id="remind-at" aria-label="Своё время, по Москве">' +
      '<button onclick="addRemind({at: document.getElementById(\'remind-at\').value})">OK</button></div>' +
    '<p class="sheet-hint rm-tz">Своё время — по Москве</p>' +           // сервер считает его московским
    '<button class="ghost" onclick="closeSheet(\'remind-sheet\')">Готово</button>';
}

async function addRemind(body) {
  haptic();
  if (body.at === "") { showToast("Выбери дату и время"); return; }
  try {
    const r = await api("/api/deadlines/" + remindItem.id + "/remind", { method: "POST", body: JSON.stringify(body) });
    remindItem.reminders = (remindItem.reminders || []).concat([{ at: r.at, label: r.label }])
      .sort((a, b) => a.at < b.at ? -1 : 1);
    showToast("✓ Напомню " + r.label);
    renderRemind();
    loadDeadlines();
  } catch (e) { showToast(e.message); }
}

async function deleteRemind(at) {
  haptic();
  try {
    await api("/api/deadlines/" + remindItem.id + "/remind?at=" + encodeURIComponent(at), { method: "DELETE" });
    remindItem.reminders = (remindItem.reminders || []).filter(r => r.at !== at);
    renderRemind();
    loadDeadlines();
  } catch (e) { showToast(e.message); }
}

function openLink(url) {
  if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
}

let toastTimer = null;
// Тосты пишутся по всему приложению с эмодзи в начале («✓ Сохранено»,
// «📨 Файл в чате») — здесь он меняется на свою иконку (js/icons.js).
const TOAST_ICONS = [["✓", "check"], ["✅", "check"], ["↩", "undo"], ["📨", "send"], ["📲", "phone"], ["🎖", "medal"],
  ["🗑", "trash"], ["⚠️", "warning"], ["📥", "download"], ["🗓", "calsub"], ["🔒", "lock"], ["📤", "upload"]];

function showToast(text, actionLabel, onAction) {
  const t = document.getElementById("toast");
  const lead = TOAST_ICONS.find(([e]) => text.startsWith(e));
  document.getElementById("toast-text").innerHTML = lead
    ? icon(lead[1]) + " " + escapeHtml(text.slice(lead[0].length).trim()) : escapeHtml(text);
  const btn = document.getElementById("toast-action");
  btn.textContent = actionLabel || "";
  btn.onclick = () => { t.classList.remove("show"); if (onAction) onAction(); };
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 4500);
}

// Отметил случайно — «Отменить» в тосте или «↩ Вернуть» у выполненного
// (раньше выполненный уезжал в свёрнутый список, и вернуть его было неочевидно).
async function toggleDeadline(id, done) {
  haptic("success");
  try {
    await api("/api/deadlines/" + id + "/toggle", { method: "POST", body: JSON.stringify({ done: done }) });
    loadDeadlines();
    loadToday();
    if (done) showToast("✓ Отмечено выполненным", "Отменить", () => toggleDeadline(id, false));
    else showToast("↩ Вернул в активные");
  } catch (e) {
    alert("Не получилось: " + e.message);
  }
}

async function deleteDeadline(id) {
  const ok = await confirmDialog("Удалить этот дедлайн?");
  if (!ok) return;
  try {
    await api("/api/deadlines/" + id, { method: "DELETE" });
    haptic("success");
    loadDeadlines(); loadToday();
  } catch (e) {
    alert("Не получилось: " + e.message);
  }
}

function confirmDialog(text) {
  return new Promise(resolve => {
    if (tg && tg.showConfirm) { try { tg.showConfirm(text, resolve); return; } catch (e) {} }
    resolve(window.confirm(text));
  });
}

let editingId = null;

// Быстрые даты над полем даты — одним нажатием вместо календаря
// (дизайн-ревью, п. 16). Третья пилюля — ближайший следующий понедельник;
// если он совпал с «Завтра» (сегодня вс) или «Через неделю» (сегодня пн) —
// вместо него ближайшая пятница, чтобы не было двух одинаковых дат.
const QD_DOW = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];

function quickDates(now) {
  const at = n => new Date(now.getFullYear(), now.getMonth(), now.getDate() + n);
  const ahead = dow => (dow - now.getDay() + 7) % 7 || 7;      // строго после сегодня
  const named = d => QD_DOW[d.getDay()] + ", " + d.getDate() + " " + MONTHS_SHORT[d.getMonth()];
  let mon = ahead(1);
  if (mon === 1 || mon === 7) mon = ahead(5);
  return [
    { label: "Сегодня", date: isoDate(at(0)) },
    { label: "Завтра", date: isoDate(at(1)) },
    { label: named(at(mon)), date: isoDate(at(mon)) },
    { label: "Через неделю", date: isoDate(at(7)) },
  ];
}

function renderQuickDates() {
  document.getElementById("nd-quick").innerHTML = quickDates(new Date()).map(q =>
    '<button type="button" data-date="' + q.date + '" onclick="pickQuickDate(this)">' + q.label + '</button>'
  ).join("");
  syncQuickDates();
}

function pickQuickDate(btn) {
  haptic();
  document.getElementById("nd-date").value = btn.dataset.date;
  syncQuickDates();
}

// Подсветка идёт за полем: выбрал дату руками — горит совпавшая пилюля или никакая.
function syncQuickDates() {
  const value = document.getElementById("nd-date").value;
  document.querySelectorAll("#nd-quick button").forEach(b => b.classList.toggle("active", b.dataset.date === value));
}

document.getElementById("nd-date").addEventListener("input", syncQuickDates);
document.getElementById("nd-date").addEventListener("change", syncQuickDates);

// Одна форма на «добавить» и «изменить»: openAddSheet() — новый личный,
// openAddSheet(id) — правка (свой личный или, для старосты, общий).
function openAddSheet(id) {
  haptic();
  const item = id ? deadlineIndex[id] : null;
  editingId = item ? item.id : null;
  document.getElementById("nd-title").textContent = item ? "Изменить дедлайн" : "Новый дедлайн";
  document.getElementById("nd-submit").textContent = item ? "Сохранить" : "Добавить";
  document.getElementById("nd-hint").innerHTML = !item
    ? icon("user", "inl") + " Личный — видишь только ты. Общие дедлайны группы добавляет староста."
    : item.personal ? icon("user", "inl") + " Личный — видишь только ты."
    : icon("edit", "inl") + " Общий дедлайн — изменится у всей группы. Автосинк СДО его больше не перезапишет.";
  if (item) {
    document.getElementById("nd-subject").value = item.subject;
    document.getElementById("nd-date").value = item.due_date;
    document.getElementById("nd-time").value = item.due_time || "";
    document.getElementById("nd-desc").value = item.description || "";
  } else {
    const d = new Date(); d.setDate(d.getDate() + 7);
    ["nd-subject", "nd-desc"].forEach(x => document.getElementById(x).value = "");
    document.getElementById("nd-date").value = isoDate(d);
    document.getElementById("nd-time").value = "23:59";
  }
  renderQuickDates();
  document.getElementById("add-sheet").classList.add("open");
  setTimeout(() => document.getElementById("nd-subject").focus(), 150);
}

function closeAddSheet() {
  document.getElementById("add-sheet").classList.remove("open");
}

async function submitDeadline() {
  const subject = document.getElementById("nd-subject").value.trim();
  if (!subject) { document.getElementById("nd-subject").focus(); return; }
  const btn = document.getElementById("nd-submit");
  btn.disabled = true;
  try {
    const payload = JSON.stringify({
      subject: subject,
      due_date: document.getElementById("nd-date").value,
      due_time: document.getElementById("nd-time").value,
      description: document.getElementById("nd-desc").value.trim(),
    });
    if (editingId) await api("/api/deadlines/" + editingId, { method: "PATCH", body: payload });
    else await api("/api/deadlines", { method: "POST", body: payload });
    haptic("success");
    showToast(editingId ? "✓ Сохранено" : "✓ Дедлайн добавлен");
    ["nd-subject", "nd-desc"].forEach(id => document.getElementById(id).value = "");
    editingId = null;
    closeAddSheet();
    loadDeadlines(); loadToday();
  } catch (e) {
    alert("Не получилось: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function loadHomework() {
  const list = document.getElementById("hw-list");
  try {
    const data = await api("/api/homework");
    if (!data.items.length) { list.innerHTML = capyEmpty("Доска ДЗ пока пустая", "Староста добавит задания — они появятся тут"); return; }
    list.innerHTML = data.items.map(h => {
      const when = h.lesson_date ? '<span class="chip warn">к паре · ' + escapeHtml(humanDate(h.lesson_date)) + '</span>' : "";   // п. 15
      const file = h.has_file ? '<div class="dl-actions"><button onclick="openHwFile(' + h.id + ', this)">' + icon("clip") + ' Открыть файл</button></div>' : "";
      return '<div class="hw-card"><div class="hw-subj">' + escapeHtml(h.subject) + '</div>' +
        (h.content ? '<div class="hw-text">' + escapeHtml(h.content) + '</div>' : '') +
        '<div class="dl-meta">' + when + '</div>' + file + '</div>';
    }).join("");
  } catch (e) {
    list.innerHTML = capyError(e.message);
  }
}

function openHwFile(id, btn) {
  sendToChat("/api/homework/" + id + "/send", "hw_" + id, btn);
}
