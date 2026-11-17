// «Рейтинг» нового дизайна (screens/rating_fresh.dart, шаг 7): открывается на
// «Я» — своё место в группе, институте и вузе; «Группы» — места групп; ник,
// видимость и из чего опыт — в листе «Мой опыт». Только при «Новом»; экран
// и обработчики — в openRating (extras.js), здесь — разметка.

/** 2940 → «2 940» (неразрывный пробел). */
function rfN(v) {
  const n = Math.trunc(+v || 0);
  return (n < 0 ? "-" : "") + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
}
const rfPeople = (n) => `${rfN(n)}\u00A0${plural(Math.trunc(n), "человек", "человека", "человек")}`;
const rfGroups = (n) => `${rfN(n)}\u00A0${plural(Math.trunc(n), "группа", "группы", "групп")}`;

/** «До 3 места 26 опыта: это 2 работы, сданные заранее» (ratingUpHint). */
function rfUpHint(scope, rules) {
  const place = scope.place ?? null, up = scope.up ?? null;
  if (place == null) return "Место появится с первым опытом: за баллы БРС и сданные работы.";
  if (place === 1) return (scope.of || 0) > 1 ? "Ты на первом месте." : "Пока опыт здесь только у тебя.";
  if (up == null || up <= 0) return "";
  const head = `До ${place - 1}\u00A0места ${rfN(up)} опыта`;
  const brs = Math.max(1, Math.trunc(rules.brs ?? 1)), submit = Math.trunc(rules.submit ?? 15), early = Math.trunc(rules.early ?? 10);
  const points = Math.ceil(up / brs);
  if (points <= 5) return `${head}: это ${points} ${plural(points, "балл", "балла", "баллов")} БРС`;
  if (up <= submit) return `${head}: это одна сданная работа`;
  if (up <= submit + early) return `${head}: это одна работа, сданная заранее`;
  const k = Math.ceil(up / (submit + early));
  if (k > 9) return head;
  return `${head}: это ${k} ${plural(k, "работа, сданная", "работы, сданные", "работ, сданных")} заранее`;
}

/** Переключатель-капсула: accent — главный («Я | Группы»), иначе тёмный. */
function rfTabs(id, labels, on, act, accent = false) {
  return `<div class="${accent ? "dl-seg" : "rf-tabs"}" id="${id}">${labels.map((t, i) =>
    `<button class="${i === on ? "on" : ""}" data-act="${act}" data-i="${i}" id="${id}-${i}" aria-pressed="${i === on}">${esc(t)}</button>`).join("")}</div>`;
}

/** Сводка: подписи сверху, крупное место слева, число справа, пояснение. */
function rfSummary({ id, eyebrow, place, placeText, sideEyebrow, sideValue, sideSub = "", sideColor = "muted", footer = "" }) {
  const p = place == null ? "—" : String(place);
  return `<div class="tile rf-sum" id="${id}">
    <div class="row rf-eyes"><span class="eyebrow grow ell">${esc(eyebrow)}</span><span class="eyebrow">${esc(sideEyebrow)}</span></div>
    <div class="row rf-big"><div class="grow rf-place"><span class="num" style="--sz:${p.length > 3 ? 44 : 54}px">${esc(p)}</span>
        <span class="bd mut" style="--sz:15px">${esc(placeText)}</span></div>
      <div class="rf-side" id="${id}-side"><div class="num" style="--sz:30px">${esc(sideValue)}</div>
        ${sideSub ? `<div class="bd b6" style="--sz:13px;margin-top:4px;color:var(--${sideColor})">${esc(sideSub)}</div>` : ""}</div></div>
    ${footer ? `<div class="bd mut" id="${id}-hint" style="--sz:14px;margin-top:var(--m)">${esc(footer)}</div>` : ""}</div>`;
}

/** Кружок с местом; без места — пунктир с точкой (скрытый, пропуск). */
function rfDot(place, me = false) {
  if (place == null) {
    return `<span class="rf-dot dots"><svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="none" stroke="var(--muted)" stroke-opacity=".7" stroke-width="2" stroke-linecap="round" stroke-dasharray="0 5.89"/>
      <circle cx="16" cy="16" r="1.6" fill="var(--muted)" fill-opacity=".7"/></svg></span>`;
  }
  const t = String(place);
  return `<span class="rf-dot${me ? " me" : ""}${t.length > 3 ? " d4" : t.length > 2 ? " d3" : ""}">${esc(t)}</span>`;
}

/** Строка списка. tag — «button» с act для нажатия. */
function rfLine({ id = "", lead, title, sub = "", xp = null, me = false, quiet = false, act = "", data = "" }) {
  const tag = act ? "button" : "div";
  return `<${tag} class="row rf-line${me ? " me" : ""}"${id ? ` id="${id}"` : ""}${act ? ` data-act="${act}"${data}` : ""}>${lead}
    <div class="grow">${quiet ? `<div class="bd mut clamp2" style="--sz:14px">${esc(title)}</div>`
      : `<div class="bd b6 ell" style="--sz:15px">${esc(title)}</div>`}
      ${sub ? `<div class="bd mut ell" style="--sz:12.5px">${esc(sub)}</div>` : ""}</div>
    ${xp != null ? `<span class="num" style="--sz:16px">${esc(xp)}</span>` : ""}${act ? icon("chevron_right", "", "font-size:18px;color:var(--muted);margin-left:-8px") : ""}</${tag}>`;
}
const rfList = (items) => `<div class="tile p0 rf-list">${items.join('<div class="divider"></div>')}</div>`;

/** Люди вкладки «Я»: в группе хвост сворачивается в «ещё N человек». */
function rfPeopleList(rows, me, scope, collapse) {
  if (!rows.length) {
    return `<div class="tile"><div class="bd mut" style="--sz:14px">Здесь пока никого с опытом. Он появится за баллы БРС и сданные работы.</div></div>`;
  }
  const meSub = (r) => (r.seen === true ? "это ты" : scope !== "group" && me.show === true ? "это ты · видят только свои" : "это ты · другим не видно");
  const mine = rows.findIndex((r) => r.me === true);
  let cut = rows.length;
  if (collapse && rows.length > 8) {
    cut = Math.max(5, mine + 2);
    if (cut >= rows.length - 1) cut = rows.length;
  }
  const shown = rows.slice(0, cut), rest = rows.slice(cut), hidden = rest.filter((r) => r.hidden === true).length;
  const items = shown.map((r, i) => {
    if (r.gap != null) return rfLine({ lead: rfDot(null), title: `${i === shown.length - 1 ? "ещё" : "дальше"} ${rfPeople(r.gap)}`, quiet: true });
    if (r.hidden === true) return rfLine({ id: `rating-hidden-${r.place}`, lead: rfDot(null), title: `${r.place}\u00A0место не показывает себя`, quiet: true });
    return rfLine({ id: r.me === true ? "rating-row-me" : `rating-row-${r.place}`, lead: rfDot(r.place, r.me === true), title: r.nick || "",
      sub: r.me === true ? meSub(r) : r.group || "", xp: rfN(r.xp), me: r.me === true });
  });
  if (rest.length) {
    items.push(rfLine({ id: "rating-more", lead: rfDot(null), act: "rf-more", quiet: true,
      title: hidden ? `ещё ${rfPeople(rest.length)}, из них ${hidden} ${plural(hidden, "скрыт", "скрыты", "скрыты")}` : `ещё ${rfPeople(rest.length)}` }));
  }
  return rfList(items);
}

function rfMeView(d, st) {
  const ranks = d.ranks || {}, g = d.group || {}, me = d.me || {}, inst = g.institute || "";
  const scopes = [["group", "Группа", "Ты в группе"]];
  if (ranks.inst) scopes.push(["inst", "Институт", inst ? `Ты в ${inst}` : "Ты в институте"]);
  scopes.push(["all", "Вуз", "Ты в вузе"]);
  const i = Math.max(0, scopes.findIndex((s) => s[0] === st.scope));
  const [key, , eyebrow] = scopes[i];
  const sc = ranks[key] || {};
  const week = Math.trunc(me.week || 0), top = key === "all" && sc.above != null;
  return `<div class="hx">${rfSummary({ id: "rating-me", eyebrow, place: sc.place ?? null,
      placeText: sc.place == null ? "пока без опыта" : `место из ${rfN(sc.of)}`, sideEyebrow: "Опыт", sideValue: rfN(me.total),
      sideSub: top ? `выше ${sc.above}%` : week > 0 ? `+${rfN(week)} за\u00A0неделю` : "", sideColor: top ? "muted" : "ok",
      footer: rfUpHint(sc, d.rules || {}) })}</div>
    <div class="hx" style="margin-top:var(--m)">${rfTabs("rating-scope", scopes.map((s) => s[1]), i, "rf-scope")}</div>
    <div class="hx" style="margin-top:var(--m)">${rfPeopleList(Array.isArray(sc.rows) ? sc.rows : [], me, key, key === "group" && !st.expanded)}</div>`;
}

function rfGroupsView(d, st) {
  const g = d.group || {}, me = d.me || {}, inst = g.institute || "";
  const tabs = [];
  if (inst) tabs.push(["Институт", d.institute_top || [], "place_inst", g.groups_inst]);
  tabs.push(["Вуз", d.university_top || [], "place", g.groups_all]);
  const i = Math.min(st.gtab, tabs.length - 1);
  const [, top, placeKey, ofRaw] = tabs[i];
  let card;
  if (g.place == null) card = acGroupCard(g);
  else {
    const hasInst = !!inst && g.place_inst != null, xp = Math.trunc(g.xp || 0), total = Math.trunc(me.total || 0);
    const up = hasInst ? g.up_inst : g.up_all, place = hasInst ? g.place_inst : g.place;
    const share = xp > 0 && total > 0 ? Math.round(total * 100 / xp) : 0;
    card = rfSummary({ id: "rating-groups-card", eyebrow: `${g.name || ""} ${hasInst ? `в ${inst}` : "в вузе"}`, place,
      placeText: `место из ${rfN(hasInst ? g.groups_inst : g.groups_all)}`, sideEyebrow: hasInst ? "В вузе" : "Опыт",
      sideValue: hasInst ? String(g.place ?? "—") : rfN(xp), sideSub: hasInst ? `из ${rfN(g.groups_all)}` : "",
      footer: [hasInst ? `У группы ${rfN(xp)} опыта` : "", up != null && place > 1 ? `до ${place - 1}\u00A0места ${rfN(up)}` : "",
        share > 0 ? `твой вклад ${share}%` : ""].filter(Boolean).join(" · ") });
  }
  if (!top.length) return `<div class="hx">${card}</div>`;
  const row = (r) => rfLine({ id: `rating-group-${r.id}-${placeKey}`, lead: rfDot(r[placeKey] ?? null, r.mine === true), title: r.name || "",
    sub: r.mine === true ? "твоя группа" : "", xp: rfN(r.xp), me: r.mine === true, act: "group",
    data: ` data-id="${r.id ?? ""}" data-name="${esc(r.name || "")}"` });
  const last = Math.trunc(top[top.length - 1][placeKey] || top.length), mine = g[placeKey] ?? null;
  const below = mine != null && mine > last && !top.some((r) => r.mine === true);
  const of = Math.trunc(ofRaw || top.length), end = below ? mine : last;
  const items = top.map(row);
  if (below) {
    if (mine - last > 1) items.push(rfLine({ lead: rfDot(null), title: `дальше ${rfGroups(mine - last - 1)}`, quiet: true }));
    items.push(row({ ...g, mine: true }));
  }
  if (end < of) items.push(rfLine({ lead: rfDot(null), title: `ещё ${rfGroups(of - end)}`, quiet: true }));
  return `<div class="hx">${card}</div>`
    + (tabs.length > 1 ? `<div class="hx" style="margin-top:var(--m)">${rfTabs("rating-groups-scope", tabs.map((t) => t[0]), i, "rf-gtab")}</div>` : "")
    + `<div class="hx" style="margin-top:var(--m)">${rfList(items)}</div>`;
}

/** Экран «Рейтинг» в новом виде; st — что открыто (переживает перезагрузку). */
function rfDraw(body, d, st) {
  body.innerHTML = backRow(`<button class="ls-ask sf-ask" data-act="rf-mine" id="rating-mine-open">${icon("person", "o", "font-size:17px;color:var(--accent)")}Мой опыт</button>`)
    + screenTitle("Рейтинг", { sub: "активность в Капибаре, не успеваемость" })
    + `<div class="dl-segwrap">${rfTabs("rating-view", ["Я", "Группы"], st.view, "rf-view", true)}</div>`
    + (st.view === 0 ? rfMeView(d, st) : rfGroupsView(d, st)) + '<div style="height:var(--xxl)"></div>';
}

/** Из чего опыт — в одну строку: название, полоса, число. */
function rfBars(parts) {
  const top = Math.max(0, ...parts.map((p) => p[1]));
  return parts.map(([t, v]) => `<div class="row rf-bar"><span class="bd ell" style="--sz:13.5px">${esc(t)}</span>
    <div class="progress grow" style="height:6px"><i style="width:${top > 0 ? Math.max(0, Math.min(1, v / top)) * 100 : 0}%"></i></div>
    <span class="num" style="--sz:15px">${rfN(v)}</span></div>`).join("");
}

/** Лист «Мой опыт». act — { show, showAll, nick }(me) → Promise<boolean>; reload — свежий me. */
function rfMineSheet(me0, rules, act, reload) {
  let me = me0, rules0 = false;
  return Sheet.show('<div class="rf-mine"></div>', (body, close, sh) => {
    sh.classList.add("rf-sheet");
    const el = body.querySelector(".rf-mine");
    const toggle = (title, sub, onS, id) => `<div class="row" style="padding:var(--m) var(--m) var(--m) var(--l)">
      <div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div><div class="bd mut" style="--sz:12.5px;margin-top:2px">${esc(sub)}</div></div>${acSwitch(onS, id)}</div>`;
    const draw = () => {
      const show = me.show === true, all = me.show_all === true;
      el.innerHTML = `<div class="row" style="padding:0 var(--xs)"><div class="grow"><div class="ttl" style="--sz:26px">Мой опыт</div>
          <div class="bd mut" style="--sz:13px;margin-top:2px">видишь только ты</div></div><span class="num" id="rating-mine-total" style="--sz:44px">${rfN(me.total)}</span></div>
        <div class="tile" id="rating-mine" style="margin-top:var(--m);padding:var(--s) var(--l)">${rfBars(acParts(me))}</div>
        <div class="eyebrow" style="padding:var(--xl) var(--xs) var(--s)">Кто меня видит</div>
        <div class="tile p0">
          <button class="row ac-brow" id="rating-nick" data-act="rf-nick"><div class="grow"><div class="bd b6" style="--sz:15px">Ник</div>
            <div class="bd mut ell" style="--sz:13px;margin-top:2px">${esc(me.nick || "")}</div></div><span class="bd b6 acc" style="--sz:14px">Изменить</span></button>
          <div class="divider"></div>
          ${toggle("Показывать меня группе", show ? "группа видит твой ник и опыт" : "сейчас группа тебя не видит", show, "rating-show")}
          <div class="divider"></div>
          ${toggle("Показывать меня всем", all ? `все видят тебя как «${me.public_nick ?? "Капибара №…"}»` : "по отдельному согласию", all, "rating-show_all")}
        </div>
        <div class="tile p0 rf-rules${rules0 ? " open" : ""}" id="rating-rules" style="margin-top:var(--m)">
          <button class="row ac-brow" data-act="rf-rules"><span class="bd b6 grow" style="--sz:15px">Как считается опыт</span>${icon("chevron_right", "", "color:var(--muted)")}</button>
          ${rules0 ? `<div class="bd mut" id="rating-rules-text" style="--sz:14px;padding:0 var(--l) var(--l)">${esc(acRulesText(rules))}</div>` : ""}</div>`;
    };
    /** Правка: переключатель щёлкает сразу (now), не вышло — обратно; вышло — свежий me. */
    const run = async (fn, now) => {
      const was = me;
      if (now) { me = { ...was, ...now }; draw(); }
      const ok = await fn(was);
      if (!ok) { me = was; draw(); return; }
      const fresh = await reload();
      if (fresh) { me = fresh; draw(); }
    };
    on(body, {
      "rf-nick": () => run(act.nick),
      "rating-show": () => run(act.show, { show: me.show !== true }),
      "rating-show_all": () => run(act.showAll, me.show_all === true ? { show_all: false } : null),
      "rf-rules": () => { tick(); rules0 = !rules0; draw(); },
    });
    draw();
  });
}

/** Экран группы в новом виде (_FreshGroup): места, как росла, из чего опыт, люди. */
function rfGroupScreen(body, g, name) {
  const people = g.people_list || [], hidden = Math.trunc(g.hidden || 0), member = g.member === true, inst = g.institute || "";
  const places = [inst && g.place_inst != null ? `${g.place_inst}\u00A0место в ${inst}` : "", g.place != null ? `${g.place}\u00A0в\u00A0вузе` : ""]
    .filter(Boolean).join(" · ");
  const history = Array.isArray(g.history) ? g.history : [], hasXp = (g.xp || 0) > 0;
  const items = people.map((p) => rfLine({ lead: icon("person", p.me === true ? "" : "o",
    `font-size:22px;width:32px;color:var(--${p.me === true ? "accent" : "muted"})`), title: p.nick || "",
    sub: p.me === true ? "это ты" : "", xp: rfN(p.xp), me: p.me === true }));
  if (!people.length || hidden > 0) {
    items.push(rfLine({ id: "rating-group-hidden", lead: rfDot(null), quiet: true, title: !people.length
      ? (member ? "Пока никто не показывает себя группе" : "Пока никто не показывает себя всем")
      : `ещё ${rfPeople(hidden)} не показывают себя` }));
  }
  body.innerHTML = backRow() + screenTitle(g.name || name, { sub: places })
    + (g.place == null ? `<div class="hx">${acGroupCard(g)}</div>` : "")
    + (hasXp && history.length > 1 ? section("Как росла группа") + `<div class="hx"><div class="tile ac-growth" id="rating-growth"></div></div>` : "")
    + (hasXp ? section("Из чего опыт группы") + `<div class="hx"><div class="tile" id="rating-parts" style="padding:var(--s) var(--l)">${rfBars(acParts(g.parts))}</div></div>` : "")
    + section("Люди") + `<div class="hx" id="rating-group-people">${rfList(items)}</div><div style="height:var(--xxl)"></div>`;
  acMountGrowth(body, g);
}
