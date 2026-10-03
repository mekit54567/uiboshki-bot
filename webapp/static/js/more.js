// Меню «Ещё» (☰ в нижней панели), свой вход в СДО и сдача работ — часть WebApp.
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Меню «Ещё» ────────────────────────────────────────────────────────────

function toggleMore(show) {
  const menu = document.getElementById("more-menu");
  const open = show === undefined ? !menu.classList.contains("open") : show;
  menu.classList.toggle("open", open);
  document.getElementById("more-btn").classList.toggle("open", open);
  if (open) {
    // каскад плиток при открытии (дизайн-ревью, п. 18): номер плитки — задержка в app.css
    menu.querySelectorAll(".more-grid button").forEach((b, i) => b.style.setProperty("--i", i));
    syncNavHeight(); haptic(); loadSdoStatus();
  }
}

// «Канал бота» и «Написать нам»: t.me — внутри Telegram, остальное — браузером;
// ссылка ещё не задана (канал не создан) — «Скоро»
function openConfigLink(url) {
  if (!url) { showToast("Скоро"); return; }
  if (/^@\w+$/.test(url)) url = "https://t.me/" + url.slice(1);
  if (/^https?:\/\/(t\.me|telegram\.me)\//i.test(url) && tg && tg.openTelegramLink) tg.openTelegramLink(url);
  else openLink(url);
}

function closeSheet(id) {
  document.getElementById(id).classList.remove("open");
}

// Подписка на расписание и дедлайны в календаре телефона (как /calendar в боте)
async function copyCalendarLink() {
  try {
    const data = await api("/api/calendar/link");
    const url = location.origin + data.ics_path;
    try { await navigator.clipboard.writeText(url); } catch (e) { prompt("Ссылка на календарь:", url); return; }
    haptic("success");
    showToast("🗓 Ссылка скопирована — Календарь → Добавить подписку");
  } catch (e) {
    showToast("Не вышло: " + e.message);
  }
}

// ── СДО: статус и подключение ─────────────────────────────────────────────

let sdoState = { state: "off" };

// Кнопка СДО внизу: не подключён или вход устарел — шапочка красная (и
// плашка приглушённо-кирпичная, когда открыта); подключён — капибара.
function setSdoNav(state) {
  const btn = document.querySelector('nav.tabs button[data-tab="sdo"]');
  if (!btn) return;
  const ok = state === "ok";
  btn.classList.toggle("sdo-off", !ok);
  btn.classList.toggle("sdo-ok", ok);
  btn.querySelector("use").setAttribute("href", ok ? "#i-capy" : "#i-cap");
}

async function loadSdoStatus() {
  try { sdoState = await api("/api/sdo/status"); } catch (e) { return sdoState; }
  setSdoNav(sdoState.state);
  return sdoState;
}

function agoText(iso) {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso.replace(" ", "T") + "Z")) / 60000));
  if (min < 1) return "Проверено только что";
  if (min < 60) return "Проверено " + min + " мин назад";
  return "Проверено " + Math.round(min / 60) + " ч назад";
}

function statusCard(dot, title, sub, cls) {
  return '<div class="st-card ' + (cls || "") + '"><span class="st-dot ' + dot + '"></span>' +
    '<div><b>' + title + '</b><div class="s">' + sub + '</div></div></div>';
}

async function openSdoSheet() {
  document.getElementById("sdo-sheet").classList.add("open");
  renderSdo();
  await loadSdoStatus();
  renderSdo();
}

function renderSdo(connecting) {
  const box = document.getElementById("sdo-body");
  const lock = '<div class="lock">' + icon("shield", "inl") + ' Вход хранится зашифрованным и используется только по твоей команде. Отключить — одной кнопкой в любой момент.</div>';
  if (connecting) {
    box.innerHTML =
      '<h3>Подключить СДО</h3>' +
      '<ol class="steps">' +
        '<li><span>Открой <b>online-edu.mirea.ru</b> на компьютере и войди в свой аккаунт</span></li>' +
        '<li><span>F12 → Application → Cookies → строка <b>MoodleSession</b></span></li>' +
        '<li><span>Скопируй значение и вставь сюда</span></li>' +
      '</ol>' +
      '<input class="searchbox" id="sdo-cookie" placeholder="Вставь MoodleSession…" autocomplete="off" autocapitalize="off" spellcheck="false">' +
      '<div class="lock">' + icon("shield", "inl") + ' Это как «оставаться в системе». Значение сразу шифруется, в переписке и логах не остаётся.</div>' +
      '<button class="primary" id="sdo-save" onclick="connectSdo()">Проверить и сохранить</button>' +
      '<button class="ghost" onclick="renderSdo()">Позже</button>';
    return;
  }
  if (sdoState.state === "ok") {
    box.innerHTML = '<h3>' + icon("cap", "inl acc") + ' СДО</h3>' +
      statusCard("ok", "Подключено, работает", sdoState.shared ? "Вход старосты из настроек бота" : agoText(sdoState.checked_at)) +
      '<p class="sheet-hint">У дедлайнов из СДО есть кнопка «' + icon("upload", "inl") + 'Сдать»: выбираешь файл — бот загружает его в нужное задание.</p>' +
      (sdoState.shared ? '' : '<button class="ghost danger" onclick="disconnectSdo()">Отключить СДО</button>') + pulseBtn();
  } else if (sdoState.state === "expired") {
    box.innerHTML = '<h3>' + icon("cap", "inl acc") + ' СДО</h3>' +
      statusCard("bad", "Вход устарел", "СДО разлогинил сессию — подключи заново", "bad") +
      '<button class="primary" onclick="renderSdo(true)">Подключить заново</button>' +
      '<button class="ghost danger" onclick="disconnectSdo()">Убрать</button>';
  } else {
    box.innerHTML = '<h3>' + icon("cap", "inl acc") + ' СДО</h3>' +
      statusCard("off", "Не подключено", "Дедлайны группы видны и без этого") +
      '<p class="sheet-hint">Подключи свой вход в СДО — и сдавай работы прямо отсюда: выбрал файл → «Сдать» → готово.</p>' +
      lock + '<button class="primary" onclick="renderSdo(true)">Подключить СДО</button>' + pulseBtn();
  }
}

// Староста: пускает ли pulse.mirea.ru сервер бота (посещаемость по датам — потом)
function pulseBtn() {
  return sdoState.starosta ? '<button class="ghost" id="pulse-btn" onclick="checkPulse()">' + icon("pulse", "inl") + ' Проверить доступ к Пульсу</button>' : '';
}

async function checkPulse() {
  const btn = document.getElementById("pulse-btn");
  btn.disabled = true; btn.textContent = "Проверяю Пульс…";
  try {
    const r = await api("/api/pulsecheck", { method: "POST" });
    btn.innerHTML = '<span class="st-dot ' + (r.ok ? "ok" : "bad") + '"></span> ' +
      escapeHtml((r.ok ? "Пульс пускает сервер" : "Пульс: " + r.why) + " · HTTP " + r.status);
  } catch (e) {
    btn.textContent = "Не вышло: " + e.message;
  }
  btn.disabled = false;
}

async function connectSdo() {
  const input = document.getElementById("sdo-cookie");
  const btn = document.getElementById("sdo-save");
  if (!input.value.trim()) { input.focus(); return; }
  btn.disabled = true; btn.textContent = "Проверяю…";
  try {
    sdoState = await api("/api/sdo/connect", { method: "POST", body: JSON.stringify({ cookie: input.value }) });
    input.value = "";
    haptic("success");
    renderSdo(); loadSdoStatus(); loadDeadlines();
    if (document.getElementById("view-sdo").classList.contains("active")) openSdo(true);
  } catch (e) {
    btn.disabled = false; btn.textContent = "Проверить и сохранить";
    showToast("⚠️ " + e.message);
  }
}

async function disconnectSdo() {
  if (!(await confirmDialog("Отключить СДО? Сдавать работы отсюда будет нельзя, пока не подключишь снова."))) return;
  try {
    sdoState = await api("/api/sdo/disconnect", { method: "POST" });
    renderSdo(); loadSdoStatus();
  } catch (e) {
    showToast("Не вышло: " + e.message);
  }
}

// ── Сдача работы ──────────────────────────────────────────────────────────

const SUBMIT_MAX_MB = 20;
const SUBMIT_MAX_FILES = 3;     // за раз (владелец: «до трёх файлов», sdo_submit.MAX_FILES)
let submitting = { item: null, files: [] };

async function openSubmit(id, work) {
  // work — задание из СДО (js/sdo.js): {cmid, subject, due_text, description, limit}
  const item = work || deadlineIndex[id];
  if (!item) return;
  haptic();
  if (sdoState.state === "off" || sdoState.state === "expired") await loadSdoStatus();
  if (sdoState.state !== "ok") { openSdoSheet(); return; }
  submitting = { item: item, files: [], limit: Math.max(1, Math.min(SUBMIT_MAX_FILES, item.limit || SUBMIT_MAX_FILES)), rules: null };
  const input = document.getElementById("submit-file");
  input.multiple = submitting.limit > 1;
  input.removeAttribute("accept");
  document.getElementById("submit-sheet").classList.add("open");
  renderSubmit();
  loadSubmitRules(submitting);
}

// Что принимает задание — СДО честно пишет это под полем файлов («только
// .zip»); раньше бот этого не показывал, и PDF с Word молча отклонялись.
async function loadSubmitRules(s) {
  const it = s.item;
  let rules;
  try {
    rules = await api("/api/sdo/submit-rules?cmid=" + (it.cmid || 0) + "&deadline_id=" + (it.id || 0));
  } catch (e) {
    rules = { error: e.message };
  }
  if (submitting !== s) return;                     // лист уже закрыли или открыли другое задание
  s.rules = rules;
  if (rules.maxfiles > 0) s.limit = Math.max(1, Math.min(s.limit, rules.maxfiles));
  const input = document.getElementById("submit-file");
  input.multiple = s.limit > 1;
  if (rules.accepted && rules.accepted.length) input.accept = rules.accepted.join(",");   // выбор файла сразу по типу
  renderSubmit();
}

function submitMaxMb() {
  const r = submitting.rules;
  const mb = r && r.maxbytes > 0 ? Math.max(1, Math.floor(r.maxbytes / 1024 / 1024)) : SUBMIT_MAX_MB;
  return Math.min(mb, SUBMIT_MAX_MB);
}

function submitExtOk(name) {
  const acc = (submitting.rules && submitting.rules.accepted) || [];
  return !acc.length || acc.some(e => name.toLowerCase().endsWith(e));
}

function submitRulesHtml() {
  const r = submitting.rules;
  if (!r) return '<div class="sub-rules loading"><span class="ic">' + icon("clock") + '</span><div class="s">Смотрю в СДО, какие файлы принимает задание…</div></div>';
  if (r.error) return '';                           // не узнали — не мешаем, СДО скажет при загрузке
  if (r.closed) return '<div class="sub-rules closed"><span class="ic">' + icon("lock") + '</span><div><b>Сдать не выйдет</b><div class="s">' + escapeHtml(r.closed) + '</div></div></div>';
  const acc = r.accepted || [];
  const what = acc.length ? (r.labels && r.labels.length ? r.labels.join(", ") : acc.join(", ")) : "Любые файлы";
  const lim = submitting.limit;
  const meta = ["до " + lim + " " + plural(lim, "файла", "файлов", "файлов"), "до " + submitMaxMb() + " МБ"];
  return '<div class="sub-rules"><span class="ic">' + icon("doc") + '</span><div><b>' + (acc.length ? "Принимает: " : "") + escapeHtml(what) + '</b>' +
    '<div class="exts">' + (acc.length ? '<span class="ext">' + escapeHtml(acc.join(" ")) + '</span>' : '') +
      meta.map(m => '<span>' + escapeHtml(m) + '</span>').join("") + '</div>' +
    (acc.length === 1 && acc[0] === ".zip" ? '<div class="s">Упакуй работу в архив: в «Файлах» iPhone — удержи файл → «Сжать».</div>' : '') +
    '</div></div>';
}

function submitHead() {
  const it = submitting.item;
  return '<h3>' + icon("upload", "inl acc") + ' Сдать работу</h3><div class="sub-task"><b>' + escapeHtml(it.subject) + '</b>' +
    '<div class="s">' + (it.due_text !== undefined ? escapeHtml(it.due_text)
      : "срок: " + escapeHtml(humanDate(it.due_date, { time: it.due_time }))) +      // дизайн-ревью, п. 15
    '</div></div>';
}

function fileSize(bytes) {
  return bytes > 1024 * 1024 ? (bytes / 1024 / 1024).toFixed(1).replace(".", ",") + " МБ" : Math.max(1, Math.round(bytes / 1024)) + " КБ";
}

function fileIconFor(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  return ext ? fileTypeIcon(name) : fileTypeIcon("");
}

function pickSubmitFiles() {
  document.getElementById("submit-file").click();
}

function renderSubmit(state, info) {
  const box = document.getElementById("submit-body");
  const files = submitting.files, n = files.length, lim = submitting.limit;
  const names = files.map(f => f.name).join(", ");
  if (state === "done") {
    box.innerHTML = '<div class="sub-done"><div class="big">' + icon("checkCircle", "xl ok") + '</div><h3>Отправлено</h3>' +
      '<p class="sheet-hint">' + escapeHtml(submitting.item.subject) + ' · ' + escapeHtml(names) +
      (info && info.status ? '<br>Статус в СДО: «' + escapeHtml(info.status) + '»' : '') + '</p>' +
      '<button class="primary" onclick="openLink(' + escapeHtml(JSON.stringify(submitting.item.description)) + ')">Открыть в СДО</button>' +
      '<button class="ghost" onclick="closeSheet(\'submit-sheet\')">Готово</button></div>';
    return;
  }
  const closed = !!(submitting.rules && submitting.rules.closed);
  if (!n) {
    box.innerHTML = submitHead() + submitRulesHtml() +
      (closed ? '' : '<div class="fpick" onclick="pickSubmitFiles()"><span class="ic">' + icon("clip") + '</span>' +
      '<div><b>' + (lim > 1 ? "Выбрать файлы" : "Выбрать файл") + '</b><div class="s">' +
      (lim > 1 ? "можно сразу до " + lim + " · " : "") + 'до ' + submitMaxMb() + ' МБ' + (lim > 1 ? ' каждый' : '') + '</div></div><span class="go">Обзор</span></div>') +
      '<button class="primary" disabled>Загрузить в СДО</button>';
    return;
  }
  const busy = state === "sending";
  box.innerHTML = submitHead() + submitRulesHtml() +
    (lim > 1 ? '<div class="fcount">' + Array.from({ length: lim }, (_, i) => '<i class="' + (i < n ? "on" : "") + '"></i>').join("") + '</div>' : '') +
    files.map((f, i) => '<div class="fpick chosen"><span class="ic">' + fileIconFor(f.name) + '</span><div><b>' + escapeHtml(f.name) + '</b>' +
      '<div class="s">' + fileSize(f.size) + '</div></div>' +
      (busy ? '' : '<button class="x" onclick="submitting.files.splice(' + i + ', 1); renderSubmit()" aria-label="Убрать">' + icon("cross") + '</button>') + '</div>').join("") +
    (!busy && n < lim ? '<div class="fpick add" onclick="pickSubmitFiles()">' + icon("plus", "inl") + ' Добавить ещё файл · ' + (lim - n) + ' из ' + lim + ' осталось</div>' : '') +
    '<div class="lock">' + icon("warning", "inl") + ' ' + (n > 1 ? n + " " + plural(n, "файл уйдёт", "файла уйдут", "файлов уйдут") : "Файл уйдёт") +
      ' преподавателю от твоего имени. Проверь названия и работу.</div>' +
    '<button class="primary" id="submit-go" onclick="sendSubmission()"' + (busy ? ' disabled' : '') + '>' +
    (busy ? 'Загружаю в СДО…' : 'Отправить на проверку' + (n > 1 ? ' · ' + n + ' ' + plural(n, "файл", "файла", "файлов") : '')) + '</button>' +
    (busy ? '' : '<button class="ghost" onclick="closeSheet(\'submit-sheet\')">Отмена</button>');
}

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

// Несколько файлов за раз: в «Файлах» iPhone — «Выбрать», в Фото — отметить
// несколько; если выбрали один, «＋ Добавить ещё файл» добирает остальные.
document.getElementById("submit-file").addEventListener("change", async e => {
  const picked = Array.from(e.target.files || []);
  e.target.value = "";
  const room = submitting.limit - submitting.files.length;
  if (picked.length > room) showToast("Можно ещё " + room + " — остальные не взял");
  for (const file of picked.slice(0, room)) {
    if (!submitExtOk(file.name || "")) {
      const acc = submitting.rules.accepted;
      showToast("«" + file.name + "» не подойдёт: СДО примет только " + acc.join(", ") + (acc.join() === ".zip" ? " — упакуй в архив" : ""));
      continue;
    }
    if (file.size > submitMaxMb() * 1024 * 1024) { showToast("«" + file.name + "» больше " + submitMaxMb() + " МБ"); continue; }
    submitting.files.push({ name: file.name || "работа", size: file.size, data: await readAsBase64(file) });
  }
  haptic();
  renderSubmit();
});

async function sendSubmission() {
  renderSubmit("sending");
  try {
    const res = await api("/api/sdo/submit", { method: "POST", body: JSON.stringify({
      deadline_id: submitting.item.id || 0, cmid: submitting.item.cmid || 0,
      files: submitting.files.map(f => ({ name: f.name, data: f.data })) }) });
    haptic("success");
    renderSubmit("done", res);
    if (submitting.item.cmid && typeof refreshTk === "function") refreshTk();
  } catch (e) {
    renderSubmit();
    showToast("⚠️ " + e.message);
    if (/подключи/.test(e.message)) { loadSdoStatus(); }
  }
}

// ── Безопасность: просто рассказать, как защищены данные ─────────────────
// Владелец: «не действие, а чтобы человек открыл и увидел — ваши данные тут
// зашифрованы, всё с ними хорошо». Цифры — с сервера (/api/security).

function secItem(ic, title, text) {
  return '<div class="sec-item"><span class="sec-ic">' + icon(ic) + '</span><div><b>' + title + '</b><p>' + text + '</p></div></div>';
}

async function openSecurity() {
  haptic();
  const box = document.getElementById("security-body");
  document.getElementById("security-sheet").classList.add("open");
  box.innerHTML = '<div class="skel" style="height:240px"></div>';
  let s = {};
  try { s = await api("/api/security"); } catch (e) {}
  const key = { passphrase: "из секретной фразы старосты", key: "отдельный ключ старосты", bot_token: "производный от ключа бота" }[s.key_source] || "в настройках сервера";
  const lim = s.limits || {};
  box.innerHTML =
    '<div class="sec-hero"><span class="sec-shield">' + icon("shield") + '</span><div><h3>Безопасность</h3>' +
      '<p>Что бот знает о тебе и как это защищено</p></div></div>' +
    secItem("lock", "Вход в СДО зашифрован",
      (s.sdo === "ok" ? "Твой вход подключён. " : "") +
      "Бот хранит не пароль, а только «оставаться в системе» — и то зашифрованным (AES + подпись, Fernet). " +
      "Ключ — " + key + ", лежит в настройках сервера отдельно от базы: даже с копией базы прочитать вход нельзя. " +
      "Используется только для твоих запросов. Отключить — в «СДО», одной кнопкой.") +
    secItem("user", "Вход в приложение — через Telegram",
      "Каждый запрос подписан Telegram — подделать его или зайти под тобой нельзя. " +
      "Подпись старше " + (s.auth_max_hours || 24) + " ч не принимается.") +
    secItem("download", "Файлы — по одноразовым ссылкам",
      "Ссылка на скачивание подписана и живёт " + (s.link_minutes || 10) + " минут; файлы из СДО бот берёт твоим входом.") +
    secItem("sparkle", "ИИ (Gemini от Google)",
      "Уходит только твой вопрос, история этого чата, нужные куски лекций группы, расписание и дедлайны. " +
      "Имя, Telegram и вход в СДО не уходят. Не пиши туда личное — бесплатный Gemini может учиться на запросах.") +
    secItem("pulse", "Статистика — без содержимого",
      "Только «кто, что открыл и когда» — без текстов вопросов, файлов и оценок. Староста видит, кто именно " +
      "заходил и какими разделами пользуется. Через " + (s.events_days || 180) + " дней удаляется сама.") +
    secItem("clock", "Защита от перегруза",
      "Не больше " + ((lim.ai || {}).count || 15) + " вопросов ИИ в минуту и " + ((lim.submit || {}).count || 6) +
      " сдач за " + ((lim.submit || {}).minutes || 10) + " минут с одного человека — чтобы никто не сжёг общий лимит и не долбил СДО.") +
    secItem("gear", "Ключи и пароли — только на сервере",
      "Токен бота, ключи ИИ и шифрования — в закрытых настройках сервера, в коде и базе их нет. Копия базы каждую ночь уходит только старосте.") +
    '<button class="ghost" onclick="closeSheet(\'security-sheet\')">Понятно</button>';
}

// ── Уведомления: конструктор (что присылать и в какие дни) ───────────────
// Раньше — только /settings в чате. Сохраняется сразу при каждом нажатии
// (/api/notify, notify_prefs.py), без кнопки «Сохранить».

const DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
let notifyState = null;

async function openNotify() {
  haptic();
  document.getElementById("notify-sheet").classList.add("open");
  const box = document.getElementById("notify-body");
  box.innerHTML = '<div class="skel" style="height:320px"></div>';
  try { notifyState = await api("/api/notify"); } catch (e) {
    box.innerHTML = '<p class="hint">Не удалось загрузить настройки: ' + escapeHtml(e.message) + '</p>';
    return;
  }
  renderNotify();
}

function ntSwitch(on, action) {
  return '<button class="nt-switch' + (on ? " on" : "") + '" role="switch" aria-checked="' + on + '" onclick="' + action + '"><span></span></button>';
}

function ntDays(key) {
  const days = notifyState.prefs[key];
  return '<div class="nt-days">' + DAY_NAMES.map((n, i) =>
    '<button class="' + (days.includes(i) ? "on" : "") + (i >= 5 ? " we" : "") + '" onclick="toggleNotifyDay(\'' + key + '\',' + i + ')">' + n + '</button>').join("") + '</div>';
}

function ntRow(title, sub, key) {
  return '<div class="nt-row"><div><b>' + title + '</b>' + (sub ? '<p>' + sub + '</p>' : '') + '</div>' +
    ntSwitch(notifyState.prefs[key], "toggleNotify('" + key + "')") + '</div>';
}

function ntCard(ic, title, sub, key, daysKey, extra) {
  const on = notifyState.prefs[key];
  return '<div class="nt-card' + (on ? "" : " off") + '"><div class="nt-head"><span class="nt-ic">' + icon(ic) + '</span>' +
    '<div><b>' + title + '</b><p>' + sub + '</p></div>' + ntSwitch(on, "toggleNotify('" + key + "')") + '</div>' +
    (on ? ntDays(daysKey) + (extra || "") : "") + '</div>';
}

// Сценарий напоминания: «выкл», пресеты и «своё» (поле ввода минут).
let notifyCustom = null;   // ключ сценария, у которого сейчас открыто поле «своё»

function minText(m) {
  const h = Math.floor(m / 60), mm = m % 60;
  return [h ? h + " ч" : "", mm ? mm + " мин" : ""].filter(Boolean).join(" ");
}

function ntRemind(r) {
  const v = notifyState.prefs[r.key];
  const own = v && !r.presets.includes(v);
  const chip = (val, text, on) => '<button class="' + (on ? "on" : "") + '" onclick="setRemind(\'' + r.key + '\',' + val + ')">' + text + '</button>';
  let html = '<div class="nt-remind"><div class="nt-sub">' + r.title + '</div><div class="nt-mins">' +
    chip(0, "выкл", v === 0) + r.presets.map(m => chip(m, minText(m), v === m)).join("") +
    '<button class="' + (own ? "on" : "") + '" onclick="openRemindCustom(\'' + r.key + '\')">' + (own ? minText(v) : "своё") + '</button></div>';
  if (notifyCustom === r.key) {
    html += '<div class="nt-custom"><input type="number" inputmode="numeric" min="1" max="' + r.max + '" id="remind-input" ' +
      'placeholder="минут до пары, до ' + r.max + '" value="' + (own ? v : "") + '">' +
      '<button onclick="saveRemindCustom(\'' + r.key + '\',' + r.max + ')">OK</button></div>';
  }
  return html + '</div>';
}

function setRemind(key, val) {
  notifyCustom = null;
  const prefs = {}; prefs[key] = val;
  saveNotify({ prefs: prefs });
}

function openRemindCustom(key) {
  haptic();
  notifyCustom = notifyCustom === key ? null : key;
  renderNotify();
  const inp = document.getElementById("remind-input");
  if (inp) inp.focus();
}

function saveRemindCustom(key, max) {
  const n = parseInt(document.getElementById("remind-input").value, 10);
  if (!(n >= 1 && n <= max)) { showToast("Число минут от 1 до " + max); return; }
  setRemind(key, n);
}

function renderNotify() {
  const s = notifyState, p = s.prefs;
  const box = document.getElementById("notify-body");
  let html = '<div class="sec-hero"><span class="sec-shield nt-bell">' + icon("bell") + '</span><div><h3>Уведомления</h3>' +
    '<p>Что бот присылает в личку и в какие дни</p></div></div>' +
    '<div class="nt-card nt-master"><div class="nt-head"><div><b>Присылать уведомления</b><p>' +
    (s.subscribed ? "Включены — настрой ниже, что именно" : "Выключены — бот ничего не пришлёт сам") + '</p></div>' +
    ntSwitch(s.subscribed, "toggleNotifyMaster()") + '</div></div>';
  if (s.subscribed) {
    const campus = s.home_campus ? "если пары не на " + escapeHtml(s.home_campus) + " — напишу, где" : "если пары в другом корпусе — напишу";
    html +=
      ntCard("sun", "Утреннее расписание", "в " + s.morning_time + " — пары на сегодня", "morning", "morning_days",
        ntRow("Погода", "строчка с погодой в начале", "weather") +
        ntRow("Другой корпус", campus, "campus") +
        ntRow("Только если есть пары", "в свободный день — тишина", "skip_empty")) +
      ntCard("clock", "Перед парой", "своё время для первой пары и после перемены", "lessons", "lesson_days",
        s.remind.map(ntRemind).join("")) +
      ntCard("deadlines", "Дедлайны", "в " + s.deadline_time + " — что сдать в ближайшие 3 дня", "deadlines", "deadline_days") +
      '<div class="nt-card' + (p.weekly ? "" : " off") + '"><div class="nt-head"><span class="nt-ic">' + icon("calendar") + '</span>' +
        '<div><b>Обзор недели</b><p>в воскресенье в 19:00 — пары по дням и что сдать</p></div>' +
        ntSwitch(p.weekly, "toggleNotify('weekly')") + '</div></div>' +
      '<div class="nt-card' + (p.grades ? "" : " off") + '"><div class="nt-head"><span class="nt-ic">' + icon("medal") + '</span>' +
        '<div><b>Новые баллы</b><p>напишу, когда в СДО изменятся баллы по предмету (если подключён вход)</p></div>' +
        ntSwitch(p.grades, "toggleNotify('grades')") + '</div></div>';
  }
  box.innerHTML = html + '<button class="ghost" onclick="closeSheet(\'notify-sheet\')">Готово</button>';
}

async function saveNotify(body) {
  haptic();
  try { notifyState = await api("/api/notify", { method: "POST", body: JSON.stringify(body) }); }
  catch (e) { showToast("Не сохранилось: " + e.message); }
  renderNotify();
}

function toggleNotifyMaster() { saveNotify({ subscribed: !notifyState.subscribed }); }

function toggleNotify(key) {
  const prefs = {}; prefs[key] = !notifyState.prefs[key];
  saveNotify({ prefs: prefs });
}

function toggleNotifyDay(key, day) {
  const days = notifyState.prefs[key];
  const prefs = {};
  prefs[key] = days.includes(day) ? days.filter(d => d !== day) : days.concat([day]);
  saveNotify({ prefs: prefs });
}

// ── Знакомство при первом входе: карточки ONBOARD, один раз ─────────────
// Флаг — в облаке Telegram (CloudStorage: тот же человек на другом телефоне
// не увидит второй раз), без него — в localStorage устройства.

const ONBOARD_KEY = "onboarded_v1";
const ONBOARD = [
  { ic: "cap", cls: "t-sdo", title: "Баллы и сдача работ",
    text: "Подключи свой вход в СДО — увидишь баллы по каждому предмету, что зачтено и сколько осталось, и сможешь сдавать работы прямо отсюда.",
    act: "Подключить СДО", go: () => openSdoSheet() },
  { ic: "bell", cls: "t-bell", title: "Уведомления под тебя",
    text: "Утром — пары и погода, перед парой — напоминание, к дедлайнам — своё время. Дни недели и «другой корпус» — настраиваются.",
    act: "Настроить", go: () => openNotify() },
  // главное отличие бота — ИИ по лекциям группы и конспекты (дизайн-ревью, п. 20)
  { ic: "sparkle", cls: "t-ai", title: "ИИ знает ваши лекции",
    text: "Отвечает по лекциям вашей группы и показывает, из какой взял. Решает задачи по фото, знает расписание и дедлайны.",
    act: "Спросить ИИ", go: () => switchTab("chat") },
  { ic: "bookOpen", cls: "t-summary", title: "Конспект за минуту",
    text: "Нажми на лекцию с пометкой в «Файлах» — ИИ коротко перескажет главное. Конспект один на всю группу.",
    act: "Открыть файлы", go: () => switchTab("files") },
  { ic: "search", cls: "t-search", title: "Расписание кого угодно",
    text: "Пары любого преподавателя, группы или аудитории МИРЭА. Нужное можно закрепить, чтобы не искать снова.",
    act: "Попробовать", go: () => switchTab("search") },
];
let onboardStep = 0;

// Флаг в облаке Telegram (CloudStorage, Bot API 6.9), без него — localStorage.
function cloudFlag(key, value, done) {
  const cs = tg && tg.CloudStorage;
  const get = value === undefined;
  try {
    if (cs && tg.isVersionAtLeast && tg.isVersionAtLeast("6.9")) {
      if (get) cs.getItem(key, (err, v) => done(err ? null : (v || "")));
      else cs.setItem(key, value);
      return;
    }
  } catch (e) {}
  try {
    if (get) done(localStorage.getItem(key) || "");
    else localStorage.setItem(key, value);
  } catch (e) { if (get) done(null); }      // хранилища нет — null, «не знаем»
}

function onboardStore(get, done) {
  if (get) cloudFlag(ONBOARD_KEY, undefined, v => done(v === null || !!v));   // не знаем — не показываем
  else cloudFlag(ONBOARD_KEY, "1");
}

// ── «Что нового»: один раз после крупного обновления ─────────────────────
// Новичок видит знакомство, а «что нового» ему ни к чему — помечаем
// прочитанным. Остальным — лист с главным, по разу на выпуск NEWS.id.
const NEWS = {
  id: "v5.15",
  items: [
    ["route", "Автопилот", "☰ Ещё → «План»: бот сам раскладывает работы СДО и дедлайны по свободным окнам между парами — чтобы дойти до зачёта или нужной оценки без авралов. Дела на сегодня — прямо между парами."],
    ["clock", "План учится", "Нажал «Сделал» и сказал, сколько заняло, — в следующий раз на похожие работы план заложит твоё время. У тестов — лимит из СДО."],
    ["checkCircle", "Что если пропущу лекцию", "Нажми на предмет в «Плане»: сколько баллов это стоит и что добавится, чтобы добрать."],
    ["search", "Поиск по смыслу", "Спрашивай своими словами — ИИ найдёт нужное в лекциях, даже если там это называется иначе. Под ответом — «Лекция 5 · слайд 12»: нажми, и откроется страница."],
  ],
};

function maybeWhatsNew(firstVisit) {
  if (firstVisit) { cloudFlag("news_seen", NEWS.id); return; }
  cloudFlag("news_seen", undefined, seen => {
    if (seen === null || seen === NEWS.id) return;
    showWhatsNew();
  });
}

function showWhatsNew() {
  document.getElementById("news-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield nt-bell">' + icon("sparkle") + '</span><div><h3>Что нового</h3>' +
    '<p>Обновили приложение — коротко о главном</p></div></div>' +
    NEWS.items.map(([ic, t, d]) => secItem(ic, t, escapeHtml(d))).join("") +
    '<button class="primary" style="margin-top:10px" onclick="closeSheet(\'news-sheet\')">Круто</button>';
  document.getElementById("news-sheet").classList.add("open");
  cloudFlag("news_seen", NEWS.id);
}

function maybeOnboard() {
  onboardStore(true, seen => {
    if (!seen) showOnboard(0);
    maybeWhatsNew(!seen);
  });
}

function showOnboard(i) {
  onboardStep = i;
  const s = ONBOARD[i];
  const box = document.getElementById("onboard");
  box.innerHTML =
    '<button class="ob-skip" onclick="finishOnboard()">Пропустить</button>' +
    '<div class="ob-card" key="' + i + '">' +
      '<div class="ob-logo">' + icon("capy", "capy") + '<span>УИБО-бот</span></div>' +
      '<div class="ob-ic sq ' + s.cls + '">' + icon(s.ic) + '</div>' +
      '<h2>' + s.title + '</h2><p>' + s.text + '</p>' +
      '<button class="ghost ob-act" onclick="finishOnboard(' + i + ')">' + s.act + '</button>' +
    '</div>' +
    '<div class="ob-dots">' + ONBOARD.map((_, j) => '<i class="' + (j === i ? "on" : "") + '"></i>').join("") + '</div>' +
    '<button class="primary ob-next" onclick="' + (i < ONBOARD.length - 1 ? "nextOnboard()" : "finishOnboard()") + '">' +
      (i < ONBOARD.length - 1 ? "Дальше" : "Начать") + '</button>';
  box.classList.add("open");
}

function nextOnboard() { haptic(); showOnboard(onboardStep + 1); }

function finishOnboard(actionIndex) {
  haptic();
  document.getElementById("onboard").classList.remove("open");
  onboardStore(false);
  if (actionIndex !== undefined) ONBOARD[actionIndex].go();
}

loadSdoStatus();
