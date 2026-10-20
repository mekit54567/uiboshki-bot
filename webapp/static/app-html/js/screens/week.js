// «Неделя» (app/lib/screens/week.dart, week_days.dart): два вида пар,
// переключатель значками справа сверху, выбор запоминается. Лента — вся
// неделя одной лентой, сверху полоса дней с точками пар; нажал день — лента
// едет к нему, открывается на сегодняшнем дне. По дням — полоса дней и пары
// выбранного карточками. Соседняя неделя — свайпом вбок или стрелками у дат;
// шапка стоит, едут подпись недели и пары. Итоги прошедших дней (новый
// дизайн) — строкой «Сводка за день», подробности — листом.
"use strict";

const WEEKDAYS_CAP = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
/** «Вторник, 6 октября» по ISO-дате. */
function dayTitle(isoDate) {
  const d = new Date(isoDate + "T12:00:00+03:00"), t = msk(d);
  return `${WEEKDAYS_CAP[t.wd]}, ${t.d} ${MONTHS[t.m - 1]}`;
}
function dayHead(isoDate, today) { return today ? `${dayTitle(isoDate)} · сегодня` : dayTitle(isoDate); }
/** «5–11 окт», через месяц — «28 сен – 4 окт». */
function weekRange(monday) {
  const a = msk(new Date(monday + "T12:00:00+03:00")), b = msk(new Date(addDays(monday, 6) + "T12:00:00+03:00"));
  return a.m === b.m ? `${a.d}–${b.d} ${MONTHS_SHORT[b.m - 1]}` : `${a.d} ${MONTHS_SHORT[a.m - 1]} – ${b.d} ${MONTHS_SHORT[b.m - 1]}`;
}
/** «6», «4,5», «−2» — без лишнего нуля, минус типографский. */
function num1(v) {
  const a = Math.abs(v), t = a === Math.round(a) ? String(Math.round(a)) : a.toFixed(1).replace(".", ",");
  return v < 0 ? "−" + t : t;
}
const signed = (v) => (v < 0 ? num1(v) : "+" + num1(v));
function summaryOf(j) {
  if (!j || typeof j !== "object") return null;
  const done = (j.done || []).filter((d) => d && (d.task || d.title)).map((d) => [String(d.task || d.title), String(d.course || "")]);
  const grades = (j.grades || []).filter((g) => g && typeof g.delta === "number").map((g) => [String(g.name || "Предмет"), g.delta]);
  return done.length || grades.length ? { done, grades, points: typeof j.points === "number" ? j.points : 0 } : null;
}

Screens.week = {
  mount(body, screen) {
    const outer = body.parentElement;
    outer.style.overflow = "hidden";
    body.className = "wrap wk";
    let shift = 0, dir = 1, data = null, dataShift = null, seq = 0, error = null;
    let days = (Prefs.get("uib_week_view") || Prefs.get("uib_today_view")) === "days";
    let selected = null, lessonsByKey = [];
    const numbers = {};

    body.innerHTML = `<div class="wk-head"></div><div class="wk-strip"></div><div class="divider"></div>
      <div class="wk-list"><div class="wk-body"></div></div>`;
    const $ = (s) => body.querySelector(s);
    const list = $(".wk-list");
    screen.scroller = list;

    const monday = (k) => addDays(mondayOf(), 7 * k);
    const label = () => {
      const n = shift in numbers ? numbers[shift] : (numbers[shift - dir] == null ? null : numbers[shift - dir] + dir);
      const range = weekRange(monday(shift));
      return n != null && n > 0 ? `${n} неделя · ${range}` : range;
    };
    const drawHead = () => {
      const lead = `<div class="wk-label"><button data-act="prev" aria-label="Прошлая неделя">${icon("chevron_left", "", "font-size:20px")}</button>
        <button class="eyebrow wk-lt" data-act="today">${esc(label())}</button>
        <button data-act="next" aria-label="Следующая неделя">${icon("chevron_right", "", "font-size:20px")}</button>
        ${shift ? '<button class="wk-today" data-act="today">Сегодня</button>' : ""}</div>`;
      const trailing = `<div class="row" style="gap:2px">
        <button class="wk-ic" data-act="search" aria-label="Поиск расписания">${icon("search", "", "color:var(--muted)")}</button>
        <div class="wk-toggle"><button class="${days ? "" : "on"}" data-act="list" aria-label="Лентой">${icon("view_agenda", "o", "font-size:18px")}</button>
        <button class="${days ? "on" : ""}" data-act="days" aria-label="По дням">${icon("calendar_view_week", "", "font-size:18px")}</button></div></div>`;
      $(".wk-head").innerHTML = screenTitle("Неделя", { lead, trailing });
    };

    const load = async (k, cached) => {
      const mon = monday(k), dates = [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(mon, i));
      const get = cached ? (p) => { const v = Api.cached(p); if (v === undefined) throw new Error("нет"); return Promise.resolve(v); } : (p) => Api.get(p);
      const res = await Promise.all([get(`/week?start=${mon}`), ...dates.map((d) => get(`/day?date=${d}`))]);
      const out = { number: Number.isInteger(res[0].week) ? res[0].week : null, monday: mon, dates, days: {}, sums: {} };
      dates.forEach((d, i) => {
        out.days[d] = (res[i + 1].lessons || []).map(lessonOf);
        const s = Theme.design2 ? summaryOf(res[i + 1].summary) : null;
        if (s) out.sums[d] = s;
      });
      return out;
    };
    const show = (my, k, d) => {
      if (my !== seq) return;
      numbers[k] = d.number;
      const fresh = dataShift !== k;
      data = d; dataShift = k; error = null;
      if (fresh) selected = null;
      drawHead(); draw(fresh);
    };
    const fetch = async () => {
      const my = ++seq, k = shift;
      try { const c = await load(k, true); if (dataShift !== k) show(my, k, c); } catch (e) {}
      try { show(my, k, await load(k, false)); }
      catch (e) { if (my === seq && dataShift !== k) { error = e; draw(true); } }
    };

    /** Итог дня, если его пора показать: прошедший день или сегодня после пар. */
    const summaryFor = (date, at) => {
      const s = data.sums[date];
      if (!s) return null;
      const today = isoDay(at);
      if (date > today) return null;
      if (date === today && (data.days[date] || []).some((l) => !l.endAt || at < l.endAt)) return null;
      return s;
    };
    const summaryCard = (s, lessons, date, k) => {
      return `<button class="tile wk-sum" data-act="sum" data-d="${date}"><div class="grow"><div class="bd mut" style="--sz:13px">Сводка за день</div>
        <div style="margin-top:2px">${summaryLine(s, lessons, 17)}</div></div><span class="mi mut">chevron_right</span></button>`;
    };
    const summaryLine = (s, lessons, size) => {
      const pairs = lessons.reduce((n, l) => n + l.pairs, 0), p = s.points, whole = p === Math.round(p);
      const parts = [[String(pairs), plural(pairs, "пара", "пары", "пар")]];
      if (s.done.length) parts.push([String(s.done.length), "сдано"]);
      if (s.grades.length && Math.abs(p) >= 0.05) parts.push([signed(p), whole ? plural(Math.abs(Math.round(p)), "балл", "балла", "баллов") : "балла"]);
      return `<span class="wk-sline">${parts.map(([a, b], i) => `${i ? '<span class="bd mut" style="--sz:15px">·</span>' : ""}<span><span class="num" style="--sz:${size}px">${esc(a)}</span><span class="bd mut" style="--sz:13px"> ${esc(b)}</span></span>`).join("")}</span>`;
    };

    const dayCell = (date, i, dots, sel, today) => {
      const t = msk(new Date(date + "T12:00:00+03:00"));
      return `<button class="wk-day${sel ? " sel" : ""}${today ? " today" : ""}" data-act="day" data-i="${i}" aria-label="${esc(dayTitle(date))}">
        <span class="bd" style="--sz:12px">${WD_SHORT[i]}</span><span class="num" style="--sz:21px;margin-top:2px">${t.d}</span>
        <span class="wk-dots">${"<i></i>".repeat(Math.min(5, dots))}</span></button>`;
    };

    const draw = (fresh = false) => {
      const body2 = $(".wk-body");
      if (!data || (error && dataShift !== shift)) {
        $(".wk-strip").innerHTML = "";
        body2.innerHTML = error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner();
        return;
      }
      const t = now(), todayIso = isoDay(t), d = data;
      if (selected === null) {
        selected = d.dates.indexOf(todayIso);
        if (selected < 0) selected = days ? Math.max(0, d.dates.findIndex((x) => d.days[x].length)) : 0;
      }
      $(".wk-strip").innerHTML = d.dates.map((x, i) => dayCell(x, i, d.days[x].length, i === selected, x === todayIso)).join("");
      lessonsByKey = [];
      const key = (l) => { lessonsByKey.push(l); return lessonsByKey.length - 1; };
      let html = "";
      if (days) {
        const date = d.dates[selected], L = d.days[date], n = L.length, head = dayHead(date, date === todayIso);
        html += section(n ? `${head} · ${n} ${plural(n, "пара", "пары", "пар")}` : head);
        html += n ? L.map((l) => `<div class="hx" style="margin-bottom:var(--s)">${lessonCard(l, t, key(l))}</div>`).join("")
          : notice("Пар нет", "Свободный день", { pose: "joy" });
        const s = summaryFor(date, t);
        if (s) html += `<div class="hx" style="margin-bottom:var(--s)">${summaryCard(s, L, date)}</div>`;
      } else {
        html += d.dates.map((date, i) => {
          const L = d.days[date], s = summaryFor(date, t), today = date === todayIso;
          const base = lessonsByKey.length;
          L.forEach((l) => key(l));
          return `<div class="wk-block" data-i="${i}"><div class="eyebrow" style="padding:0 0 var(--s) var(--s);${today ? "color:var(--text)" : ""}">${esc(dayHead(date, today))}</div>
            ${L.length ? lessonList(L, t, { keyBase: base }) : `<div class="tile"><div class="bd b6" style="--sz:17px">Пар нет</div><div class="bd mut" style="--sz:13px;margin-top:3px">Свободный день</div></div>`}
            ${s ? `<div style="margin-top:var(--s)">${summaryCard(s, L, date)}</div>` : ""}</div>`;
        }).join("") + '<div style="height:160px"></div>';
      }
      body2.innerHTML = html + (days ? '<div class="pad-bottom"></div>' : "");
      body2.classList.toggle("wk-waiting", dataShift !== shift);
      if (fresh) {
        body2.classList.remove("wk-in-l", "wk-in-r"); void body2.offsetWidth;
        body2.classList.add(dir > 0 ? "wk-in-r" : "wk-in-l");
        // лента открывается на сегодняшнем дне (прошедшие — выше)
        screen.quietUntil = Date.now() + 600;
        if (!days) {
          const b = body2.querySelector(`.wk-block[data-i="${selected}"]`);
          list.scrollTop = b ? b.offsetTop - 2 : 0;
        } else list.scrollTop = 0;
      }
    };

    const shiftBy = (k) => {
      tick();
      if (k > 0) Ach.unlock("week_next");
      dir = Math.sign(k); shift += k; error = null;
      drawHead();
      $(".wk-body").classList.add("wk-waiting");
      fetch();
    };
    on(body, {
      prev: () => shiftBy(-1),
      next: () => shiftBy(1),
      today: () => { if (shift) shiftBy(-shift); },
      search: () => { tick(); if (window.openSearch) openSearch(); else toast("Скоро"); },
      list: () => { if (!days) return; tick(); days = false; Prefs.set("uib_week_view", "list"); drawHead(); draw(true); },
      days: () => { if (days) return; tick(); days = true; Prefs.set("uib_week_view", "days"); drawHead(); draw(true); },
      day(b) {
        tick();
        const i = +b.dataset.i;
        if (days) { if (i !== selected) { dir = i > selected ? 1 : -1; selected = i; draw(true); } return; }
        selected = i;
        $(".wk-strip").querySelectorAll(".wk-day").forEach((x, k) => x.classList.toggle("sel", k === i));
        const blk = body.querySelector(`.wk-block[data-i="${i}"]`);
        screen.quietUntil = Date.now() + 700;
        if (blk) list.scrollTo({ top: blk.offsetTop - 2, behavior: "smooth" });
      },
      lesson(b) { const l = lessonsByKey[+b.dataset.k]; if (l && window.openLesson) openLesson(l.raw); },
      sum(b) { const date = b.dataset.d; summarySheet(data.sums[date], data.days[date], date, summaryLine); },
      retry: () => fetch(),
    });
    // свайп вбок — соседняя неделя; вертикальную прокрутку не трогает
    let sx = null, sy = 0, st = 0;
    list.addEventListener("touchstart", (e) => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; st = Date.now(); }, { passive: true });
    list.addEventListener("touchend", (e) => {
      if (sx === null) return;
      const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy, dt = Math.max(1, Date.now() - st);
      sx = null;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && Math.abs(dx) / dt > 0.25) shiftBy(dx < 0 ? 1 : -1);
    });
    // лента: при прокрутке выделен день, до которого долистали
    list.addEventListener("scroll", () => {
      if (days || !data) return;
      const blocks = [...body.querySelectorAll(".wk-block")];
      let cur = 0;
      for (const b of blocks) if (b.offsetTop - list.scrollTop <= 40) cur = +b.dataset.i;
      if (cur !== selected) {
        selected = cur;
        $(".wk-strip").querySelectorAll(".wk-day").forEach((x, k) => x.classList.toggle("sel", k === cur));
      }
    }, { passive: true });
    drawHead();
    draw();
    fetch();
    screen.reload = () => { if (dataShift === shift) fetch(); };
    pullRefresh(screen, () => fetch());
  },
  onShow(body, screen) { if (screen.reload) screen.reload(); },
};

/** Лист «Сводка за день»: итог строкой, что сдал и баллы по предметам. */
function summarySheet(s, lessons, date, line) {
  const row = (ic, color, title, sub = "", end = "") => `<div class="row" style="align-items:flex-start;padding:6px 0">
    ${icon(ic, "", `font-size:18px;color:${color};margin-top:2px`)}<div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div>
    ${sub ? `<div class="bd mut" style="--sz:13px">${esc(sub)}</div>` : ""}</div>${end}</div>`;
  const head = (t) => `<div class="eyebrow" style="padding-top:var(--xl);padding-bottom:var(--xs)">${esc(t)}</div>`;
  Sheet.show(`<div class="eyebrow">Сводка за день</div><div class="nm" style="--sz:20px;margin-top:4px">${esc(dayTitle(date))}</div>
    <div style="margin-top:var(--m)">${line(s, lessons, 22)}</div>
    ${s.done.length ? head("Сдано") + s.done.map(([t, c]) => row("check_circle", "var(--ok)", t, c)).join("") : ""}
    ${s.grades.length ? head("Баллы СДО") + s.grades.map(([n, d]) => row("auto_awesome", d < 0 ? "var(--danger)" : "var(--accent)", n, "",
      `<span class="num" style="--sz:17px${d < 0 ? ";color:var(--danger)" : ""}">${signed(d)}</span>`)).join("") : ""}
    <div style="height:var(--xl)"></div>`);
}
