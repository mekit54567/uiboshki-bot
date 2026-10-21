// Помощник (app/lib/screens/chat.dart): вопросы ИИ, который опирается на
// лекции группы. Можно выбрать предмет; под ответом — откуда взято
// («Лекция 4 · стр. 3»), нажал — страница. Вложение (фото или PDF/DOCX/PPTX/TXT
// до 10 МБ) уходит ИИ один раз, а текст документа (file_text с сервера)
// помнится в вопросе. Чаты — на телефоне (до 20, в каждом последние 40
// сообщений; тот же ключ, что у Flutter-версии), «Прошлые чаты» — листом.
// Снаружи: openChat().
"use strict";

const CH_STORE = "uib_cache:chats";   // shared_preferences → localStorage «flutter.uib_cache:chats»
const CH_LEGACY = "uib_cache:chat";
const CH_KEEP = 40, CH_MAX = 20, CH_MAX_BYTES = 10 * 1024 * 1024;
const CH_MIMES = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", heic: "image/heic",
  pdf: "application/pdf", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation", txt: "text/plain" };
const CH_SUGGEST = ["Чем метрика отличается от KPI?", "Объясни 3 лекцию", "Что сдать на этой неделе?"];

function chMime(name) { return CH_MIMES[String(name).split(".").pop().toLowerCase()] || ""; }
/** Сообщение (ChatMsg.fromJson). */
function chMsg(j) {
  const a = j.att;
  return { role: j.role || "user", content: j.content || "", html: j.html || "", sources: j.sources || [], files: j.files || [],
    choose: (j.choose || []).map(String), error: j.error === true, att: a && typeof a === "object" ? { name: String(a.name ?? "файл"), image: a.image === true } : null,
    fileText: j.file_text || "", failed: j.failed === true, think: j.think && typeof j.think === "object" ? j.think : null, deep: false };
}
/** ChatMsg.toJson — что хранится на телефоне. */
function chMsgJson(m) {
  const o = { role: m.role, content: m.content };
  if (m.html) o.html = m.html;
  if (m.sources.length) o.sources = m.sources;
  if (m.files.length) o.files = m.files;
  if (m.att) o.att = { name: m.att.name, image: m.att.image };
  if (m.fileText) o.file_text = m.fileText;
  if (m.failed) o.failed = true;
  if (m.think) o.think = m.think;
  return o;
}
/** Заголовок чата — начало первого вопроса (до 60 знаков). */
function chTitle(log) {
  for (const m of log) {
    const c = String(m.content ?? "").trim();
    if (m.role === "user" && c) return c.length > 60 ? c.slice(0, 60) : c;
  }
  return "Новый чат";
}
/** «сегодня, 14:05» / «вчера» / «12 окт» — когда писали в чат. */
function chWhen(ms, today) {
  const d = new Date(ms), day = (x) => Date.UTC(x.getFullYear(), x.getMonth(), x.getDate());
  const diff = Math.round((day(today) - day(d)) / 864e5);
  if (diff === 0) return `сегодня, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (diff === 1) return "вчера";
  return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}${d.getFullYear() !== today.getFullYear() ? " " + d.getFullYear() : ""}`;
}
function chThread(j) {
  return { id: String(j.id), title: String(j.title ?? "Новый чат"), updated: +j.updated || 0,
    log: Array.isArray(j.log) ? j.log : [], subject: String(j.subject ?? "") };
}
function chNewId() { return "c" + (now().getTime() * 1000 + Math.floor(Math.random() * 1000)); }
/** Строка из shared_preferences: Flutter хранит её JSON-строкой. */
function chReadStore(key) {
  const v = Prefs.get(key);
  if (v === null || v === undefined) return null;
  try { return typeof v === "string" ? JSON.parse(v) : v; } catch (e) { return null; }
}
/** Долгий POST: ответ ИИ идёт до минуты-двух. */
function chPost(path, body, timeout = 180000) { return Api._req("POST", path, body, timeout); }

function openChat() {
  Nav.push((wrap, screen) => {
    wrap.classList.add("ch");
    let log = [], id = null, subject = "", subjects = [], waiting = false, att = null, attNote = null;
    let chats = [], dirty = false, left = null, thinkOffer = null, thinkOn = false, chooseAtt = null, alive = true;
    const thinkLeft = () => (thinkOffer && typeof thinkOffer.left === "number" ? thinkOffer.left : null);
    const thinkCan = () => thinkOffer !== null && (thinkLeft() === null || thinkLeft() > 0) && att === null;

    wrap.innerHTML = `<div class="ch-top"></div><div class="ch-list"></div>
      <div class="ch-foot"><div class="ch-tg"></div><div class="ch-ap"></div>
        <div class="ch-bar"><button class="ch-clip" data-act="attach" aria-label="Прикрепить фото или файл">${icon("attach_file")}</button>
          <textarea rows="1" enterkeyhint="send" placeholder="Спроси про лекцию или задачу" aria-label="Вопрос"></textarea>
          <button class="ch-send" data-act="send" aria-label="Отправить">${icon("arrow_upward")}</button></div></div>
      <input type="file" class="ch-file" hidden accept="${Object.keys(CH_MIMES).map((x) => "." + x).join(",")}">`;
    const $ = (s) => wrap.querySelector(s);
    const top = $(".ch-top"), list = $(".ch-list"), input = $("textarea"), bar = $(".ch-bar"), picker = $(".ch-file");

    // ── хранение ──
    const persist = () => Prefs.set(CH_STORE, JSON.stringify({ chats, current: id ?? "" }));
    const openThread = (c) => { id = c.id; log = c.log.map(chMsg); subject = c.subject; dirty = false; };
    const restore = () => {
      try {
        let current = null;
        const j = chReadStore(CH_STORE);
        if (j) {
          chats = (j.chats || []).map(chThread);
          current = typeof j.current === "string" ? j.current : null;
        } else {
          const old = chReadStore(CH_LEGACY);
          if (old) {
            // прежняя одна история — первым чатом, он и откроется
            const l = Array.isArray(old.log) ? old.log : [];
            if (l.length) {
              const c = { id: chNewId(), title: chTitle(l), updated: now().getTime(), log: l, subject: String(old.subject ?? "") };
              chats = [c]; current = c.id;
            }
            Prefs.set(CH_STORE, JSON.stringify({ chats, current: current ?? "" }));
            Prefs.set(CH_LEGACY, null);
          }
        }
        const open = current === null ? chats[0] : chats.find((c) => c.id === current);
        if (open) openThread(open);
      } catch (e) {}
    };
    /** Записать разговор в чат (null — новый) и поднять наверх; ошибки и «по какому предмету?» не храним. */
    const store = (cid, l, subj, create = true) => {
      const keep = l.filter((m) => !m.error && !m.choose.length).map(chMsgJson);
      let c = cid === null ? null : chats.find((x) => x.id === cid) || null;
      if (!keep.length) return c ? c.id : null;
      if (!c) {
        if (!create) return null;   // чат удалили, пока ждали ответ
        c = { id: cid ?? chNewId(), title: "", updated: 0, log: [], subject: "" };
      }
      c.log = keep.length > CH_KEEP ? keep.slice(keep.length - CH_KEEP) : keep;
      c.title = chTitle(keep); c.subject = subj; c.updated = now().getTime();
      chats = [c, ...chats.filter((x) => x.id !== c.id)].slice(0, CH_MAX);
      return c.id;
    };
    const save = () => { id = store(id, log, subject); dirty = false; persist(); };
    const leave = () => { if (dirty) save(); };

    // ── рисование ──
    const drawTop = () => {
      top.innerHTML = `<button class="ch-back" data-act="back" aria-label="Назад">${icon("arrow_back_ios_new", "", "font-size:20px")}</button>
        <div class="grow row" style="justify-content:flex-end;gap:0;min-width:0">
        ${chats.length ? `<button class="ch-ic" data-act="history" aria-label="Прошлые чаты">${icon("history")}</button>` : ""}
        ${log.length ? `<button class="ch-ic" data-act="newchat" aria-label="Новый чат">${icon("add_comment", "o")}</button>` : ""}
        <button class="ch-subj" data-act="subject">${icon("menu_book", "o", "font-size:16px;color:var(--accent)")}<span>${esc(subject || "Все предметы")}</span></button></div>`;
    };
    let srcMap = [];
    const srcRef = (src) => srcMap.push(src) - 1;
    const bubble = (m, mi) => {
      if (m.role === "user") {
        const a = m.att;
        return `<div class="ch-me"><div>${a ? `<div class="ch-att">${icon(a.image ? "image" : "description", "o", "font-size:16px")}<span>${esc(a.name)}</span></div>` : ""}
          <div class="bd" style="--sz:15px">${esc(m.content)}</div></div></div>`;
      }
      const seen = new Set();
      const pages = m.sources.filter((s) => s.page != null && !seen.has(`${s.id}:${s.page}`) && seen.add(`${s.id}:${s.page}`));
      const whole = m.sources.filter((s) => s.page == null);
      const cites = {};
      for (const s of m.sources) if (typeof s.n === "number") cites[Math.trunc(s.n)] = s;
      const cite = (n) => (cites[n] ? `<span class="ch-cite" role="button" aria-label="Источник ${n}" data-act="src" data-k="${srcRef(cites[n])}">${n}</span>` : null);
      const text = m.html ? flTgHtml(m.html, { cite }) : Object.keys(cites).length ? flCiteText(m.content, cite) : esc(m.content);
      let h = `<div class="bd tg${m.error ? " ch-err" : ""}" style="--sz:15px">${text}</div>`;
      // ошибка последним сообщением — «Повторить» (тот же вопрос ещё раз)
      if (m.error && mi === log.length - 1 && !waiting) {
        h += `<div class="ch-chips" style="padding:var(--s) 0 0"><button class="ch-chip pick" data-act="retry">${icon("refresh", "", "font-size:16px;color:var(--accent)")}<span>Повторить</span></button></div>`;
      }
      // выбрали предмет — список сворачивается в одну строку (Никита 21.10)
      if (m.chosen) {
        h += `<div class="ch-chosen bd" style="--sz:14px;font-weight:600;padding:var(--s) 0 0">${icon("check_circle", "", "font-size:18px;color:var(--accent)")} ${esc(m.chosen)}</div>`;
      } else if (m.choose.length) {
        h += `<div class="ch-chips" style="padding:var(--s) 0 0">${m.choose.map((c, i) =>
          `<button class="ch-chip pick" data-act="choose" data-m="${mi}" data-k="${i}">${esc(c)}</button>`).join("")}</div>`;
      }
      if (m.files.length || pages.length || whole.length) {
        const chip = (ic, label, act, k) => `<button class="ch-chip src" data-act="${act}" data-k="${k}">${icon(ic, "o", "font-size:16px;color:var(--accent)")}<span>${esc(label)}</span></button>`;
        h += `<div class="ch-chips" style="padding:var(--s) 0 0">${[
          ...m.files.map((f) => chip("insert_drive_file", String(f.title), "fileref", srcRef(f))),
          ...pages.slice(0, 6).map((s) => chip("auto_stories", String(s.label ?? s.title), "src", srcRef(s))),
          ...whole.slice(0, 4).map((s) => chip("menu_book", String(s.title), "src", srcRef(s))),
        ].join("")}</div>`;
      }
      return `<div class="ch-ai">${h}</div>`;
    };
    const drawList = () => {
      srcMap = [];
      let h = screenTitle("Kapi ИИ");
      if (!log.length) {
        h += `<div style="padding:0 var(--xl) var(--l)"><div class="bd mut" style="--sz:15px">Отвечает по лекциям твоей группы: объяснит тему, решит задачу, скажет, где в лекции.</div>
          ${left !== null ? `<div class="row" style="gap:6px;margin-top:var(--s)">${icon("chat_bubble_outline", "", `font-size:16px;color:${left > 0 ? "var(--accent)" : "var(--warn)"}`)}
            <div class="bd b6 grow" style="--sz:14px;color:${left > 0 ? "var(--text)" : "var(--warn)"}">${left > 0
              ? `Сегодня можно ещё ${left} ${plural(left, "вопрос", "вопроса", "вопросов")}` : "На сегодня вопросы кончились — завтра можно снова"}</div></div>` : ""}</div>
          <div class="ch-chips">${CH_SUGGEST.map((q, i) => `<button class="ch-chip" data-act="suggest" data-k="${i}">${esc(q)}</button>`).join("")}</div>`;
      }
      h += log.map(bubble).join("");
      const last = log[log.length - 1];
      if (!waiting && last && last.think) {
        const t = last.think, l = typeof t.left === "number" ? t.left : null;
        h += `<div style="padding:0 var(--xl) var(--s)"><button class="ch-chip think" data-act="think"${l !== 0 ? "" : " disabled"}>
          ${icon("psychology", "o", "font-size:18px;color:var(--accent)")}<span>${esc(t.label ?? "Подумать ещё")}${l === null ? "" : " · " + l}</span></button></div>`;
      }
      if (waiting) h += '<div class="ch-wait eyebrow">Думаю…</div>';
      list.innerHTML = h;
    };
    const drawFoot = () => {
      const tg = $(".ch-tg");
      if (thinkOffer === null) tg.innerHTML = "";
      else {
        const l = thinkLeft(), out = l !== null && l <= 0, attached = att !== null;
        const tap = thinkCan() && !waiting, onn = thinkOn && thinkCan();
        const can = tap || (!out && !attached);
        const note = onn ? "следующий вопрос Капибара решит, подумав подольше" : out ? "на сегодня всё — завтра снова" : attached ? "к фото и файлам — нет" : "";
        tg.innerHTML = `<div class="ch-think"><button class="ch-toggle${onn ? " on" : ""}${can ? " can" : ""}" data-act="toggle" aria-pressed="${onn}"${tap ? "" : " disabled"}>
          ${icon("psychology", "o")}<span>Подумать${l === null ? "" : " · " + Math.max(0, l)}</span></button>
          ${note ? `<div class="bd mut grow clamp2" style="--sz:12px">${esc(note)}</div>` : ""}</div>`;
      }
      const ap = $(".ch-ap");
      if (!att && attNote === null) ap.innerHTML = "";
      else {
        ap.innerHTML = `<div class="ch-attp${att ? "" : " bad"}">${icon(!att ? "error_outline" : att.image ? "image" : "description", att ? "o" : "",
          `font-size:18px;color:${att ? "var(--accent)" : "var(--danger)"}`)}
          <div class="bd grow ell" style="--sz:13px;color:${att ? "var(--text)" : "var(--danger)"}">${esc(att ? "прикреплено: " + att.name : attNote)}</div>
          <button data-act="unattach" aria-label="Убрать">${icon("close", "", "font-size:18px")}</button></div>`;
      }
      $(".ch-clip").disabled = waiting;
      $(".ch-send").disabled = waiting;
    };
    const draw = () => { drawTop(); drawList(); drawFoot(); };
    const toEnd = () => requestAnimationFrame(() => list.scrollTo({ top: list.scrollHeight + 200, behavior: "smooth" }));

    // ── разговор ──
    /** История для сервера: без ошибок и вопросов без ответа; два ответа подряд — только последний. */
    const history = (l) => {
      const ok = l.filter((m) => !m.error && !m.failed && m.content && !m.choose.length);
      return ok.filter((m, i) => !(m.role === "assistant" && i + 1 < ok.length && ok[i + 1].role === "assistant"))
        .map((m) => ({ role: m.role, content: m.fileText ? `${m.content}\n\n${m.fileText}` : m.content }));
    };
    const takeThink = (r) => { if (r && r.think && typeof r.think === "object") thinkOffer = r.think; };
    const deliver = (l, cid, answer) => {
      if (!alive) return;
      if (l !== log) {
        // пока ждали, ушли в другой чат — ответ в свой (если его не удалили)
        const c = chats.find((x) => x.id === cid);
        if (!c) return;
        l.push(answer);
        store(cid, l, c.subject, false);
        if (id === cid) { openThread(c); draw(); }
        persist();
        return;
      }
      log.push(answer);
      waiting = false;
      save();
      draw();
      toEnd();
    };
    const answerOf = (r, withFiles) => chMsg({ role: "assistant", content: r.content || "", html: r.html || "", sources: r.sources || [],
      files: withFiles ? r.files || [] : [], choose: withFiles ? r.choose || [] : [], think: r.think });
    const send = async (again = null, againAtt = null) => {
      const text = again ?? input.value.trim();
      const a = again !== null ? againAtt : att;
      if ((!text && !a) || waiting) return;
      tick();
      const l = log;   // ответ — в этот разговор, даже если открыли другой
      id ??= chNewId();
      const cid = id;
      let entry;
      if (again === null) {
        // в истории — только текст; само вложение уходит отдельным полем
        entry = chMsg({ role: "user", content: text || (a.image ? "Реши задание на фото." : "Разбери этот файл."),
          att: a ? { name: a.name, image: a.image } : null });
        entry.deep = thinkOn && thinkCan();   // «Подумать» — на один вопрос
        log.push(entry);
        dirty = true;
        thinkOn = false;
      } else entry = [...log].reverse().find((m) => m.role === "user");
      const deep = entry.deep;
      entry.failed = false;
      input.value = ""; fit();
      att = null; attNote = null; waiting = true;
      draw(); toEnd();
      const body = { history: history(log), subject };
      if (a) body.attachment = { name: a.name, mime: a.mime, data: a.data };
      if (deep) body.think_first = true;
      let answer;
      try {
        const r = await chPost("/chat", body);
        Ach.unlock("ai");
        takeThink(r);
        if (typeof r.file_text === "string") entry.fileText = r.file_text;
        // «завтра МБП …» — сервер узнал предмет по сокращению: переключаем шапку
        if (typeof r.subject === "string" && r.subject && l === log) { subject = r.subject; drawTop(); }
        answer = answerOf(r, true);
        if (answer.choose.length) chooseAtt = a;   // выберет предмет — вложение уйдёт ещё раз
        else entry.deep = false;
        // «Подумать» — свой лимит, обычный дневной счёт не трогает
        if (!deep && left !== null && left > 0 && !answer.choose.length && !answer.files.length) left -= 1;
      } catch (e) {
        entry.failed = true; entry.deep = false;
        answer = chMsg({ role: "assistant", content: errorText(e), error: true });
      }
      deliver(l, cid, answer);
    };
    /** «Подумать ещё»: тот же вопрос заново решает модель второго уровня; новый ответ — под прежним. */
    const think = async () => {
      if (waiting || log.length < 2 || log[log.length - 1].role !== "assistant") return;
      tick();
      const l = log, cid = id;
      waiting = true; draw(); toEnd();
      const body = { history: history(log.slice(0, -1)), subject, think: true };
      let answer;
      try {
        const r = await chPost("/chat", body);
        Ach.unlock("ai");
        takeThink(r);
        answer = answerOf(r, false);
      } catch (e) { answer = chMsg({ role: "assistant", content: errorText(e), error: true }); }
      deliver(l, cid, answer);
    };
    const reset = () => { att = null; attNote = null; waiting = false; input.value = ""; fit(); };
    const newChat = () => { tick(); leave(); id = null; log = []; reset(); draw(); persist(); };
    const switchTo = (c) => { if (c.id === id) return; leave(); openThread(c); reset(); draw(); persist(); toEnd(); };
    const del = (c) => {
      chats = chats.filter((x) => x.id !== c.id);
      if (c.id === id) { id = null; log = []; waiting = false; dirty = false; }
      draw(); persist();
    };

    // ── листы ──
    const pickSubject = async () => {
      const names = ["", ...subjects];
      const v = await Sheet.show(names.map((n, i) => `<button class="ch-pick" data-act="pick" data-k="${i}"><span class="grow">${esc(n || "Все предметы")}</span>
        ${n === subject ? icon("check", "", "color:var(--accent)") : ""}</button>`).join(""), (b, close, sh) => {
        sh.classList.add("ch-sh70");
        on(b, { pick: (x) => close(names[+x.dataset.k]) });
      });
      if (typeof v === "string" && v !== subject) { subject = v; dirty = log.length > 0; drawTop(); }
    };
    const openChats = async () => {
      tick();
      if (dirty) save();   // открытый — в списке вместе со своим вопросом
      let items = [...chats];
      const today = now();
      const picked = await Sheet.show(`<div class="ttl" style="--sz:22px">Прошлые чаты</div>
        <div class="bd mut" style="--sz:13px;margin:4px 0 var(--m)">Хранятся на этом телефоне — до ${CH_MAX} последних.</div>
        ${log.length ? `<button class="tile row" data-act="new" style="padding:var(--m) var(--l);margin-bottom:var(--s)">${icon("add_comment", "o", "font-size:20px;color:var(--accent)")}
          <div class="bd b6 grow" style="--sz:15px">Новый чат</div></button>` : ""}<div class="ch-threads"></div><div style="height:var(--xs)"></div>`, (b, close, sh) => {
        sh.classList.add("ch-sh");
        const box = b.querySelector(".ch-threads");
        const drawItems = () => {
          box.innerHTML = items.map((c, i) => `<div class="ch-thread" data-i="${i}"><div class="ch-del">Удалить</div>
            <div class="tile row${c.id === id ? " cur" : ""}" data-act="open" data-k="${i}" role="button" tabindex="0">
              ${icon("chat_bubble_outline", "", "font-size:20px;color:var(--accent)")}
              <div class="grow"><div class="bd b6 clamp2" style="--sz:15px">${esc(c.title)}</div>
                <div class="bd mut ell" style="--sz:13px;margin-top:2px">${esc([chWhen(c.updated, today),
                  `${c.log.length} ${plural(c.log.length, "сообщение", "сообщения", "сообщений")}`, c.subject].filter(Boolean).join(" · "))}</div></div>
              <button class="ch-x" data-act="del" data-k="${i}" aria-label="Удалить чат">${icon("close", "", "font-size:20px")}</button></div></div>`).join("");
        };
        const remove = (i) => {
          tick();
          const c = items[i];
          items = items.filter((x) => x !== c);
          del(c);
          if (!items.length) close(undefined); else drawItems();
        };
        drawItems();
        on(b, { new: () => close("new"), open: (x) => close(items[+x.dataset.k]), del: (x) => remove(+x.dataset.k) });
        // смахнуть влево — удалить (Dismissible)
        let x0 = null, y0 = 0, el = null, dx = 0, lock = null;
        box.addEventListener("touchstart", (e) => {
          const t = e.target.closest(".ch-thread");
          if (!t) return;
          el = t; x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; lock = null;
        }, { passive: true });
        box.addEventListener("touchmove", (e) => {
          if (x0 === null) return;
          const mx = e.touches[0].clientX - x0, my = e.touches[0].clientY - y0;
          if (lock === null && Math.abs(mx) + Math.abs(my) > 8) lock = Math.abs(mx) > Math.abs(my) ? "x" : "y";
          if (lock !== "x") return;
          dx = Math.min(0, mx);
          el.classList.add("drag");
          el.querySelector(".tile").style.transform = `translateX(${dx}px)`;
        }, { passive: true });
        box.addEventListener("touchend", () => {
          if (x0 === null) return;
          const tile = el.querySelector(".tile"), i = +el.dataset.i, w = el.offsetWidth;
          x0 = null;
          if (lock === "x" && -dx > w * 0.4) {
            tile.style.transition = "transform .2s"; tile.style.transform = `translateX(${-w}px)`;
            setTimeout(() => remove(i), 200);
          } else {
            tile.style.transition = "transform .2s"; tile.style.transform = "";
            setTimeout(() => { tile.style.transition = ""; el.classList.remove("drag"); }, 220);
          }
        });
      });
      if (!alive) return;
      if (picked && typeof picked === "object") { tick(); switchTo(picked); }
      else if (picked === "new") newChat();
    };
    const openSource = (src) => {
      tick();
      if (src.page != null) flPageSheet(src.id, Math.trunc(src.page));
      else flFileSheet(flFileOf({ id: src.id, title: src.title, has_text: true }));
    };

    // ── вложение ──
    picker.addEventListener("change", () => {
      const f = picker.files && picker.files[0];
      picker.value = "";
      if (!f) return;
      const mime = chMime(f.name);
      if (f.size > CH_MAX_BYTES) { att = null; attNote = "Файл больше 10 МБ — не пролезет."; drawFoot(); return; }
      if (!mime) { att = null; attNote = "Умею читать PDF, DOCX, PPTX и TXT, а ещё фото."; drawFoot(); return; }
      const rd = new FileReader();
      rd.onload = () => {
        const s = String(rd.result || ""), data = s.slice(s.indexOf(",") + 1);
        att = { name: f.name, mime, data, image: mime.startsWith("image/") };
        attNote = null; drawFoot();
      };
      rd.readAsDataURL(f);
    });

    // ── поле ввода ──
    const fit = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 5 * 20.25 + 20) + "px"; };
    input.addEventListener("input", fit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    // клавиатура: нажатие на переписку (не на кнопку) убирает её; палец, доведённый до поля, — тоже; смахнуть поле вниз — тоже
    list.addEventListener("click", (e) => { if (!e.target.closest("[data-act]") && document.activeElement === input) input.blur(); });
    let ty = null, fromBar = false;
    const barTop = () => bar.getBoundingClientRect().top;
    wrap.addEventListener("touchstart", (e) => { ty = e.touches[0].clientY; fromBar = ty >= barTop(); }, { passive: true });
    wrap.addEventListener("touchmove", (e) => {
      if (ty === null || document.activeElement !== input) return;
      const y = e.touches[0].clientY, down = y - ty;
      if (fromBar ? down > 24 : down > 0 && y >= barTop()) { input.blur(); ty = null; }
    }, { passive: true });
    wrap.addEventListener("touchend", () => { ty = null; }, { passive: true });
    // клавиатура выезжает — окно меньше: переписка и поле в видимой части, низ переписки не уезжает
    const vv = window.visualViewport;
    const onVV = () => {
      if (!vv) return;
      const atEnd = list.scrollTop >= list.scrollHeight - list.clientHeight - 48;
      const r = wrap.getBoundingClientRect();
      const h = vv.offsetTop + vv.height - r.top;
      wrap.style.height = vv.height < innerHeight - 80 ? Math.max(200, h) + "px" : "";
      if (atEnd) requestAnimationFrame(() => (list.scrollTop = list.scrollHeight));
    };
    if (vv) { vv.addEventListener("resize", onVV); vv.addEventListener("scroll", onVV); }

    on(wrap, {
      back: () => Nav.pop(),
      send: () => send(),
      attach: () => { tick(); picker.click(); },
      unattach: () => { att = null; attNote = null; drawFoot(); },
      toggle: () => { if (!thinkCan() || waiting) return; tick(); thinkOn = !thinkOn; drawFoot(); },
      history: openChats,
      newchat: newChat,
      subject: pickSubject,
      suggest: (b) => { input.value = CH_SUGGEST[+b.dataset.k]; send(); },
      retry: () => {
        if (waiting || !log.length || !log[log.length - 1].error) return;
        tick();
        log.pop();
        const lastQ = [...log].reverse().find((x) => x.role === "user");
        if (lastQ) send(lastQ.content, null); else draw();
      },
      choose: (b) => {
        if (waiting) return;
        tick();
        const m = log[+b.dataset.m], subj = m.choose[+b.dataset.k];
        subject = subj;
        m.chosen = subj;
        const lastQ = [...log].reverse().find((x) => x.role === "user");
        send(lastQ.content, chooseAtt);
      },
      think,
      src: (b) => openSource(srcMap[+b.dataset.k]),
      fileref: (b) => { tick(); flFileSheet(flFileOf(srcMap[+b.dataset.k])); },
    });

    restore();
    draw();
    requestAnimationFrame(() => (list.scrollTop = list.scrollHeight));
    Api.get("/subjects").then((j) => {
      if (!alive) return;
      subjects = (j.subjects || []).filter((s) => s.lectures === true).map((s) => String(s.name));
      const q = j.quota;
      left = q && typeof q.left === "number" ? Math.trunc(q.left) : null;
      thinkOffer = j.think && typeof j.think === "object" ? j.think : null;
      draw();
    }).catch(() => {});
    return () => {
      alive = false;
      if (vv) { vv.removeEventListener("resize", onVV); vv.removeEventListener("scroll", onVV); }
    };
  });
}

window.openChat = openChat;
