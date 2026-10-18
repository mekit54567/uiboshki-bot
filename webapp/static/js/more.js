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

// «Канал и связь»: канал бота и «Написать нам» — одна плитка, лист с двумя
// строками (как «Новости и связь» в приложении); ссылки не задана — «Скоро»
function openLinks() {
  haptic();
  const row = (ic, title, text, call) => '<button class="sec-item link-item" onclick="closeSheet(\'links-sheet\'); ' +
    call + '"><span class="sec-ic">' + icon(ic) + '</span><div><b>' + title + '</b><p>' + text + '</p></div>' +
    icon("chevron", "link-chev") + '</button>';
  document.getElementById("links-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield nt-bell">' + icon("send") + '</span><div><h3>Канал и связь</h3>' +
      '<p>Новости бота и как с нами связаться</p></div></div>' +
    row("send", "Канал бота", "Новости, как всё устроено и что нового", "openConfigLink(CHANNEL_URL)") +
    row("message", "Написать нам", "Идея, ошибка или вопрос — ответим", "openConfigLink(CONTACT_URL)") +
    '<button class="ghost" onclick="closeSheet(\'links-sheet\')">Закрыть</button>';
  document.getElementById("links-sheet").classList.add("open");
}

// «Позвать»: готовое сообщение с личной ссылкой (referrals.py) — Telegram сам
// предложит выбрать чат; друг начнёт пользоваться — обоим дни «Капибары+»
async function shareBot() {
  let url;
  try { url = (await api("/api/invite")).tg_share; }
  catch (e) {
    const text = "Капибара — расписание любой группы МИРЭА, дедлайны и баллы СДО в одном месте";
    url = "https://t.me/share/url?url=" + encodeURIComponent(location.origin + "/about") + "&text=" + encodeURIComponent(text);
  }
  if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
  else openLink(url);
}

// «Капибара+»: статус, цены, оплата — на сайте по личной ссылке (billing.py),
// дни за друзей и ранги ачивок
const RANK_NAMES = { dawn: "Рассвет", noon: "Полдень", dusk: "Сумерки", midnight: "Полночь" };

function fmtDay(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

// «Позови друга»: сколько друзей ещё дадут дни пригласившему — число с сервера
// (referrals.REF_MAX), не здесь; выбрал — честно, что бонус закончился
function inviteText(inv) {
  const max = inv.ref_max || 0, got = inv.ref_counted || 0;
  const came = " По твоей ссылке пришло: " + (inv.came || 0) + ".";
  if (max && got >= max)
    return "Ты уже позвал " + max + " друзей — бонус за приглашения закончился, друзьям дни по-прежнему дают." + came;
  return "Когда он попользуется " + inv.friend_days + " дня, вам обоим +" + inv.bonus_days + " дней." +
    (max ? " Тебе — максимум за " + max + " друзей, засчитано " + got + " из " + max + "." : "") + came;
}

async function openPlus() {
  haptic();
  const box = document.getElementById("plus-body");
  document.getElementById("plus-sheet").classList.add("open");
  box.innerHTML = '<div class="skel" style="height:240px"></div>';
  let d;
  try { d = await api("/api/plus"); }
  catch (e) { box.innerHTML = '<p class="sheet-hint">' + escapeHtml(e.message) + '</p>'; return; }
  const inv = d.invite || {};
  const founderNote = d.founder ? "У тебя метка Early Supporter: цена первых пользователей остаётся за тобой навсегда"
    : (d.prices || []).some(p => p.founder) ? "Сейчас цена первых пользователей: кто оплатит по ней, так и платит всегда" : "";
  const state = d.unlimited
    ? statusCard("ok", "У тебя безлимит" + (d.unlimited_until ? " до " + fmtDay(d.unlimited_until) : " навсегда"),
      "ИИ без дневных лимитов, платить не нужно")
    : d.paid_until
    ? statusCard("ok", "Подписка до " + fmtDay(d.until), founderNote || "Оплата добавит дни к этому сроку")
    : d.gift
      ? statusCard("ok", "Подарок группе до " + fmtDay(d.gift), "Платить не нужно — всё уже включено")
      : statusCard("off", "Подписки нет", founderNote || "Всё бесплатное — расписание, сроки, баллы, файлы — остаётся бесплатным");
  const prices = (d.prices || []).map(p => '<div class="plus-price"><span>' + escapeHtml(p.title) + ' · ' + p.days + ' дней' +
    (p.founder ? ' <i>Early Supporter</i>' : '') + '</span><b>' + (p.price < p.full ? '<s>' + p.full + '&nbsp;₽</s> ' : '') + p.price + '&nbsp;₽</b></div>').join("");
  const ranks = Object.entries(inv.ranks || {}).map(([k, r]) =>
    RANK_NAMES[k] + " — " + r.days + " дн." + (r.claimed ? " (получен)" : "")).join(" · ");
  box.innerHTML =
    '<div class="sec-hero"><span class="sec-shield nt-bell">' + icon("medal") + '</span><div><h3>Капибара+</h3>' +
      '<p>Подписка на Капибару</p></div></div>' + state +
    secItem("sparkle", "Что даёт", (d.unlimited ? "ИИ без ограничений" + (d.unlimited_until ? " до " + fmtDay(d.unlimited_until) : "")
      : "ИИ — до 100 вопросов в день для любой группы") + ", иконки и наряды капибары " +
      "«по подписке», значок. Дальше — ответы на билеты, «Пульс группы», «Архив потока».") +
    (d.unlimited ? "" : prices +        // безлимиту цены и оплата ни к чему (робот 18.10)
      (d.pay_url
        ? '<button class="primary" style="margin-top:10px" onclick="openLink(\'' + d.pay_url + '\')">Оплатить на сайте</button>' +
          '<p class="sheet-hint">Без автосписаний, июль и август не считаются. Условия — в <a class="legal-link" onclick="openLegal(event, \'offer\')">оферте</a>.</p>'
        : '<p class="sheet-hint">Оплата скоро заработает.</p>')) +
    secItem("users", "Позови друга", inviteText(inv)) +
    (ranks ? secItem("medal", "Ранги ачивок", "Закрыл ранг в приложении — дни подписки: " + ranks) : "") +
    '<button class="ghost" onclick="shareBot()">' + icon("share", "inl") + ' Позвать друга</button>' +
    (d.donate_url ? secItem("heart", "Поддержать проект", "Разово, сумма на выбор — 100, 300, 500 ₽ или своя.") +
      '<button class="ghost" onclick="openLink(\'' + d.donate_url + '\')">' + icon("heart", "inl") + ' Поддержать проект</button>' : "") +
    '<button class="ghost" onclick="closeSheet(\'plus-sheet\')">Закрыть</button>';
}

// «Поддержать проект» (строка под плитками «Ещё»): донат на сайте по личной
// ссылке (billing.py) — не подписка, ничего не открывает, просто спасибо
async function openDonate() {
  haptic();
  let d;
  try { d = await api("/api/donate"); }
  catch (e) { showToast("Не вышло: " + e.message); return; }
  if (d.hidden) return;
  if (d.url) openLink(d.url);
  else showToast("Поддержать можно будет совсем скоро — оплата ещё подключается");
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
      consentRow("sdo-agree", "syncSdoBtn()", ", в том числе из СДО: баллы, посещения, задания") +
      '<button class="primary" id="sdo-save" disabled onclick="connectSdo()">Проверить и сохранить</button>' +
      (GUIDE_URL ? '<button class="ghost" onclick="openConfigLink(GUIDE_URL)">Гайд со скринами — в канале</button>' : '') +
      '<button class="ghost" onclick="renderSdo()">Позже</button>';
    return;
  }
  if (sdoState.state === "ok") {
    box.innerHTML = '<h3>' + icon("cap", "inl acc") + ' СДО</h3>' +
      statusCard("ok", "Подключено, работает", sdoState.shared ? "Вход старосты из настроек бота" : agoText(sdoState.checked_at)) +
      '<p class="sheet-hint">У дедлайнов из СДО есть кнопка «' + icon("upload", "inl") + 'Сдать»: выбираешь файл — бот загружает его в нужное задание.</p>' +
      (sdoState.can_share ? '<div class="share-row"><div><b>Делиться заданиями с группой</b><span>Бот возьмёт из твоего СДО задания и сроки для всей ' +
        escapeHtml(sdoState.group || "группы") + '. Баллы и работы никто не увидит.</span></div>' +
        ntSwitch(sdoState.share, "toggleSdoShare()") + '</div>' : '') +
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

// Кнопка подключения — только с галочкой согласия (152-ФЗ, privacy.js)
function syncSdoBtn() {
  document.getElementById("sdo-save").disabled = !consentChecked("sdo-agree");
}

async function connectSdo() {
  const input = document.getElementById("sdo-cookie");
  const btn = document.getElementById("sdo-save");
  if (!consentChecked("sdo-agree")) return;
  if (!input.value.trim()) { input.focus(); return; }
  btn.disabled = true; btn.textContent = "Проверяю…";
  try {
    sdoState = await api("/api/sdo/connect", { method: "POST", body: JSON.stringify({ cookie: input.value, agree: true }) });
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
  // Пока файл грузится, лист могли закрыть и открыть «Сдать» у другого
  // задания — тогда итог этой сдачи только тостом, чужой лист не трогаем.
  const s = submitting;
  renderSubmit("sending");
  try {
    const res = await api("/api/sdo/submit", { method: "POST", body: JSON.stringify({
      deadline_id: s.item.id || 0, cmid: s.item.cmid || 0,
      files: s.files.map(f => ({ name: f.name, data: f.data })) }) });
    haptic("success");
    if (submitting === s) renderSubmit("done", res);
    else showToast("✓ «" + s.item.subject + "» сдано");
    if (s.item.cmid && typeof refreshTk === "function") refreshTk();
  } catch (e) {
    if (submitting === s) { renderSubmit(); showToast("⚠️ " + e.message); }
    else showToast("⚠️ «" + s.item.subject + "» не сдано: " + e.message);
    if (/подключи/.test(e.message)) { loadSdoStatus(); }
  }
}

// ── Безопасность: просто рассказать, как защищены данные ─────────────────
// Владелец: «не действие, а чтобы человек открыл и увидел — ваши данные тут
// зашифрованы, всё с ними хорошо». Цифры — с сервера (/api/security).

// «Ещё → Установить»: где ещё есть Капибара — Telegram, PWA на телефоне и
// компьютере (uiboshki.ru/app), своё приложение. Раньше плитка «Ярлык» только
// добавляла ярлык Telegram, и про PWA никто не знал (владелец, 09.10).
const APP_URL = "https://www.uiboshki.ru/app";

function openPlatforms() {
  haptic();
  const ios = /iPhone|iPad/.test(navigator.userAgent);
  document.getElementById("platforms-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield nt-bell">' + icon("phone") + '</span><div><h3>Капибара — везде</h3>' +
    '<p>Те же пары, сроки и баллы — в Telegram, в браузере и на экране телефона</p></div></div>' +
    secItem("send", "Telegram", "Бот пишет про пары и сроки, а приложение открывается кнопкой слева от поля ввода." +
      (IN_TG ? " Ярлык на экран «Домой» — кнопка внизу." : "")) +
    secItem("phone", "Как приложение — без Telegram",
      "Открой <b>uiboshki.ru/app</b> в " + (ios ? "Safari → «Поделиться» → «На экран „Домой“»." :
        "Chrome → «Установить приложение» (на iPhone — Safari → «Поделиться» → «На экран „Домой“»).") +
      " Вход — через Telegram или VK, уведомления приходят пушем, расписание открывается и без сети.") +
    secItem("laptop", "На компьютере", "Тот же адрес в Chrome, Edge или Яндекс Браузере — значок «Установить» в адресной строке.") +
    secItem("sparkle", "Android и iPhone", "Своё приложение уже собирается — скоро.") +
    '<button class="primary" style="margin-top:10px" onclick="addToHome()">' +
      (IN_TG ? "Ярлык на экран «Домой»" : "Установить") + '</button>' +
    '<button class="ghost" onclick="copyAppLink()">' + icon("copy", "inl") + ' Скопировать ссылку</button>';
  document.getElementById("platforms-sheet").classList.add("open");
}

async function copyAppLink() {
  try { await navigator.clipboard.writeText(APP_URL); } catch (e) { prompt("Ссылка на приложение:", APP_URL); return; }
  haptic("success");
  showToast("Ссылка скопирована — открой её в браузере телефона или компьютера");
}

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
      "Токен бота, ключи ИИ и шифрования — в закрытых настройках сервера, в коде и базе их нет. Копия базы каждую ночь " +
      "уходит только владельцу бота в Telegram, старые копии он удаляет раз в месяц.") +
    '<div id="logins"></div><div id="devices"></div>' +
    '<h3 style="margin-top:16px">Твои данные</h3>' +
    '<p class="sheet-hint">Что храним, сколько и кому передаём — в <a class="legal-link" onclick="openLegal(event, \'privacy\')">' +
      'Политике обработки персональных данных</a>. Твоё <a class="legal-link" onclick="openLegal(event, \'consent\')">' +
      'согласие на обработку персональных данных</a> можно отозвать — удалив всё:</p>' +
    '<button class="ghost danger" onclick="deleteMyData()">Удалить все мои данные</button>' +
    '<button class="ghost" onclick="closeSheet(\'security-sheet\')">Понятно</button>';
  loadDevices();
  loadLogins();
}

// Чем ещё можно входить: VK ID и Яндекс ID (webapp/routes/auth.py). Привязка — в
// браузере: там вход у провайдера и кнопка «Да, привязать» с именем аккаунта.
async function loadLogins() {
  let res;
  try { res = await api("/api/auth/identities"); } catch (e) { return; }
  const box = document.getElementById("logins");
  if (!box || !res.available.length) return;
  const have = new Set(res.items.map(i => i.provider));
  box.innerHTML = '<h3 style="margin-top:16px">Вход без Telegram</h3>' +
    '<p class="hint">Привяжи VK или Яндекс — сможешь войти, даже если Telegram не откроется.</p>' +
    res.available.map(p => have.has(p.id)
      ? '<div class="dev-row"><div><b>' + escapeHtml(p.name) + '</b><span>привязан</span></div>' +
        '<button class="ghost danger" onclick="unlinkLogin(\'' + p.id + '\')">Отвязать</button></div>'
      : '<button class="ghost" onclick="linkLogin(\'' + p.id + '\')">Привязать ' + escapeHtml(p.name) + '</button>').join("");
}

async function linkLogin(provider) {
  haptic();
  try {
    const res = await api("/api/auth/" + provider + "/link", { method: "POST", body: JSON.stringify({ client: "web" }) });
    if (IN_TG) openLink(res.url); else location.href = res.url;
  } catch (e) { showToast(e.message); }
}

async function unlinkLogin(provider) {
  haptic();
  try { await api("/api/auth/identities/" + provider, { method: "DELETE" }); } catch (e) { showToast(e.message); return; }
  loadLogins();
}

// Устройства, где вошли в приложение без Telegram (этап 2): выйти на одном или везде
async function loadDevices() {
  let res;
  try { res = await api("/api/auth/sessions"); } catch (e) { return; }
  const box = document.getElementById("devices");
  if (!box || !res.items.length) return;
  box.innerHTML = '<h3 style="margin-top:16px">Устройства</h3>' + res.items.map(d =>
    '<div class="dev-row"><div><b>' + escapeHtml(d.device || "Браузер") + (d.current ? " · это" : "") + '</b><span>заходил ' +
    escapeHtml(humanDate((d.last_seen || "").slice(0, 10))) + '</span></div>' +
    '<button class="ghost danger" onclick="revokeDevice(' + d.id + ', ' + !!d.current + ')">Выйти</button></div>').join("") +
    (res.items.length > 1 ? '<button class="ghost danger" onclick="revokeDevice(0, true)">Выйти везде</button>' +
      '<p class="sheet-hint">Выйдут все устройства и выключатся пуши. Вход через VK или Яндекс останется, пока не отвяжешь его выше.</p>' : '');
}

async function revokeDevice(id, current) {
  haptic();
  try {
    if (id) await api("/api/auth/sessions/" + id, { method: "DELETE" });
    else await api("/api/auth/logout?everywhere=true", { method: "POST" });
  } catch (e) { showToast(e.message); return; }
  if (current && !IN_TG) {
    saveToken("");
    try { navigator.serviceWorker.controller.postMessage("logout"); } catch (e) {}
    location.replace("/app");
    return;
  }
  loadDevices();
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

// Пуши на это устройство — только в установленном приложении вне Telegram (PWA)
function pushSupported() {
  return !IN_TG && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function renderPushRow() {
  if (!pushSupported()) return;
  const box = document.getElementById("notify-body");
  let on = false;
  try {
    const reg = await navigator.serviceWorker.ready;
    on = !!(await reg.pushManager.getSubscription()) && Notification.permission === "granted";
  } catch (e) {}
  // под шапкой листа, а не над ней; renderNotify перерисовывает лист при каждом
  // тумблере — старую строку убрать, иначе их станет две (или ни одной)
  const old = document.getElementById("push-row");
  if (old) old.remove();
  const row = document.createElement("div");
  row.id = "push-row";
  row.className = "share-row";
  row.innerHTML = '<div><b>Уведомления на этом устройстве</b><span>Утро, пары, дедлайны и новые задания — ' +
    'пушем, как у обычного приложения.</span></div>' + ntSwitch(on, "togglePush(" + on + ")");
  const hero = box.querySelector(".sec-hero");
  if (hero) hero.after(row); else box.prepend(row);
}

async function togglePush(on) {
  haptic();
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (on) {
      if (sub) { await api("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }); await sub.unsubscribe(); }
      showToast("Пуши на этом устройстве выключены");
    } else if (await enablePush()) {
      showToast("Готово — пуши будут приходить сюда");
    }
  } catch (e) { showToast("Не получилось: " + e.message); }
  openNotify();
  if (typeof initPwaHint === "function") initPwaHint();
}

// Спросить разрешение и подписать устройство на пуши — из «Уведомлений» и из
// подсказки на «Сегодня» (home.js). Звать по нажатию: иначе iPhone не спросит.
async function enablePush() {
  try {
    if (await Notification.requestPermission() !== "granted") { showToast("Разреши уведомления в настройках браузера"); return false; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    const { key } = await api("/api/push/key");
    const pad = "=".repeat((4 - key.length % 4) % 4);
    const raw = Uint8Array.from(atob((key + pad).replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const fresh = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: raw });
    await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(fresh.toJSON()) });
    return true;
  } catch (e) { showToast("Не получилось: " + e.message); return false; }
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

// Вечерняя сводка на завтра (evening_digest.py, Никита 12.10): пары, погода,
// сроки — в выбранное время. Сервер отдаёт ключ только при новом дизайне
// (DESIGN2=0 — пункта нет).
const EVENING_TIMES = ["19:00", "20:00", "21:00", "22:00"];

function ntEvening(p) {
  if (!("evening" in p)) return "";
  const t = p.evening_time || "20:00";
  const times = EVENING_TIMES.includes(t) ? EVENING_TIMES : EVENING_TIMES.concat([t]).sort();
  return '<div class="nt-card' + (p.evening ? "" : " off") + '"><div class="nt-head"><span class="nt-ic">' + icon("moon") + '</span>' +
    '<div><b>Вечерняя сводка</b><p>Пары и сроки на завтра · ' + escapeHtml(t) + '</p></div>' +
    ntSwitch(p.evening, "toggleNotify('evening')") + '</div>' +
    (p.evening ? '<div class="nt-mins">' + times.map(x =>
      '<button class="' + (x === t ? "on" : "") + '" onclick="setEveningTime(\'' + x + '\')">' + x + '</button>').join("") + '</div>' : "") +
    '</div>';
}

function setEveningTime(t) {
  saveNotify({ prefs: { evening_time: t } });
}

// Тесты СДО (quiz_alerts.py, Никита 12.10): один пункт, по нажатию — за
// сколько до закрытия напомнить (несколько сразу) и «Тест открылся».
const QUIZ_CHOICES = [1440, 180, 60, 30, 10];
let notifyQuizOpen = false;

function quizLabel(m) { return m >= 1440 ? "1 день" : minText(m); }

function quizSummary(p) {
  const r = (p.quiz_remind || []).slice().sort((a, b) => b - a).map(quizLabel);
  const parts = [];
  if (r.length) parts.push("за " + (r.length > 1 ? r.slice(0, -1).join(", ") + " и " + r[r.length - 1] : r[0]) + " до закрытия");
  if (p.quiz_open !== false) parts.push("когда откроют");
  return parts.length ? parts.join(" · ") : "выключено";
}

function ntQuiz(s) {
  const p = s.prefs, mins = p.quiz_remind || [], on = mins.length > 0 || p.quiz_open !== false;
  let html = '<div class="nt-card' + (on ? "" : " off") + '"><div class="nt-head tap" onclick="toggleQuizCard()">' +
    '<span class="nt-ic">' + icon("clock") + '</span><div><b>Тесты СДО</b><p>' + quizSummary(p) + '</p></div>' +
    '<span class="nt-chev' + (notifyQuizOpen ? " open" : "") + '">' + icon("chevron") + '</span></div>';
  if (notifyQuizOpen) {
    html += '<div class="nt-remind"><div class="nt-sub">Напомнить до закрытия</div><p class="nt-note">можно несколько</p>' +
      '<div class="nt-mins">' + (s.quiz_choices || QUIZ_CHOICES).map(m =>
        '<button class="' + (mins.includes(m) ? "on" : "") + '" onclick="toggleQuizRemind(' + m + ')">' + quizLabel(m) + '</button>').join("") +
      '</div></div>' +
      '<div class="nt-row"><div><b>Тест открылся</b><p>напишу, когда преподаватель откроет тест</p></div>' +
      ntSwitch(p.quiz_open !== false, "toggleQuizOpen()") + '</div>';
  }
  return html + '</div>';
}

function toggleQuizCard() {
  haptic();
  notifyQuizOpen = !notifyQuizOpen;
  renderNotify();
}

function toggleQuizRemind(m) {
  const list = (notifyState.prefs.quiz_remind || []).slice();
  const i = list.indexOf(m);
  if (i >= 0) list.splice(i, 1); else list.push(m);
  saveNotify({ prefs: { quiz_remind: list.sort((a, b) => b - a) } });
}

function toggleQuizOpen() {
  saveNotify({ prefs: { quiz_open: notifyState.prefs.quiz_open === false } });
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
        ntSwitch(p.grades, "toggleNotify('grades')") + '</div></div>' +
      '<div class="nt-card' + (p.new_tasks ? "" : " off") + '"><div class="nt-head"><span class="nt-ic">' + icon("deadlines") + '</span>' +
        '<div><b>Новые задания</b><p>напишу, когда в СДО появится задание или перенесут срок</p></div>' +
        ntSwitch(p.new_tasks, "toggleNotify('new_tasks')") + '</div></div>' +
      ntQuiz(s) +
      ntEvening(p);
  }
  box.innerHTML = html + '<button class="ghost" onclick="closeSheet(\'notify-sheet\')">Готово</button>';
  renderPushRow();
}

// Быстрые нажатия (Пн, Вт, Ср подряд) терялись: каждый запрос нёс список
// дней из ещё не обновлённого notifyState. Теперь меняем у себя сразу, а
// запросы уходят по очереди; ответ сервера берём от последнего.
let notifyQueue = Promise.resolve();
let notifyPending = 0;

function saveNotify(body) {
  haptic();
  if (body.subscribed !== undefined) notifyState.subscribed = body.subscribed;
  if (body.prefs) Object.assign(notifyState.prefs, body.prefs);
  renderNotify();
  notifyPending++;
  notifyQueue = notifyQueue.then(async () => {
    let fresh = null;
    try { fresh = await api("/api/notify", { method: "POST", body: JSON.stringify(body) }); }
    catch (e) {
      showToast("Не сохранилось: " + e.message);
      try { fresh = await api("/api/notify"); } catch (e2) {}     // что на самом деле сохранено
    }
    if (--notifyPending === 0 && fresh) { notifyState = fresh; renderNotify(); }
  });
  return notifyQueue;
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
  id: "v5.50",
  items: [
    ["phone", "Без Telegram — тоже", "uiboshki.ru/app ставится на экран телефона или компьютера как приложение: вход через Telegram или VK, уведомления пушем. Как — «Ещё → Установить»."],
    ["users", "Любая группа МИРЭА", "Расписание, рассылки и сроки — своей группы. Поменять — «Ещё → Моя группа»."],
    ["edit", "Общий срок — под себя", "Перенёс срок или убрал лишнее — меняется только у тебя, у остальных всё как было. «Как у всех» — вернуть."],
    ["sparkle", "Своё приложение", "Для Android и iPhone — уже собирается. Расскажем в канале."],
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

// ── Своя группа (этап 1: любая группа института) ─────────────────────────────
// /api/me → myGroup; нет группы — лист открывается сам и без группы не
// закрывается. Поиск — /api/groups/search (справочник расписания МИРЭА).

let myGroup = null, myPlan = "own", groupTimer = null, groupSeq = 0;

function openGroup(force) {
  if (!force) haptic();
  document.getElementById("group-sheet").classList.add("open");
  document.getElementById("group-body").innerHTML =
    '<h3>' + icon("users", "inl acc") + (myGroup ? " Моя группа" : " Из какой ты группы?") + '</h3>' +
    (myGroup ? '<p class="hint">Сейчас: <b>' + escapeHtml(myGroup.name) + '</b>. Сменить — найди другую.' +
               (myGroup.own ? '' : ' <a href="#" onclick="requestGroupAdmin(); return false">Я староста этой группы</a>') + '</p>'
             : '<p class="hint">Найди свою — покажу её расписание, дедлайны и файлы.</p>') +
    '<input class="searchbox" id="group-search" enterkeyhint="search" placeholder="Например: УИБО-03-24" autocomplete="off" oninput="groupInput()">' +
    '<div id="group-results"></div>';
}

function groupInput() {
  clearTimeout(groupTimer);
  groupTimer = setTimeout(searchGroups, 250);
}

async function searchGroups() {
  const q = document.getElementById("group-search").value.trim(), my = ++groupSeq;
  const box = document.getElementById("group-results");
  if (q.length < 2) { box.innerHTML = ""; return; }
  try {
    const res = await api("/api/groups/search?q=" + encodeURIComponent(q));
    if (my !== groupSeq) return;
    box.innerHTML = res.items.length ? res.items.map(g =>
      '<button class="group-row" onclick="pickGroup(' + g.id + ')">' + escapeHtml(g.name) + icon("chevron", "inl") + '</button>').join("")
      : '<p class="hint">Не нашёл. Напиши, как в расписании: УИБО-03-24</p>';
  } catch (e) {
    if (my === groupSeq) box.innerHTML = '<p class="hint">Не удалось найти: ' + escapeHtml(e.message) + '</p>';
  }
}

async function pickGroup(id) {
  haptic("success");
  try {
    const res = await api("/api/me/group", { method: "POST", body: JSON.stringify({ id }) });
    const changed = !myGroup || myGroup.id !== res.group.id;
    myGroup = res.group;
    closeSheet("group-sheet");
    showToast("Твоя группа — " + res.group.name);
    if (changed) { todayData = null; loadToday(); }
  } catch (e) { showToast(e.message); }
}

async function requestGroupAdmin() {
  haptic();
  try {
    const res = await api("/api/me/group/admin", { method: "POST" });
    showToast(res.message);
  } catch (e) { showToast(e.message); }
}

async function toggleSdoShare() {
  haptic();
  try {
    sdoState = await api("/api/sdo/share", { method: "POST", body: JSON.stringify({ share: !sdoState.share }) });
    renderSdo();
    if (sdoState.share) showToast("Спасибо! Задания группы появятся в дедлайнах через минуту");
  } catch (e) { showToast(e.message); }
}
