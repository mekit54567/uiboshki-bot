// Дедлайны и ДЗ — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Дедлайны ──────────────────────────────────────────────────────────────

function daysUntil(iso) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((new Date(iso + "T00:00:00") - today) / 86400000);
}

function dueBadge(item) {
  if (item.done) return '<span class="chip ok">✓ готово</span>';
  const days = daysUntil(item.due_date);
  let cls = "ok", label;
  if (days < 0) { cls = "danger"; label = "просрочено"; }
  else if (days === 0) { cls = "danger"; label = "сегодня"; }
  else if (days === 1) { cls = "warn"; label = "завтра"; }
  else if (days <= 3) { cls = "warn"; label = "через " + days + " дн."; }
  else { const d = new Date(item.due_date + "T00:00:00"); label = d.getDate() + "." + String(d.getMonth() + 1).padStart(2, "0"); }
  return '<span class="chip ' + cls + '">' + label + (item.due_time ? " · " + escapeHtml(item.due_time) : "") + '</span>';
}

document.querySelectorAll("#dl-seg button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll("#dl-seg button").forEach(x => x.classList.toggle("active", x === b));
  const hw = b.dataset.seg === "hw";
  document.getElementById("seg-dl").style.display = hw ? "none" : "block";
  document.getElementById("seg-hw").style.display = hw ? "block" : "none";
  document.getElementById("fab-add").style.display = hw ? "none" : "block";
  haptic();
  if (hw) loadHomework();
}));

async function loadDeadlines() {
  const list = document.getElementById("deadline-list");
  try {
    const data = await api("/api/deadlines?include_done=true");
    const stat = data.stats;
    document.getElementById("deadline-stat").textContent =
      stat.active + " активных" + (stat.overdue ? " · " + stat.overdue + " просрочено" : "");
    if (!data.items.length) {
      list.innerHTML = '<div class="empty">Дедлайнов нет 🎉<br>Свой можно добавить кнопкой ＋</div>';
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
      (groups.done.length ? '<details class="done-group"><summary><p class="group-title">Выполнено · ' + groups.done.length +
        ' ▾ <span style="text-transform:none;font-weight:600">— нажми, чтобы вернуть</span></p></summary><div class="list">' +
        groups.done.map(renderDeadline).join("") + '</div></details>' : "");
  } catch (e) {
    list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
}

let deadlineIndex = {};

function renderDeadline(item) {
  deadlineIndex[item.id] = item;
  const desc = item.description || "";
  const isLink = /^https?:\/\//.test(desc);
  const actions = [];
  if (item.done) actions.push('<button onclick="event.stopPropagation(); toggleDeadline(' + item.id + ', false)">↩ Вернуть в активные</button>');
  if (isLink) actions.push('<a href="#" onclick="event.stopPropagation(); openLink(' + escapeHtml(JSON.stringify(desc)) + '); return false;">🔗 Задание</a>');
  if (item.can_edit) actions.push('<button onclick="event.stopPropagation(); openAddSheet(' + item.id + ')">✏️ Изменить</button>');
  if (item.can_edit) actions.push('<button class="del" onclick="event.stopPropagation(); deleteDeadline(' + item.id + ')">🗑 Удалить</button>');
  return (
    '<div class="deadline-card ' + (item.done ? "done" : "") + '" onclick="toggleDeadline(' + item.id + ', ' + (!item.done) + ')">' +
      '<div class="checkbox ' + (item.done ? "checked" : "") + '">' + (item.done ? "✓" : "") + '</div>' +
      '<div class="dl-body">' +
        '<p class="dl-title">' + escapeHtml(item.subject) + '</p>' +
        (desc && !isLink ? '<p class="dl-desc">' + escapeHtml(desc) + '</p>' : '') +
        '<div class="dl-meta">' + dueBadge(item) + (item.personal ? '<span class="chip">👤 личный</span>' : '') + '</div>' +
        (actions.length ? '<div class="dl-actions">' + actions.join("") + '</div>' : '') +
      '</div>' +
    '</div>'
  );
}

function openLink(url) {
  if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
}

let toastTimer = null;
function showToast(text, actionLabel, onAction) {
  const t = document.getElementById("toast");
  document.getElementById("toast-text").textContent = text;
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

// Одна форма на «добавить» и «изменить»: openAddSheet() — новый личный,
// openAddSheet(id) — правка (свой личный или, для старосты, общий).
function openAddSheet(id) {
  haptic();
  const item = id ? deadlineIndex[id] : null;
  editingId = item ? item.id : null;
  document.getElementById("nd-title").textContent = item ? "Изменить дедлайн" : "Новый дедлайн";
  document.getElementById("nd-submit").textContent = item ? "Сохранить" : "Добавить";
  document.getElementById("nd-hint").textContent = !item
    ? "👤 Личный — видишь только ты. Общие дедлайны группы добавляет староста."
    : item.personal ? "👤 Личный — видишь только ты."
    : "✏️ Общий дедлайн — изменится у всей группы. Автосинк СДО его больше не перезапишет.";
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
    if (!data.items.length) { list.innerHTML = '<div class="empty">Доска ДЗ пока пустая</div>'; return; }
    list.innerHTML = data.items.map(h => {
      const when = h.lesson_date ? '<span class="chip warn">к ' + h.lesson_date.slice(8, 10) + "." + h.lesson_date.slice(5, 7) + '</span>' : "";
      const file = h.has_file ? '<div class="dl-actions"><button onclick="openHwFile(' + h.id + ')">📎 Открыть файл</button></div>' : "";
      return '<div class="hw-card"><div class="hw-subj">' + escapeHtml(h.subject) + '</div>' +
        (h.content ? '<div class="hw-text">' + escapeHtml(h.content) + '</div>' : '') +
        '<div class="dl-meta">' + when + '</div>' + file + '</div>';
    }).join("");
  } catch (e) {
    list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
}

function openHwFile(id) {
  const link = "https://t.me/" + BOT_USERNAME + "?start=hw_" + id;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(link); else window.open(link, "_blank");
}
