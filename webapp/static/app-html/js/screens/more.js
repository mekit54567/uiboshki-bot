// «Ещё» (app/lib/screens/more.dart, дизайн 23Б): сверху кто я и группа, под
// ними баллы БРС одной цифрой и одной фразой (нажал — «Учёба»), ачивки и
// рейтинг строками, настройки плитками по две; действия с пояснениями —
// строками под плитками, «Выйти» и приписка для магазинов. Экраны настроек
// (Уведомления, Оформление, Безопасность, Группа, тур) — js/screens/settings.js.
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
  if (reached > 0) parts.push([`На ${mark} хватает в `, false], [`${reached} из ${rated}`, true], [` ${of(rated)}.`, false]);
  if (lowest) parts.push([" Меньше всего — ", false], [lowest.title, true], [`, ${mrNum(lowest.score)}.`, false]);
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

Screens.more = {
  mount(body, screen) {
    const st = { me: null, error: null, points: null, pointsFailed: false, pointsBusy: false, rating: undefined,
      links: {}, plus: false, donate: false, optPending: [], optAnswers: {}, adminNote: null };

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
      const total = Array.isArray(window.ACHIEVEMENTS) ? window.ACHIEVEMENTS.length : Object.keys(MR_ACH_RANK).length;
      const rankOf = (id) => {
        const a = Array.isArray(window.ACHIEVEMENTS) && window.ACHIEVEMENTS.find((x) => x.id === id);
        return (a && a.rank) || MR_ACH_RANK[id] || "dawn";
      };
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

    const draw = () => {
      if (!st.me) {
        body.innerHTML = st.error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(st.error), { pose: "sad", retry: "retry" }) : spinner();
        return;
      }
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
        if (first || !st.pointsBusy) loadPoints(first);
      } catch (e) {
        if (e.status === 401) return;
        st.error = e;
        if (!st.me) draw();
      }
    };

    on(body, {
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
      notify() { tick(); window.openNotify(); },
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
        const subjects = [...st.optPending, ...Object.keys(st.optAnswers).filter((k) => !st.optPending.includes(k))];
        const s = subjects[+b.dataset.i], attend = b.dataset.a === "1";
        try { await Api.post("/optional", { subject: s, attend }); }
        catch (e) { toast("Не сохранилось: " + errorText(e), "error"); return; }
        st.optPending = st.optPending.filter((x) => x !== s);
        st.optAnswers[s] = attend;
        draw();
        toast(attend ? `Пары «${s}» будут в расписании` : `Убрал «${s}» из расписания`, "done");
      },
      async logout() {
        const ok = await confirmSheet({ title: "Выйти?", text: "На этом устройстве. Войти снова — через бота.", action: "Выйти", cancel: "Остаться", danger: true });
        if (ok) logout();
      },
    });

    // сразу — из запаса телефона, свежие следом (Loader.fromCache)
    const c = Api.cached("/me");
    if (c) st.me = c;
    draw();
    load();
    loadRating();
    loadOptional();
    loadExtras();
    screen.mrDraw = () => { if (st.me) draw(); };
    pullRefresh(screen, () => Promise.all([load(), loadRating(), loadOptional(), loadExtras()]));
  },
  // ачивки могли открыться на других вкладках — строка ачивок свежая
  onShow(body, screen) { if (screen.mrDraw) screen.mrDraw(); },
};
