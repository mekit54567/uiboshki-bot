// «Сегодня» (app/lib/screens/today.dart): группа с неделей и погода одной
// строкой, капибара, приветствие по времени суток; ближайшая пара крупно —
// время, название, кабинет плашкой цвета предмета и «через»; во время пары —
// сколько до конца, полоска и где следующая. Ниже пары дня карточками и что
// горит по срокам. Время тикает раз в 30 секунд.
"use strict";

const ORDINAL = ["первая", "вторая", "третья", "четвёртая", "пятая", "шестая", "седьмая", "восьмая"];
function ordinal(i) { return ORDINAL[i] || `${i + 1}-я`; }
function poseAt(h) { return h >= 5 && h < 12 ? "morning" : h >= 12 && h < 17 ? "day" : h >= 17 && h < 23 ? "evening" : "night"; }
function greeting(h) { return { morning: "Доброе утро", day: "Добрый день", evening: "Добрый вечер" }[poseAt(h)] || "Доброй ночи"; }

const CAPY_LINES = {
  morning: ["Сначала кофе, потом пары", "Глаза открыты наполовину. Этого хватит", "Проснулась раньше будильника. Почти",
    "Кофе горячий, дедлайны пока холодные", "Утро начинается с кружки кофе, а не с\u00A0СДО", "Ещё глоток, и можно в метро",
    "Утро доброе, если пары не с девяти", "Капибара и кофе: лучший старт дня", "Сделай вид, что ты жаворонок"],
  day: ["Пишу лабу. Не отвлекай, пожалуйста", "Ctrl+S каждые пять минут", "Капибара в потоке",
    "Ещё одна вкладка, и точно всё пойму", "Обед был? Если нет, иди поешь", "Компилируется… можно моргнуть"],
  evening: ["Вечер. Лампа горит, дела тают", "Ещё одна глава, и спать", "Читаю лекцию, которую проспала",
    "Тёплый свет и ни одного дедлайна. Мечта", "Пары кончились, учёба нет", "Сегодня ты молодец. Даже если нет"],
  night: ["Тсс, капибара спит", "Zzz… дедлайны подождут до утра", "Спит и видит зачёт автоматом",
    "Сон тоже подготовка к экзамену", "Пять минут… ещё пять минут…", "Снится, что СДО не упал", "Мяч мягкий, сон крепкий"],
};
const MOMENT_LINES = { dayOver: "На сегодня всё. Свобода", weekOver: "Неделя закончилась, а капибара нет",
  dayOff: "Выходной. Отдыхаю и тебе советую", rain: "Зонт не забудь" };

/** Погода из /api/today для шапки: температура и коротко небо (weatherBrief). */
function weatherBrief(raw) {
  const full = String(raw || "").replace(/[^\p{L}\p{N}\s°+\-−.,:·]/gu, "").replace(/\s+/g, " ").trim();
  if (!full) return null;
  const parts = full.split(" · ")[0].split(",").map((x) => x.trim()).filter(Boolean);
  if (!parts.length) return null;
  return { temp: parts[0], sky: parts.length > 1 ? shortSky(parts[1]) : "", full };
}
function weatherDetails(raw) {
  const w = weatherBrief(raw);
  if (!w) return null;
  const halves = w.full.split(" · ");
  let desc = "", feels = "";
  for (const x of halves[0].split(",").slice(1)) {
    const v = x.trim();
    if (v.startsWith("ощущается")) feels = v;
    else if (!desc && v) desc = v[0].toUpperCase() + v.slice(1);
  }
  return { temp: w.temp, desc, feels, advice: halves.slice(1).join(" · ").trim() };
}
function shortSky(desc) {
  const x = desc.toLowerCase().trim();
  for (const [k, s] of [["гроза", "гроза"], ["ливень", "ливень"], ["снег", "снег"], ["дожд", "дождь"], ["морось", "морось"],
    ["туман", "туман"], ["пасмурно", "пасмурно"], ["облачн", "облачно"], ["ясно", "ясно"]]) if (x.includes(k)) return s;
  return x.split(" ").pop();
}
function rainy(raw) { const w = weatherBrief(raw); return !!w && ["дождь", "ливень", "морось", "гроза"].includes(w.sky); }

Screens.today = {
  mount(body, screen) {
    let data = null, lessons = [], wxOpen = false, capyN = 0, taps = 0, tapTimer = 0;
    const load = async (fromCache = false) => {
      const get = fromCache ? (p) => Promise.resolve(Api.cached(p)) : (p) => Api.get(p);
      const extra = (p) => get(p).catch(() => null);
      const today = isoDay();
      const [j, me, week, tomorrow] = await Promise.all([get("/today"), extra("/me"), extra(`/week?start=${mondayOf()}`),
        extra(`/day?date=${addDays(today, 1)}`)]);
      if (!j) return null;
      if (fromCache && j.date && j.date !== today) return null;     // утром в запасе — вчерашний день
      const days = week && Array.isArray(week.days) ? week.days : null;
      return {
        lessons: (j.lessons || []).map(lessonOf),
        cancelled: (j.cancelled || []).map(lessonOf),
        tf: j.tomorrow_first ? lessonOf(j.tomorrow_first) : null,
        soon: ((j.deadlines && j.deadlines.soon) || []).filter((d) => (d.days ?? 0) >= 0),
        weather: String(j.weather || ""),
        name: String((me && me.first_name) || "").trim(),
        group: me && me.group ? String(me.group.name || "") : "",
        week: week && Number.isInteger(week.week) ? week.week : null,
        more: days && days.length ? days.some((d) => d.date > today && (d.dots || []).length) : null,
        tomorrow: tomorrow && Array.isArray(tomorrow.lessons) ? tomorrow.lessons.map(lessonOf) : [],
      };
    };

    const draw = () => {
      if (!data) return;
      const t = now(), h = msk(t).h, L = data.lessons;
      let current = null, next = null;
      for (const l of L) {
        if (!l.startAt || !l.endAt) continue;
        if (t >= l.startAt && t < l.endAt) current = l;
        if (!next && t < l.startAt) next = l;
      }
      const shown = Theme.design2 && data.cancelled.length ? [...L, ...data.cancelled].sort((a, b) => a.start.localeCompare(b.start)) : L;
      const hello = data.name ? `${greeting(h)},\n${data.name}` : greeting(h);
      lessons = [];
      const key = (l) => { lessons.push(l); return lessons.length - 1; };
      let title, focus = "", note = "";
      if (!L.length) {
        title = hello;
        const tf = data.tf;
        note = notice("Сегодня пар нет", !tf ? "Завтра тоже свободно." : !data.tomorrow.length ? `Завтра первая — ${tf.start}, ${tf.title}.` : `Завтра первая — в ${tf.start}.`, { pose: "joy" });
      } else if (current) {
        title = `Идёт ${ordinal(L.indexOf(current))} пара`;
        focus = liveFocus(current, next, t, key);
      } else if (next) {
        const i = L.indexOf(next);
        title = i === 0 ? hello : "Перемена";
        focus = nextFocus(`${ordinal(i)} пара в`, next, i > 0 ? L[i - 1] : null, t, key);
      } else {
        title = hello;
        if (data.tf) focus = nextFocus("завтра первая пара в", data.tf, null, t, key);
        else note = notice("Пары закончились", "Завтра свободно.", { pose: "joy" });
      }
      const free = !L.length || (!current && !next);
      const rest = !L.length ? data.tomorrow : !current && !next && data.tomorrow.length > 1 ? data.tomorrow.slice(1) : [];
      const look = Theme.design2 ? Look.load() : Look.classic;
      let list = "";
      if (L.length) {
        list += section(`сегодня · ${L.length} ${plural(L.length, "пара", "пары", "пар")}`);
        if (look.day === "rows") {
          const base = lessons.length;
          shown.forEach((l) => key(l));
          list += `<div class="hx" style="margin-bottom:var(--s)">${lessonList(shown, t, { keyBase: base })}</div>`;
        } else list += shown.map((l) => `<div class="hx" style="margin-bottom:var(--s)">${lessonCard(l, t, l.cancelled ? undefined : key(l))}</div>`).join("");
      }
      if (rest.length) {
        list += section(`завтра · ${L.length ? "ещё " : ""}${rest.length} ${plural(rest.length, "пара", "пары", "пар")}`);
        list += rest.map((l) => `<div class="hx" style="margin-bottom:var(--s)">${lessonCard(l, t, key(l))}</div>`).join("");
      }
      if (data.soon.length) {
        list += section(data.soon.some((d) => dueOf(d) - t < 3 * 864e5) ? "горит" : "сдать");
        list += `<div class="hx">${soonList(data.soon, t)}</div>`;
      } else if (free) {
        list += section("сдать") + `<div class="hx"><div class="tile row" style="gap:var(--s)">${icon("task_alt", "", "font-size:17px;color:var(--ok)")}
          <span class="bd mut grow" style="--sz:14px">Открытых сроков нет</span></div></div>`;
      }
      const moments = [];
      const awake = poseAt(h) !== "night";
      if (!L.length) moments.push("dayOff");
      else if (awake && !current && !next) moments.push(data.more === false ? "weekOver" : "dayOver");
      if (awake && rainy(data.weather)) moments.push("rain");
      screen.capyLines = [...moments.map((m) => MOMENT_LINES[m]), ...CAPY_LINES[poseAt(h)]];
      body.innerHTML = top() + `<div class="td-head"><div class="ttl td-title${title.includes("\n") ? "" : " one"}" style="--sz:30px">${esc(title)}</div>
        <button class="td-capy" data-act="capy" aria-label="Капибара">${capy(poseAt(h), 62)}</button></div>
        ${focus ? `<div class="td-focus">${focus}</div>` : ""}${note ? `<div style="height:var(--m)"></div>${note}` : ""}
        ${list}<div class="pad-bottom"></div>`;
      fitTitle();
    };

    // «Идёт первая пара», «Перемена» — одной строкой, на узком экране мельче
    const fitTitle = () => {
      const el = body.querySelector(".td-title.one");
      if (!el) return;
      let sz = 30;
      while (el.scrollWidth > el.clientWidth && sz > 18) { sz -= 1; el.style.setProperty("--sz", sz + "px"); }
    };

    const top = () => {
      const w = weatherBrief(data.weather), d = weatherDetails(data.weather);
      const head = [data.group, data.week != null ? `${data.week} неделя` : ""].filter(Boolean).join(" · ");
      let chips = head ? `<span class="td-chip">${esc(head)}</span>` : "";
      if (w) chips += `<button class="td-chip" data-act="wx" aria-label="${esc(wxOpen ? "Свернуть погоду" : "Погода: " + w.full)}">${esc(w.sky ? `${w.temp} ${w.sky}` : w.temp)}</button>`;
      const card = wxOpen && d ? `<button class="td-wx" data-act="wx"><div class="row"><span class="num" style="--sz:40px">${esc(d.temp)}</span>
        <div class="grow">${d.desc ? `<div class="bd b6" style="--sz:15px">${esc(d.desc)}</div>` : ""}${d.feels ? `<div class="bd mut" style="--sz:13px">${esc(d.feels)}</div>` : ""}</div></div>
        ${d.advice ? `<span class="td-advice">${icon("checkroom", "", "font-size:15px")}<span>${esc(d.advice)}</span></span>` : ""}</button>` : "";
      return `<div class="td-top">${chips}${card}</div>`;
    };

    const nameRow = (l, key) => `<button class="nm" style="--sz:18px;display:block;text-align:left" data-act="lesson" data-k="${key(l)}">${esc(l.title)}</button>`;
    const roomTile = (l, key) => {
      const r = splitRoom(l.room), c = ink(l.title);
      const fg = Theme.darkInk ? "#fff" : `color-mix(in srgb, ${c}, #000 82%)`;
      return `<button class="td-box room" style="background:${c};color:${fg}" data-act="lesson" data-k="${key(l)}">
        <div class="bd" style="--sz:12px;opacity:.75">${r.code.includes(",") ? "кабинеты" : "кабинет"}</div>
        <div class="bd td-fit" style="--sz:21px;font-weight:800;margin-top:2px">${esc(r.code || l.room)}</div>
        ${r.campus ? `<div class="bd b6" style="--sz:12px;margin-top:2px">корпус ${esc(r.campus)}</div>` : ""}</button>`;
    };
    const infoTile = (label, value, { sub = "", subColor = "", fit = true, act = "" } = {}) =>
      `<button class="td-box"${act}><div class="bd mut" style="--sz:12px">${esc(label)}</div>
        <div class="bd ${fit ? "td-fit" : "clamp2"}" style="--sz:${fit ? 21 : 16}px;font-weight:800;margin-top:2px">${esc(value)}</div>
        ${sub ? `<div class="bd clamp2" style="--sz:12px;margin-top:2px;${subColor ? `color:${subColor};font-weight:700` : "color:var(--muted)"}">${esc(sub)}</div>` : ""}</button>`;

    const nextFocus = (label, l, prev, at, key) => {
      const from = prev ? campusOf(prev.room) : "", to = campusOf(l.room);
      const moving = from && to && from !== to;
      const gap = prev && prev.endAt && l.startAt ? Math.round((l.startAt - prev.endAt) / 60000) : 0;
      const tiles = [];
      if (l.room) tiles.push(roomTile(l, key));
      if (l.startAt) tiles.push(infoTile("через", spanText(minutesTo(at, l.startAt)), { sub: l.teacher, act: ` data-act="lesson" data-k="${key(l)}"` }));
      else if (l.teacher) tiles.push(infoTile("ведёт", l.teacher, { fit: false, act: ` data-act="lesson" data-k="${key(l)}"` }));
      return `<div class="bd mut" style="--sz:13px">${esc(label)}</div>
        <div class="num" style="--sz:52px;margin-top:4px">${esc(l.start)}</div>
        <div style="height:var(--s)"></div>${nameRow(l, key)}<div style="height:var(--m)"></div>
        <div class="td-tiles">${tiles.join("")}</div>
        ${moving ? `<div class="row" style="gap:4px;margin-top:var(--s);color:var(--warn)">${icon("directions_walk", "", "font-size:16px")}
          <span class="bd b6" style="--sz:13px">Другой корпус — ${esc(to)}, на переход ${gap} мин</span></div>` : ""}`;
    };

    const liveFocus = (l, n, at, key) => {
      const c = ink(l.title), live = liveAt(l, at);
      const from = live ? live.start : l.startAt, till = live ? live.end : l.endAt;
      const total = till - from, passed = Math.max(0, Math.min(total, at - from));
      const label = !live || live.of === 1 ? "до конца" : live.pause ? `перемена · до ${live.index}-й пары из ${live.of}` : `до конца пары · ${live.index} из ${live.of}`;
      let after;
      if (n) {
        const fromC = campusOf(l.room), toC = campusOf(n.room), known = fromC && toC, moving = known && fromC !== toC;
        const room = splitRoom(n.room).code, stay = room && room === splitRoom(l.room).code;
        after = infoTile(`дальше в ${n.start}`, room || n.title, { fit: !!room,
          sub: stay ? "тот же кабинет, никуда не идти" : moving ? `другой корпус, ${toC}` : known ? "тот же корпус" : room ? n.title : n.kind,
          subColor: moving ? "var(--warn)" : "", act: ` data-act="lesson" data-k="${key(n)}"` });
      } else after = infoTile("конец в", l.end, { sub: "последняя на сегодня", act: ` data-act="lesson" data-k="${key(l)}"` });
      const m = minutesTo(at, till);
      const unit = (t) => `<span class="bd b6 mut" style="--sz:18px;margin:0 6px">${t}</span>`;
      const big = (t) => `<span class="num" style="--sz:52px;color:${c}">${t}</span>`;
      const count = m >= 60 ? big(Math.floor(m / 60)) + unit("ч") + big(String(m % 60).padStart(2, "0")) + unit("мин") : big(m) + unit("мин");
      return `<div class="bd mut" style="--sz:13px">${esc(label)}</div>
        <div style="margin-top:4px;display:flex;align-items:baseline" aria-label="до конца ${spanText(m)}">${count}</div>
        <div class="progress" style="height:6px;margin-top:var(--m);--c:${c}"><i style="width:${total ? (passed / total) * 100 : 0}%"></i></div>
        <div style="height:var(--m)"></div>${nameRow(l, key)}<div style="height:var(--m)"></div>
        <div class="td-tiles">${l.room ? roomTile(l, key) : ""}${after}</div>`;
    };

    const soonList = (items, at) => `<div class="tile p0">${items.map((d, i) => {
      const left = dueOf(d) - at, hot = left < 864e5;
      return `${i ? '<div class="divider"></div>' : ""}<div class="row" style="gap:var(--s);padding:11px var(--l)">
        ${icon("local_fire_department", "o", `font-size:17px;color:${hot ? "var(--danger)" : "var(--warn)"}`)}
        <span class="bd b6 grow" style="--sz:14px">${esc(d.subject)}</span>
        <span class="bd b6" style="--sz:12.5px;color:${hot ? "var(--danger)" : "var(--muted)"}">${esc(leftText(left))}</span></div>`;
    }).join("")}</div>`;

    on(body, {
      wx() { tick(); wxOpen = !wxOpen; draw(); },
      lesson(b) { const l = lessons[+b.dataset.k]; if (l && window.openLesson) openLesson(l.raw); },
      capy() {
        tick();
        taps++;
        clearTimeout(tapTimer);
        tapTimer = setTimeout(() => (taps = 0), 12000);
        const lines = screen.capyLines || CAPY_LINES.day;
        // редкие фразы — полночные ачивки (achievements/captions.dart)
        let text = Math.floor(Math.random() * 10000) === 0 ? "Ты нашёл меня. Теперь ты один из нас"
          : Math.floor(Math.random() * 100) === 0 ? "Это секретная фраза. Никому не говори"
          : taps >= 5 ? "Ну хватит щекотать" : lines[capyN++ % lines.length];
        if (taps >= 5) taps = 0;
        if (Ach.capyTouched) Ach.capyTouched(new Date());
        if (text.startsWith("Ты нашёл меня")) Ach.unlock("one_of_us");
        if (text.startsWith("Это секретная")) Ach.unlock("secret");
        // как showCapy в приложении (widgets/capy.dart): выпрыгивает, подпись
        // печатается по буквам с курсором, ненапечатанное — прозрачным (строка
        // не прыгает); закрывается нажатием. Сверхредкая — темнее и медленнее
        const turn = text.startsWith("Ты нашёл меня");
        const ov = document.createElement("div");
        ov.className = "td-cap" + (turn ? " turn" : "");
        ov.innerHTML = `<div class="td-cap-pop">${capy(poseAt(msk().h), 180)}</div><div class="ttl" style="--sz:24px;max-width:320px">` +
          `<span class="td-typed"></span><i class="td-caret"></i><span class="td-rest">${esc(text)}</span></div>`;
        const typed = ov.querySelector(".td-typed"), rest = ov.querySelector(".td-rest");
        let shown = 0, timer = 0;
        const show = (n) => { shown = n; typed.textContent = text.slice(0, n); rest.textContent = text.slice(n); };
        if (matchMedia("(prefers-reduced-motion: reduce)").matches) show(text.length);
        else {
          timer = setTimeout(() => {
            timer = setInterval(() => { show(shown + 1); if (shown >= text.length) clearInterval(timer); }, turn ? 70 : 45);
          }, turn ? 3500 : 270); // печатать — когда капибара уже выпрыгнула (или повернулась)
        }
        ov.addEventListener("click", () => { clearTimeout(timer); clearInterval(timer); ov.remove(); });
        document.body.appendChild(ov);
      },
    });

    const refresh = async () => {
      try { data = await load(); draw(); }
      catch (e) {
        if (!data) body.innerHTML = '<div style="height:60px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "retry" });
      }
    };
    on(body, { retry: () => { body.innerHTML = spinner(); refresh(); } });
    // сразу — из запаса телефона, свежие следом (как Loader.fromCache)
    load(true).then((d) => { if (d && !data) { data = d; draw(); } }).catch(() => {});
    body.innerHTML = spinner();
    refresh();
    const timer = setInterval(draw, 30000);
    screen.reload = refresh;
    pullRefresh(screen, refresh);
    return () => clearInterval(timer);
  },
  onShow(body, screen) { if (screen.reload) screen.reload(); },
};
