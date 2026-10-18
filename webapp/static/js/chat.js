// Чат с ИИ: история, вложения, предметы — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Чат ───────────────────────────────────────────────────────────────────

// Чаты живут в localStorage этого устройства (только текст, без вложений):
// закрыл WebApp — открыл — разговор на месте. «＋ Новый» не стирает старый —
// он остаётся в «☰ Чаты» (до 20 последних).
const CHATS_KEY = "chats.v1", OLD_CHAT_KEY = "chatLog.v1";
// Какой чат был открыт: «new» — нажали «＋ Новый» и ещё ничего не написали;
// тогда при следующем заходе открывается этот новый, а не старый (просьба владельца).
const CHAT_CUR_KEY = "chats.current";
let chats = loadChats();              // [{id, title, updated, log}]
let chatId = null, chatLog = [];      // [{role, content, html, att, files, sources, file_text}]
(function () {
  let cur = null;
  try { cur = localStorage.getItem(CHAT_CUR_KEY); } catch (e) {}
  const c = cur === "new" ? null : (chats.find(x => x.id === cur) || chats[0]);
  if (c) { chatId = c.id; chatLog = c.log; }
})();

function rememberChat() {
  try { localStorage.setItem(CHAT_CUR_KEY, chatId || "new"); } catch (e) {}
}
let pendingAttachment = null;         // {name, mime, data(base64), url}

function loadChats() {
  try {
    const list = JSON.parse(localStorage.getItem(CHATS_KEY) || "null");
    if (Array.isArray(list)) return list;
    const old = JSON.parse(localStorage.getItem(OLD_CHAT_KEY) || "[]");   // прежняя одна история
    return old.length ? [{ id: "c" + Date.now(), title: chatTitle(old), updated: Date.now(), log: old }] : [];
  } catch (e) { return []; }
}
function chatTitle(log) {
  const first = log.find(m => m.role === "user" && m.content);
  return first ? first.content.slice(0, 60) : "Новый чат";
}
// Без аргументов — открытый чат; с id и log — другой (ответ ИИ пришёл в чат,
// из которого уже ушли).
function saveChatLog(id, log) {
  const own = !id || id === chatId;
  if (own) {
    if (!chatLog.length) return;
    if (!chatId) chatId = "c" + Date.now();
    id = chatId; log = chatLog;
  }
  let cur = chats.find(c => c.id === id);
  if (!cur) {
    if (!own) return;                 // тот чат удалили, пока ждали ответ
    cur = { id: id }; chats.unshift(cur);
  }
  cur.log = log.slice(-40); cur.title = chatTitle(log); cur.updated = Date.now();
  chats = [cur, ...chats.filter(c => c !== cur)].slice(0, 20);
  try { localStorage.setItem(CHATS_KEY, JSON.stringify(chats)); } catch (e) {}
  if (own) rememberChat();
}

// Лог чата по id: открытый — chatLog, остальные — из списка (null — удалён).
function chatLogOf(id) {
  if (id === chatId) return chatLog;
  const c = chats.find(x => x.id === id);
  return c ? c.log : null;
}

const SUGGESTIONS = [
  "Что сдавать на этой неделе?",
  "Какие у нас пары завтра?",
  "Объясни простыми словами, что такое NPV",
  "📷 Прикрепи фото задачи — решу по шагам",
];

function renderChat() {
  const log = document.getElementById("chat-log");
  log.innerHTML = "";
  if (!chatLog.length) {
    const empty = document.createElement("div");
    empty.className = "chat-empty";
    empty.innerHTML = '<div class="chat-avatar">' + icon("sparkle") + '</div><p>Спрашивай про учёбу, присылай фото задач и файлы лекций.<br>Я знаю ваше расписание, дедлайны и ДЗ.</p><div class="suggest"></div>';
    const box = empty.querySelector(".suggest");
    SUGGESTIONS.forEach(t => {
      const b = document.createElement("button");
      if (t.startsWith("📷")) b.innerHTML = icon("camera", "inl") + escapeHtml(t.slice(2).trim());
      else b.textContent = t;
      b.onclick = () => {
        if (t.startsWith("📷")) { document.getElementById("chat-file").click(); return; }
        document.getElementById("chat-input").value = t;
        sendChat();
      };
      box.appendChild(b);
    });
    log.appendChild(empty);
    return;
  }
  chatLog.forEach(m => appendMsg(m.role, m.content, "", m.html, m.att, false, m.files, m.sources));
  addQuickReplies();
}

function newChat() {
  haptic();
  chatId = null;
  chatLog = [];
  rememberChat();
  clearAttachment();
  renderChat();
}

// ☰ Чаты — список прошлых разговоров прямо на месте ленты.
function openChats() {
  haptic();
  const log = document.getElementById("chat-log");
  if (!chats.length) { showToast("Пока один чат — этот"); return; }
  log.innerHTML = '<button class="file-back" onclick="renderChat()">‹ К чату</button>' +
    chats.map((c, i) => '<div class="chat-item' + (c.id === chatId ? ' cur' : '') + '" onclick="switchChat(' + i + ')">' +
      '<div style="min-width:0;flex:1"><div class="ft">' + escapeHtml(c.title) + '</div>' +
      '<div class="fs">' + new Date(c.updated).toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) +
      ' · ' + c.log.length + ' ' + plural(c.log.length, "сообщение", "сообщения", "сообщений") + '</div></div>' +
      '<button class="del" onclick="event.stopPropagation(); deleteChat(' + i + ')" aria-label="Удалить">' + icon("cross") + '</button></div>').join("");
}
function switchChat(i) {
  const c = chats[i];
  if (!c) return;
  haptic();
  chatId = c.id; chatLog = c.log;
  rememberChat();
  clearAttachment();
  renderChat();
  scrollChatToEnd();
}

// Чат с историей открывается на последнем сообщении, как в Telegram: раньше —
// сверху, на самых старых (дизайн-ревью, п. 1). Пустой чат не крутим.
function scrollChatToEnd() {
  if (!chatLog.length) return;
  requestAnimationFrame(() => window.scrollTo(0, document.documentElement.scrollHeight));
}
function deleteChat(i) {
  const c = chats[i];
  if (!c) return;
  chats.splice(i, 1);
  try { localStorage.setItem(CHATS_KEY, JSON.stringify(chats)); } catch (e) {}
  if (c.id === chatId) { chatId = null; chatLog = []; rememberChat(); }
  chats.length ? openChats() : renderChat();
}

function appendMsg(role, content, reasoning, html, att, scroll = true, files, sources) {
  const log = document.getElementById("chat-log");
  const empty = log.querySelector(".chat-empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "bot");
  if (att && att.url) {
    const img = document.createElement("img");
    img.className = "att"; img.src = att.url; img.alt = att.name || "фото";
    div.appendChild(img);
  } else if (att && att.name) {
    const chip = document.createElement("div");
    chip.className = "file-att"; chip.innerHTML = icon(att.image ? "image" : "doc", "inl") + escapeHtml(att.name);
    div.appendChild(chip);
  }
  if (content || html) {
    const textNode = document.createElement("div");
    // html собирает сервер (utils.md_to_tg_html_chunks): всё, кроме <b>/<i>/<code>/<pre>, экранировано
    // переносы строк вокруг блока кода не нужны (white-space: pre-wrap): блок сам
    // с новой строки, а лишние \n давали две-три пустые строки до и после кода
    if (html) textNode.innerHTML = html.replace(/\n*(<pre>[\s\S]*?<\/pre>)\n*/g, "$1"); else textNode.textContent = content;
    // номера фрагментов [1], [2] от поиска по смыслу — нажимаемые: страница лекции
    if (html && sources && sources.some(f => f.n)) {
      textNode.innerHTML = textNode.innerHTML.replace(/\[(\d{1,2})\]/g, (m, n) =>
        sources.some(f => f.n === +n) ? '<button class="cite" data-n="' + n + '">' + n + '</button>' : m);
      textNode.addEventListener("click", e => {
        const b = e.target.closest(".cite");
        const f = b && sources.find(x => x.n === +b.dataset.n);
        if (f) openPage(f.id, f.page);
      });
    }
    div.appendChild(textNode);
  }
  // «скинь лк 5 по …» — найденные файлы с теми же кнопками, что во вкладке «Файлы»
  if (files && files.length) {
    const box = document.createElement("div");
    box.className = "chat-files";
    box.innerHTML = files.map(f => fileCard(f, false)).join("");
    div.appendChild(box);
  }
  // на какие лекции ИИ опирался — тап открывает файл во вкладке «Файлы»
  if (sources && sources.length) {
    const src = document.createElement("div");
    src.className = "msg-src";
    if (sources[0].label) {
      // поиск по смыслу: «Лекция 5 · слайд 12» → страница; одинаковые места — один чип
      const seen = new Set(), uniq = sources.filter(f => !seen.has(f.id + ":" + f.page) && seen.add(f.id + ":" + f.page));
      src.className = "msg-src pages";
      src.innerHTML = uniq.slice(0, 6).map(f =>
        '<button onclick="openPage(' + f.id + ',' + f.page + ')">' + icon("bookOpen", "inl") + escapeHtml(f.label) + '</button>').join("") +
        (uniq.length > 6 ? '<span>+' + (uniq.length - 6) + '</span>' : "");
    } else {
      src.innerHTML = icon("bookOpen", "inl") + sources.slice(0, 4).map(f =>
        '<button onclick="openFileFromLink(' + f.id + ')">' + escapeHtml(f.title.slice(0, 40)) + '</button>').join(" · ") +
        (sources.length > 4 ? " · +" + (sources.length - 4) : "");
    }
    div.appendChild(src);
  }
  if (reasoning) {
    const det = document.createElement("details");
    det.className = "think";
    det.innerHTML = '<summary>Ход мыслей</summary><div class="think-body"></div>';
    det.querySelector(".think-body").textContent = reasoning;
    div.appendChild(det);
  }
  if (role !== "user" && content && !content.startsWith("⚠️")) {
    const tools = document.createElement("div");
    tools.className = "msg-tools";
    const copy = document.createElement("button");
    copy.innerHTML = icon("copy", "inl") + "Копировать";
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(content); } catch (e) {
        const ta = document.createElement("textarea"); ta.value = content; document.body.appendChild(ta);
        ta.select(); try { document.execCommand("copy"); } catch (e2) {} ta.remove();
      }
      haptic("success");
      copy.innerHTML = icon("check", "inl") + "Скопировано";
      setTimeout(() => { copy.innerHTML = icon("copy", "inl") + "Копировать"; }, 1500);
    };
    tools.appendChild(copy);
    div.appendChild(tools);
  }
  log.appendChild(div);
  if (scroll) requestAnimationFrame(() => window.scrollTo(0, document.documentElement.scrollHeight));
  return div;
}

function typingBubble() {
  const log = document.getElementById("chat-log");
  const div = document.createElement("div");
  div.className = "msg bot typing-dots";
  div.innerHTML = "<span></span><span></span><span></span>";
  log.appendChild(div);
  requestAnimationFrame(() => window.scrollTo(0, document.documentElement.scrollHeight));
  return div;
}

// ── вложения ──
const MAX_FILE_MB = 10;
document.getElementById("chat-file").addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!file) return;
  if (file.size > MAX_FILE_MB * 1024 * 1024) { alert("Файл больше " + MAX_FILE_MB + " МБ — не пролезет"); return; }
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = String(reader.result);
    const image = (file.type || "").startsWith("image/");
    pendingAttachment = {
      name: file.name || (image ? "фото.jpg" : "файл"),
      mime: file.type || "",
      data: dataUrl.slice(dataUrl.indexOf(",") + 1),
      url: image ? dataUrl : "",
      image: image,
    };
    renderAttachment();
    haptic();
  };
  reader.readAsDataURL(file);
});

function renderAttachment() {
  const box = document.getElementById("attach-preview");
  box.innerHTML = "";
  renderThinkToggle();                 // к фото и файлу «Подумать» нет
  if (!pendingAttachment) return;
  const chip = document.createElement("div");
  chip.className = "attach-chip";
  if (pendingAttachment.url) {
    const img = document.createElement("img"); img.src = pendingAttachment.url; chip.appendChild(img);
  } else {
    const ic = document.createElement("span"); ic.innerHTML = icon("doc"); chip.appendChild(ic);
  }
  const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = pendingAttachment.name; chip.appendChild(nm);
  const x = document.createElement("button"); x.innerHTML = icon("cross"); x.setAttribute("aria-label", "Убрать"); x.onclick = clearAttachment;
  chip.appendChild(x);
  box.appendChild(chip);
  syncNavHeight();
}

function clearAttachment() {
  pendingAttachment = null;
  renderAttachment();
  syncNavHeight();
}

// ── «Подумать» до вопроса (подписка, think.py) ──
// Переключатель над полем ввода (Никита 18.10: «выбрать перед ответом
// сразу»): включил — следующий вопрос сразу решает модель второго уровня,
// без обычного ответа. Одноразовый: вопрос ушёл — выключается сам, чтобы
// дневной лимит не уходил случайно. Нет подписки — переключателя нет;
// кончилось на сегодня или прикреплён файл — серый.
let thinkOffer = null, thinkArmed = false;     // {label, left, daily} с сервера

function setThinkOffer(o) {
  thinkOffer = o || null;
  renderThinkToggle();
}

function renderThinkToggle() {
  const box = document.getElementById("think-toggle");
  if (!thinkOffer) {
    thinkArmed = false;
    box.innerHTML = "";
  } else {
    const can = thinkOffer.left > 0 && !pendingAttachment;
    if (!can) thinkArmed = false;
    box.innerHTML = '<button class="think-toggle' + (thinkArmed ? " on" : "") + '" onclick="toggleThink()" aria-pressed="' +
      thinkArmed + '"' + (can ? "" : " disabled") + ">" + icon("sparkle", "inl") + "Подумать · " + thinkOffer.left + "</button>" +
      '<span class="think-note">' + (thinkArmed ? "следующий вопрос решит DeepSeek, подумав"
        : thinkOffer.left > 0 ? (pendingAttachment ? "к фото и файлам — нет" : "") : "на сегодня всё — завтра снова") + "</span>";
  }
  syncNavHeight();
}

function toggleThink() {
  if (!thinkOffer || !(thinkOffer.left > 0) || pendingAttachment) return;
  thinkArmed = !thinkArmed;
  haptic();
  renderThinkToggle();
}

// ── предметы (с лекциями — чат опирается на них) ──
async function loadChatSubjects() {
  try {
    const data = await api("/api/subjects");
    setThinkOffer(data.think);
    const sel = document.getElementById("chat-subject");
    data.subjects.forEach(s => {
      const o = document.createElement("option");
      o.value = s.name; o.textContent = s.name + (s.lectures ? " · есть лекции" : "");
      sel.appendChild(o);
    });
  } catch (e) {}
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const btn = document.getElementById("chat-send");
  if (btn.disabled) return;            // Enter, пока первый вопрос без ответа, — не второй запрос
  const text = input.value.trim();
  const att = pendingAttachment;
  if (!text && !att) return;
  input.value = "";
  input.style.height = "auto";
  clearAttachment();
  btn.disabled = true;

  dropQuickReplies();
  const shownAtt = att ? { name: att.name, url: att.url, image: att.image } : null;
  appendMsg("user", text, "", "", shownAtt);
  // В истории для сервера — только текст; само вложение уходит отдельным полем.
  const content = text || (att ? (att.image ? "Реши задание на фото." : "Разбери этот файл.") : "");
  const entry = { role: "user", content: content, att: shownAtt ? { name: shownAtt.name, image: shownAtt.image } : null };
  if (thinkArmed && !att) {            // «Подумать» — на один вопрос
    entry.deep = true;
    thinkArmed = false;
    renderThinkToggle();
  }
  chatLog.push(entry);
  saveChatLog();
  try {
    await requestAnswer(entry, att);
  } finally {
    btn.disabled = false;
  }
}

// Вопрос без ответа (ошибка ИИ) помечается failed и следующим сообщениям
// в историю не идёт. Живой тест: после «ИИ недоступен» на «Привет» модель
// отвечала на прошлый, неотвеченный вопрос. Повторить — кнопкой под ошибкой.
//
// Пока ИИ думает, можно открыть другой чат или «＋ Новый»: ответ пишется в
// тот чат, где задан вопрос, а рисуется, только если он сейчас открыт.
// Текст вложенного документа (file_text с сервера) хранится в записи вопроса
// и уходит в историю следующих вопросов — иначе ИИ забывал файл со второго.
// История для сервера: два ответа подряд («Подумать ещё» под ответом) —
// уходит только последний, роли чередуются.
function historyOf(log) {
  const ok = log.filter(m => m.content && !m.failed);
  return ok.filter((m, i) => !(m.role === "assistant" && ok[i + 1] && ok[i + 1].role === "assistant"))
    .map(m => ({ role: m.role, content: m.content + (m.file_text ? "\n\n" + m.file_text : "") }));
}

async function requestAnswer(entry, att) {
  const pending = typingBubble();
  const myId = chatId;
  const history = historyOf(chatLog);
  const body = { history: history, subject: document.getElementById("chat-subject").value };
  if (att) body.attachment = { name: att.name, mime: att.mime, data: att.data };
  if (entry.deep) body.think_first = true;
  try {
    const data = await api("/api/chat", { method: "POST", body: JSON.stringify(body) });
    pending.remove();
    if (data.think) setThinkOffer(data.think);
    const here = chatId === myId, log = chatLogOf(myId);
    if (data.choose && data.choose.length) {
      // выберет предмет — вопрос уйдёт заново, «Подумать» остаётся при нём
      if (here) askSubject(entry, att, data);
      else if (log) { entry.failed = true; saveChatLog(myId, log); }
      return;
    }
    delete entry.failed;
    delete entry.deep;
    if (data.file_text) entry.file_text = data.file_text;
    if (!log) return;                                 // чат удалили, пока ждали
    log.push({ role: "assistant", content: data.content, html: data.html, files: data.files, sources: data.sources,
               think: data.think });
    if (!here) { saveChatLog(myId, log); return; }
    appendMsg("assistant", data.content, data.reasoning, data.html, null, true, data.files, data.sources);
    saveChatLog();
    addQuickReplies();
    haptic("success");
  } catch (e) {
    pending.remove();
    entry.failed = true;
    delete entry.deep;                 // «Повторить» — уже обычным вопросом
    if (chatId !== myId) { const log = chatLogOf(myId); if (log) saveChatLog(myId, log); return; }
    saveChatLog();
    const bubble = appendMsg("assistant", "⚠️ " + e.message);
    const retry = document.createElement("button");
    retry.className = "chat-retry";
    retry.innerHTML = icon("refresh", "inl") + "Повторить";
    retry.onclick = () => {
      if (document.getElementById("chat-send").disabled) return;   // другой вопрос ещё ждёт ответа
      bubble.remove();
      chatLog.splice(chatLog.indexOf(entry), 1);   // повтор — последним, чтобы ответ был на него
      delete entry.failed;
      chatLog.push(entry);
      askAgain(entry, att);
    };
    bubble.appendChild(retry);
  }
}

// Повтор вопроса (кнопкой под ошибкой или выбором предмета): пока ждём —
// «Отправить» выключена, как при обычной отправке.
function askAgain(entry, att) {
  const btn = document.getElementById("chat-send");
  btn.disabled = true;
  return requestAnswer(entry, att).finally(() => { btn.disabled = false; });
}

// Высота панели вкладок (с учётом «безопасной зоны» внизу iPhone) — для
// поля ввода чата, которое стоит прямо над ней.
function syncNavHeight() {
  const nav = document.querySelector("nav.tabs");
  if (nav && nav.offsetHeight) document.documentElement.style.setProperty("--nav-h", nav.offsetHeight + "px");
  const dock = document.querySelector(".chat-dock");
  if (dock && dock.offsetHeight) document.documentElement.style.setProperty("--dock-h", dock.offsetHeight + "px");
}
syncNavHeight();
window.addEventListener("resize", syncNavHeight);
if (tg && tg.onEvent) tg.onEvent("viewportChanged", syncNavHeight);

// Пока открыта клавиатура — панель вкладок прячем, поле ввода опускаем вниз.
const chatInput = document.getElementById("chat-input");
chatInput.addEventListener("focus", () => document.body.classList.add("typing"));
chatInput.addEventListener("blur", () => setTimeout(() => {
  document.body.classList.remove("typing");
  syncNavHeight();
  // панель вкладок вернулась и подняла поле ввода — докручиваем, чтобы
  // последний ответ не остался под ним
  requestAnimationFrame(() => window.scrollTo(0, document.documentElement.scrollHeight));
}, 150));
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + "px";
  syncNavHeight();
});

document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});

// Быстрые ответы — только под последним ответом ИИ, одна строка.
const QUICK_REPLIES = [
  ["Короче", "Объясни то же самое короче, в 3–4 предложениях."],
  ["Подробнее", "Разбери подробнее, по шагам."],
  ["Пример", "Приведи простой пример из жизни или задачу с решением."],
  ["Проверь меня", "Задай мне 3 коротких вопроса по этой теме, по одному, и проверь ответы."],
];
function dropQuickReplies() {
  document.querySelectorAll(".quick-replies").forEach(el => el.remove());
}
function addQuickReplies() {
  dropQuickReplies();
  const last = chatLog[chatLog.length - 1];
  if (!last || last.role !== "assistant" || last.files || !last.content || /^(⚠️|🤔|🤷)/.test(last.content)) return;
  const bubbles = document.querySelectorAll("#chat-log .msg.bot");
  const bubble = bubbles[bubbles.length - 1];
  if (!bubble) return;
  const row = document.createElement("div");
  row.className = "quick-replies";
  QUICK_REPLIES.forEach(([label, prompt]) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = () => {
      if (document.getElementById("chat-send").disabled) return;
      document.getElementById("chat-input").value = prompt;
      sendChat();
    };
    row.appendChild(b);
  });
  // «Подумать ещё» (подписка): тот же вопрос заново решает модель
  // второго уровня, со своим дневным лимитом — он в подписи кнопки
  if (last.think) {
    const b = document.createElement("button");
    b.className = "think";
    const left = last.think.left;              // null — безлимит
    b.textContent = last.think.label + (left == null ? "" : " · " + left);
    b.disabled = left === 0;
    b.onclick = thinkAgain;
    row.prepend(b);
  }
  bubble.after(row);
}

async function thinkAgain() {
  const btn = document.getElementById("chat-send");
  if (btn.disabled) return;
  const idx = chatLog.length - 1;
  if (idx < 1 || chatLog[idx].role !== "assistant") return;
  btn.disabled = true;
  dropQuickReplies();
  const pending = typingBubble();
  const myId = chatId;
  const body = { history: historyOf(chatLog.slice(0, idx)), subject: document.getElementById("chat-subject").value,
                 think: true };
  try {
    const data = await api("/api/chat", { method: "POST", body: JSON.stringify(body) });
    pending.remove();
    if (data.think) setThinkOffer(data.think);
    const log = chatLogOf(myId);
    if (!log) return;
    log.push({ role: "assistant", content: data.content, html: data.html, sources: data.sources, think: data.think });
    if (chatId !== myId) { saveChatLog(myId, log); return; }
    appendMsg("assistant", data.content, data.reasoning, data.html, null, true, null, data.sources);
    saveChatLog();
    haptic("success");
  } catch (e) {
    pending.remove();
    if (chatId === myId) showToast(e.message);
  } finally {
    btn.disabled = false;
    if (chatId === myId) addQuickReplies();
  }
}

// «По какому предмету?» — вопрос явно про лекции, а предмет не угадан.
// Тап по предмету: он выбирается сверху, и тот же вопрос уходит заново.
// Пока не выбрал — вопрос в историю не идёт (как после ошибки).
function askSubject(entry, att, data) {
  entry.failed = true;
  saveChatLog();
  const bubble = appendMsg("assistant", "", "", escapeHtml(data.content));
  const row = document.createElement("div");
  row.className = "subject-choice";
  data.choose.forEach(name => {
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = () => {
      if (document.getElementById("chat-send").disabled) return;
      haptic();
      const sel = document.getElementById("chat-subject");
      if (![...sel.options].some(o => o.value === name)) {
        const o = document.createElement("option"); o.value = name; o.textContent = name; sel.appendChild(o);
      }
      sel.value = name;
      bubble.remove();
      chatLog.splice(chatLog.indexOf(entry), 1);
      delete entry.failed;
      chatLog.push(entry);
      askAgain(entry, att);
    };
    row.appendChild(b);
  });
  bubble.appendChild(row);
}

// ── Страница лекции из ответа ИИ (поиск по смыслу) ─────────────────────────
// Текст страницы — из индекса, у PDF — ещё и сама страница картинкой. Листать
// соседние; «Открыть файл» — целиком, как во вкладке «Файлы».
let pageView = null;

async function openPage(id, page) {
  haptic();
  pageView = { id: id, page: page };
  const box = document.getElementById("page-content");
  box.innerHTML = '<div class="skel" style="height:22px;width:60%"></div><div class="skel" style="height:260px;margin-top:14px"></div>';
  document.getElementById("page-sheet").classList.add("open");
  try {
    const p = await api("/api/files/" + id + "/page/" + page);
    if (!pageView || pageView.id !== id) return;
    pageView = p;
    const where = (p.kind === "слайд" ? "Слайд " : p.kind === "стр." ? "Страница " : "Часть ") + p.page + " из " + p.pages;
    box.innerHTML = '<h3 style="margin:0 0 2px">' + escapeHtml(p.title) + '</h3><div class="sheet-hint" style="margin-top:0">' + where + '</div>' +
      (p.image ? '<img class="page-img" src="' + escapeHtml(p.image) + '" alt="' + escapeHtml(where) + '" onerror="this.remove()">' : '') +
      (p.text ? '<div class="page-text' + (p.image ? ' small' : '') + '">' + escapeHtml(p.text) + '</div>' : '') +
      '<div class="page-nav"><button class="ghost" ' + (p.page <= 1 ? "disabled" : "") + ' onclick="openPage(' + id + ',' + (p.page - 1) + ')">‹</button>' +
      '<button class="primary" onclick="closeSheet(\'page-sheet\'); openFileFromLink(' + id + ')">Открыть файл</button>' +
      '<button class="ghost" ' + (p.page >= p.pages ? "disabled" : "") + ' onclick="openPage(' + id + ',' + (p.page + 1) + ')">›</button></div>';
  } catch (e) {
    box.innerHTML = '<div class="empty">Не открылось: ' + escapeHtml(e.message) + '</div>' +
      '<button class="primary" onclick="closeSheet(\'page-sheet\'); openFileFromLink(' + id + ')">Открыть файл целиком</button>';
  }
}

