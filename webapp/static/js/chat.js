// Чат с ИИ: история, вложения, предметы — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Чат ───────────────────────────────────────────────────────────────────

// История чата живёт в localStorage этого устройства (только текст, без
// вложений): закрыл WebApp — открыл — разговор на месте. «Новый чат» — чистит.
const CHAT_KEY = "chatLog.v1";
let chatLog = loadChatLog();          // [{role, content, html, att}]
let pendingAttachment = null;         // {name, mime, data(base64), url}

function loadChatLog() {
  try { return JSON.parse(localStorage.getItem(CHAT_KEY) || "[]"); } catch (e) { return []; }
}
function saveChatLog() {
  try { localStorage.setItem(CHAT_KEY, JSON.stringify(chatLog.slice(-40))); } catch (e) {}
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
    empty.innerHTML = '<div class="chat-avatar">✨</div><p>Спрашивай про учёбу, присылай фото задач и файлы лекций.<br>Я знаю ваше расписание, дедлайны и ДЗ.</p><div class="suggest"></div>';
    const box = empty.querySelector(".suggest");
    SUGGESTIONS.forEach(t => {
      const b = document.createElement("button");
      b.textContent = t;
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
  chatLog.forEach(m => appendMsg(m.role, m.content, "", m.html, m.att, false));
}

function newChat() {
  haptic();
  chatLog = [];
  saveChatLog();
  clearAttachment();
  renderChat();
}

function appendMsg(role, content, reasoning, html, att, scroll = true) {
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
    chip.className = "file-att"; chip.textContent = (att.image ? "🖼 " : "📄 ") + att.name;
    div.appendChild(chip);
  }
  if (content || html) {
    const textNode = document.createElement("div");
    // html собирает сервер (utils.md_to_tg_html_chunks): всё, кроме <b>/<i>/<code>/<pre>, экранировано
    if (html) textNode.innerHTML = html; else textNode.textContent = content;
    div.appendChild(textNode);
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
    copy.textContent = "⧉ Копировать";
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(content); } catch (e) {
        const ta = document.createElement("textarea"); ta.value = content; document.body.appendChild(ta);
        ta.select(); try { document.execCommand("copy"); } catch (e2) {} ta.remove();
      }
      haptic("success");
      copy.textContent = "✓ Скопировано";
      setTimeout(() => { copy.textContent = "⧉ Копировать"; }, 1500);
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
  if (!pendingAttachment) return;
  const chip = document.createElement("div");
  chip.className = "attach-chip";
  if (pendingAttachment.url) {
    const img = document.createElement("img"); img.src = pendingAttachment.url; chip.appendChild(img);
  } else {
    const ic = document.createElement("span"); ic.textContent = "📄"; chip.appendChild(ic);
  }
  const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = pendingAttachment.name; chip.appendChild(nm);
  const x = document.createElement("button"); x.textContent = "✕"; x.setAttribute("aria-label", "Убрать"); x.onclick = clearAttachment;
  chip.appendChild(x);
  box.appendChild(chip);
  syncNavHeight();
}

function clearAttachment() {
  pendingAttachment = null;
  renderAttachment();
  syncNavHeight();
}

// ── предметы (с лекциями — чат опирается на них) ──
async function loadChatSubjects() {
  try {
    const data = await api("/api/subjects");
    const sel = document.getElementById("chat-subject");
    data.subjects.forEach(s => {
      const o = document.createElement("option");
      o.value = s.name; o.textContent = (s.lectures ? "📖 " : "") + s.name;
      sel.appendChild(o);
    });
  } catch (e) {}
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  const att = pendingAttachment;
  if (!text && !att) return;
  input.value = "";
  input.style.height = "auto";
  clearAttachment();
  const btn = document.getElementById("chat-send");
  btn.disabled = true;

  const shownAtt = att ? { name: att.name, url: att.url, image: att.image } : null;
  appendMsg("user", text, "", "", shownAtt);
  // В истории для сервера — только текст; само вложение уходит отдельным полем.
  const content = text || (att ? (att.image ? "Реши задание на фото." : "Разбери этот файл.") : "");
  const entry = { role: "user", content: content, att: shownAtt ? { name: shownAtt.name, image: shownAtt.image } : null };
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
async function requestAnswer(entry, att) {
  const pending = typingBubble();
  const history = chatLog.filter(m => m.content && !m.failed).map(m => ({ role: m.role, content: m.content }));
  const body = { history: history, subject: document.getElementById("chat-subject").value };
  if (att) body.attachment = { name: att.name, mime: att.mime, data: att.data };
  try {
    const data = await api("/api/chat", { method: "POST", body: JSON.stringify(body) });
    pending.remove();
    delete entry.failed;
    appendMsg("assistant", data.content, data.reasoning, data.html);
    chatLog.push({ role: "assistant", content: data.content, html: data.html });
    saveChatLog();
    haptic("success");
  } catch (e) {
    pending.remove();
    entry.failed = true;
    saveChatLog();
    const bubble = appendMsg("assistant", "⚠️ " + e.message);
    const retry = document.createElement("button");
    retry.className = "chat-retry";
    retry.textContent = "↻ Повторить";
    retry.onclick = () => {
      bubble.remove();
      chatLog.splice(chatLog.indexOf(entry), 1);   // повтор — последним, чтобы ответ был на него
      delete entry.failed;
      chatLog.push(entry);
      requestAnswer(entry, att);
    };
    bubble.appendChild(retry);
  }
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
