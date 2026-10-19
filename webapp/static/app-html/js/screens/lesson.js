// «Пара» (app/lib/screens/lesson.dart): что за пара и сколько идёт, где
// (аудитория, этаж и корпус), кто ведёт (все его пары и оценка в капибарах),
// с кем пара; реакции и обсуждение группы (своя группа); по предмету —
// баллы и лекции. Открывается нажатием на пару где угодно: openLesson(raw).
"use strict";

/** Этаж по номеру аудитории: «А-223» → 2 этаж, «А-046» → цокольный (roomFloor). */
function roomFloor(room) {
  const m = /^(?:[А-ЯЁA-Z]{1,4}-?)?(\d)\d\d(?!\d)/.exec(String(room).trim());
  if (!m) return "";
  return m[1] === "0" ? "цокольный этаж" : `${m[1]} этаж`;
}
/** Тот же предмет в СДО и в файлах: без регистра и «ё» (sameSubject). */
function sameSubject(a, b) {
  const n = (x) => String(x).toLowerCase().replace(/ё/g, "е").trim();
  a = n(a); b = n(b);
  return a === b || (a.length > 12 && b.startsWith(a)) || (b.length > 12 && a.startsWith(b));
}
function markWord(label) { return label === "зачёт" ? "зачёт" : `«${label}»`; }
/** Предмет из /api/sdo/grades (study.dart: Course). */
function courseOf(j) {
  const marks = (j.marks || []).map((m) => ({ at: m.at, label: String(m.label) }));
  const c = { raw: j, id: j.id, title: j.title || "", needLabel: j.need_label || "", score: j.score || 0, max: j.max || 100,
    need: j.need || 0, worksTotal: j.works_total || 0, worksPassed: j.works_passed || 0, marks };
  c.top = marks.length ? marks[marks.length - 1].at : c.max;
  const got = marks.filter((m) => c.score >= m.at).map((m) => m.label);
  const label = got.length ? got[got.length - 1] : c.needLabel;
  c.enoughText = label ? `на ${markWord(label)} уже хватает` : "баллов уже хватает";
  return c;
}

const RATING_MOODS = ["злюсь", "грустно", "нормально", "довольна", "в восторге"];
const RATING_EMOTIONS = ["emotion_1_angry", "emotion_2_sad", "emotion_3_calm", "emotion_4_pleased", "emotion_5_delighted"];
function ratingCapy(name, size, color) {
  return `<i class="capy" style="--img:url(/img/rating/${name}.png);width:${size}px;height:${size * 0.95}px;color:${color}"></i>`;
}
function ratingRow(value, size, color) {
  let out = "";
  for (let i = 1; i <= 5; i++) out += ratingCapy(value >= i - 0.25 ? "rating_full" : value >= i - 0.75 ? "rating_half" : "rating_empty", size, color);
  return `<span class="ls-rrow">${out}</span>`;
}
const fmtRating = (v) => v.toFixed(1).replace(".", ",");

const REACTIONS = [["joy", "joy", "Класс"], ["calm", "morning", "Норм"], ["hard", "sad", "Сложно"], ["sleep", "night", "Скучно"], ["angry", "angry", "Злой препод"]];

function openLesson(raw, { own = true } = {}) {
  Ach.unlock("lesson");
  const l = lessonOf(raw);
  Nav.push((body) => {
    const t = now();
    const c = ink(l.title);
    const live = l.startAt && l.endAt && t >= l.startAt && t < l.endAt;
    const campus = campusOf(l.room), room = l.room.replace(/\s*\([^)]*\)/g, "").trim(), floor = roomFloor(room);
    const groups = l.groups.split(/,\s*/).filter(Boolean);
    const q = l.startAt ? new URLSearchParams({ start: l.startAt.toISOString(), title: l.title }).toString() : "";
    const value = !live ? (l.endAt && t >= l.endAt ? 1 : 0) : (t - l.startAt) / (l.endAt - l.startAt);
    const kind = l.kind ? l.kind[0].toUpperCase() + l.kind.slice(1) : "";
    const infoRow = (ic, title, text, act = "", extra = "") => `<${act ? "button" : "div"} class="irow"${act ? ` data-act="${act}"` : ""}>
      ${icon(ic, "o")}<div class="grow"><div class="bd b6" style="--sz:16px">${esc(title)}</div><div class="bd mut" style="--sz:13px">${esc(text)}</div>${extra}</div>
      ${act ? `<span class="mi chev">chevron_right</span>` : ""}</${act ? "button" : "div"}>`;
    let rows = "";
    if (room) rows += infoRow("place", room, [floor, campus ? `корпус ${campus}` : "", !campus && !floor ? "аудитория · её расписание" : "расписание аудитории"].filter(Boolean).join(" · "), "room");
    if (l.teacher) rows += (rows ? '<div class="divider"></div>' : "") + infoRow("person", l.teacher, "все пары преподавателя", "teacher", own ? '<div class="ls-rating"></div>' : "");
    if (groups.length > 1) rows += '<div class="divider"></div>' + infoRow("groups", `Поток · ${groups.length} ${plural(groups.length, "группа", "группы", "групп")}`, groups.length > 3 ? `${groups[0]} … ${groups[groups.length - 1]}` : groups.join(", "));
    body.innerHTML = backRow() + `<div style="padding:0 var(--xl) var(--l)">
        <div class="ttl" style="--sz:${titleSize(l.title, 30)}px">${esc(glue(l.title))}</div>
        ${kind || live ? `<div class="row" style="gap:6px;margin-top:var(--xs)"><i class="cm-dot" style="width:8px;height:8px;background:${c}"></i>
          <span class="bd mut" style="--sz:15px">${esc(kind)}${kind && live ? " · " : ""}${live ? `<b style="color:${c}">идёт</b>` : ""}</span></div>` : ""}
        <div class="row" style="margin-top:var(--l)"><span class="bd b7" style="--sz:14px">${esc(l.start)}</span>
          <div class="progress grow" style="--c:${c}"><i style="width:${value * 100}%"></i></div>
          <span class="bd b7" style="--sz:14px">${esc(l.end)}</span></div>
      </div>
      <div class="hx"><div class="tile p0 ls-info">${rows}<div class="ls-together"></div></div></div>
      <div class="ls-react"></div><div class="ls-comments"></div><div class="ls-extras"></div><div class="pad-bottom"></div>`;
    const $ = (s) => body.querySelector(s);
    const handlers = {
      room: () => window.openTarget ? openTarget(room, 3) : toast("Скоро"),
      teacher: () => window.openTarget ? openTarget(l.teacher, 2) : toast("Скоро"),
    };
    on(body, handlers);

    // с кем пара: группы с парой в том же кабинете (/api/lesson/groups)
    if (groups.length <= 1 && l.startAt && (l.room || l.teacher)) {
      Api.get("/lesson/groups?" + new URLSearchParams({ start: l.startAt.toISOString(), room: l.room, teacher: l.teacher })).then((j) => {
        const g = (j && j.groups) || [];
        if (!g.length) return;
        const n = g.length;
        $(".ls-together").innerHTML = '<div class="divider"></div>' + infoRow("groups", n === 1 ? `Вместе с ${g[0]}` : `Общая пара · ещё ${n} ${plural(n, "группа", "группы", "групп")}`,
          n === 1 ? "общая пара · расписание группы" : n > 10 ? `${g.slice(0, 9).join(", ")} и ещё ${n - 9}` : g.join(", "), n === 1 ? "together" : "");
        handlers.together = () => window.openTarget ? openTarget(g[0], 1) : toast("Скоро");
      }).catch(() => {});
    }

    // оценка преподавателя в капибарах (вариант А, 19.10)
    if (own && l.teacher) {
      let r = null;
      const drawRating = () => {
        const box = $(".ls-rating");
        if (!box || !r) return;
        const avg = r.avg, n = r.count || 0, mine = r.mine, can = r.can_rate === true;
        if (avg == null && !can) { box.innerHTML = ""; return; }
        const note = avg != null ? `${fmtRating(avg)} · ${n} ${plural(n, "оценка", "оценки", "оценок")}`
          : mine != null ? `твоя — ${mine} · среднее покажем от ${r.show_min || 3} оценок` : "оцени первым";
        box.innerHTML = `<span class="ls-rate" role="button" tabindex="0" data-act="rate" aria-label="Оценка преподавателя: ${esc(note)}">
          ${ratingRow(avg ?? mine ?? 0, 18, avg == null && mine == null ? "var(--muted)" : "var(--text)")}
          <span class="bd mut ell" style="--sz:13px;${avg != null ? "font-weight:600" : ""}">${esc(note)}</span></span>`;
      };
      Api.get("/teacher/rating?" + new URLSearchParams({ name: l.teacher })).then((j) => { r = j; drawRating(); }).catch(() => {});
      handlers.rate = async (b, e) => {
        e.stopPropagation();
        if (!r || r.can_rate !== true) return;
        tick();
        const res = await rateSheet(l.teacher, r.mine);
        if (res) { r = res; drawRating(); }
      };
      // строка оценки внутри строки преподавателя: её нажатие — не «все пары»
      $(".ls-info").addEventListener("click", (e) => {
        if (e.target.closest(".ls-rating")) { e.stopPropagation(); e.preventDefault(); handlers.rate(null, e); }
      }, true);
    }

    // реакции на пару (5.100): пять поз капибары, счёт группы
    if (own && !l.cancelled && l.startAt) {
      let counts = {}, mine = null, open = false, busy = false;
      const draw = () => {
        const total = Object.values(counts).reduce((a, b) => a + b, 0);
        if (!open && !total) { $(".ls-react").innerHTML = ""; return; }
        $(".ls-react").innerHTML = section("Как пара") + `<div class="hx"><div class="tile" style="padding:var(--s)"><div class="row" style="gap:0">
          ${REACTIONS.map(([id, pose, label]) => {
            const onn = mine === id, color = onn ? "var(--accent)" : "var(--text)";
            return `<button class="ls-choice${onn ? " on" : ""}" ${open ? `data-act="react" data-k="${id}"` : "disabled"} aria-label="${label}, ${counts[id] || 0}">
              ${capy(pose, 44, color)}<span class="bd ell" style="--sz:12px;color:${color};font-weight:${onn ? 700 : 500}">${label}</span>
              <span class="bd b7" style="--sz:13px;color:${onn ? color : "var(--muted)"}">${counts[id] ? counts[id] : "&nbsp;"}</span></button>`;
          }).join("")}</div>
          <div class="bd mut" style="--sz:12px;text-align:center;padding:var(--xs) var(--s)">${open ? "Видит только твоя группа, без имён" : "Отметить можно две недели после пары"}</div></div></div>`;
      };
      const take = (j) => { counts = j.counts || {}; mine = j.mine || null; open = j.open === true; };
      Api.get("/lesson/reactions?" + q).then((j) => { take(j); draw(); }).catch(() => {});
      handlers.react = async (b) => {
        if (busy) return;
        tick();
        const kind = b.dataset.k, was = [{ ...counts }, mine], next = mine === kind ? null : kind;
        if (mine) counts[mine] = Math.max(0, (counts[mine] || 1) - 1);
        if (next) counts[next] = (counts[next] || 0) + 1;
        mine = next; busy = true; draw();
        try { take(await Api.post("/lesson/reactions", { start: l.startAt.toISOString(), title: l.title, kind: next || "" })); }
        catch (e) { [counts, mine] = was; toast("Не отметилось, попробуй ещё раз", "error"); }
        busy = false; draw();
      };
    }

    // обсуждение группы: два последних и «Всё обсуждение · N» (5.108.1)
    if (own && l.startAt) {
      let st = null;
      const draw = () => {
        if (!st || (!st.open && !st.items.length)) { $(".ls-comments").innerHTML = ""; return; }
        const n = st.items.length, last = st.items.slice(-2);
        $(".ls-comments").innerHTML = section(n ? `Обсуждение группы · ${n}` : "Обсуждение группы") +
          last.map((cm) => `<div class="hx" style="margin-bottom:var(--s)">${bubble(cm, true)}</div>`).join("") +
          `<div class="hx" style="padding-top:var(--xs)"><button class="btn outline" data-act="discuss">${icon(n ? "forum" : "edit", "o", "font-size:20px")}
            ${n ? `Всё обсуждение · ${n}` : "Написать группе"}</button></div>
          ${n ? "" : `<div class="bd mut" style="--sz:12px;padding:var(--s) var(--xl) 0">Перенесли, где аудитория, что задали — видит только твоя группа</div>`}`;
      };
      const load = () => Api.get("/lesson/comments?" + q).then((j) => { st = { items: j.items || [], open: j.open === true, max: j.max || 500 }; draw(); }).catch(() => {});
      load();
      handlers.discuss = async () => { tick(); await discussionSheet(l, st, (s2) => { st = s2; draw(); }); load(); };
      body.addEventListener("contextmenu", (e) => { const b = e.target.closest("[data-cm]"); if (b) { e.preventDefault(); holdComment(b, load); } });
      longPress(body, "[data-cm]", (b) => holdComment(b, load));
    }

    // по предмету: баллы и три последние лекции
    Promise.all([Api.get("/sdo/grades").catch(() => null), Api.get("/files").catch(() => null)]).then(([g, f]) => {
      const course = g && g.courses ? g.courses.find((x) => sameSubject(x.title, l.title)) : null;
      const seen = new Set();
      const lectures = (f && f.items ? f.items : []).filter((x) => sameSubject(x.subject, l.title) && x.category === "lecture")
        .reverse().filter((x) => seen.add(`${x.head || x.title}|${x.topic || ""}`.toLowerCase())).slice(0, 3);
      if (!course && !lectures.length) return;
      let html = section("По предмету");
      if (course) {
        const cc = courseOf(course);
        html += `<div class="hx"><button class="tile row" data-act="course" style="gap:var(--l)">${ring(cc.score / cc.top, c, `<span class="num" style="--sz:18px">${cc.score}</span>`)}
          <div class="grow"><div class="bd mut" style="--sz:13px">Баллы БРС</div>
          <div class="bd b7" style="--sz:16px">${cc.need > 0 ? `до «${esc(cc.needLabel)}» ещё ${cc.need}` : esc(cc.enoughText)}</div>
          ${cc.worksTotal > 0 ? `<div class="bd mut" style="--sz:13px">работы: зачтено ${cc.worksPassed} из ${cc.worksTotal}</div>` : ""}</div>
          <span class="mi mut">chevron_right</span></button></div>`;
        handlers.course = () => window.openCourse ? openCourse(course) : toast("Скоро");
      }
      lectures.forEach((x, i) => {
        html += `<div class="hx" style="padding-top:var(--s)"><button class="tile row" data-act="lecture" data-k="${i}" style="padding:var(--m) var(--l)">
          ${icon("menu_book", "o", "font-size:20px;color:var(--muted)")}<div class="grow"><div class="bd b6" style="--sz:15px">${esc(x.head || x.title)}</div>
          ${x.topic ? `<div class="bd mut" style="--sz:13px">${esc(x.topic)}</div>` : ""}</div>
          ${x.has_text ? `<span class="bd b7 acc" style="--sz:13px">${x.has_summary ? "Конспект" : "Открыть"}</span>` : ""}</button></div>`;
      });
      handlers.lecture = (b) => window.openFile ? openFile(lectures[+b.dataset.k]) : toast("Скоро");
      $(".ls-extras").innerHTML = html;
    });
  }, { tint: subjectColor(l.title) });
}

/** Долгое нажатие (сообщение обсуждения): touch — 500 мс без сдвига. */
function longPress(root, sel, fn) {
  let timer = 0, x = 0, y = 0;
  root.addEventListener("touchstart", (e) => {
    const b = e.target.closest(sel);
    if (!b) return;
    x = e.touches[0].clientX; y = e.touches[0].clientY;
    timer = setTimeout(() => { timer = 0; fn(b); }, 500);
  }, { passive: true });
  const stop = () => { clearTimeout(timer); timer = 0; };
  root.addEventListener("touchmove", (e) => { if (Math.hypot(e.touches[0].clientX - x, e.touches[0].clientY - y) > 10) stop(); }, { passive: true });
  root.addEventListener("touchend", stop);
}

function commentTime(created) {
  const t = new Date(String(created).replace(" ", "T") + "Z");
  if (isNaN(t)) return "";
  const a = msk(t), d = msk();
  return a.iso === d.iso ? hm(t) : `${a.d}.${String(a.m).padStart(2, "0")} ${hm(t)}`;
}
/** Сообщение пузырём; своё — справа, цветом акцента. */
function bubble(cm, preview = false) {
  const mine = cm.mine === true, time = commentTime(cm.created_at || "");
  const author = mine ? "ты" : cm.author;
  return `<div class="ls-bub${mine ? " mine" : ""}"><div class="bd mut" style="--sz:12px;padding:2px var(--m)">${esc(time ? `${author} · ${time}` : author)}</div>
    <div class="ls-msg${preview ? " clamp3" : ""}" data-cm="${cm.id}" data-mine="${mine ? 1 : 0}"${preview ? ' data-act="discuss"' : ""}>${esc(cm.text)}</div></div>`;
}
async function holdComment(b, reload) {
  const id = +b.dataset.cm;
  if (b.dataset.mine !== "1") { if (window.openReportMenu) openReportMenu("comment", id, reload); return; }
  tick();
  if (!(await confirmSheet({ title: "Удалить комментарий?", action: "Удалить", danger: true }))) return;
  try { await Api.del("/lesson/comments/" + id); reload(); } catch (e) { toast(errorText(e), "error"); }
}

/** Всё обсуждение листом: сообщения и поле ввода снизу. */
function discussionSheet(l, st, onChange) {
  const q = new URLSearchParams({ start: l.startAt.toISOString(), title: l.title }).toString();
  return Sheet.show(`<div class="ttl" style="--sz:24px">Обсуждение пары</div>
    <div class="bd mut" style="--sz:13px;margin-top:2px">Видит только твоя группа. Долгое нажатие на чужое — пожаловаться или скрыть автора</div>
    <div class="ls-list"></div><div class="ls-input"></div>`, (body, close, sheet) => {
    sheet.classList.add("ls-sheet");
    let s = st || { items: [], open: false, max: 500 }, busy = false;
    const draw = () => {
      const list = body.querySelector(".ls-list");
      list.innerHTML = s.items.length ? s.items.map((cm) => `<div style="margin-bottom:var(--s)">${bubble(cm)}</div>`).join("")
        : `<div class="bd mut" style="--sz:15px;text-align:center;padding:var(--xl)">Пока тихо. Перенесли, где аудитория, что задали — напиши группе</div>`;
      body.querySelector(".ls-input").innerHTML = s.open ? `<div class="ls-field"><textarea rows="1" maxlength="${s.max}" placeholder="Написать группе…"></textarea>
        <button class="ls-send" data-act="send" aria-label="Отправить">${icon("arrow_upward", "", "font-size:20px")}</button></div>`
        : `<div class="bd mut" style="--sz:13px;padding:var(--xs) 0">Писать можно за неделю до пары и две недели после</div>`;
      list.scrollTop = list.scrollHeight;
      const ta = body.querySelector("textarea");
      if (ta) ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 110) + "px"; });
    };
    const reload = () => Api.get("/lesson/comments?" + q).then((j) => { s = { ...s, items: j.items || [] }; draw(); onChange(s); }).catch(() => {});
    draw();
    on(body, {
      async send() {
        const ta = body.querySelector("textarea"), text = ta.value.trim();
        if (!text || busy) return;
        tick(); busy = true;
        try {
          const j = await Api.post("/lesson/comments", { start: l.startAt.toISOString(), title: l.title, text });
          s = { ...s, items: j.items || [] }; draw(); onChange(s);
        } catch (e) { toast(errorText(e), "error"); }
        busy = false;
      },
    });
    body.addEventListener("contextmenu", (e) => { const b = e.target.closest("[data-cm]"); if (b) { e.preventDefault(); holdComment(b, reload); } });
    longPress(body, "[data-cm]", (b) => holdComment(b, reload));
  });
}

/** Лист оценки преподавателя: пять капибар, эмоция и «N из 5». → новый ответ сервера. */
function rateSheet(name, mine) {
  let score = mine || 0, busy = false;
  return Sheet.show(`<div class="ttl" style="--sz:24px">Как тебе ${esc(name)}?</div>
    <div class="bd mut" style="--sz:14px;margin-top:4px">Только цифра, без отзывов. Видно среднее всех оценок — от трёх</div>
    <div class="ls-pick"></div><div class="ls-mood"></div>
    <button class="btn primary" data-act="done" style="margin-top:var(--l)">Готово</button>
    ${mine != null ? '<button class="btn text" data-act="clear">Убрать мою оценку</button>' : ""}`, (body, close) => {
    const draw = () => {
      body.querySelector(".ls-pick").innerHTML = [1, 2, 3, 4, 5].map((i) => `<button data-act="pick" data-k="${i}" aria-label="${i} из 5" class="${score === i ? "on" : ""}">
        ${ratingCapy(i <= score ? "rating_full" : "rating_empty", 54, i <= score ? "var(--accent)" : "var(--muted)")}</button>`).join("");
      body.querySelector(".ls-mood").innerHTML = !score ? `<span class="bd mut" style="--sz:15px">Нажми на капибару</span>`
        : `${ratingCapy(RATING_EMOTIONS[score - 1], 72, "var(--accent)")}<div><div class="ttl" style="--sz:30px">${score} из 5</div>
           <div class="bd mut" style="--sz:14px">${RATING_MOODS[score - 1]}</div></div>`;
      body.querySelector("[data-act=done]").disabled = !score || busy;
    };
    const send = async (v) => {
      if (busy) return;
      busy = true; draw();
      try { close(await Api.post("/teacher/rating", { name, score: v })); }
      catch (e) { toast(errorText(e), "error"); busy = false; draw(); }
    };
    draw();
    on(body, { pick(b) { tick(); score = +b.dataset.k; draw(); }, done: () => send(score), clear: () => send(0) });
  });
}

window.openLesson = openLesson;
