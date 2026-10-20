// ДЗ группы (доска старосты, /addhw в боте) и заметки к парам на сегодня и
// завтра (/note в боте, «+» — здесь же) — app/lib/screens/homework.dart.
// Входы — плитками на вкладке «Сдать»: openHomework(), openNotes().
"use strict";

/** «пт, 9 окт» — везде на доске ДЗ и в заметках один формат (shortDay). */
function dlShortDay(iso) {
  if (!/^\d{4}-\d\d-\d\d/.test(iso || "")) return iso || "";
  const t = msk(new Date(iso.slice(0, 10) + "T12:00:00+03:00"));
  return `${WD_SHORT[t.wd].toLowerCase()}, ${t.d} ${MONTHS_SHORT[t.m - 1]}`;
}

/** Экран поверх вкладок с загрузкой (_Page + Loader): load() → данные, view(data) → html. */
function dlPage(load, view, handlers, { cacheKey = null } = {}) {
  Nav.push((body) => {
    let data = null, error = null;
    const draw = () => {
      if (data) body.innerHTML = view(data);
      else body.innerHTML = backRow() + (error ? '<div style="height:80px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner());
    };
    const reload = async () => {
      try { data = await load(false); error = null; } catch (e) { error = e; }
      draw();
    };
    if (cacheKey) { try { const c = load(true); if (c) data = c; } catch (e) {} }
    on(body, { retry() { error = null; draw(); reload(); }, ...handlers(reload, () => data) });
    draw();
    reload();
  });
}

function dlHomeworkOf(j) {
  return { id: j.id, subject: j.subject || "", content: j.content || "", lessonDate: j.lesson_date || "", hasFile: j.has_file === true, mine: j.mine === true };
}

function openHomework() {
  const path = "/homework";
  const parse = (j) => (j && Array.isArray(j.items) ? j.items.map(dlHomeworkOf) : []);
  dlPage((cache) => (cache ? (Api.cached(path) ? parse(Api.cached(path)) : null) : Api.get(path).then(parse)), (items) => {
    const today = isoDay();
    const isPast = (h) => /^\d{4}-\d\d-\d\d/.test(h.lessonDate) && h.lessonDate.slice(0, 10) < today;
    const card = (h, past) => {
      const dateColor = past ? "var(--muted)" : "var(--warn)";
      return `<div class="hx" style="margin-bottom:var(--s)"><div class="tile hw-card"${past ? ' style="opacity:.55"' : ""}>
        <i class="hw-bar" style="background:${ink(h.subject)}"></i>
        <div class="grow"><div class="bd b6" style="--sz:15px">${esc(h.subject)}</div>
          ${h.content ? `<div class="bd mut" style="--sz:14px;margin-top:4px;white-space:pre-wrap">${esc(h.content)}</div>` : ""}
          ${h.lessonDate ? `<div class="row" style="gap:4px;margin-top:var(--s)">${icon("event", "o", `font-size:14px;color:${dateColor}`)}
            <span class="bd b6" style="--sz:12px;color:${dateColor}">к паре · ${esc(dlShortDay(h.lessonDate))}</span></div>` : ""}
          ${h.hasFile ? `<button class="hw-file" data-act="send" data-id="${h.id}">${icon("attach_file", "", "font-size:16px")}Прислать файл</button>` : ""}
        </div>${h.mine ? "" : `<div class="hw-more">${dlReportButton("hw", h.id)}</div>`}</div></div>`;
    };
    const ahead = items.filter((h) => !isPast(h)), past = items.filter(isPast);
    let html = backRow() + screenTitle("ДЗ группы");
    if (!items.length) html += notice("Доска ДЗ пока пустая", "Староста добавит задания — они появятся тут.", { pose: "joy" });
    html += ahead.map((h) => card(h, false)).join("");
    if (past.length) html += section("Прошло") + past.map((h) => card(h, true)).join("");
    return html + '<div style="height:var(--xxl)"></div>';
  }, (reload) => ({
    async send(b) {
      tick();
      try {
        await Api.post(`/homework/${b.dataset.id}/send`);
        toast("Отправил в Telegram — файл в чате с ботом.", "done");
      } catch (e) { toast(errorText(e), "error"); }
    },
    report: (b) => openReportMenu(b.dataset.kind, +b.dataset.id, reload),
  }), { cacheKey: path });
}
window.openHomework = openHomework;

function openNotes() {
  const today = isoDay(), tomorrow = addDays(today, 1);
  const parse = (j) => (j && Array.isArray(j.items) ? j.items : []).map((n) => ({
    id: typeof n.id === "number" ? Math.trunc(n.id) : 0, subject: n.subject || "", text: n.text || "", mine: n.mine === true }));
  const paths = [`/notes?date=${today}`, `/notes?date=${tomorrow}`];
  dlPage((cache) => {
    if (cache) { const c = paths.map((p) => Api.cached(p)); return c.every((x) => x !== undefined) ? c.map(parse) : null; }
    return Promise.all(paths.map((p) => Api.get(p).then(parse)));
  }, (days) => {
    const total = days[0].length + days[1].length;
    let html = backRow() + screenTitle("Заметки", { trailing: `<button class="dl-fab" data-act="add" aria-label="Новая заметка">${icon("add")}</button>` });
    if (!total) html += notice("Заметок нет", "Пометку к паре или дню добавь кнопкой «+» — её увидит вся группа под расписанием.", { pose: "joy" });
    days.forEach((notes, i) => {
      if (!notes.length) return;
      html += section(i === 0 ? `Сегодня · ${dlShortDay(today)}` : `Завтра · ${dlShortDay(tomorrow)}`);
      html += notes.map((n) => `<div class="hx" style="margin-bottom:var(--s)"><div class="tile hw-note${n.id > 0 ? " act" : ""}">
        ${icon("push_pin", "o", "font-size:18px;color:var(--accent)")}
        <div class="grow">${n.subject ? `<div class="bd b6" style="--sz:15px">${esc(n.subject)}</div>` : ""}<div class="bd" style="--sz:15px;white-space:pre-wrap">${esc(n.text)}</div></div>
        ${n.mine && n.id > 0 ? `<button class="dl-ib" data-act="del" data-id="${n.id}" aria-label="Убрать заметку">${icon("delete_outline", "", "font-size:20px;color:var(--muted)")}</button>`
          : n.id > 0 ? dlReportButton("note", n.id) : ""}</div></div>`).join("");
    });
    return html + '<div style="height:var(--xxl)"></div>';
  }, (reload) => ({
    async add() {
      tick();
      const saved = await dlNoteSheet();
      if (!saved) return;
      toast(saved, "done");
      reload();
    },
    async del(b) {
      const ok = await confirmSheet({ title: "Убрать заметку?", text: "Она пропадёт у всей группы.", action: "Убрать", danger: true });
      if (!ok) return;
      try { await Api.del(`/notes/${b.dataset.id}`); } catch (e) { toast(errorText(e), "error"); return; }
      reload();
    },
    report: (b) => openReportMenu(b.dataset.kind, +b.dataset.id, reload),
  }), { cacheKey: paths[0] });
}
window.openNotes = openNotes;

/** Лист «Новая заметка»: день, пара этого дня (по желанию) и текст. → подпись для плашки или null. */
function dlNoteSheet() {
  const MAX = 500;   // как NOTE_MAX в боте
  const today = isoDay(), tomorrow = addDays(today, 1);
  let date = tomorrow, subject = "", subjects = [], asked = 0, error = null, busy = false;
  return Sheet.show(`<div class="ttl" style="--sz:24px">Новая заметка</div>
    <div class="hw-public">${icon("groups", "", "font-size:22px;color:var(--accent)")}
      <span class="bd b6 grow" style="--sz:14px">Это не личная заметка: её увидит вся группа под расписанием этого дня.</span></div>
    <button class="hw-rules" data-act="rules"><span class="bd mut" style="--sz:13px">Добавляя, соглашаешься с <span style="color:var(--dl-link)">Правилами Капибары</span></span></button>
    <div class="eyebrow" style="margin-top:var(--l)">Когда</div>
    <div class="dl-chips hw-days"></div>
    <div class="hw-subj"></div>
    <div style="height:var(--l)"></div>
    <div class="hw-tawrap"><textarea class="field dl-field hw-text" rows="2" maxlength="${MAX}" placeholder="Контрольная, принести ноутбук…" autocapitalize="sentences"></textarea>
      <div class="bd mut hw-count" style="--sz:12px">0/${MAX}</div></div>
    <div class="dl-err"></div>
    <div style="height:var(--m)"></div>
    <button class="btn primary dl-btn50" data-act="save">Показать всей группе</button>`, (body, close) => {
    const ta = body.querySelector(".hw-text");
    const max6 = (() => { const t = msk(); const d = new Date(Date.UTC(t.y, t.m - 1 + 6, t.d, 12)); return d.toISOString().slice(0, 10); })();
    const draw = () => {
      const other = date !== today && date !== tomorrow;
      body.querySelector(".hw-days").innerHTML = `<button class="dl-chip${date === today ? " on" : ""}" data-act="day" data-d="${today}">Сегодня</button>
        <button class="dl-chip${date === tomorrow ? " on" : ""}" data-act="day" data-d="${tomorrow}">Завтра</button>
        <span class="dl-chip${other ? " on" : ""}">${esc(other ? dlShortDay(date) : "Другой день")}${dlPickInput("date", date, { min: today, max: max6, act: "date" })}</span>`;
      body.querySelector(".hw-subj").innerHTML = subjects.length ? `<div class="eyebrow" style="margin-top:var(--l)">К паре</div>
        <div class="dl-chips"><button class="dl-chip${subject ? "" : " on"}" data-act="subj" data-k="-1">Ко всему дню</button>
        ${subjects.map((s, i) => `<button class="dl-chip${subject === s ? " on" : ""}" data-act="subj" data-k="${i}">${esc(s)}</button>`).join("")}</div>` : "";
      body.querySelector(".dl-err").innerHTML = error ? `<div class="bd" style="--sz:14px;color:var(--danger);margin-top:var(--s)">${esc(error)}</div>` : "";
      body.querySelector("[data-act=save]").disabled = busy;
    };
    const loadSubjects = async () => {
      const mine = ++asked;
      let got = [];
      try {
        const j = await Api.get(`/day?date=${date}`);
        for (const l of (j && j.lessons) || []) { const t = String(l.title || "").trim(); if (t && !got.includes(t)) got.push(t); }
      } catch (e) { got = []; }
      if (mine !== asked) return;
      subjects = got;
      if (!got.includes(subject)) subject = "";
      draw();
    };
    const setDate = (d) => { tick(); date = d; draw(); loadSubjects(); };
    draw();
    loadSubjects();
    setTimeout(() => ta.focus(), 300);
    ta.addEventListener("input", () => {
      body.querySelector(".hw-count").textContent = `${ta.value.length}/${MAX}`;
      ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight + 2, 150) + "px";
    });
    dlBindPickers(body, (what, v) => { if (what === "date") setDate(v); });
    on(body, {
      day: (b) => setDate(b.dataset.d),
      subj(b) { tick(); const k = +b.dataset.k; subject = k < 0 ? "" : subjects[k]; draw(); },
      rules: () => (window.openLegal ? openLegal("rules") : toast("Скоро")),
      async save() {
        const text = ta.value.trim();
        if (!text) { error = "Напиши, что запомнить"; draw(); return; }
        tick();
        busy = true; error = null; draw();
        try {
          await Api.post("/notes", { date, subject, text });
          close(`Заметка на ${dlShortDay(date)} — видна всей группе`);
          return;
        } catch (e) { error = errorText(e); }
        busy = false; draw();
      },
    });
  }).then((v) => (typeof v === "string" ? v : null));
}
window.dlNoteSheet = dlNoteSheet;
