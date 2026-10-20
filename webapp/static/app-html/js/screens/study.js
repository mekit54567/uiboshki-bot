// «Учёба» (app/lib/screens/study.dart): баллы БРС по предметам — кольцо
// «сколько набрано», сколько до следующей отметки, работы текущего контроля.
// Нажал предмет — его экран (openCourse): отметки, цель (widgets/goal_card.dart),
// посещения лекций, работы, из чего баллы и как они росли. Там же — лёгкий
// график по неделям (widgets/trend_chart.dart: window.trendChart) для рейтинга.
"use strict";

/** Число без лишних знаков: 6 → «6», 2.5 → «2,5» (fmtNum). */
function stNum(v) {
  v = Number(v) || 0;
  return v === Math.round(v) ? String(Math.round(v)) : v.toFixed(1).replace(".", ",");
}
/** «2026-08-27» → «27 августа»; не дата — пусто (dayMonth). */
function stDayMonth(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${+m[3]} ${MONTHS[+m[2] - 1]}` : "";
}
function stPoints(n) { return `${stNum(n)} ${plural(Math.ceil(n), "балл", "балла", "баллов")}`; }
function stWorks(n) { return `${n} ${plural(n, "работу", "работы", "работ")}`; }
/** Ответ сервера «подключи СДО…» / «вход устарел…» — нужен свой вход (needsSdo). */
function stNeedsSdo(message) { return /подключи|устарел/.test(message || ""); }
/** Что даёт свой вход (sdoPerks). */
const ST_PERKS = [
  ["school", "o", "Баллы по каждому предмету и сколько осталось до зачёта или «3»"],
  ["check_circle_outline", "", "Какие работы текущего контроля зачтены, а какие нет"],
  ["upload", "", "Сдача работ прямо отсюда — до 3 файлов за раз"],
  ["notifications_none", "", "Бот напишет, когда появятся новые баллы"],
];

/** Предмет целиком (Course.fromJson): к courseOf из lesson.js — работы, итог, цель. */
function stCourse(j) {
  const c = courseOf(j);
  c.finalMark = j.final || "";
  c.works = j.works || [];
  c.categories = j.categories || [];
  c.goal = j.goal && typeof j.goal === "object" ? j.goal : null;
  c.attendance = j.attendance && typeof j.attendance === "object" ? j.attendance : null;
  c.history = j.history && typeof j.history === "object" ? j.history : null;
  return c;
}

/** Кольцо баллов (ScoreRing): доля от высшей отметки, растёт при появлении. */
function stRing(value, color, inner, size = 54, stroke = 5) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value || 0));
  return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${stroke}"/>
    ${v > 0 ? `<circle class="st-arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${c} ${c}" style="--c:${c};--o:${c * (1 - v)}"/>` : ""}</svg>
    <span class="st-in">${inner}</span></div>`;
}

// ── Вкладка «Учёба» ──
const ST_SDO_BADGE = { ok: ["var(--ok)", "СДО подключено"], expired: ["var(--danger)", "Вход в СДО устарел"] };

/** Карточка «подключи СДО» (_ConnectCard / _ConnectBenefit). */
function stConnectCard(problem) {
  const expired = problem.includes("устарел");
  if (Theme.design2 && !expired) {
    return `<div class="hx"><div class="tile st-card" style="text-align:center">
      <div style="height:var(--s)"></div>
      <span class="acc">${capy("joy", 96)}</span>
      <div class="ttl" style="--sz:22px;margin-top:var(--m)">Подключи СДО</div>
      <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Баллы, посещения и сдача работ появятся здесь</div>
      <button class="btn primary st-btn48" style="margin-top:var(--l)" data-act="connect">Подключить</button>
    </div></div>`;
  }
  let title = problem.replace(/:\s*вкладка.*$/, "");
  if (title) title = title[0].toUpperCase() + title.slice(1);
  return `<div class="hx"><div class="tile st-card">
    <div class="row" style="gap:var(--l)"><span class="acc">${capy(expired ? "sad" : "day", 64)}</span>
      <div class="grow bd b6" style="--sz:17px">${esc(title)}</div></div>
    <div class="bd mut" style="--sz:14px;margin-top:var(--m)">Баллы и задания у каждого свои — их видно только со своим входом в СДО.</div>
    <div style="height:var(--m)"></div>
    ${ST_PERKS.map(([ic, v, t]) => `<div class="row" style="padding:4px 0">${icon(ic, v, "font-size:18px;color:var(--accent)")}<div class="grow bd" style="--sz:14px">${esc(t)}</div></div>`).join("")}
    <button class="btn primary st-btn48" style="margin-top:var(--l)" data-act="connect">${expired ? "Подключить заново" : "Подключить СДО"}</button>
  </div></div>`;
}

/** Строка предмета (_CourseRow). */
function stCourseRow(c, k) {
  const color = ink(c.title);
  const status = c.finalMark ? `итог — ${c.finalMark}`
    : c.need > 0 ? `до «${c.needLabel}» ещё ${c.need} ${plural(Math.round(c.need), "балл", "балла", "баллов")}` : c.enoughText;
  return `<div style="padding:0 var(--l) var(--s)"><button class="tile row" data-act="course" data-k="${k}" style="gap:0">
    ${stRing(c.score / c.top, color, `<span class="num" style="--sz:18px">${esc(c.score)}</span>`)}<i style="width:var(--l);flex:none"></i>
    <div class="grow"><div class="bd b6" style="--sz:15px">${esc(c.title)}</div>
      <div class="bd" style="--sz:13px;margin-top:3px;color:${c.need > 0 ? "var(--muted)" : "var(--ok)"}">${esc(status)}</div>
      ${c.worksTotal > 0 ? `<div class="bd mut" style="--sz:13px">работы: зачтено ${c.worksPassed} из ${c.worksTotal}</div>` : ""}</div>
    <span class="mi mut">chevron_right</span></button></div>`;
}

Screens.study = {
  mount(body, screen) {
    let data = null, busy = false;
    /** Баллы и статус входа рядом; без статуса баллы всё равно показываем. */
    const load = async (fromCache) => {
      const get = fromCache
        ? (p) => { const v = Api.cached(p); return v === undefined ? Promise.reject(new Error("нет в запасе")) : Promise.resolve(v); }
        : (p) => Api.get(p);
      const status = get("/sdo/status").then((r) => (r && typeof r === "object" ? r.state || null : null), () => null);
      try {
        const j = await get("/sdo/grades");
        return { courses: (j.courses || []).map(stCourse), problem: null, sdo: await status };
      } catch (e) {
        if (e instanceof ApiError && e.status) return { courses: [], problem: e.message, sdo: await status };
        throw e;
      }
    };
    const draw = () => {
      const d = data;
      const badge = d.sdo == null ? "" : (() => {
        const [color, label] = ST_SDO_BADGE[d.sdo] || ["var(--muted)", "СДО не подключено"];
        return `<button class="st-badge" data-act="connect" aria-label="${label}"><i style="background:${color}"></i><span aria-hidden="true">СДО</span></button>`;
      })();
      let rest = "";
      if (d.problem && stNeedsSdo(d.problem)) rest = stConnectCard(d.problem);
      else if (d.problem) rest = notice("Баллы не видны", d.problem, { retry: "retry" });
      else if (!d.courses.length) rest = notice("Пока пусто", "Преподаватели ещё не завели журналы.");
      body.innerHTML = screenTitle("Учёба", { trailing: badge }) + `
        <div class="row st-doors">
          <button class="tile" data-act="chat">${icon("auto_awesome", "o", "color:var(--accent)")}
            <div class="nm" style="--sz:18px;margin-top:var(--m)">Kapi ИИ</div><div class="bd mut" style="--sz:13px;margin-top:2px">Отвечает по лекциям</div></button>
          <button class="tile" data-act="files">${icon("folder", "o", "color:var(--accent)")}
            <div class="nm" style="--sz:18px;margin-top:var(--m)">Файлы</div><div class="bd mut" style="--sz:13px;margin-top:2px">лекции, практики</div></button>
        </div>
        ${rest}${d.courses.map(stCourseRow).join("")}<div style="height:120px"></div>`;
    };
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try { data = await load(false); draw(); }
      catch (e) {
        if (e instanceof ApiError && e.status === 401) return;
        if (!data) body.innerHTML = '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "retry" });
      } finally { busy = false; }
    };
    on(body, {
      retry: () => { if (!data) body.innerHTML = spinner(); refresh(); },
      connect: () => { tick(); openSdoConnect().then(refresh); },
      chat: () => { tick(); if (window.openChat) openChat(); else toast("Скоро"); },
      files: () => { tick(); if (window.openFiles) openFiles(); else toast("Скоро"); },
      course: (b) => { tick(); const c = data && data.courses[+b.dataset.k]; if (c) openCourse(c.raw); },
    });
    screen.reload = refresh;
    pullRefresh(screen, refresh);
    // сразу — из запаса телефона, свежие следом (Loader.fromCache)
    body.innerHTML = spinner();
    load(true).then((d) => { if (d && !data) { data = d; draw(); } }).catch(() => {});
    refresh();
  },
  onShow(body, screen) { if (screen.reload) screen.reload(); },
};

// ── Экран предмета (CourseScreen) ──
const ST_WORK = {
  ok: ["check_circle", "", "зачтено"],
  low: ["error_outline", "", "ниже порога"],
  wait: ["hourglass_top", "", "ждёт оценки"],
  open: ["radio_button_unchecked", "", "можно сдать"],
  miss: ["cancel", "o", "не сдано"],
};

/** Работа текущего контроля (_WorkRow): задание или тест — свой экран, прочее — страница в СДО. */
function stWorkRow(w, k) {
  const st = ST_WORK[w.status] || ["radio_button_unchecked", "", ""];
  const color = { ok: "var(--ok)", low: "var(--danger)", miss: "var(--danger)", wait: "var(--warn)" }[w.status] || "var(--muted)";
  const isTask = (w.module === "assign" || w.module === "quiz") && Number.isInteger(w.cmid);
  const url = typeof w.url === "string" ? w.url : null;
  const grade = w.grade;
  const tag = isTask || url ? `button data-act="work" data-k="${k}"` : "div";
  return `<${tag} class="irow st-work">${icon(st[0], st[1], `font-size:20px;color:${color}`)}
    <div class="grow bd b6" style="--sz:14px">${esc(w.name)}</div>
    <div class="bd" style="--sz:13px;margin-left:calc(var(--s) - var(--m));color:${grade != null ? "var(--text)" : "var(--muted)"}">${esc(grade != null ? `${grade}/${w.max}` : st[2])}</div>
    ${isTask ? `<span class="mi" style="font-size:20px;color:var(--muted);margin-left:calc(var(--xs) - var(--m))">chevron_right</span>` : ""}
  </${tag.split(" ")[0]}>`;
}

/** «Назад» экрана предмета: IconButton 40 с отступом s, стрелка 20. */
function stBack() {
  return `<div class="st-back"><button data-act="back" aria-label="Назад">${icon("arrow_back_ios_new", "", "font-size:20px")}</button></div>`;
}

function openCourse(raw) {
  const course = stCourse(raw);
  Nav.push((body, screen) => {
    let data = null, alive = true;
    const path = `/sdo/grades/${course.id}`;
    const draw = () => {
      const c = data, color = ink(c.title);
      const lectures = c.attendance && Array.isArray(c.attendance.lectures) ? c.attendance.lectures : [];
      body.innerHTML = stBack() + screenTitle(c.title, { sub: c.marks.length > 1 ? "экзамен" : "зачёт" }) + `
        <div class="hx"><div class="tile st-card row" style="gap:var(--l)">
          ${stRing(c.score / c.top, color, `<div style="text-align:center"><div class="num" style="--sz:40px">${esc(c.score)}</div>
            <div class="bd mut" style="--sz:12px">из ${esc(c.top)}</div></div>`, 120, 10)}
          <div class="grow"><div class="bd mut" style="--sz:13px">Отметки</div>
            <div class="st-marks">${c.marks.map((m) => {
              const got = c.score >= m.at;
              return `<span class="bd b6" style="--sz:13px;background:${got ? color : "var(--line)"};color:${got ? "#fff" : "var(--muted)"}">${esc(m.label)} · ${esc(m.at)}</span>`;
            }).join("")}</div>
            <div class="bd b7" style="--sz:16px;margin-top:var(--m)">${esc(c.need > 0 ? `ещё ${c.need} до «${c.needLabel}»` : c.enoughText)}</div>
          </div></div></div>
        ${c.goal ? `<div class="hx" style="margin-top:var(--m)"><div class="st-goal"></div></div>` : ""}
        ${lectures.length ? section("Посещения лекций") + `<div class="hx"><div class="tile">${stAttendance(c.attendance, color)}</div></div>` : ""}
        ${c.works.length ? section(`Текущий контроль · ${c.worksPassed} из ${c.worksTotal} зачтено`)
          + `<div class="hx"><div class="tile p0">${c.works.map((w, i) => (i ? '<div class="divider"></div>' : "") + stWorkRow(w, i)).join("")}</div></div>` : ""}
        ${c.categories.length ? section("Из чего баллы") + c.categories.map((cat) => {
          const max = Number(cat.max) || 0, v = max === 0 ? 0 : Math.max(0, Math.min(1, cat.score / max));
          return `<div style="padding:0 var(--xl) var(--m)"><div class="row" style="gap:0"><div class="grow bd" style="--sz:14px">${esc(cat.name)}</div>
            <div class="bd b6" style="--sz:14px">${esc(cat.score)} / ${esc(cat.max)}</div></div>
            <div class="progress" style="margin-top:5px;--c:${color}"><i style="width:${v * 100}%"></i></div></div>`;
        }).join("") : ""}
        ${c.history ? section("Как растут баллы") + `<div class="hx"><div class="tile st-hist"></div></div>` : ""}
        <div style="height:var(--xxl)"></div>`;
      if (c.goal) stGoalCard(body.querySelector(".st-goal"), c.id, c.goal, color);
      if (c.history) stHistory(body.querySelector(".st-hist"), c.history, color);
    };
    const refresh = async () => {
      try {
        const j = await Api.get(path);
        if (!alive) return;
        data = stCourse(j);
        draw();
      } catch (e) {
        if (!alive || (e instanceof ApiError && e.status === 401)) return;
        if (!data) body.innerHTML = stBack() + '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "retry" });
      }
    };
    on(body, {
      retry: () => { body.innerHTML = stBack() + spinner(); refresh(); },
      work: (b) => {
        const w = data && data.works[+b.dataset.k];
        if (!w) return;
        tick();
        if ((w.module === "assign" || w.module === "quiz") && Number.isInteger(w.cmid)) {
          if (window.openTask) openTask(w, data.title); else toast("Скоро");
        } else if (typeof w.url === "string") openLink(w.url);
      },
    });
    const cached = Api.cached(path);
    if (cached !== undefined) { data = stCourse(cached); draw(); }
    else body.innerHTML = stBack() + spinner();
    refresh();
    return () => { alive = false; };
  }, { tint: subjectColor(course.title) });
}
window.openCourse = openCourse;

// ── Цель (GoalCard) ──
/** Главная строка «Цели» называет то, что мешает (goalHeadline). */
function stGoalHeadline(g) {
  const label = markWord(String(g.label));
  const works = Math.trunc((g.tk && g.tk.left) || 0);
  const need = g.need || 0, mode = g.mode;
  if (mode === "auto" || mode === "exam") {
    if (g.status === "done") return mode === "auto" ? `${label} выходит автоматом` : "Баллов хватает";
    if (need > 0) return `Не хватает ${stPoints(need)}`;
    if (works > 0) return `Нужно зачесть ещё ${stWorks(works)}`;
    return mode === "exam" ? "Хватит любого балла на экзамене" : "Баллов хватает";
  }
  const pending = g.exam_pending === true;
  if (pending && g.auto_ok !== true) {
    const short = g.exam_short || 0;
    if (short > 0) return `Не хватает ${stPoints(short)}`;
    const exam = g.need_exam || 0;
    const onExam = exam > 0 ? `на ${label} нужно ${stPoints(exam)} на экзамене` : `на ${label} хватит любого балла на экзамене`;
    return g.auto != null ? `${markWord(String(g.auto))} автоматом, ${onExam}` : onExam[0].toUpperCase() + onExam.slice(1);
  }
  if (g.status === "done") return pending ? `${label} выходит автоматом` : "Баллов хватает";
  if (need > 0) return `Не хватает ${stPoints(need)}`;
  if (works > 0) return `Нужно зачесть ещё ${stWorks(works)}`;
  return "Баллов хватает";
}
/** Строка под главной: сколько нужно и второй путь (goalSubline). */
function stGoalSubline(g) {
  const works = Math.trunc((g.tk && g.tk.left) || 0);
  const need = g.need || 0, mode = g.mode;
  const what = g.label === "зачёт" ? "зачёта" : markWord(String(g.label));
  const at = stPoints(g.at || 0);
  if (mode === "auto") return [`для ${what} автоматом нужно ${at} за семестр`, works > 0 ? `и зачесть ещё ${stWorks(works)}` : ""].filter(Boolean).join(" ");
  if (mode === "exam") {
    const exam = g.need_exam || 0, short = g.exam_short || 0;
    return [`для ${what} нужно ${at} вместе с экзаменом`,
      short > 0 ? `с полным экзаменом добрать ещё ${stNum(short)} работами и лекциями` : need > 0 && exam > 0 ? `хватит ${stPoints(exam)} на экзамене` : ""]
      .filter(Boolean).join(" · ");
  }
  const pending = g.exam_pending === true, autoOk = g.auto_ok === true;
  const parts = [`для ${what} нужно ${at}`];
  if (pending && autoOk && need > 0 && (g.need_exam || 0) > 0) parts.push(`или ${stPoints(g.need_exam)} на экзамене`);
  if (need > 0 && works > 0 && (autoOk || !pending)) parts.push(`и зачесть ещё ${stWorks(works)}`);
  if (pending && !autoOk && g.auto == null && g.auto_best != null) parts.push(`${markWord(String(g.auto_best))} можно получить автоматом`);
  return parts.join(" · ");
}
/** Какие работы нельзя пропустить (mustLine). */
function stMustLine(g) {
  const must = (g.must || []).map(String);
  if (!must.length) return null;
  const open = Math.trunc(g.open_count || 0);
  if (must.length > 1 && must.length >= open) return "сдать нужно все открытые работы: без любой не дойдёшь";
  if (must.length > 3) return `без ${must.length} открытых работ не дойдёшь — сдавай все`;
  return `без «${must.join("», «")}» не дойдёшь`;
}

/**
 * Заливка «Цели» (LinearGradient topRight → bottomLeft): Flutter смешивает цвета
 * без учёта прозрачности, поэтому середина заметно ярче, чем у CSS, — повторяем
 * его промежуточными точками. Угол — по диагонали карточки (stAngle).
 */
function stGoalGradient(tone) {
  const dark = Theme.dark, a0 = dark ? 0.28 : 0.16, a1 = dark ? 0.6 : 1;
  const stops = [0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => {
    const a = a0 + (a1 - a0) * t;
    return `color-mix(in srgb, color-mix(in srgb, ${tone}, var(--card-solid) ${t * 100}%) ${(a * 100).toFixed(1)}%, transparent) ${t * 100}%`;
  });
  return `linear-gradient(var(--st-ang, 225deg), ${stops.join(", ")})`;
}
/** Угол заливки — от правого верхнего угла к левому нижнему, как Alignment в Flutter. */
function stAngle(el) {
  requestAnimationFrame(() => {
    const w = el.offsetWidth, h = el.offsetHeight;
    if (w && h) el.style.setProperty("--st-ang", `${180 + Math.atan2(w, h) * 180 / Math.PI}deg`);
  });
}

/** Карточка «Цель» в el: выбор отметки и счёта — POST /sdo/goal/<курс>. */
function stGoalCard(el, courseId, goal, color) {
  let g = goal, error = null, shownCapy = null;
  const draw = () => {
    const status = String(g.status || "ok");
    const [tone, verdict] = status === "done" && g.exam_pending === true ? ["var(--ok)", "автомат"]
      : status === "done" ? ["var(--ok)", `${markWord(String(g.label))} есть`]
      : status === "tight" ? ["var(--warn)", "впритык"]
      : status === "no" ? ["var(--danger)", "не хватит"] : ["var(--ok)", "дойдёшь"];
    const need = g.need || 0, tk = g.tk || {};
    const headline = stGoalHeadline(g);
    const marks = (g.marks || []).map(String);
    const lines = [];
    if ((g.open_count || 0) > 0) lines.push(["upload", "", `работы: открыто ${g.open_count} · до +${stNum(g.open_points || 0)}`]);
    if ((g.attendance_left || 0) > 0) lines.push(["groups", "o", `посещения лекций: до +${stNum(g.attendance_left)}`]);
    if ((g.exam_left || 0) > 0) lines.push(["workspace_premium", "o", `экзамен: до +${stNum(g.exam_left)}`]);
    if ((tk.total || 0) > 0) lines.push(["task_alt", "", `зачтено ${tk.passed} из ${tk.total} · нужно ${tk.need}${(tk.left || 0) > 0 ? ` → из ${tk.open} открытых зачесть ${tk.left}` : ""}`]);
    const must = stMustLine(g);
    if (must) lines.push(["priority_high", "", must]);
    if (need > 0 && status !== "done") lines.push(["auto_awesome", "o", `если сдать всё, ходить на лекции${(g.exam_left || 0) > 0 ? " и сдать экзамен" : ""} — до ${stNum(g.best || 0)}`]);
    if ((g.lost_count || 0) > 0) lines.push(["warning_amber", "", `ниже порога или срок прошёл: ${g.lost_count} — не считаю, пригодится, если дадут пересдать`]);
    if (g.skip && typeof g.skip === "object") {
      const sk = g.skip;
      const after = sk.status === status ? "ничего не изменится"
        : { done: "всё равно есть", tight: "станет впритык", no: "уже не хватит" }[sk.status] || "дойдёшь";
      lines.push(["schedule", "", `пропущу лекцию ${stDayMonth(sk.date)}: −${stNum(sk.value || 0)} → ${after}`]);
    }
    // набрал — капибара прыгает, не хватит — грустит; анимация — только когда появилась
    const pose = status === "done" ? "joy" : status === "no" ? "sad" : null;
    const anim = pose !== shownCapy ? (pose === "joy" ? " st-hop" : " st-sigh") : "";
    shownCapy = pose;
    const mode = g.mode === "auto" || g.mode === "exam" ? g.mode : null;
    el.innerHTML = `<div class="tile st-card" style="background:${stGoalGradient(tone)}">
      <div class="row" style="gap:0"><div class="ttl" style="--sz:20px">Цель</div><div class="grow"></div>
        ${pose ? `<span class="st-gcapy${pose === "sad" ? " sad" : ""}${anim}" data-act="hop" style="color:${pose === "joy" ? "var(--ok)" : "var(--muted)"}">${capy(pose, 46)}</span>` : ""}
        <span class="bd b7 st-verdict" style="--sz:13px;color:${tone};background:color-mix(in srgb, ${tone} 18%, transparent)">${esc(verdict)}</span></div>
      <div style="height:var(--m)"></div>
      ${mode ? `<div class="st-mode"><button class="${mode === "auto" ? "on" : ""}" data-act="mode" data-v="auto" aria-label="Считать автомат">автомат</button>
        <button class="${mode === "exam" ? "on" : ""}" data-act="mode" data-v="exam" aria-label="Считать с экзаменом">с экзаменом</button></div><div style="height:var(--s)"></div>` : ""}
      <div class="st-seg">${marks.map((m) => `<button class="${m === g.label ? "on" : ""}" data-act="mark" data-v="${esc(m)}" aria-label="Цель ${esc(m)}"
        style="${m === g.label ? `background:${color}` : ""}">${esc(m)}</button>`).join("")}</div>
      <div class="ttl" style="--sz:${headline.length > 28 ? 21 : 26}px;margin-top:var(--l);color:${status === "done" ? "var(--ok)" : "var(--text)"}">${esc(headline)}</div>
      <div class="bd mut" style="--sz:13px;margin-top:4px">${esc(stGoalSubline(g))}</div>
      <div style="height:var(--m)"></div>
      ${lines.map(([ic, v, t]) => `<div class="row" style="align-items:flex-start;gap:var(--s);padding-top:6px">${icon(ic, v, "font-size:16px;color:var(--muted);margin-top:1px")}
        <div class="grow bd" style="--sz:14px">${esc(t)}</div></div>`).join("")}
      ${status === "no" ? `<div class="bd" style="--sz:13px;color:var(--danger);margin-top:var(--m)">${esc(tk.reachable === false
        ? "Открытых работ меньше, чем нужно зачесть: без пересдачи экзамена по БРС не будет."
        : `Даже если сдать всё и ходить на все лекции, будет ${stNum(g.best || 0)} — меньше ${stNum(g.at || 0)}. Можно выбрать цель ниже.`)}</div>` : ""}
      ${error ? `<div class="bd" style="--sz:13px;color:var(--danger);margin-top:var(--s)">${esc(error)}</div>` : ""}
    </div>`;
    stAngle(el.firstElementChild);
  };
  const post = async (body) => {
    tick();
    try {
      const r = await Api.post(`/sdo/goal/${courseId}`, body);
      // экран предмета мог перерисоваться — выбор пишем и в сам ответ предмета
      for (const k of Object.keys(goal)) delete goal[k];
      Object.assign(goal, r);
      g = Object.assign({}, r);
      error = null;
    } catch (e) { error = errorText(e); }
    draw();
  };
  on(el, {
    mark: (b) => { if (b.dataset.v !== String(g.label)) post({ label: b.dataset.v }); },
    mode: (b) => { if (b.dataset.v !== g.mode) post({ mode: b.dataset.v }); },
    hop: (b) => {
      if (!b.classList.contains("st-gcapy") || shownCapy !== "joy") return;
      tick();
      b.classList.remove("st-hop");
      void b.offsetWidth;
      b.classList.add("st-hop");
    },
  });
  draw();
}

// ── Посещения лекций (AttendanceStrip) ──
function stAttendance(att, color) {
  const lectures = att.lectures || [];
  const total = att.total ?? lectures.length;
  const box = (l) => {
    const bg = { ok: color, excused: `color-mix(in srgb, ${color} 50%, transparent)`, miss: "transparent" }[l.status] || "var(--line)";
    const border = { miss: "var(--danger)", wait: color }[l.status] || "transparent";
    return `<i class="st-lec" title="${esc(`${l.n} лекция · ${stDayMonth(l.date)}`)}" style="background:${bg};border-color:${border}"></i>`;
  };
  return `<div class="st-lecs">${lectures.map(box).join("")}</div>
    <div class="bd mut" style="--sz:13px;margin-top:var(--s)">был на ${att.attended ?? 0} из ${att.past ?? 0} прошедших · всего ${total}${
      (att.waiting || 0) > 0 ? ` · ждём балл за ${att.waiting}` : ""}</div>`;
}

// ── Как росли баллы (HistoryChart) ──
function stHistory(el, history, color) {
  const pts = (history.points || []).map((x) => [Date.parse(String(x[0])), Number(x[1])]).filter((p) => !isNaN(p[0]));
  const delta = history.week_delta;
  el.innerHTML = `${delta != null ? `<div class="bd b7" style="--sz:14px;color:${delta > 0 ? "var(--ok)" : "var(--muted)"}">${delta > 0 ? "+" : ""}${stNum(delta)} за неделю</div>` : ""}
    <div style="height:var(--s)"></div>
    ${pts.length < 2 ? `<div class="bd mut" style="--sz:13px">График появится, когда наберётся история: бот запоминает сумму раз в день, когда ты смотришь баллы.</div>`
      : '<div class="st-line"></div>'}`;
  if (pts.length < 2) return;
  const box = el.querySelector(".st-line");
  const paint = () => {
    const w = box.clientWidth || 300, h = 90;
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    const lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
    const span = hi - lo === 0 ? 1 : hi - lo;
    const at = (p) => [t1 === t0 ? w : (p[0] - t0) / (t1 - t0) * w, h - 6 - (p[1] - lo) / span * (h - 12)];
    const xy = pts.map(at);
    const line = xy.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    const fill = `${line}L${xy[xy.length - 1][0].toFixed(1)},${h}L${xy[0][0].toFixed(1)},${h}Z`;
    const last = xy[xy.length - 1], id = "stg" + Math.random().toString(36).slice(2, 8);
    box.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".3"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient>
        <clipPath id="${id}c"><rect class="st-reveal" x="0" y="0" width="${w}" height="${h}"/></clipPath></defs>
      <line x1="0" y1="${h - 0.5}" x2="${w}" y2="${h - 0.5}" stroke="var(--line)" stroke-width="1"/>
      <g clip-path="url(#${id}c)"><path d="${fill}" fill="url(#${id})"/>
        <path d="${line}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/></g>
      <circle class="st-dot" cx="${last[0]}" cy="${last[1]}" r="4.5" fill="${color}"/></svg>`;
  };
  requestAnimationFrame(paint);
}

// ── График по неделям (TrendChart) — для рейтинга ──
/** Шкала: нижняя и верхняя граница и подписи оси (trendScale). */
function stTrendScale(values, invert) {
  const known = values.filter((v) => typeof v === "number");
  if (!known.length) return { lo: 0, hi: 1, ticks: [] };
  let hi = Math.max(...known);
  const lo = invert ? 1 : 0;
  if (hi - lo < 1) hi = lo + 1;
  const top = Math.round(hi);
  let ticks;
  if (invert && top <= 6) { ticks = []; for (let v = 1; v <= top; v++) ticks.push(v); }
  else ticks = [...new Set([Math.round(lo), Math.round((lo + hi) / 2), top])];
  return { lo, hi, ticks };
}
/**
 * Лёгкий график по неделям в el: values — числа или null (рвёт линию), labels —
 * «12.10», invert — меньше лучше (место), format(v) — подпись значения.
 * Палец на графике — черта и «неделя · значение» сверху.
 */
window.trendChart = function trendChart(el, { values, labels, invert = false, format = (v) => String(v), height = 132 }) {
  const n = values.length;
  const lastIndex = () => { for (let i = n - 1; i >= 0; i--) if (values[i] != null) return i; return null; };
  const scale = stTrendScale(values, invert);
  const gutter = scale.ticks.length ? Math.max(...scale.ticks.map((t) => String(t).length)) * 6.4 + 8 : 0;
  let hover = null;
  const delta = (i) => {
    if (invert || i === 0) return "";
    const a = values[i], b = values[i - 1];
    if (a == null || b == null || a === b) return "";
    const d = Math.trunc(a - b);
    return ` · ${d > 0 ? "+" : "−"}${Math.abs(d)} за неделю`;
  };
  el.innerHTML = `<div class="st-tr-top"></div><div class="st-tr" style="height:${height}px;margin-top:var(--s)"></div>
    ${n > 1 ? `<div class="row bd mut" style="--sz:11.5px;gap:0;margin-top:6px;padding-left:${gutter}px"><span>${esc(labels[0])}</span><span class="grow"></span><span>сейчас</span></div>` : ""}`;
  const top = el.querySelector(".st-tr-top"), box = el.querySelector(".st-tr");
  const paint = () => {
    const shown = hover ?? lastIndex();
    top.innerHTML = shown == null ? "" : `<span class="bd b7" style="--sz:14px">${esc(format(values[shown]))}</span><span class="bd mut" style="--sz:12.5px">  ${
      esc(shown === n - 1 ? "сейчас" : `неделя с ${labels[shown]}`)}${esc(delta(shown))}</span>`;
    const w = box.clientWidth || 300, h = height, pad = 6, plot = w - gutter;
    const x = (i) => gutter + (n === 1 ? plot / 2 : i * plot / (n - 1));
    const y = (v) => { const t = (v - scale.lo) / (scale.hi - scale.lo), hh = h - pad * 2; return invert ? pad + t * hh : h - pad - t * hh; };
    let svg = "";
    for (const v of scale.ticks) {
      svg += `<line x1="${gutter}" y1="${y(v)}" x2="${w}" y2="${y(v)}" stroke="var(--line)" stroke-width="1"/>
        <text x="${gutter - 8}" y="${y(v)}" text-anchor="end" dominant-baseline="central" fill="var(--muted)" font-size="11" font-family="Onest">${v}</text>`;
    }
    const id = "sttr" + Math.random().toString(36).slice(2, 8);
    if (n && values.some((v) => v != null)) {
      const runs = [];
      for (let i = 0; i < n; i++) {
        if (values[i] == null) continue;
        if (!runs.length || runs[runs.length - 1][runs[runs.length - 1].length - 1] !== i - 1) runs.push([i]);
        else runs[runs.length - 1].push(i);
      }
      for (const run of runs) {
        const d = run.map((i, k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(values[i]).toFixed(1)}`).join("");
        if (!invert && run.length > 1) svg += `<path d="${d}L${x(run[run.length - 1])},${h}L${x(run[0])},${h}Z" fill="url(#${id})"/>`;
        svg += `<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
      }
      const dot = (i, r) => `<circle cx="${x(i)}" cy="${y(values[i])}" r="${r + 2}" fill="var(--card-solid)"/><circle cx="${x(i)}" cy="${y(values[i])}" r="${r}" fill="var(--accent)"/>`;
      if (invert) for (let i = 0; i < n; i++) if (values[i] != null) svg += dot(i, 3);
      if (hover != null) {
        svg += `<line x1="${x(hover)}" y1="0" x2="${x(hover)}" y2="${h}" stroke="var(--line)" stroke-width="1.5"/>`;
        if (values[hover] != null) svg += dot(hover, 5);
      } else { const l = lastIndex(); if (l != null) svg += dot(l, 5); }
    }
    box.innerHTML = `<svg width="${w}" height="${h}" style="overflow:visible"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".28"/><stop offset="1" stop-color="var(--accent)" stop-opacity=".02"/></linearGradient></defs>${svg}</svg>`;
  };
  const touch = (e) => {
    if (!n) return;
    const r = box.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - r.left - gutter) / (r.width - gutter) * (n - 1))));
    if (i !== hover) { hover = i; paint(); }
  };
  const leave = () => { if (hover != null) { hover = null; paint(); } };
  box.style.touchAction = "pan-y";
  box.addEventListener("pointerdown", (e) => { box.setPointerCapture && box.setPointerCapture(e.pointerId); touch(e); });
  box.addEventListener("pointermove", (e) => { if (e.buttons || e.pointerType === "touch") touch(e); });
  box.addEventListener("pointerup", leave);
  box.addEventListener("pointercancel", leave);
  box.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") leave(); });
  requestAnimationFrame(paint);
};
/** Из чего сложился опыт (PartsBars): строки «название — полоса — число». parts — [[название, число]]. */
window.partsBars = function partsBars(parts) {
  const top = parts.reduce((m, p) => (p[1] > m ? p[1] : m), 0), sum = parts.reduce((m, p) => m + p[1], 0);
  return parts.map(([title, v]) => `<div style="padding:6px 0"><div class="row" style="gap:0"><div class="grow bd" style="--sz:14px">${esc(title)}</div>
    ${sum > 0 && v > 0 ? `<span class="bd mut" style="--sz:12.5px;white-space:pre">${Math.round(v * 100 / sum)}%  </span>` : ""}
    <span class="num" style="--sz:15px">${Math.trunc(v)}</span></div>
    <div class="progress" style="height:6px;margin-top:6px"><i style="width:${top > 0 ? Math.max(0, Math.min(1, v / top)) * 100 : 0}%"></i></div></div>`).join("");
};
