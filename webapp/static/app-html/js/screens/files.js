// Файлы курсов (app/lib/screens/files.dart): предметы → файлы по типам
// (лекции, практики…). Нажал файл — лист: конспект (общий на всех, ИИ
// зовётся один раз), скачать, просмотр в браузере, прислать в Telegram.
// Поиск сверху: файлы по названию и места в самих лекциях («где было про
// NPV?» → «Лекция 5 · слайд 12» и отрывок) — нажал, открылась страница.
// Снаружи: openFiles() — экран «Файлы», openSubjectFiles(subject, files) —
// файлы предмета, openFile(raw) — лист файла, openPage(fileId, page, subject) —
// страница лекции, flTgHtml(html, {cite}) — разметка Telegram в HTML.
"use strict";

/** Файл из /api/files (FileItem.fromJson). */
function flFileOf(j) {
  return {
    raw: j, id: j.id, title: j.title || "",
    head: j.head ? j.head : (j.title || ""), topic: j.topic || "",
    subject: j.subject || "", fileName: j.file_name || "", category: j.category || "other",
    hasText: j.has_text === true, hasSummary: j.has_summary === true, canEdit: j.can_edit === true,
  };
}

const FL_CATEGORY_ICONS = { lecture: "menu_book", practice: "science", control: "fact_check", method: "library_books",
  exam: "workspace_premium", other: "insert_drive_file" };
/** Фильтр файлов предмета: «Лабы» отдельно от практик (в базе это один тип). */
const FL_FILTERS = { lecture: "Лекции", practice: "Практики", lab: "Лабы", control: "КР и тесты", method: "Методички",
  exam: "Экзамен", other: "Другое" };
/** Тип файла словом под названием в поиске: «лекция», «лаба». */
const FL_KIND_WORD = { lecture: "лекция", practice: "практика", lab: "лаба", control: "контрольная", method: "методичка",
  exam: "к экзамену" };

/** Название раздела: у зачётного предмета «Экзамен» — «Вопросы к зачёту». */
function flFilterLabel(k, credit = false) { return k === "exam" && credit ? "Вопросы к зачёту" : FL_FILTERS[k] || FL_FILTERS.other; }
/** Предмет зачётный — по журналу СДО; нет предмета в журнале — null. */
function flIsCredit(grades, subject) {
  for (const c of (grades && grades.courses) || []) {
    if (!c || typeof c !== "object" || !sameSubject(String(c.title), subject)) continue;
    if (typeof c.kind === "string" && c.kind) return c.kind === "credit";
    return (c.marks || []).length === 1;
  }
  return null;
}
function flFilterOf(f) { return f.category === "practice" && /лаб|lab/i.test(f.title) ? "lab" : f.category; }
/** «Лекция 2» раньше «Лекция 10»: числа сравниваются как числа. */
function flNaturalCompare(a, b) {
  const x = a.toLowerCase().match(/\d+|\D+/g) || [], y = b.toLowerCase().match(/\d+|\D+/g) || [];
  for (let i = 0; i < x.length && i < y.length; i++) {
    const nx = /^\d+$/.test(x[i]) ? +x[i] : null, ny = /^\d+$/.test(y[i]) ? +y[i] : null;
    const c = nx !== null && ny !== null ? nx - ny : x[i] < y[i] ? -1 : x[i] > y[i] ? 1 : 0;
    if (c) return c;
  }
  return x.length - y.length;
}
/** Одинаковые названия (PDF и PPTX одной лекции) — одной строкой; первым — с конспектом или текстом. */
function flGroupSame(files) {
  const groups = new Map();
  for (const f of files) {
    const k = `${f.head}|${f.topic}`.trim().toLowerCase();
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(f);
  }
  const rank = (f) => (f.hasSummary ? 0 : f.hasText ? 1 : 2);
  const out = [...groups.values()].map((g) => g.sort((a, b) => rank(a) - rank(b)));
  out.sort((a, b) => flNaturalCompare(a[0].title, b[0].title));
  return out;
}
function flExt(f) { return f.fileName.includes(".") ? f.fileName.split(".").pop().toUpperCase() : ""; }
/** Цвет формата: PDF красный, презентация оранжевая, Word синий, таблица зелёная. */
function flFormatColor(ext) {
  if (ext === "PDF") return "var(--danger)";
  if (["PPT", "PPTX", "ODP", "KEY"].includes(ext)) return "#F2994A";
  if (["DOC", "DOCX", "RTF", "ODT"].includes(ext)) return "#4F8CFF";
  if (["XLS", "XLSX", "CSV", "ODS"].includes(ext)) return "var(--ok)";
  if (["ZIP", "RAR", "7Z"].includes(ext)) return "#8B7CF6";
  if (["JPG", "JPEG", "PNG", "HEIC"].includes(ext)) return "#2EC4B6";
  return "var(--muted)";
}
/** Значок формата слева от файла (FormatBadge). */
function flBadge(ext, category) {
  const c = flFormatColor(ext), label = ext.length > 4 ? ext.slice(0, 4) : ext;
  return `<span class="fl-badge" style="color:${c};background:color-mix(in srgb, ${c} ${Theme.dark ? 18 : 14}%, transparent)">${
    label ? `<b>${esc(label)}</b>` : icon(FL_CATEGORY_ICONS[category] || "insert_drive_file", "o", "font-size:20px")}</span>`;
}

/** Корни слов запроса — первые пять букв (без окончаний). */
function flStems(q) {
  return q.toLowerCase().split(/[^\p{L}\p{N}_]+/u).filter((w) => w.length >= 3).map((w) => (w.length > 5 ? w.slice(0, 5) : w));
}
/** Отрывок, где слова запроса выделены. */
function flMark(text, stems) {
  if (!stems.length) return esc(text);
  const re = new RegExp(`(${stems.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})[\\p{L}\\p{N}_]*`, "giu");
  let out = "", at = 0;
  for (const m of text.matchAll(re)) {
    out += esc(text.slice(at, m.index)) + `<b class="fl-mark">${esc(m[0])}</b>`;
    at = m.index + m[0].length;
  }
  return out + esc(text.slice(at));
}

// ── Разметка Telegram → HTML (widgets/tg_html.dart) ──
const FL_ENTITIES = { "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " ", "&amp;": "&" };
function flUnescape(s) { let o = s; for (const [k, v] of Object.entries(FL_ENTITIES)) o = o.split(k).join(v); return o; }
/** «[1]» в тексте — кнопкой к источнику: cite(n) вернул HTML или null (тогда «[n]» как есть). */
function flCiteText(text, cite) {
  if (!cite) return esc(text);
  let out = "", pos = 0;
  for (const m of text.matchAll(/\[(\d{1,2})\]/g)) {
    const span = cite(+m[1]);
    if (span == null) continue;
    out += esc(text.slice(pos, m.index)) + span;
    pos = m.index + m[0].length;
  }
  return out + esc(text.slice(pos));
}
/** HTML Telegram → безопасный HTML: b, i, u, s, code, pre, a, blockquote; незнакомые теги — без них. */
function flTgHtml(html, { cite = null } = {}) {
  const stack = [], hrefs = [];
  let out = "", pos = 0;
  const cls = { b: "b", strong: "b", i: "i", em: "i", u: "u", ins: "u", s: "s", strike: "s", del: "s", code: "code", pre: "code", blockquote: "q", a: "a" };
  const text = (raw) => {
    if (!raw) return;
    const href = stack.includes("a") && hrefs.length ? hrefs[hrefs.length - 1] : null;
    const code = stack.includes("code") || stack.includes("pre");
    const plain = flUnescape(raw);
    const inner = cite && href === null && !code ? flCiteText(plain, cite) : esc(plain);
    const c = [...new Set(stack.map((t) => cls[t]).filter(Boolean))].map((x) => "tg-" + x).join(" ");
    if (href !== null && /^(https?:|tg:|mailto:)/i.test(href)) out += `<a class="${c}" href="${esc(href)}" target="_blank" rel="noopener">${inner}</a>`;
    else out += c ? `<span class="${c}">${inner}</span>` : inner;
  };
  for (const m of html.matchAll(/<(\/?)([a-zA-Z0-9-]+)([^>]*)>/g)) {
    text(html.slice(pos, m.index));
    pos = m.index + m[0].length;
    const closing = m[1] === "/", name = m[2].toLowerCase();
    if (name === "br") { text("\n"); continue; }
    if (closing) {
      const i = stack.lastIndexOf(name);
      if (i >= 0) stack.splice(i);
      if (name === "a" && hrefs.length) hrefs.pop();
      if (name === "blockquote" || name === "pre") text("\n");
    } else {
      stack.push(name);
      if (name === "a") {
        const h = /href\s*=\s*["']([^"']*)["']/.exec(m[3] || "");
        hrefs.push(flUnescape(h ? h[1] : ""));
      }
    }
  }
  text(html.slice(pos));
  return out;
}

// ── Экран «Файлы» ──
function openFiles() {
  Nav.push((body) => {
    let files = null, query = "", seq = 0, found = null, hits = null, ready = true, timer = 0, bySubject = {};
    body.innerHTML = backRow() + screenTitle("Файлы") + '<div class="fl-top"></div><div class="fl-list">' + spinner() + "</div>";
    const top = body.querySelector(".fl-top"), list = body.querySelector(".fl-list");
    const card = (rows) => `<div class="hx"><div class="tile p0">${rows.join('<div class="divider"></div>')}</div></div>`;
    let rowFiles = [];
    const keyOf = (f) => { rowFiles.push(f); return rowFiles.length - 1; };

    const drawResults = () => {
      rowFiles = [];
      const spin = '<div class="fl-spin"><div class="spinner" style="margin:0 auto"></div></div>';
      if (found === null) { list.innerHTML = spin; return; }
      if (!found.length && hits !== null && !hits.length) {
        list.innerHTML = notice("Ничего не нашлось", ready ? "Ни в названиях, ни в тексте лекций." : "Тексты лекций ещё индексируются.", { pose: "sad" });
        return;
      }
      const stems = flStems(query);
      let h = "";
      if (found.length) h += section(`Файлы · ${found.length}`) + card(found.map((f) => flRow(f, keyOf(f), { withSubject: true })));
      if (hits === null) h += spin;
      else if (hits.length) {
        h += section("В тексте лекций") + card(hits.map((x, i) => `<button class="fl-row top" data-act="hit" data-k="${i}">
          ${icon("auto_stories", "o", "font-size:20px;color:var(--muted);margin-top:2px")}
          <div class="grow"><div class="bd b6" style="--sz:15px">${esc(x.title)}${x.place ? `<span class="acc"> · ${esc(x.place)}</span>` : ""}</div>
          <div class="bd mut" style="--sz:13px;margin-top:2px">${flMark(x.snippet, stems)}</div>
          ${x.subject ? `<div class="bd mut" style="--sz:12px;margin-top:2px">${esc(x.subject)}</div>` : ""}</div></button>`));
      }
      list.innerHTML = h;
    };
    const drawSubjects = () => {
      rowFiles = [];
      if (!files.length) { list.innerHTML = notice("Пока пусто", "Файлы курсов появятся после выгрузки из СДО."); return; }
      const subjects = Object.keys(bySubject).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
      list.innerHTML = subjects.map((s, i) => `<div class="hx" style="padding-bottom:var(--s)">
        <button class="tile row fl-subj" data-act="subject" data-k="${i}">
          <i class="fl-dot" style="background:${ink(s)}"></i><div class="grow bd b6" style="--sz:15px">${esc(s)}</div>
          <span class="bd mut" style="--sz:14px">${bySubject[s].length}</span><span class="mi mut">chevron_right</span></button></div>`).join("");
      list.subjects = subjects;
    };
    const draw = () => {
      if (!files) return;
      bySubject = {};
      for (const f of files) (bySubject[f.subject || "Без предмета"] ||= []).push(f);
      if (files.length && !top.firstChild) {
        top.innerHTML = `<div class="hx" style="padding-bottom:var(--m)"><label class="fl-search">${icon("search", "", "color:var(--muted)")}
          <input type="search" enterkeyhint="search" autocomplete="off" placeholder="Название или слово из лекции" aria-label="Поиск файлов">
          <button data-act="clear" aria-label="Очистить" hidden>${icon("close", "", "color:var(--muted)")}</button></label></div>`;
        const inp = top.querySelector("input"), clr = top.querySelector("[data-act=clear]");
        inp.addEventListener("input", () => {
          clr.hidden = !inp.value;
          clearTimeout(timer);
          timer = setTimeout(() => run(inp.value.trim()), 350);
        });
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });
        top.clear = () => { inp.value = ""; clr.hidden = true; clearTimeout(timer); run(""); };
      } else if (!files.length) top.innerHTML = "";
      if (query) drawResults(); else drawSubjects();
    };
    const run = async (q) => {
      if (q === query) return;
      const my = ++seq;
      query = q; found = null; hits = null; ready = true;
      if (!q) { draw(); return; }
      drawResults();
      const enc = encodeURIComponent(q);
      const fp = Api.get("/files?q=" + enc).then((j) => (j.items || []).map(flFileOf)).catch(() => []);
      const lp = q.length < 3 ? Promise.resolve({ items: [], ready: true })
        : Api.get("/lecture-search?q=" + enc).then((j) => ({ items: j.items || [], ready: j.ready !== false })).catch(() => ({ items: [], ready: true }));
      const f = await fp;
      if (my !== seq) return;
      found = f; drawResults();
      const l = await lp;
      if (my !== seq) return;
      hits = l.items.map((h) => ({ fileId: h.file_id, page: h.page || 1, title: h.title || "", subject: h.subject || "", place: h.place || "", snippet: h.snippet || "" }));
      ready = l.ready; drawResults();
    };
    const take = (j) => (j.items || []).map(flFileOf);
    const load = async () => {
      try { files = take(await Api.get("/files")); draw(); }
      catch (e) {
        if (!files) list.innerHTML = '<div style="height:60px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "retry" });
      }
    };
    on(body, {
      retry: () => { list.innerHTML = spinner(); load(); },
      clear: () => top.clear && top.clear(),
      subject: (b) => { const s = list.subjects[+b.dataset.k]; openSubjectFiles(s, bySubject[s]); },
      file: (b) => { tick(); flFileSheet(rowFiles[+b.dataset.k]); },
      hit: (b) => { tick(); const h = hits[+b.dataset.k]; flPageSheet(h.fileId, h.page, h.subject); },
    });
    const c = Api.cached("/files");
    if (c && c.items) { files = take(c); draw(); }
    load();
    return () => clearTimeout(timer);
  });
}

/** Строка файла (_FileRow): значок формата, «Лекция N», тема, «есть конспект»; тот же файл в другом формате — чипами справа. */
function flRow(f, k, { withSubject = false, same = [], sameKeys = [] } = {}) {
  const kw = FL_KIND_WORD[flFilterOf(f)];
  const info = [withSubject && f.subject ? f.subject : "", withSubject && kw ? kw : ""].filter(Boolean).join(" · ");
  return `<div class="fl-row" data-act="file" data-k="${k}" role="button" tabindex="0">${flBadge(flExt(f), f.category)}
    <div class="grow"><div class="nm" style="--sz:15px">${esc(f.head)}</div>
    ${f.topic ? `<div class="bd" style="--sz:14px;margin-top:2px">${esc(f.topic)}</div>` : ""}
    ${info || f.hasSummary ? `<div class="bd mut" style="--sz:12px">${f.hasSummary ? '<span class="b6" style="color:var(--ok)">есть конспект</span>' : ""}${
      f.hasSummary && info ? " · " : ""}${esc(info)}</div>` : ""}</div>
    ${same.map((o, i) => { const e = flExt(o); return `<button class="fl-same" data-act="file" data-k="${sameKeys[i]}" style="color:${flFormatColor(e)}">${esc(e || "ещё")}</button>`; }).join("")}
  </div>`;
}

/** Файлы предмета (SubjectFilesScreen): чипы типов, разделы по типам. */
function openSubjectFiles(subject, list) {
  const files = (list || []).map((f) => (f && f.raw ? f : flFileOf(f)));
  Nav.push((body) => {
    let filter = null, credit = false;
    const byKind = {};
    for (const f of files) (byKind[flFilterOf(f)] ||= []).push(f);
    const kinds = Object.keys(FL_FILTERS).filter((k) => byKind[k]);
    const color = ink(subject);
    let rowFiles = [];
    const card = (fs) => {
      const rows = flGroupSame(fs).map((g) => {
        const k = rowFiles.push(g[0]) - 1;
        const sameKeys = g.slice(1).map((o) => rowFiles.push(o) - 1);
        return flRow(g[0], k, { same: g.slice(1), sameKeys });
      });
      return `<div class="hx"><div class="tile p0">${rows.join('<div class="divider"></div>')}</div></div>`;
    };
    const draw = () => {
      rowFiles = [];
      const chip = (key, label) => `<button class="fl-chip${filter === key ? " on" : ""}" data-act="filter" data-k="${key ?? ""}"
        aria-pressed="${filter === key}" style="--c:${color}">${esc(label)}</button>`;
      const chips = kinds.length > 1 ? `<div class="fl-chips">${chip(null, "Все")}${kinds.map((k) => chip(k, `${flFilterLabel(k, credit)} · ${byKind[k].length}`)).join("")}</div>` : "";
      const old = body.querySelector(".fl-chips"), sx = old ? old.scrollLeft : 0;
      body.innerHTML = backRow() + screenTitle(subject) + chips +
        (filter !== null && byKind[filter] ? '<div style="height:var(--s)"></div>' + card(byKind[filter])
          : kinds.map((k) => section(flFilterLabel(k, credit)) + card(byKind[k])).join("")) + '<div style="height:var(--xxl)"></div>';
      const nc = body.querySelector(".fl-chips");
      if (nc) nc.scrollLeft = sx;
    };
    on(body, {
      filter: (b) => { tick(); filter = b.dataset.k || null; draw(); },
      file: (b) => { tick(); flFileSheet(rowFiles[+b.dataset.k]); },
    });
    draw();
    // зачёт или экзамен — из журнала СДО; нет входа или сети — как было
    if (files.some((f) => flFilterOf(f) === "exam")) {
      Api.get("/sdo/grades").then((g) => { if (flIsCredit(g, subject) === true) { credit = true; draw(); } }).catch(() => {});
    }
  }, { tint: subjectColor(subject) });
}

/** Адрес картинки страницы: сервер даёт полный, стенд — относительный. */
function flPageImage(url) { return /^https?:/.test(url) ? url : "/" + url.replace(/^\//, ""); }

/** Лист файла (_FileSheet): скачать, просмотр, в Telegram, пожаловаться; конспект. */
function flFileSheet(f) {
  let summary = null, note = null, busy = false;
  return Sheet.show('<div class="fl-sheet"></div>', (root, close, sheet) => {
    sheet.classList.add("fl-sh85");
    const box = root.querySelector(".fl-sheet");
    const draw = () => {
      let sum = "";
      if (f.hasText) {
        sum = `<div class="ttl" style="--sz:20px;margin-top:var(--xl)">Конспект</div><div style="height:var(--s)"></div>` +
          (summary !== null ? `<div class="bd tg" style="--sz:15px">${flTgHtml(summary)}</div>`
            : busy ? '<div style="padding:var(--l)"><div class="spinner" style="margin:0 auto"></div></div>'
            : `<button class="fl-tbtn acc" data-act="make">${icon("auto_awesome", "o")}<span class="bd b6" style="--sz:15px">Сделать конспект</span></button>`);
      }
      box.innerHTML = `<div class="eyebrow">${esc(f.subject)}</div>
        <div class="nm" style="--sz:21px;margin-top:4px">${esc(f.title)}</div>
        <div class="row" style="gap:var(--s);margin-top:var(--l)">
          <button class="fl-btn fill grow" data-act="download">${icon("download", "", "font-size:18px")}Скачать</button>
          <button class="fl-btn line grow" data-act="view">${icon("visibility", "o", "font-size:18px")}Просмотр</button></div>
        <button class="fl-tbtn" data-act="send">${icon("send", "", "font-size:16px")}Прислать в Telegram</button>
        ${f.canEdit ? "" : `<button class="fl-tbtn" data-act="report">${icon("flag", "o", "font-size:16px")}Пожаловаться или скрыть</button>`}
        ${note !== null ? `<div class="bd mut" style="--sz:14px;margin-top:var(--m)">${esc(note)}</div>` : ""}${sum}`;
    };
    const setNote = (t) => { note = t; draw(); };
    const loadSummary = async (make) => {
      busy = true; note = make ? "Делаю конспект — это до минуты…" : null; draw();
      try {
        const r = make ? await Api._req("POST", "/summary/" + f.id, {}, 120000) : await Api.get("/summary/" + f.id);
        summary = typeof r.summary === "string" ? r.summary : null;
        note = null;
        if (summary !== null) Ach.unlock("summary");
      } catch (e) { note = errorText(e); }
      busy = false; draw();
    };
    const send = async () => {
      tick();
      try { await Api._req("POST", `/files/${f.id}/send`, {}, 60000); setNote("Отправил в Telegram — файл в чате с ботом."); }
      catch (e) { setNote(errorText(e)); }
    };
    on(box, {
      async download() {
        tick();
        try {
          const r = await Api._req("POST", `/files/${f.id}/link`, {}, 30000);
          // в вебе — обычная загрузка по ссылке
          const a = document.createElement("a");
          a.href = r.url; a.download = r.file_name || f.fileName || ""; a.rel = "noopener";
          document.body.appendChild(a); a.click(); a.remove();
        } catch (e) {
          // больше 20 МБ Bot API не отдаёт — тогда файл придёт в Telegram
          setNote(errorText(e));
          if (e.status && String(e.message).includes("отправлю в чат")) await send();
        }
      },
      async view() {
        tick();
        // окно — сразу по нажатию: открытое после ответа сервера Safari считает всплывающим
        let w = null;
        try { w = window.open("", "_blank"); } catch (e) {}
        try {
          const r = await Api._req("POST", `/files/${f.id}/link`, {}, 30000);
          const url = r.url + "&view=1";
          if (w) { try { w.opener = null; } catch (e) {} w.location.href = url; } else openLink(url);
        } catch (e) { if (w) w.close(); setNote(errorText(e)); }
      },
      send,
      report: () => (window.openReportMenu ? openReportMenu("file", f.id) : toast("Скоро")),
      make: () => loadSummary(true),
    });
    draw();
    if (f.hasSummary) loadSummary(false);
  });
}

/** Страница лекции (_PageSheet): у PDF — картинкой, ниже текст; листать соседние, «Весь файл». */
function flPageSheet(fileId, page, subject = "") {
  let p = null, error = null, seq = 0, cur = page, title = "";
  return Sheet.show('<div class="fl-page"></div>', (root, close, sheet) => {
    sheet.classList.add("fl-sh88");
    const box = root.querySelector(".fl-page");
    const whole = `<button class="fl-btn fill grow" data-act="whole">${icon("description", "o", "font-size:18px")}Весь файл</button>`;
    const draw = () => {
      if (error !== null) {
        box.innerHTML = `<div class="ttl" style="--sz:22px">Не открылось</div><div class="bd mut" style="--sz:15px;margin-top:var(--s)">${esc(error)}</div>
          <div class="row" style="margin-top:var(--l)">${whole}</div>`;
        return;
      }
      if (!p) { box.innerHTML = spinner(); return; }
      const pg = p.page || cur, pages = p.pages || pg;
      const kind = p.kind === "слайд" ? "Слайд" : p.kind === "стр." ? "Страница" : "Часть";
      const img = p.image || "", text = String(p.text || "").trim();
      box.innerHTML = `<div class="eyebrow">${kind} ${pg} из ${pages}</div>
        <div class="nm" style="--sz:20px;margin-top:4px">${esc(title)}</div>
        ${img ? `<img class="fl-img" src="${esc(flPageImage(img))}" alt="${kind} ${pg}" onerror="this.remove()">` : ""}
        ${text ? `<div class="bd fl-text${img ? " mut" : ""}" style="--sz:${img ? 13 : 15}px">${esc(text)}</div>` : ""}
        <div class="row" style="margin-top:var(--l);gap:var(--xs)">
          <button class="fl-nav" data-act="prev" aria-label="Предыдущая"${pg > 1 ? "" : " disabled"}>${icon("chevron_left")}</button>
          ${whole}
          <button class="fl-nav" data-act="next" aria-label="Следующая"${pg < pages ? "" : " disabled"}>${icon("chevron_right")}</button></div>`;
    };
    const open = async (n) => {
      const my = ++seq;
      error = null; cur = n; draw();
      try {
        const r = await Api.get(`/files/${fileId}/page/${n}`);
        if (my !== seq) return;
        p = r; title = r.title || title;
        Ach.unlock("found");
        draw();
        sheet.scrollTop = 0;
      } catch (e) { if (my === seq) { error = errorText(e); draw(); } }
    };
    on(box, {
      prev: () => open((p.page || cur) - 1),
      next: () => open((p.page || cur) + 1),
      whole: () => {
        tick();
        close();
        flFileSheet(flFileOf({ id: fileId, title, subject, has_text: true }));
      },
    });
    open(page);
  });
}

window.openFiles = openFiles;
window.openSubjectFiles = openSubjectFiles;
/** Лист файла: raw — объект из /api/files (или {id, title, subject, has_text}). */
window.openFile = (raw) => flFileSheet(raw && raw.raw ? raw : flFileOf(raw || {}));
/** Страница лекции: из ответа помощника, из поиска. */
window.openPage = (fileId, page, subject = "") => flPageSheet(fileId, page, subject);
