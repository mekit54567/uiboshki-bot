// «Ещё» (app/lib/screens/more.dart, дизайн 23Б): сверху кто я и группа, под
// ними баллы БРС одной цифрой и одной фразой (нажал — «Учёба»), ачивки и
// рейтинг строками, настройки плитками по две; действия с пояснениями —
// строками под плитками, «Выйти» и приписка для магазинов. Экраны настроек
// (Уведомления, Оформление, Безопасность, Группа, тур) — js/screens/settings.js.
// С «Новым» в «Оформлении» — короткий экран по макету Е3 (more_fresh.dart).
"use strict";

/** Приписка для магазинов (api/links.dart: unofficialNote). */
const MR_UNOFFICIAL = "Неофициальное приложение для студентов РТУ МИРЭА. Его сделали студенты, а не университет.";

/** Ачивки: id → ранг (achievements/catalog.dart), пока нет общего каталога. */
const MR_ACH_RANK = {
  lesson: "dawn", week_next: "dawn", goal: "dawn", sdo: "dawn", widget: "dawn", look: "dawn", ai: "dawn", summary: "dawn",
  remind: "dawn", teacher: "dawn", submit: "noon", week5: "noon", early: "noon", streak: "noon", plus: "noon", found: "noon",
  auto: "dusk", clean: "dusk", month: "dusk", calm: "dusk", t2222: "midnight", wave: "midnight", fri13: "midnight",
  secret: "midnight", one_of_us: "midnight",
};
const MR_RANK = {
  dawn: { pose: "morning", sky: ["#FFE7C2", "#FFB38A", "#F08A6E"], ink: "#5B2A1A" },
  noon: { pose: "day", sky: ["#7CC6FF", "#5BA6F7", "#3D8BF2"], ink: "#FFFFFF" },
  dusk: { pose: "evening", sky: ["#3B2A6E", "#B24B8F", "#FF9A5A"], ink: "#FFFFFF" },
  midnight: { pose: "night", sky: ["#0A0D2A", "#13173C", "#1A1F4D"], ink: "#FFE9A8" },
};

/** «подключи» / «устарел» в ответе /sdo/grades — нужен свой вход в СДО (sdo_connect.dart: needsSdo). */
function mrNeedsSdo(message) { return /подключи|устарел/.test(message); }
/** 13 → «13», 12.5 → «12,5» (goal_card.dart: fmtNum). */
function mrNum(v) { return v === Math.round(v) ? String(Math.round(v)) : v.toFixed(1).replace(".", ","); }
/** «@имя» → https://t.me/имя */
function mrUrl(v) { return v.startsWith("@") ? "https://t.me/" + v.slice(1) : v; }

// Ответы, которые помнятся на запуск (links.dart: appLinks; plusShown, donateShown)
let mrLinksMemo = null;
async function mrAppLinks() {
  if (mrLinksMemo) return mrLinksMemo;
  const m = await Api.get("/meta");
  const l = (m && m.links) || {};
  const out = {};
  for (const k of Object.keys(l)) out[k] = String(l[k] ?? "");
  return (mrLinksMemo = out);
}
const mrShown = {};
/** Показывать ли «Капибару+» (/plus) и «Поддержать проект» (/donate): сервер сказал hidden:false. */
async function mrShownBy(path) {
  if (path in mrShown) return mrShown[path];
  try {
    const r = await Api.get(path);
    return (mrShown[path] = !!r && typeof r === "object" && r.hidden === false);
  } catch (e) { return false; }
}

/** Баллы БРС одной фразой (PointsSummary): кусками [текст, жирный]. */
function mrPointsSummary(courses) {
  if (!courses.length) return { total: 0, parts: [["Пока пусто — преподаватели ещё не завели журналы.", false]] };
  let rated = 0, reached = 0;
  const firsts = [];
  for (const c of courses) {
    if (!c.marks.length) continue;
    const first = c.marks.reduce((a, b) => (b.at < a.at ? b : a));
    rated++;
    if (c.score >= first.at) reached++;
    if (!firsts.includes(first.label)) firsts.push(first.label);
  }
  firsts.sort((a, b) => (a === "зачёт" ? 1 : 0) - (b === "зачёт" ? 1 : 0));   // «3» раньше зачёта
  const total = courses.length;
  const average = Math.round(courses.reduce((s, c) => s + c.score, 0) / total);
  const lowest = total > 1 ? courses.reduce((a, b) => (b.score < a.score ? b : a)) : null;
  const of = (n) => plural(n, "предмета", "предметов", "предметов");
  if (courses.every((c) => c.score <= 0)) {
    return { total, average, parts: [[total > 1 ? `Баллов пока нет — ни в одном из ${total} ${of(total)}.` : "Баллов пока нет.", false]] };
  }
  const mark = firsts.map(markWord).join(" или ");
  const parts = [];
  if (rated > 0 && reached === 0) parts.push([`На ${mark} пока не хватает ни в одном из ${rated} ${of(rated)}.`, false]);
  if (reached > 0) parts.push([`На ${mark} хватает в `, false], [`${reached}\u00a0из\u00a0${rated}`, true], [` ${of(rated)}.`, false]);
  if (lowest) parts.push([" Меньше всего\u00a0— ", false], [lowest.title, true], [`, ${mrNum(lowest.score)}.`, false]);
  return { total, average, parts };
}

/** Значок в мягком квадрате цвета акцента — у плиток настроек (_IconBox). */
function mrIconBox(name, variant = "o") {
  return `<span class="mr-ibox">${icon(name, variant)}</span>`;
}
/** Строка меню: значок, название и пояснение (_MenuRow); act пусто — не нажимается. */
function mrMenuRow(ic, variant, title, sub, act, attrs = "") {
  const tag = act ? "button" : "div";
  return `<${tag} class="mr-mrow"${act ? ` data-act="${act}"` : ""}${attrs}>${icon(ic, variant, "color:var(--accent)")}
    <div class="grow"><div class="bd b6" style="--sz:16px">${esc(title)}</div><div class="bd mut" style="--sz:13px">${esc(sub)}</div></div>
    ${act ? icon("chevron_right", "", "color:var(--muted)") : ""}</${tag}>`;
}
/** Круглый значок ранга (RankBadge): общий из ачивок, если он уже есть. */
function mrRankBadge(rank, size, open = true) {
  if (typeof window.rankBadge === "function") return window.rankBadge(rank, size, open);
  const r = MR_RANK[rank] || MR_RANK.dawn;
  return `<span class="mr-badge${open ? "" : " off"}" style="width:${size}px;height:${size}px;background:linear-gradient(${r.sky.join(",")})">
    <span style="position:absolute;left:50%;top:${size * 0.3}px;transform:translateX(-50%)">${capy(r.pose, size * 0.58, r.ink)}</span></span>`;
}

/** Лист «Новости и связь» / «Капибара в других местах»: что за ссылка — и кнопка, решает человек (showLinksSheet). */
function mrLinksSheet(links, title = "Новости и связь") {
  return Sheet.show(`<div class="ttl" style="--sz:22px;margin-bottom:var(--m)">${esc(title)}</div>
    ${links.map(([ic, variant, name, sub, button, url], i) => `<div class="tile row mr-link">
      ${icon(ic, variant, "color:var(--accent)")}
      <div class="grow"><div class="bd b6" style="--sz:16px">${esc(name)}</div><div class="bd mut" style="--sz:13px">${esc(sub)}</div></div>
      <button class="mr-go" data-act="go" data-i="${i}">${esc(button)}</button></div>`).join("")}`,
  (body) => on(body, { go(b) { tick(); openLink(links[+b.dataset.i][5]); } }));
}
/** «Новости и связь»: канал бота и «Написать нам» — что задал сервер. */
function mrNewsLinks(l) {
  const out = [];
  if (l.channel) out.push(["campaign", "o", "Канал бота", "Новости, как всё устроено и что нового", "Открыть канал", mrUrl(l.channel)]);
  if (l.contact) out.push(["chat_bubble_outline", "", "Написать нам", "Идея, ошибка или вопрос — ответим", "Написать", mrUrl(l.contact)]);
  return out;
}
/** «Капибара в других местах» (places): бот и канал; «в браузере» — не в браузере же. */
function mrPlaces(l) {
  const out = [];
  if (l.bot) out.push(["send", "o", "Telegram-бот", "Расписание в чате, напоминания до пары и приложение прямо в Telegram", "Открыть", l.bot]);
  if (l.news) out.push(["campaign", "o", "Канал Капибары", "Новости и обновления", "Открыть", mrUrl(l.news)]);
  // приложение для Android — тем, кто не на iPhone (на iPhone ссылка на чужой магазин ни к чему)
  if (l.rustore && !/iPhone|iPad|iPod/.test(navigator.userAgent))
    out.push(["phone_android", "o", "Приложение для Android", "Капибара в RuStore — с виджетом и уведомлениями", "Открыть", l.rustore]);
  return out;
}

/** Календарь (_calendarSheet): пары и сроки — подпиской в календаре телефона. */
async function mrCalendarSheet() {
  const v = await Sheet.show(`<div class="ttl" style="--sz:24px">Календарь</div>
    <div class="bd mut" style="--sz:15px;margin-top:8px">Пары и сроки появятся в календаре телефона и будут обновляться сами.</div>
    <div style="height:var(--xl)"></div>
    <button class="btn primary" data-act="add">Добавить в календарь</button>
    <button class="btn text mr-cancel" data-act="copy">Скопировать ссылку</button>`,
  (body, close) => on(body, { add: () => close("add"), copy: () => close("copy") }));
  if (v === "add") await mrSubscribe(false);
  else if (v === "copy") await mrSubscribe(true);
}
async function mrSubscribe(copy) {
  let path;
  try {
    const r = await Api.get("/calendar/link");
    path = String((r && r.ics_path) || "");
    if (!path) { toast("Не получилось взять ссылку — попробуй позже", "error"); return; }
  } catch (e) { toast(errorText(e), "error"); return; }
  const https = location.origin + path;
  if (!copy) {
    let opened = null;
    try { opened = window.open("webcal://" + https.replace(/^https?:\/\//, ""), "_blank"); } catch (e) {}
    if (opened !== null) return;
  }
  try { await navigator.clipboard.writeText(https); }
  catch (e) { toast("Не удалось скопировать — попробуй ещё раз.", "error"); return; }
  toast(copy ? "Ссылка скопирована — в календаре: «Добавить подписку» и вставь её"
             : "Календарь не открылся — ссылка скопирована, добавь подписку в календаре", "done");
}

// ── «Ещё» нового дизайна (макет Е3, Никита 11.11; app/lib/screens/more_fresh.dart) ──
// Имя, группа и курс; ачивки и рейтинг одной карточкой; «Моя учёба»,
// «Настройки», «Ещё» строками; «Сообщество» и «О Капибаре» — листы.
// Баллов БРС здесь нет — они на «Учёбе».

/** «3 курс» по году поступления в конце названия группы (courseOfGroup); учебный год — с сентября. */
function mrCourseOf(name, at) {
  const m = /-(\d{2})$/.exec(String(name).trim());
  if (!m) return null;
  const start = at.getMonth() >= 8 ? at.getFullYear() : at.getFullYear() - 1;
  const n = start - (2000 + Number(m[1])) + 1;
  return n >= 1 && n <= 6 ? `${n}\u00a0курс` : null;
}
const MR_NOTIFY = [["morning", "утро"], ["lessons", "перед парой"], ["deadlines", "дедлайны"], ["weekly", "обзор недели"],
  ["grades", "новые баллы"], ["new_tasks", "новые задания"], ["evening", "вечер"]];
/** Что включено в «Уведомлениях» — одной строкой под пунктом (notifySummary). */
function mrNotifySummary(d) {
  if (!d || d.subscribed !== true) return "выключены";
  const prefs = d.prefs || {};
  const known = MR_NOTIFY.filter(([k]) => k in prefs);
  const onNow = known.filter(([k]) => prefs[k] === true).map(([, t]) => t);
  if (!onNow.length) return "ничего не включено";
  if (onNow.length === known.length) return "включены все";
  if (onNow.length <= 2) return onNow.join(", ");
  return `${onNow.slice(0, 2).join(", ")} и ещё ${onNow.length - 2}`;
}
/** Строка в «Ещё» нового вида: «только важное · тихо с 23:00» (freshNotifySummary). */
function mrFreshNotifySummary(d) {
  if (!d || d.subscribed !== true) return "выключены";
  const what = { important: "только важное", daily: "помощь каждый день", custom: "своя настройка" }[d.profile]
    || mrNotifySummary(d);                     // старый сервер наборов не знает
  const q = (d.quiet_hours && d.quiet_hours.from) || "23:00";
  return d.prefs && d.prefs.quiet === true ? `${what} · тихо с ${q}` : what;
}
/** «Тетрадь, книжный шрифт» — что сейчас в «Оформлении» (lookSummary). */
function mrLookSummary() {
  const r = document.documentElement.dataset;
  const theme = { night: "Ночная тетрадь", depth: "Глубина" }[r.appTheme] || "Тетрадь";
  return `${theme}, ${r.font === "strict" ? "строгий" : "книжный"} шрифт`;
}
/** Строка списка (_FreshRow): значок в мягком квадрате, название, пояснение и стрелка; act пусто — не нажимается. */
function mrFRow(act, ic, variant, title, sub = "", { key = "", subCls = "", danger = false } = {}) {
  const tag = act ? "button" : "div";
  return `<${tag} class="mf-row${danger ? " da" : ""}"${act ? ` data-act="${act}"` : ""}${key ? ` data-key="${key}"` : ""}>
    <span class="mf-ic">${icon(ic, variant)}</span>
    <span class="grow"><span class="bd mf-t">${esc(title)}</span>${sub ? `<span class="bd mf-s${subCls ? " " + subCls : ""}">${esc(sub)}</span>` : ""}</span>
    ${act && !danger ? icon("chevron_right", "", "color:var(--muted)") : ""}</${tag}>`;
}
/** Карточка-список (_FreshList): строки через тонкую линию; пустые пропускаются. */
function mrFList(rows) { return `<div class="tile p0 mf-list">${rows.filter(Boolean).join('<div class="divider"></div>')}</div>`; }
/** Лист нового вида: заголовок и карточки на цвете экрана; пункт сначала закрывает лист, потом делает своё. */
function mrFSheet(title, html, acts, { keep = false } = {}) {
  return Sheet.show(`<div class="ttl" style="--sz:22px;margin-bottom:var(--m)">${esc(title)}</div>${html}`, (b, close, sh) => {
    sh.classList.add("mf-sheet");
    const wrapped = {};
    for (const [k, f] of Object.entries(acts)) wrapped[k] = (el) => { if (!keep) close(); f(el, b); };
    on(b, wrapped);
  });
}
/** Ранг ачивки: из общего каталога, если он уже есть. */
function mrRankOf(id) {
  const a = Array.isArray(window.ACHIEVEMENTS) && window.ACHIEVEMENTS.find((x) => x.id === id);
  return (a && a.rank) || MR_ACH_RANK[id] || "dawn";
}
function mrAchTotal() { return Array.isArray(window.ACHIEVEMENTS) ? window.ACHIEVEMENTS.length : Object.keys(MR_ACH_RANK).length; }

Screens.more = {
  mount(body, screen) {
    const st = { me: null, error: null, points: null, pointsFailed: false, pointsBusy: false, rating: undefined,
      links: {}, plus: false, donate: false, optPending: [], optAnswers: {}, adminNote: null, notify: null };

    // ── баллы: грузятся сами по себе, СДО не отвечает — остальной экран работает ──
    const fetchPoints = async () => {
      try {
        const j = await Api.get("/sdo/grades");
        return { courses: ((j && j.courses) || []).map(courseOf), problem: null };
      } catch (e) {
        if (e.status) return { courses: [], problem: e.message };
        throw e;
      }
    };
    const loadPoints = async (cache = true) => {
      st.pointsBusy = true;
      try {
        if (cache && !st.points) {
          const c = Api.cached("/sdo/grades");
          if (c && c.courses) { st.points = { courses: c.courses.map(courseOf), problem: null }; draw(); }
        }
        st.points = await fetchPoints();
        st.pointsFailed = false;
      } catch (e) { st.pointsFailed = !st.points; }
      st.pointsBusy = false;
      draw();
    };
    const loadRating = () => Api.get("/rating").then((v) => v, () => null).then((v) => { st.rating = v; draw(); });
    const loadOptional = async () => {
      try {
        const r = await Api.get("/optional");
        st.optPending = ((r && r.pending) || []).map(String);
        st.optAnswers = {};
        for (const [k, v] of Object.entries((r && r.answers) || {})) st.optAnswers[k] = v === true;
        draw();
      } catch (e) {}
    };
    const loadNotify = () => Api.get("/notify").then((v) => { st.notify = v; draw(); }, () => {});
    const loadExtras = () => {
      mrAppLinks().catch(() => ({})).then((l) => { st.links = l; draw(); });
      mrShownBy("/plus").then((v) => { st.plus = v; draw(); });
      mrShownBy("/donate").then((v) => { st.donate = v; draw(); });
    };

    const profile = (me) => {
      const first = String(me.first_name || "").trim(), user = String(me.username || "").trim();
      const name = first || (user ? "@" + user : "Ещё");
      const letter = first ? [...first][0].toUpperCase() : "";
      return `<div class="mr-prof"><div class="mr-ava" aria-hidden="true">${letter ? esc(letter) : icon("person")}</div>
        <div class="grow"><div class="nm" style="--sz:22px">${esc(name)}</div>
        <div class="bd mut" style="--sz:14px;margin-top:2px">${esc((me.group && me.group.name) || "группа не выбрана")}</div></div></div>`;
    };
    const quiet = (text, act, { title = "", ic = "cloud_off" } = {}) => `<div class="hx"><button class="tile row mr-quiet${title ? " big" : ""}" data-act="${act}">
      ${title ? mrIconBox(ic) : icon(ic, "", "font-size:20px;color:var(--muted)")}
      <div class="grow">${title ? `<div class="bd b6" style="--sz:16px">${esc(title)}</div>` : ""}<div class="bd mut" style="--sz:13px">${esc(text)}</div></div>
      ${title ? icon("chevron_right", "", "color:var(--muted)") : ""}</button></div>`;
    const points = () => {
      const d = st.points;
      if (!d && st.pointsFailed) return quiet("Баллы не загрузились — нажми, чтобы попробовать ещё раз", "points-retry");
      if (d && d.problem) {
        if (mrNeedsSdo(d.problem)) {
          return quiet("Баллы БРС по каждому предмету и сколько до зачёта или «3»", "sdo", { ic: "school",
            title: d.problem.includes("устарел") ? "Вход в СДО устарел — подключи заново" : "Подключи СДО — тут будут баллы" });
        }
        return quiet("Баллы не видны: " + d.problem, "points-retry");
      }
      const sum = d ? mrPointsSummary(d.courses) : null;
      const words = `<div class="bd mr-words">${sum ? sum.parts.map(([t, b]) => (b ? `<b>${esc(t)}</b>` : esc(t))).join("")
        : '<span class="mut">Считаю баллы…</span>'}</div>`;
      const num = sum && sum.total ? `<div class="num" style="--sz:44px">${sum.average}</div>` : "";
      return `<div class="hx"><button class="tile mr-points" data-act="study">
        <div class="row"><div class="bd mut grow" style="--sz:13px">Баллы БРС, в среднем</div>${icon("chevron_right", "", "font-size:20px;color:var(--muted)")}</div>
        <div style="height:var(--s)"></div>${num ? `<div class="mr-pbody">${num}${words}</div>` : words}</button></div>`;
    };
    const achRow = () => {
      const got = Ach.done;
      const total = mrAchTotal(), rankOf = mrRankOf;
      const last = Object.entries(got).filter(([id]) => rankOf(id)).sort((a, b) => String(b[1]).localeCompare(String(a[1]))).slice(0, 3);
      const n = Object.keys(got).length;
      const badges = !last.length ? mrRankBadge("dawn", 36, false)
        : last.slice().reverse().map(([id], i) => `<span class="mr-bwrap" style="left:${18 * (last.length - 1 - i)}px">${mrRankBadge(rankOf(id), 36)}</span>`).join("");
      return `<div class="hx"><button class="tile row mr-ach" data-act="ach">
        <span class="mr-badges" style="width:${36 + 18 * Math.max(0, last.length - 1)}px">${badges}</span>
        <div class="grow"><div class="row" style="gap:0"><span class="bd b7 grow" style="--sz:15px">Ачивки</span>
          <span class="bd mut" style="--sz:13px">${Math.min(n, total)} из ${total}</span></div>
          <div class="progress" style="height:6px;margin-top:6px;border-radius:4px"><i style="width:${Math.min(1, n / total) * 100}%"></i></div></div>
        ${icon("chevron_right", "", "color:var(--muted)")}</button></div>`;
    };
    const ratingLine = (data) => {
      const g = data && data.group;
      if (!g || g.place == null) return "места групп в институте и вузе";
      const inst = g.institute;
      return inst && g.place_inst != null ? `${g.place_inst} место в ${inst} · ${g.place} в вузе` : `${g.place} место в вузе`;
    };
    const ratingRowHtml = () => `<div class="hx"><button class="tile row mr-rate" data-act="rating">
      ${icon("leaderboard", "o", "color:var(--accent)")}
      <div class="grow"><div class="bd b7" style="--sz:15px">Рейтинг</div><div class="bd mut" style="--sz:13px">${esc(ratingLine(st.rating))}</div></div>
      ${icon("chevron_right", "", "color:var(--muted)")}</button></div>`;
    const tiles = () => {
      const items = [["notify", "notifications_none", "", "Уведомления"], ["look", "palette", "o", Theme.design2 ? "Оформление" : "Тема и шрифт"],
        ["security", "shield", "o", "Безопасность"], ["calendar", "event_available", "o", "Календарь"], ["group", "swap_horiz", "", "Группа"]];
      if (mrNewsLinks(st.links).length) items.push(["links", "forum", "o", "Новости и связь"]);
      if (st.plus) items.push(["plus", "workspace_premium", "o", "Капибара+"]);
      let out = "";
      for (let i = 0; i < items.length; i += 2) {
        const one = ([act, ic, v, t], wide) => `<button class="tile mr-set${wide ? " wide" : ""}" data-act="${act}" data-key="more:${act}">
          ${mrIconBox(ic, v)}<span class="bd b6 mr-st">${esc(t)}</span></button>`;
        out += i + 1 < items.length ? `<div class="mr-pair">${one(items[i])}${one(items[i + 1])}</div>` : one(items[i], true);
      }
      return `<div class="hx mr-grid">${out}</div>`;
    };
    const optional = () => {
      const subjects = [...st.optPending, ...Object.keys(st.optAnswers).filter((k) => !st.optPending.includes(k))];
      if (!subjects.length) return "";
      return section("Предметы по выбору") + subjects.map((s, i) => {
        const pending = st.optPending.includes(s);
        const text = pending ? "Ходишь? Если нет — уберу эти пары из твоего расписания." : st.optAnswers[s] ? "Хожу — пары в расписании" : "Не хожу — пары скрыты";
        const choice = (attend) => {
          const onNow = st.optAnswers[s] === attend;
          return `<button class="mr-choice${onNow ? " on" : ""}" data-act="opt" data-i="${i}" data-a="${attend ? 1 : 0}"${onNow ? " disabled" : ""}>${attend ? "Хожу" : "Не хожу"}</button>`;
        };
        return `<div class="hx" style="margin-bottom:var(--s)"><div class="tile">
          <div class="row">${icon("military_tech", "o", "color:var(--accent)")}<div class="bd b6 grow" style="--sz:16px">${esc(s)}</div></div>
          <div class="bd mut" style="--sz:13px;margin-top:4px">${esc(text)}</div>
          <div class="row" style="gap:var(--s);margin-top:var(--m)">${choice(true)}${choice(false)}</div></div></div>`;
      }).join("");
    };
    const menu = () => {
      const rows = [
        mrMenuRow("lightbulb", "o", "Как пользоваться", "короткий тур: что где и какие есть жесты", "tour"),
        mrMenuRow("devices_other", "o", "Капибара в других местах", "Telegram-бот, браузер и компьютер", "places"),
        mrMenuRow("group_add", "o", "Позвать", "готовое сообщение со ссылкой — другу или в чат группы", "invite"),
      ];
      if (st.donate) {
        rows.push(mrMenuRow("favorite_border", "", "Поддержать проект", "разово, сумма на выбор", "donate", ' data-key="more:donate"'));
        rows.push(mrMenuRow("push_pin", "o", "Роадмап", "что дальше — для тех, кто поддержал", "roadmap", ' data-key="more:roadmap"'));
      }
      const g = st.me.group;
      if (g && g.own !== true) {
        rows.push(mrMenuRow("verified_user", "o", "Я староста этой группы", st.adminNote || "спрошу владельца бота — сможешь вести общие сроки и ДЗ",
          st.adminNote ? "" : "admin"));
      }
      return `<div class="hx"><div class="tile p0">${rows.join('<div class="divider"></div>')}</div></div>`;
    };

    const optSubjects = () => [...st.optPending, ...Object.keys(st.optAnswers).filter((k) => !st.optPending.includes(k))];
    const freshHtml = () => {
      const me = st.me;
      const first = String(me.first_name || "").trim(), user = String(me.username || "").trim();
      const name = first || (user ? "@" + user : "Ещё");
      const g = me.group, group = g && g.name ? String(g.name) : "";
      const course = mrCourseOf(group, now());
      const chev = icon("chevron_right", "", "color:var(--muted)");
      // ачивки: значок последней полученной (ни одной — закрытый «Рассвет»), «N из 25» и полоска
      const got = Ach.done, n = Object.keys(got).length, total = mrAchTotal();
      const last = Object.entries(got).sort((a, b) => String(b[1]).localeCompare(String(a[1])))[0];
      const ach = `<button class="mf-row mf-big" data-act="ach" data-key="more:achievements">
        ${last ? mrRankBadge(mrRankOf(last[0]), 52) : mrRankBadge("dawn", 52, false)}
        <span class="grow"><span class="row" style="gap:var(--s)"><span class="bd mf-t big grow">Ачивки</span>
          <span class="bd mut" style="--sz:13px">${Math.min(n, total)}\u00a0из\u00a0${total}</span></span>
          <span class="progress mf-bar"><i style="width:${Math.min(1, n / total) * 100}%"></i></span></span>${chev}</button>`;
      // рейтинг: место группы в институте, иначе в вузе
      const rg = st.rating && st.rating.group;
      const inst = rg && rg.place_inst != null ? rg.place_inst : null;
      const place = inst != null ? inst : (rg && rg.place != null ? rg.place : null);
      const rname = rg && rg.name ? String(rg.name) : group;
      const rline = place == null ? "места групп в институте и вузе"
        : `${rname} на ${place}\u00a0месте ${inst != null ? "в\u00a0институте" : "в\u00a0вузе"}`;
      const rating = `<button class="mf-row mf-big" data-act="rating" data-key="more:rating">
        <span class="mf-place">${place == null ? icon("leaderboard", "o") : `<span class="num">${esc(place)}</span>`}</span>
        <span class="grow"><span class="bd mf-t big">Рейтинг</span><span class="bd mf-s">${esc(rline)}</span></span>${chev}</button>`;
      const subjects = optSubjects();
      let opt = "";
      if (subjects.length) {
        const s0 = subjects[0];
        const state = st.optPending.includes(s0) ? "ходишь?" : st.optAnswers[s0] ? "хожу" : "не хожу";
        opt = mrFRow("optional", "school", "o", "Предметы по выбору",
          `${s0}: ${state}${subjects.length > 1 ? ` · ещё ${subjects.length - 1}` : ""}`,
          { key: "more:optional", subCls: st.optPending.length ? "ac" : "" });
      }
      const news = mrNewsLinks(st.links).length > 0;
      return `<div class="row mf-head"><div class="grow"><div class="ttl mf-name" style="--sz:30px">${esc(name)}</div>
          <div class="bd mut" style="--sz:13px;margin-top:6px">${esc(group ? [group, course].filter(Boolean).join(" · ") : "группа не выбрана")}</div></div>
          <span class="mf-capy" aria-hidden="true">${capy("joy", 62)}</span></div>
        <div class="hx">${mrFList([ach, rating])}</div>
        ${section("Моя учёба")}
        <div class="hx">${mrFList([
          mrFRow("group", "group", "o", "Сменить мою группу", group ? "сейчас " + group : "группа не выбрана", { key: "more:group" }),
          g && g.own !== true ? mrFRow(st.adminNote ? "" : "admin", "verified_user", "o", "Я староста этой группы",
            st.adminNote || "спрошу владельца бота — сможешь вести общие сроки и ДЗ") : "",
          opt,
          mrFRow("calendar", "event_available", "o", "Добавить в\u00a0календарь телефона", "", { key: "more:calendar" }),
        ])}</div>
        ${section("Настройки")}
        <div class="hx">${mrFList([
          mrFRow("notify", "notifications_none", "", "Уведомления", st.notify ? mrFreshNotifySummary(st.notify) : "", { key: "more:notify" }),
          mrFRow("look", "palette", "o", "Оформление", mrLookSummary(), { key: "more:theme" }),
          mrFRow("security", "shield", "o", "Безопасность и мои данные", "", { key: "more:security" }),
        ])}</div>
        ${section("Ещё")}
        <div class="hx">${mrFList([
          mrFRow("community", "person_add_alt", "o", "Сообщество", news ? "позвать друга, новости и связь" : "позвать друга или группу", { key: "more:community" }),
          mrFRow("about", "lightbulb", "o", "О Капибаре", st.plus || st.donate ? "как пользоваться, другие устройства, поддержка"
            : "как пользоваться и другие устройства", { key: "more:about" }),
        ])}</div>
        <div style="height:var(--m)"></div>
        <div class="hx">${mrFList([mrFRow("logout", "logout", "", "Выйти", "", { key: "more:logout", danger: true })])}</div>
        <div style="height:120px"></div>`;
    };

    const draw = () => {
      if (!st.me) {
        body.innerHTML = st.error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(st.error), { pose: "sad", retry: "retry" }) : spinner();
        return;
      }
      if (Theme.fresh) { body.innerHTML = freshHtml(); return; }
      body.innerHTML = profile(st.me) + points() + '<div style="height:var(--m)"></div>' + achRow()
        + '<div style="height:var(--s)"></div>' + ratingRowHtml() + '<div style="height:var(--m)"></div>' + tiles()
        + optional() + '<div style="height:var(--m)"></div>' + menu() + '<div style="height:var(--s)"></div>'
        + `<div class="hx"><button class="tile row" data-act="logout">${icon("logout", "", "color:var(--danger)")}
            <span class="bd b6" style="--sz:15px;color:var(--danger)">Выйти</span></button></div>`
        + `<div class="bd mut mr-note">${esc(MR_UNOFFICIAL)}</div><div style="height:120px"></div>`;
      fitTiles();
    };
    // один размер надписей на всю сетку: самое длинное слово влезает в половину строки (_TileGrid._fit)
    const fitTiles = () => {
      const half = body.querySelector(".mr-pair .mr-set");
      if (!half) return;
      const width = half.clientWidth - 2 * 12 - 2;
      const c = document.createElement("canvas").getContext("2d");
      c.font = "600 15px Onest";
      let widest = 0;
      body.querySelectorAll(".mr-st").forEach((el) => el.textContent.split(" ").forEach((w) => { widest = Math.max(widest, c.measureText(w).width); }));
      const sz = widest <= width ? 15 : (15 * width / widest) * 0.98;
      body.querySelectorAll(".mr-st").forEach((el) => el.style.setProperty("--sz", sz + "px"));
    };

    const load = async () => {
      try {
        const me = await Api.get("/me");
        const first = !st.me;
        st.me = me || {};
        st.error = null;
        draw();
        // баллов в новом «Ещё» нет — они на «Учёбе»
        if (!Theme.fresh && (first || !st.pointsBusy)) loadPoints(first);
      } catch (e) {
        if (e.status === 401) return;
        st.error = e;
        if (!st.me) draw();
      }
    };

    // ответ «хожу / не хожу» на предмет по выбору — и в прежнем экране, и в листе нового
    const answerOpt = async (s, attend) => {
      try { await Api.post("/optional", { subject: s, attend }); }
      catch (e) { toast("Не сохранилось: " + errorText(e), "error"); return false; }
      st.optPending = st.optPending.filter((x) => x !== s);
      st.optAnswers[s] = attend;
      draw();
      toast(attend ? `Пары «${s}» будут в расписании` : `Убрал «${s}» из расписания`, "done");
      return true;
    };
    const acts = {
      retry() { st.error = null; draw(); load(); },
      study() { tick(); Tabs.show(3); },
      "points-retry"() { tick(); loadPoints(false); },
      async sdo() {
        tick();
        if (typeof window.openSdoConnect !== "function") { toast("Скоро"); return; }
        await window.openSdoConnect();
        if (Tabs.screens[3]) { const s = Tabs.screens[3]; if (typeof s.cleanup === "function") s.cleanup(); s.mounted = false; s.body.innerHTML = ""; }
        loadPoints(false);
      },
      async ach() {
        tick();
        if (typeof window.openAchievements === "function") window.openAchievements(); else toast("Скоро");
      },
      async rating() {
        tick();
        if (typeof window.openRating !== "function") { toast("Скоро"); return; }
        await window.openRating();
        loadRating();
      },
      notify() {
        tick();
        // новый вид и сервер знает наборы — «Что присылать» (У2), иначе прежний экран
        if (Theme.fresh && (!st.notify || "profile" in st.notify)) window.openNotifyHome(() => loadNotify());
        else window.openNotify(() => loadNotify());
      },
      look() { tick(); window.openLook(); },
      security() { tick(); window.openSecurity(); },
      calendar() { tick(); mrCalendarSheet(); },
      async group() {
        tick();
        const g = await window.openGroupPick();
        if (g) Tabs.rebuild();
      },
      links() { tick(); mrLinksSheet(mrNewsLinks(st.links)); },
      plus() { tick(); if (typeof window.openPlus === "function") window.openPlus(); else toast("Скоро"); },
      tour() { tick(); window.showTour(); },
      async places() {
        tick();
        let l;
        try { l = await mrAppLinks(); } catch (e) { toast(errorText(e), "error"); return; }
        mrLinksSheet(mrPlaces(l), "Капибара в других местах");
      },
      invite() { tick(); if (typeof window.openInvite === "function") window.openInvite(); else toast("Скоро"); },
      donate() { tick(); if (typeof window.openDonate === "function") window.openDonate(); else toast("Скоро"); },
      roadmap() { tick(); if (typeof window.openRoadmap === "function") window.openRoadmap(); else toast("Скоро"); },
      async admin() {
        tick();
        try { await Api.post("/me/group/admin"); st.adminNote = "Запрос отправлен — ответ придёт в бота."; }
        catch (e) { st.adminNote = errorText(e); }
        draw();
      },
      async opt(b) {
        tick();
        await answerOpt(optSubjects()[+b.dataset.i], b.dataset.a === "1");
      },
      // ── новый вид: листы «Сообщество», «О Капибаре», «Предметы по выбору» ──
      community() {
        tick();
        const news = mrNewsLinks(st.links), ch = !!st.links.channel, co = !!st.links.contact;
        mrFSheet("Сообщество", mrFList([
          mrFRow("invite", "person_add_alt", "o", "Позвать", "готовое сообщение другу или в\u00a0чат группы", { key: "more:invite" }),
          news.length ? mrFRow("links", "chat_bubble_outline", "", "Новости и связь",
            ch && co ? "канал Капибары и «Написать нам»" : ch ? "канал Капибары" : "«Написать нам»", { key: "more:links" }) : "",
        ]), { invite: () => acts.invite(), links: () => acts.links() });
      },
      about() {
        tick();
        // на iPhone сервер «Капибару+» и «Поддержать» не показывает — и в листе их нет (App Store 3.1.1)
        const paid = st.plus || st.donate ? '<div style="height:var(--m)"></div>' + mrFList([
          st.plus ? mrFRow("plus", "star_outline", "", "Капибара+", "", { key: "more:plus" }) : "",
          st.donate ? mrFRow("donate", "favorite_border", "", "Поддержать проект", "разово, сумма на выбор", { key: "more:donate" }) : "",
          st.donate ? mrFRow("roadmap", "push_pin", "o", "Роадмап", "что дальше, для тех, кто поддержал", { key: "more:roadmap" }) : "",
        ]) : "";
        mrFSheet("О Капибаре", mrFList([
          mrFRow("tour", "lightbulb", "o", "Как пользоваться", "короткий тур: что где и какие есть жесты", { key: "more:tour" }),
          mrFRow("places", "devices_other", "o", "Капибара в других местах", "Telegram-бот, браузер и компьютер", { key: "more:places" }),
        ]) + paid + `<div class="bd mut" style="--sz:13px;margin-top:var(--m)">${esc(MR_UNOFFICIAL)}</div>`,
        { tour: () => acts.tour(), places: () => acts.places(), plus: () => acts.plus(), donate: () => acts.donate(), roadmap: () => acts.roadmap() });
      },
      optional() {
        tick();
        const list = optSubjects();   // порядок не меняется, пока лист открыт
        const cards = () => list.map((s) => {
          const text = st.optPending.includes(s) ? "Ходишь? Если нет — уберу эти пары из твоего расписания."
            : st.optAnswers[s] ? "Хожу — пары в расписании" : "Не хожу — пары скрыты";
          const choice = (attend) => {
            const onNow = st.optAnswers[s] === attend && !st.optPending.includes(s);
            return `<button class="mr-choice${onNow ? " on" : ""}" data-act="fopt" data-s="${esc(s)}" data-a="${attend ? 1 : 0}"${onNow ? " disabled" : ""}>${attend ? "Хожу" : "Не хожу"}</button>`;
          };
          return `<div class="tile mf-opt"><div class="row">${icon("military_tech", "o", "color:var(--accent)")}<div class="bd b6 grow" style="--sz:16px">${esc(s)}</div></div>
            <div class="bd mut" style="--sz:13px;margin-top:4px">${esc(text)}</div>
            <div class="row" style="gap:var(--s);margin-top:var(--m)">${choice(true)}${choice(false)}</div></div>`;
        }).join("");
        mrFSheet("Предметы по выбору", `<div class="mf-opts">${cards()}</div>`, {
          async fopt(el, b) {
            tick();
            if (await answerOpt(el.dataset.s, el.dataset.a === "1")) b.querySelector(".mf-opts").innerHTML = cards();
          },
        }, { keep: true });
      },
      async logout() {
        const ok = await confirmSheet({ title: "Выйти?", text: "На этом устройстве. Войти снова — через бота.", action: "Выйти", cancel: "Остаться", danger: true });
        if (ok) logout();
      },
    };
    on(body, acts);

    // сразу — из запаса телефона, свежие следом (Loader.fromCache)
    const c = Api.cached("/me");
    if (c) st.me = c;
    draw();
    load();
    loadRating();
    loadOptional();
    loadExtras();
    if (Theme.fresh) loadNotify();
    // вернулся из «Уведомлений» или с другой вкладки — строка под ними свежая
    screen.mrDraw = () => { if (st.me) draw(); if (Theme.fresh) loadNotify(); };
    pullRefresh(screen, () => Promise.all([load(), loadRating(), loadOptional(), loadExtras(), Theme.fresh ? loadNotify() : null]));
  },
  // ачивки могли открыться на других вкладках — строка ачивок свежая
  onShow(body, screen) { if (screen.mrDraw) screen.mrDraw(); },
};
