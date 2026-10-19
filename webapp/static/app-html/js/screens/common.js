// Общее для экранов с парами: модель пары (api/models.dart: Lesson), карточка
// пары (LessonCard), список пар (LessonList), кабинет плашкой (RoomPill,
// RoomWas, RoomLine) — из app/lib/screens/today.dart.
"use strict";

/** Пара из ответа API (Lesson.fromJson). */
function lessonOf(j) {
  const d = (s) => (s ? new Date(s) : null);
  return {
    raw: j, start: j.start || "", end: j.end || "", title: j.title || "", kind: j.kind || "", room: j.room || "",
    teacher: j.teacher || "", status: j.status || "", groups: j.groups || "", number: j.num == null ? "" : String(j.num),
    pairs: typeof j.pairs === "number" ? j.pairs : 1, startAt: d(j.start_iso), endAt: d(j.end_iso),
    parts: (j.parts || []).filter((x) => Array.isArray(x) && x.length === 2).map((x) => [new Date(x[0]), new Date(x[1])]),
    roomWas: j.room_was || "", changedAt: j.room_changed_at || j.cancelled_at || "", cancelled: j.cancelled_at != null,
  };
}
/** Что идёт в t внутри пары или блока (Lesson.liveAt). */
function liveAt(l, t) {
  if (!l.startAt || !l.endAt || t < l.startAt || t >= l.endAt) return null;
  for (let i = 0; i < l.parts.length; i++) {
    const [a, b] = l.parts[i];
    if (t >= a && t < b) return { index: i + 1, of: l.parts.length, start: a, end: b, pause: false };
    if (i + 1 < l.parts.length && t >= b && t < l.parts[i + 1][0]) return { index: i + 2, of: l.parts.length, start: b, end: l.parts[i + 1][0], pause: true };
  }
  return { index: 1, of: 1, start: l.startAt, end: l.endAt, pause: false };
}
/** «25 мин», от часа — «2 ч 05 мин». */
function spanText(m) { return m >= 60 ? `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, "0")} мин` : `${m} мин`; }
/** Минут до момента, вверх: за 30 секунд до начала — «1 мин». */
function minutesTo(from, to) { const s = Math.floor((to - from) / 1000); return s <= 0 ? 0 : Math.floor((s + 59) / 60); }
/** «13 ч 02 мин», «73 мин», «2 дня» (leftText). */
function leftText(ms) {
  if (ms < 0) return "срок прошёл";
  const h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000);
  if (h >= 48) { const d = Math.floor(h / 24); return `${d} ${plural(d, "день", "дня", "дней")}`; }
  if (h >= 1) return `${h} ч ${String(m % 60).padStart(2, "0")} мин`;
  return `${m} мин`;
}
/** Срок дедлайна (Deadline.due): дата + время по Москве. */
function dueOf(d) {
  const t = d.due_time || "23:59";
  return new Date(`${d.due_date}T${t}:00+03:00`);
}
function campusOf(room) { const m = /\(([^)]+)\)/.exec(room || ""); return m ? m[1].trim() : ""; }
/** «А-332 (МП-1), Б-304 (МП-1)» → кабинеты и корпус. */
function splitRoom(room) {
  const codes = [], camp = [];
  for (const r of String(room || "").split(/,\s*/)) {
    const code = r.replace(/\s*\([^)]*\)/g, "").trim(), c = campusOf(r);
    if (code) codes.push(code);
    if (c && !camp.includes(c)) camp.push(c);
  }
  return { code: codes.join(", "), campus: camp.join(", ") };
}
/** Кабинет с корпусом: у нескольких кабинетов одного корпуса он один раз (roomText). */
function roomText(room) {
  const parts = String(room || "").trim().split(/,\s*/).filter(Boolean);
  const one = (r) => { const code = r.replace(/\s*\([^)]*\)/g, "").trim(), c = campusOf(r); return c ? `${code} (${c})` : code; };
  const r = splitRoom(room);
  const shared = parts.length > 1 && !r.campus.includes(",") && parts.every((x) => campusOf(x) === r.campus);
  return shared && r.campus ? `${r.code} (${r.campus})` : parts.map(one).join(", ");
}
/** Кабинет плашкой цвета предмета (RoomPill). color — CSS-цвет; inked — уже тёмный оттенок. */
function roomPill(room, color, size = 14, inked = false) {
  const fg = inked && Theme.darkInk ? color : `color-mix(in srgb, ${color}, ${Theme.dark ? "#fff" : "#000"} ${Theme.dark ? 55 : 35}%)`;
  return `<span class="cm-pill" style="font-size:${size}px;padding:${size * 0.25}px ${size * 0.65}px;border-radius:${size * 0.65}px;
    color:${fg};background:color-mix(in srgb, ${color} ${Theme.dark ? 22 : 16}%, transparent)">${esc(roomText(room))}</span>`;
}
/** Кабинет сменили: прежний зачёркнут, новый плашкой, ниже — когда (RoomWas). */
function roomWas(l, size = 14) {
  return `<div><div class="cm-wrap"><span class="bd mut" style="--sz:${size}px;text-decoration:line-through">${esc(roomText(l.roomWas))}</span>
    ${roomPill(l.room, "var(--warn)", size)}</div>
    <div class="bd b6" style="--sz:12px;color:var(--warn);margin-top:3px">${l.changedAt ? "кабинет изменён в " + esc(l.changedAt) : "кабинет изменён"}</div></div>`;
}
/** Строка под названием: кабинет, тип пары (и чьи пары), «идёт» (RoomLine). */
function roomLine(l, extra = [], live = false) {
  const c = ink(l.title);
  const rest = [l.kind ? l.kind.toLowerCase() : "", ...extra].filter(Boolean).join(" · ");
  let first = "";
  if (Theme.design2 && l.cancelled) first = `<span class="bd b7 mut" style="--sz:13px">пары не будет</span>`;
  else if (Theme.design2 && l.roomWas) first = roomWas(l);
  else if (l.room) first = roomPill(l.room, c, 14, true);
  return `<div class="cm-wrap">${first}${rest ? `<span class="bd mut" style="--sz:13px">${esc(rest)}</span>` : ""}${
    live ? `<span class="bd b7" style="--sz:13px;color:${c}">идёт</span>` : ""}</div>`;
}
/** «идёт · ещё 23 мин»; в блоке — «идёт 2-я из 5 · ещё 23 мин», на перемене — «перемена · ещё 8 мин». */
function liveLine(l, at) {
  const live = liveAt(l, at);
  if (!live) return "идёт";
  const left = spanText(minutesTo(at, live.end));
  if (live.of === 1) return "идёт · ещё " + left;
  return live.pause ? "перемена · ещё " + left : `идёт ${live.index}-я из ${live.of} · ещё ${left}`;
}
/** Номер пары по звонку — квадратик справа; у идущей залит акцентом (PairBadge). */
function pairBadge(n, live) {
  return `<span class="cm-badge${live ? " on" : ""}" aria-label="${esc(n)} пара">${esc(n)}</span>`;
}

/** Пара карточкой (LessonCard). key — номер пары в списке для data-act="lesson". */
function lessonCard(l, at, key) {
  const c = ink(l.title), base = subjectColor(l.title);
  const past = l.endAt && at >= l.endAt;
  const live = l.startAt && l.endAt && !past && at >= l.startAt;
  const total = live ? l.endAt - l.startAt : 0, passed = live ? Math.max(0, Math.min(total, at - l.startAt)) : 0;
  const look = Theme.design2 ? Look.load() : Look.classic;
  const stripe = look.card === "stripe";
  const moved = Theme.design2 && l.roomWas && !l.cancelled, gone = Theme.design2 && l.cancelled;
  const tint = Theme.dark ? `color-mix(in srgb, ${base} ${live ? 20 : 13}%, transparent)`
                          : `color-mix(in srgb, ${base} ${live ? 16 : 10}%, var(--card))`;
  const bg = stripe || gone ? "var(--card)" : `linear-gradient(90deg, ${tint} 0%, var(--card) 60%)`;
  const border = live ? "color-mix(in srgb, var(--ok) 60%, transparent)" : moved ? "var(--warn)" : "var(--line)";
  const dot = (color, text, style) => `<div class="row" style="gap:6px"><i class="cm-dot" style="background:${color}"></i><span class="bd" style="${style}">${esc(text)}</span></div>`;
  let room = "";
  if (gone) room = `<div class="bd b7 mut" style="--sz:13px;margin-top:7px">пары не будет</div>`;
  else if (l.room) room = `<div style="margin-top:7px">${moved ? roomWas(l, 13) : roomPill(l.room, c, 13, true)}</div>`;
  return `<button class="tile p0 cm-card${past || gone ? " cm-faded" : ""}"${gone || key === undefined ? " disabled" : ` data-act="lesson" data-k="${key}"`}
    style="border-radius:18px;background:${bg};border-color:${border}">
    ${stripe ? `<i class="cm-stripe" style="background:${c}"></i>` : ""}
    <div class="row" style="align-items:flex-start;gap:0;padding:var(--m) var(--m) var(--m) 14px">
      <div style="width:50px;flex:none"><div class="bd b7" style="--sz:15px">${esc(l.start)}</div>
        <div class="bd mut" style="--sz:12px;margin-top:1px">${esc(l.end)}</div></div>
      <div class="grow">
        <div class="nm" style="--sz:15px${gone ? ";text-decoration:line-through;color:var(--muted)" : ""}">${esc(l.title)}</div>
        ${l.kind ? `<div style="margin-top:5px">${dot(gone ? "var(--muted)" : c, l.kind.toLowerCase(), "--sz:13px;color:var(--muted)")}</div>` : ""}
        ${room}
        ${l.teacher && !gone ? `<div class="bd mut" style="--sz:13px;margin-top:5px">${esc(l.teacher)}</div>` : ""}
        ${live ? `<div style="margin-top:7px">${dot("var(--ok)", liveLine(l, at), "--sz:13px;font-weight:700;color:var(--ok)")}</div>` : ""}
      </div>
      ${l.number ? `<div style="margin-left:var(--s)">${pairBadge(l.number, live)}</div>` : ""}
    </div>
    ${live ? `<div class="progress" style="height:3px;border-radius:0;background:color-mix(in srgb, var(--ok) 12%, transparent)"><i style="width:${total ? (passed / total) * 100 : 0}%;background:var(--ok);border-radius:0"></i></div>` : ""}
  </button>`;
}

/** Пары списком одной карточкой (LessonList). showGroups — чьи пары (расписание преподавателя). */
function lessonList(lessons, at, { keyBase = 0, tappable = true, showGroups = false } = {}) {
  return `<div class="tile p0">${lessons.map((l, i) => {
    const past = l.endAt && at >= l.endAt;
    const live = l.startAt && !past && at >= l.startAt;
    const gone = Theme.design2 && l.cancelled;
    const tag = tappable && !gone ? `button data-act="lesson" data-k="${keyBase + i}"` : "div";
    return `${i ? '<div class="divider"></div>' : ""}<${tag} class="cm-lrow${past || gone ? " cm-faded2" : ""}">
      <div style="width:50px;flex:none"><div class="bd b6" style="--sz:15px">${esc(l.start)}</div><div class="bd mut" style="--sz:12px">${esc(l.end)}</div></div>
      <i class="cm-bar" style="background:${ink(l.title)}"></i>
      <div class="grow"><div class="nm" style="--sz:15px${gone ? ";text-decoration:line-through" : ""}">${esc(l.title)}</div>
        <div style="margin-top:5px">${roomLine(l, showGroups && l.groups ? [l.groups] : [], live)}</div></div>
    </${tag.split(" ")[0]}>`;
  }).join("")}</div>`;
}

/** Понедельник недели даты (week.dart: mondayOf), ISO-строкой по Москве. */
function mondayOf(date = now()) {
  const t = msk(date);
  return isoDay(new Date(Date.UTC(t.y, t.m - 1, t.d) - t.wd * 864e5 - MSK + 12 * 3600e3));
}
/** ISO-дата через n дней от date (по Москве). */
function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00+03:00");
  return isoDay(new Date(d.getTime() + n * 864e5));
}
