// Поиск расписания любой группы, преподавателя или аудитории МИРЭА
// (app/lib/screens/search.dart, compare.dart): справочник на сервере, у
// однофамильцев — выбор листом. Закреплённые — на сервере, недавние — на этом
// устройстве. Нажал — расписание на 8 недель, недели листаются без запросов;
// у группы — «Сравнить» со своей неделей.
"use strict";

const TARGET_KINDS = { 1: ["Группа", "groups", "o"], 2: ["Преподаватель", "person", "o"], 3: ["Аудитория", "meeting_room", "o"] };
// с приставкой запаса ответов API: «выйти» стирает их вместе с ним
const RECENT_KEY = "uib_cache:recent_targets";

function targetOf(j) { return { type: +j.type, id: +j.id, title: String(j.title || ""), hint: String(j.hint || "") }; }
const sameTarget = (a, b) => a.type === b.type && a.id === b.id;
function recentTargets() {
  try { return (JSON.parse(localStorage.getItem(RECENT_KEY) || "[]") || []).map(targetOf); } catch (e) { return []; }
}
function rememberTarget(t) {
  try {
    const list = [t, ...recentTargets().filter((x) => !sameTarget(x, t))].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.map((x) => ({ type: x.type, id: x.id, title: x.title }))));
  } catch (e) {}
}

/** Строка найденного (_TargetRow). */
function targetRow(t, k, pinned = false) {
  const [kind, ic, v] = TARGET_KINDS[t.type] || ["", "calendar_today", "o"];
  return `<div class="hx" style="margin-bottom:var(--s)"><button class="tile row" data-act="open" data-k="${k}" style="padding:var(--m) var(--l)">
    ${icon(ic, v, "color:var(--accent)")}
    <div class="grow"><div class="bd b6" style="--sz:16px">${esc(t.title)}</div>
      <div class="bd mut" style="--sz:13px">${esc([kind, t.hint].filter(Boolean).join(" · "))}</div></div>
    ${pinned ? icon("push_pin", "", "font-size:16px;color:var(--muted)") : ""}
    ${icon("chevron_right", "", "color:var(--muted)")}</button></div>`;
}

window.openSearch = function openSearch() {
  Nav.push((body, screen) => {
    let type = 0, items = null, ready = true, busy = false, failed = "", seq = 0, timer = 0;
    let pins = [], recents = recentTargets(), shown = [];
    body.innerHTML = `${backRow()}${screenTitle("Поиск")}
      <div class="hx"><label class="sr-field">${icon("search", "", "color:var(--muted)")}
        <input type="search" enterkeyhint="search" autocomplete="off" placeholder="Фамилия, группа или аудитория">
        <button data-act="clear" aria-label="Очистить" hidden>${icon("close", "", "color:var(--muted)")}</button></label></div>
      <div class="sr-chips"></div><div style="height:var(--s)"></div><div class="sr-out"></div><div class="pad-bottom"></div>`;
    const q = body.querySelector("input"), out = body.querySelector(".sr-out"), chips = body.querySelector(".sr-chips");
    const clear = body.querySelector('[data-act="clear"]');
    setTimeout(() => q.focus(), 350); // сразу с курсором в поле (2.6)

    const drawChips = () => {
      chips.innerHTML = [[0, "Все"], [1, "Группы"], [2, "Преподаватели"], [3, "Аудитории"]]
        .map(([t, label]) => `<button class="sr-chip${t === type ? " on" : ""}" data-act="type" data-t="${t}" aria-pressed="${t === type}">${label}</button>`).join("");
    };
    const draw = () => {
      clear.hidden = !q.value;
      if (q.value.trim().length >= 2) {
        if (failed) { out.innerHTML = notice("Не получилось", failed, { pose: "sad", retry: "retry" }); return; }
        if (busy || !items) { out.innerHTML = smallSpinner(); return; }
        if (!items.length) {
          out.innerHTML = ready ? notice("Ничего не нашлось", "Проверь, как написано, или попробуй часть фамилии.", { pose: "sad" })
                                : notice("Справочник ещё собирается", "Первый запуск занимает около получаса — попробуй чуть позже.");
          return;
        }
        shown = items;
        out.innerHTML = items.map((t, i) => targetRow(t, i, pins.some((p) => sameTarget(p, t)))).join("");
        return;
      }
      const rec = recents.filter((t) => !pins.some((p) => sameTarget(p, t)));
      if (!pins.length && !rec.length) {
        out.innerHTML = notice("Чьё расписание ищем?", "Начни вводить фамилию преподавателя, номер группы или аудитории — например «Морозов» или «УИБО-03». Нужное можно закрепить.");
        return;
      }
      shown = [...pins, ...rec];
      out.innerHTML = (pins.length ? section("Закреплённые") + pins.map((t, i) => targetRow(t, i, true)).join("") : "")
        + (rec.length ? section("Недавние") + rec.map((t, i) => targetRow(t, pins.length + i)).join("") : "");
    };
    const search = async () => {
      clearTimeout(timer);
      const my = ++seq, text = q.value.trim(); // ответ на старый запрос не перетирает новый
      if (text.length < 2) { items = null; busy = false; failed = ""; draw(); return; }
      busy = true; failed = ""; draw();
      try {
        const r = await Api.get(`/search?q=${encodeURIComponent(text)}&type=${type}`);
        if (my !== seq) return;
        items = (r.items || []).map(targetOf); ready = r.ready !== false; busy = false;
      } catch (e) {
        if (my !== seq) return;
        busy = false; failed = errorText(e);
      }
      draw();
    };
    const loadSaved = async () => {
      try { pins = ((await Api.get("/pins")).items || []).map(targetOf); } catch (e) {}
      recents = recentTargets();
      draw();
    };
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 250); clear.hidden = !q.value; });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter") { q.blur(); search(); } });
    screen.scroller.addEventListener("touchmove", () => { if (document.activeElement === q) q.blur(); }, { passive: true });
    on(body, {
      clear: () => { q.value = ""; search(); q.focus(); },
      type: (b) => { tick(); type = +b.dataset.t; drawChips(); search(); },
      retry: search,
      open: (b) => { const t = shown[+b.dataset.k]; if (t) openTargetScreen(t); },
    });
    screen.onShow = loadSaved; // там могли закрепить или открепить
    drawChips();
    draw();
    loadSaved();
  });
};

/** Найти в справочнике МИРЭА и открыть (lesson.dart: openTarget). type: 1 — группа, 2 — преподаватель, 3 — аудитория. */
window.openTarget = async function openTarget(query, type) {
  let items;
  try {
    items = (await Api.get(`/search?q=${encodeURIComponent(query)}&type=${type}`)).items || [];
  } catch (e) { toast("Расписание МИРЭА сейчас не отвечает", "error"); return; }
  if (!items.length) { toast(`«${query}» в расписании МИРЭА не нашёл`); return; }
  let pick = items[0];
  if (items.length > 1) {
    // однофамильцы: «Морозов В. А.» бывает трижды — подсказка у каждого
    const list = items.slice(0, 8);
    pick = await Sheet.show(list.map((it, i) => `<button class="sr-pick" data-act="pick" data-k="${i}">
      <div class="bd b6" style="--sz:15px">${esc(it.title)}</div>${it.hint ? `<div class="bd mut" style="--sz:13px">${esc(it.hint)}</div>` : ""}</button>`).join(""),
    (b, close) => on(b, { pick: (el) => close(list[+el.dataset.k]) }));
    if (!pick) return;
  }
  openTargetScreen(targetOf(pick));
};

function openTargetScreen(t) {
  tick();
  rememberTarget(t);
  Nav.push((body, screen) => targetScreen(body, screen, t));
}

/** «Эта неделя», «Следующая неделя» или «13–18 октября» (_weekLabel). */
function targetWeekLabel(week, today) {
  const monday = week.monday || (week.days[0] || {}).date;
  const offset = Math.round((new Date(monday + "T12:00:00+03:00") - new Date(mondayOf(new Date(today + "T12:00:00+03:00")) + "T12:00:00+03:00")) / (7 * 864e5));
  if (offset === 0) return "Эта неделя";
  if (offset === 1) return "Следующая неделя";
  if (offset === -1) return "Прошлая неделя";
  const a = msk(new Date(monday + "T12:00:00+03:00")), b = msk(new Date(addDays(monday, 5) + "T12:00:00+03:00"));
  return a.m === b.m ? `${a.d}–${b.d} ${MONTHS[b.m - 1]}` : `${a.d} ${MONTHS[a.m - 1]} – ${b.d} ${MONTHS[b.m - 1]}`;
}
/** Неделя назад/вперёд с подписью (WeekSwitch). */
function weekSwitch(label, number, prev, next) {
  const arrow = (act, ic, ok, tip) => `<button class="sr-arrow" data-act="${act}" aria-label="${tip}"${ok ? "" : " disabled"}>${icon(ic, "", `color:var(--${ok ? "text" : "line"})`)}</button>`;
  return `<div class="hx"><div class="tile row" style="padding:var(--xs);gap:0">
    ${arrow("prev", "chevron_left", prev, "Неделя раньше")}
    <div class="grow" style="text-align:center"><div class="bd b7" style="--sz:16px">${esc(label)}</div>
      ${number != null ? `<div class="bd mut" style="--sz:13px">${number} неделя</div>` : ""}</div>
    ${arrow("next", "chevron_right", next, "Неделя позже")}</div></div>`;
}
/** Дни подряд: пустые подряд — одной строкой «Пн–Ср — пар нет» (emptyRuns). */
function emptyRuns(days, today) {
  const out = [];
  days.forEach((d, i) => {
    const none = !(d.lessons || []).length;
    if (i >= 6 && none) return;
    const alone = !none || d.date === today, last = out[out.length - 1];
    if (!alone && last && last.empty && addDays(last.to, 1) === d.date) last.to = d.date;
    else out.push({ empty: !alone, index: i, from: d.date, to: d.date });
  });
  return out;
}
function emptyDaysText(from, to) {
  const a = WD_SHORT[msk(new Date(from + "T12:00:00+03:00")).wd], b = WD_SHORT[msk(new Date(to + "T12:00:00+03:00")).wd];
  return `${from === to ? a : `${a}–${b}`} — пар нет`;
}

function targetScreen(body, screen, t) {
  let data = null, failed = false, pinned = false, pinBusy = false, week = 0, lessons = [];
  const weeks = () => (data && data.weeks) || [];
  const today = () => (data && data.today) || isoDay(now());
  const title = () => {
    const x = String((data && data.title) || "");
    return !x || x === String(t.id) ? (t.title || x) : x;
  };
  const firstWeek = () => {
    const w = weeks();
    for (let i = 0; i < w.length; i++) for (const d of w[i].days) if (d.date >= today() && (d.lessons || []).length) return i;
    return 0;
  };
  const head = () => {
    const ws = weeks();
    return `<div class="row" style="gap:0"><div class="grow">${backRow()}</div>
      ${data && t.type === 1 && ws.length ? `<button class="sr-compare" data-act="compare">${icon("compare_arrows", "", "font-size:20px")}<span>Сравнить</span></button>` : ""}
      ${data ? `<button class="sr-pin" data-act="pin" aria-label="${pinned ? "Открепить" : "Закрепить"}"${pinBusy ? " disabled" : ""}>${icon("push_pin", pinned ? "" : "o", `color:var(--${pinned ? "accent" : "muted"})`)}</button>` : ""}</div>`;
  };
  const draw = () => {
    if (failed) {
      body.innerHTML = head() + '<div style="height:var(--xxl)"></div>' + notice("Сайт МИРЭА сейчас не отвечает", "Расписание появится, как только он оживёт. Обычно это минуты.", { pose: "sad", retry: "retry" });
      return;
    }
    if (!data) { body.innerHTML = head() + spinner(); return; }
    const ws = weeks(), w = ws[week], at = now();
    lessons = [];
    let html = head() + screenTitle(title());
    if (data.stale) html += `<div class="row" style="gap:var(--s);padding:0 var(--xl) var(--s)">${icon("warning_amber", "", "font-size:16px;color:var(--warn)")}
      <span class="bd" style="--sz:13px;color:var(--warn)">МИРЭА не отвечает · данные от ${esc(data.stale)}</span></div>`;
    if (!w) html += notice("Пар нет", "В расписании пусто.");
    else {
      html += weekSwitch(targetWeekLabel(w, today()), Number.isInteger(w.week) ? w.week : null, week > 0, week < ws.length - 1);
      for (const run of emptyRuns(w.days, today())) {
        if (run.empty) {
          html += `<div class="hx" style="margin-top:var(--l)"><div class="tile" style="padding:var(--m) var(--l)"><span class="bd mut" style="--sz:15px">${emptyDaysText(run.from, run.to)}</span></div></div>`;
          continue;
        }
        const ls = (w.days[run.index].lessons || []).map(lessonOf), isToday = run.from === today();
        html += `<div class="hx" style="margin-top:var(--l)"><div class="eyebrow" style="padding:0 0 var(--s) var(--s);color:var(--${isToday ? "text" : "muted"})">${esc(dayHead(run.from, isToday))}</div>
          ${ls.length ? lessonList(ls, at, { keyBase: lessons.length, showGroups: t.type !== 1 })
                      : '<div class="tile" style="padding:var(--m) var(--l)"><span class="bd mut" style="--sz:15px">Пар нет</span></div>'}</div>`;
        lessons.push(...ls);
      }
    }
    body.innerHTML = html + '<div class="pad-bottom"></div>';
  };
  const load = async () => {
    failed = false;
    try {
      data = await Api.get(`/target/${t.type}/${t.id}`);
      pinned = data.pinned === true;
      week = firstWeek();
    } catch (e) { failed = true; }
    draw();
  };
  const shift = (k) => {
    const next = Math.max(0, Math.min(weeks().length - 1, week + k));
    if (next === week) return;
    tick(); week = next; draw();
    screen.scroller.scrollTop = 0;
  };
  on(body, {
    retry: load,
    prev: () => shift(-1),
    next: () => shift(1),
    lesson: (b) => { const l = lessons[+b.dataset.k]; if (l) openLesson(l.raw, { own: false }); },
    compare: () => openCompare(title(), weeks(), week),
    pin: async () => {
      const was = pinned, path = `/pins/${t.type}/${t.id}`;
      pinBusy = true; draw();
      try {
        if (was) await Api.del(path); else await Api.put(path, { title: title() });
        tick();
        pinned = !was;
        toast(was ? "Откреплено" : "Закреплено — будет сверху в поиске", "done");
      } catch (e) {
        toast(e instanceof ApiError ? "Не получилось: " + e.message : errorText(e), "error");
      }
      pinBusy = false; draw();
    },
  });
  // свайп вбок — соседняя неделя
  let x0 = null, y0 = 0;
  body.addEventListener("touchstart", (e) => { const p = e.touches[0]; x0 = p.clientX > 30 ? p.clientX : null; y0 = p.clientY; }, { passive: true });
  body.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const p = e.changedTouches[0], dx = p.clientX - x0;
    if (Math.abs(dx) > 70 && Math.abs(dx) > 2 * Math.abs(p.clientY - y0)) shift(dx < 0 ? 1 : -1);
    x0 = null;
  });
  draw();
  load();
  pullRefresh(screen, load);
}

// ── «Сравнить неделю» (compare.dart) ──
const normText = (s) => String(s).toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
/** Пары двух групп одного дня — по времени начала, общие — одной строкой (compareDay). */
function compareDay(mine, theirs) {
  const starts = [...new Set([...mine, ...theirs].map((l) => l.start))].sort();
  return starts.map((s) => {
    const a = mine.find((l) => l.start === s), b = theirs.find((l) => l.start === s);
    const together = !!(a && b && normText(a.title) === normText(b.title) && normText(a.room) === normText(b.room));
    return { start: s, end: (a || b).end, mine: a, theirs: b, together };
  });
}
function bothFreeFrom(mine, theirs) {
  const ends = [...mine, ...theirs].map((l) => l.end).sort();
  return ends.length ? ends[ends.length - 1] : "";
}
function compareCell(l, together = false) {
  if (!l) return '<div class="cmp-cell free"><span class="bd mut" style="--sz:12px">свободно</span></div>';
  const c = ink(l.title), room = l.room.replace(/\s*\([^)]*\)/g, "").trim();
  return `<div class="cmp-cell" style="background:color-mix(in srgb, ${c} 14%, transparent)">
    <div class="bd b6 cmp-t" style="--sz:13px">${esc(l.title)}</div>
    <div class="bd cmp-s" style="--sz:12px;color:${together ? c : "var(--muted)"}">${esc([together ? "вместе" : "", l.kind, room].filter(Boolean).join(" · "))}</div></div>`;
}

/** Самое длинное слово влезает в строку — шрифт мельче, но не меньше 82 % (fitWordSize). */
const _measure = document.createElement("canvas").getContext("2d");
function fitWords(els) {
  for (const el of els) {
    const cs = getComputedStyle(el), base = parseFloat(cs.fontSize), width = el.clientWidth - 1;
    _measure.font = `${cs.fontWeight} ${base}px ${cs.fontFamily}`;
    const widest = Math.max(...el.textContent.split(/\s+/).map((w) => _measure.measureText(w).width));
    if (widest > width) el.style.setProperty("--sz", Math.max(base * 0.82, (base * width) / widest * 0.98) + "px");
  }
}

function openCompare(other, weeks, start) {
  Nav.push((body) => {
    let week = start, me = "Моя группа";
    const own = {}; // понедельник → Promise {дата: пары}
    const ownWeek = (w) => own[w.monday] || (own[w.monday] = Promise.all(w.days.map((d) => Api.get(`/day?date=${d.date}`)))
      .then((res) => Object.fromEntries(w.days.map((d, i) => [d.date, (res[i].lessons || []).map(lessonOf)])))
      .catch(() => { delete own[w.monday]; return {}; })); // «Ещё раз» спросит заново
    const draw = async () => {
      const w = weeks[week];
      const top = backRow() + screenTitle("Сравнить неделю") + weekSwitch(weekRange(w.monday), Number.isInteger(w.week) ? w.week : null, week > 0, week < weeks.length - 1)
        + `<div class="row cmp-head" style="gap:var(--s)"><div class="grow bd b7" style="--sz:13px;color:var(--accent)">${esc(me)}</div>
          <div class="grow bd b7" style="--sz:13px">${esc(other)}</div></div>`;
      body.innerHTML = top + '<div style="height:var(--xxl)"></div>' + spinner();
      const mine = await ownWeek(w);
      if (weeks[week] !== w) return;
      if (!Object.keys(mine).length) {
        body.innerHTML = top + notice("Не загрузилось", "Свою неделю не получилось загрузить", { pose: "sad", retry: "retry" });
        return;
      }
      let html = "";
      w.days.forEach((d, i) => {
        const a = mine[d.date] || [], b = (d.lessons || []).map(lessonOf);
        if (i >= 6 && !a.length && !b.length) return;
        const rows = compareDay(a, b), free = bothFreeFrom(a, b);
        const foot = !rows.length ? "Пар нет у обеих" : !a.length ? `У тебя пар нет · у ${other} до ${free}`
          : !b.length ? `У ${other} пар нет · у тебя до ${free}` : `Обе свободны с ${free}`;
        html += `<div class="hx" style="margin-top:var(--l)"><div class="eyebrow mut" style="padding:0 0 var(--s) var(--s)">${esc(dayTitle(d.date))}</div>
          <div class="tile" style="padding:var(--s)">${rows.map((r) => `<div class="cmp-row"><div class="bd b7" style="--sz:13px;width:44px;flex:none;padding-top:var(--s)">${esc(r.start)}</div>
            ${r.together ? compareCell(r.mine, true) : compareCell(r.mine) + compareCell(r.theirs)}</div>`).join("")}
            <div class="bd mut" style="--sz:13px;padding:var(--xs) var(--s)">${esc(foot)}</div></div></div>`;
      });
      body.innerHTML = top + html + '<div class="pad-bottom"></div>';
      fitWords(body.querySelectorAll(".cmp-t"));
    };
    const shift = (k) => {
      const next = Math.max(0, Math.min(weeks.length - 1, week + k));
      if (next === week) return;
      tick(); week = next; draw();
    };
    on(body, { prev: () => shift(-1), next: () => shift(1), retry: draw });
    Api.get("/me").then((j) => { const n = String((j.group || {}).name || ""); if (n) { me = n; draw(); } }).catch(() => {});
    draw();
  });
}
