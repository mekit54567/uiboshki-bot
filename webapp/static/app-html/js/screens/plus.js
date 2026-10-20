// «Капибара+» (app/lib/plus/): экран подписки (plus_screen.dart), лист
// «Позвать друга», «Поддержать проект» (donate.dart), «Роадмап»
// (roadmap.dart), бонусные дни за ранг ачивок и «кто позвал» (plus.dart).
// Это веб: оплата и подписка видны (на iPhone-сборке их прячут по правилу
// App Store) — сервер для не-iOS отдаёт цены и ссылку на оплату на сайте.
"use strict";

const AC_PLUS_PERKS = [
  ["auto_awesome", "ИИ сверх пробы", "до 100 вопросов в день для любой группы МИРЭА"],
  ["palette", "Иконки и наряды капибары", "те, что «по подписке», в «Оформлении»"],
  ["workspace_premium", "Значок «друг Капибары»", "в профиле"],
  ["upcoming", "Дальше", "ответы на экзаменационные билеты, «Пульс группы», «Архив потока»"],
];
const AC_MONTHS_GEN = MONTHS;

/** «14 ноября» из «2026-11-14» (с годом, если не этот). */
function acUntil(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!m) return "";
  const year = +m[1] !== msk().y ? " " + m[1] : "";
  return `${+m[3]} ${AC_MONTHS_GEN[+m[2] - 1]}${year}`;
}
function acDays(n) { return `${n} ${plural(n, "день", "дня", "дней")}`; }
const acInt = (v) => (Number.isInteger(v) ? v : 0);

/** Друг уже дал пригласившему все дни, за кого дают (ref_max). */
function acInviteDone(d) { return acInt(d.ref_max) > 0 && acInt(d.ref_counted) >= acInt(d.ref_max); }
/** Лимит приглашений (inviteLimit); null — старый сервер без лимита. */
function acInviteLimit(d) {
  const max = acInt(d.ref_max), got = acInt(d.ref_counted);
  if (max <= 0) return null;
  const friends = plural(max, "друга", "друзей", "друзей");
  if (got >= max) return `Ты уже позвал ${max} ${friends} — бонус за приглашения закончился, друзьям дни по-прежнему дают`;
  return `Тебе — максимум за ${max} ${friends}, засчитано ${got} из ${max}`;
}

// «Показывать ли» — ответ помнится на запуск; не ответил — плитки/строки нет.
let _acPlusShown = null, _acDonateShown = null;
/** Плитка «Капибара+» в «Ещё»: сервер сказал hidden:false. → Promise<boolean>. */
window.plusShown = async function plusShown() {
  if (_acPlusShown !== null) return _acPlusShown;
  try { const r = await Api.get("/plus"); return (_acPlusShown = !!(r && r.hidden === false)); }
  catch (e) { return false; }
};
/** Строки «Поддержать проект» и «Роадмап» в «Ещё». → Promise<boolean>. */
window.donateShown = async function donateShown() {
  if (_acDonateShown !== null) return _acDonateShown;
  try { const r = await Api.get("/donate"); return (_acDonateShown = !!(r && r.hidden === false)); }
  catch (e) { return false; }
};

function acOpenOr(url) {
  tick();
  if (!acOpen(url)) toast("Не открылось — попробуй ещё раз", "error");
}

/** Строка с иконкой, названием и подписью (_Row). */
function acPerkRow(ic, title, sub) {
  return `<div class="row" style="padding:var(--m) var(--l)">${icon(ic, "o", "color:var(--accent)")}
    <div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div><div class="bd mut" style="--sz:13px">${esc(sub)}</div></div></div>`;
}
function acTag(text) { return `<span class="ac-tag">${esc(text)}</span>`; }

// ── Экран «Капибара+» ────────────────────────────────────────────────────

window.openPlus = function openPlus() {
  tick();
  Nav.push((body) => {
    acLoad(body, "/plus", (d) => {
      if (d.hidden !== false) { body.innerHTML = backRow() + screenTitle("Капибара+"); return; }
      _acPlusShown = true;
      body.innerHTML = acPlusBody(d);
    });
    on(body, {
      pay: (b) => acOpenOr(b.dataset.url),
      offer: (b) => acOpenOr(b.dataset.url),
      invite: () => { tick(); openInvite(); },
      donate: () => openDonate(),
    });
  });
};

function acPlusBody(d) {
  const active = d.active === true, unlimited = d.unlimited === true, founder = d.founder === true;
  const gift = d.paid_until == null && typeof d.gift === "string";
  const prices = Array.isArray(d.prices) ? d.prices : [];
  const payUrl = String(d.pay_url || ""), offerUrl = String(d.offer_url || "");
  const invite = d.invite && typeof d.invite === "object" ? d.invite : {};
  const ranks = invite.ranks && typeof invite.ranks === "object" ? invite.ranks : {};
  const unlimitedUntil = typeof d.unlimited_until === "string" ? d.unlimited_until : null;
  const perks = unlimited
    ? [["auto_awesome", "ИИ без ограничений", unlimitedUntil === null ? "без дневных лимитов, навсегда" : `без дневных лимитов до ${acUntil(unlimitedUntil)}`], ...AC_PLUS_PERKS.slice(1)]
    : AC_PLUS_PERKS;
  const fp = prices.find((x) => x.founder === true);
  const founderPrice = fp ? fp.price : null;
  const head = unlimited ? (unlimitedUntil !== null ? `У тебя безлимит до ${acUntil(unlimitedUntil)}` : "У тебя безлимит навсегда")
    : gift ? `Подарок группе до ${acUntil(d.gift)}` : active ? `Действует до ${acUntil(d.until)}` : "Подписки нет";
  const sub = unlimited ? "ИИ без дневных лимитов, платить не нужно" : gift ? "Платить не нужно — всё уже включено"
    : active ? "Оплата добавит дни к этому сроку" : "Всё главное работает и без неё — она для тех, кому нужно больше";
  let h = backRow() + screenTitle("Капибара+", { sub: "подписка на Капибару" });
  h += `<div class="hx"><div class="tile" id="plus-state" style="border-radius:var(--r-card)"><div class="row">
    ${active ? icon("verified", "", "font-size:30px;color:var(--ok)") : icon("workspace_premium", "o", "font-size:30px;color:var(--accent)")}
    <div class="grow"><div class="bd b6" style="--sz:17px">${esc(head)}</div>
      <div class="bd mut" style="--sz:13px;margin-top:2px">${esc(sub)}</div>
      ${founder && !unlimited ? `<div class="row" style="gap:var(--s);margin-top:var(--s)">${acTag("Early Supporter")}${founderPrice != null
        ? `<div class="bd mut grow" style="--sz:13px">месяц для тебя — ${esc(founderPrice)} ₽, навсегда</div>` : ""}</div>` : ""}
    </div></div></div></div>`;
  h += section("Что даёт") + `<div class="hx"><div class="tile p0">${perks.map((p, i) => (i ? '<div class="divider"></div>' : "") + acPerkRow(...p)).join("")}</div></div>`;
  if (!unlimited && prices.length) {
    h += section(prices.some((x) => x.founder === true) ? "Цены первых пользователей" : "Цены");
    h += `<div class="hx"><div class="tile p0">${prices.map((p, i) => (i ? '<div class="divider"></div>' : "") + acPriceRow(p)).join("")}</div></div>`;
  }
  if (!unlimited) {
    h += `<div style="padding:var(--l) var(--l) 0">${payUrl ? `<button class="btn primary" id="plus-pay" data-act="pay" data-url="${esc(payUrl)}">${icon("open_in_new", "", "font-size:20px")}Оплатить на сайте</button>`
      : `<div class="tile" id="plus-soon"><div class="row">${icon("schedule", "", "color:var(--muted)")}<div class="bd mut grow" style="--sz:14px">Оплата скоро заработает. Бонусные дни за ранги и друзей уже начисляются.</div></div></div>`}</div>
      <div class="bd mut" style="--sz:13px;padding:var(--m) var(--xl) 0">Без автосписаний: каждый срок оплачивается отдельно. Июль и август в срок не считаются.</div>
      ${offerUrl ? `<div style="padding-left:var(--m)"><button class="ac-tb" data-act="offer" data-url="${esc(offerUrl)}"><span class="bd b6 acc" style="--sz:14px">Оферта</span></button></div>` : ""}`;
  }
  h += section("Позови друга") + `<div class="hx">${acInviteCard(invite)}</div>`;
  h += section("Поддержать проект") + `<div class="hx"><button class="tile" id="plus-donate" data-act="donate"><div class="row">
    ${icon("favorite_border", "", "color:var(--accent)")}
    <div class="grow"><div class="bd b6" style="--sz:15px">Сказать спасибо рублём</div><div class="bd mut" style="--sz:13px">Разово, сумма на выбор</div></div>
    ${icon("chevron_right", "", "color:var(--muted)")}</div></button></div>`;
  if (Object.keys(ranks).length) {
    h += section("Бонусы за ранги ачивок")
      + `<div class="bd mut" style="--sz:13px;padding:0 var(--xl) var(--s)">Открой все ачивки ранга на телефоне — дни подписки придут сами.</div>`
      + `<div class="hx"><div class="tile p0">${AC_RANKS.filter((r) => ranks[r.id] && typeof ranks[r.id] === "object")
        .map((r) => (r.id !== "dawn" ? '<div class="divider"></div>' : "") + acRankRow(r, ranks[r.id])).join("")}</div></div>`;
  }
  return h + '<div style="height:var(--xxl)"></div>';
}

function acPriceRow(p) {
  const nowP = p.price, full = p.full;
  const cut = typeof nowP === "number" && typeof full === "number" && nowP < full;
  const days = acInt(p.days);
  return `<div class="row" id="plus-price-${esc(p.plan)}" style="padding:var(--m) var(--l)">
    <div class="grow"><div class="bd b6" style="--sz:15px">${esc(p.title || "")}</div>
      <div class="ac-wrap">${days > 0 ? `<span class="bd mut" style="--sz:13px">${acDays(days)}</span>` : ""}${p.founder === true ? acTag("Early Supporter") : ""}</div></div>
    ${cut ? `<span class="bd mut" style="--sz:14px;text-decoration:line-through">${esc(full)} ₽</span>` : ""}
    <span class="bd b7" style="--sz:18px">${esc(nowP)} ₽</span></div>`;
}

function acRankRow(r, info) {
  const days = acInt(info.days), need = acInt(info.need_days), claimed = info.claimed === true;
  return `<div class="row" id="plus-rank-${r.id}" style="padding:var(--m) var(--l)">${acBadge(r.id, 34)}
    <div class="grow"><div class="bd b6" style="--sz:15px">${esc(r.title)} · +${acDays(days)}</div>
      <div class="bd" style="--sz:13px;color:var(--${claimed ? "ok" : "muted"})">${claimed ? "получено"
        : need > 1 ? `все ачивки ранга и ${need} ${plural(need, "день", "дня", "дней")} с заходами` : "все ачивки ранга"}</div></div>
    ${claimed ? icon("check_circle", "", "color:var(--ok)") : ""}</div>`;
}

function acInviteCard(invite) {
  const came = acInt(invite.came), rewarded = acInt(invite.rewarded), bonus = acInt(invite.bonus_days), need = acInt(invite.friend_days);
  const limit = acInviteLimit(invite);
  return `<div class="tile" id="plus-invite">
    ${bonus > 0 ? `<div class="bd b6" style="--sz:15px">+${acDays(bonus)} ${acInviteDone(invite) ? "другу" : "обоим"}, когда друг попользуется Капибарой ${need} ${plural(need, "день", "дня", "дней")}</div>` : ""}
    ${limit !== null ? `<div class="bd" style="--sz:13px;margin-top:4px">${esc(limit)}</div>` : ""}
    <div class="bd mut" style="--sz:13px;margin-top:4px">${came === 0 ? "По твоей ссылке пока никто не пришёл"
      : limit !== null ? `Пришло по ссылке: ${came}` : `Пришло по ссылке: ${came} · засчитано: ${rewarded}`}</div>
    <div style="height:var(--m)"></div>
    <button class="btn primary" style="min-height:46px;font-size:15px" data-act="invite">${icon("group_add", "o", "font-size:20px")}Позвать друга</button>
  </div>`;
}

// ── «Позвать друга» ─────────────────────────────────────────────────────

async function acCopy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  try {
    const t = document.createElement("textarea");
    t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    const ok = document.execCommand("copy");
    t.remove();
    return ok;
  } catch (e) { return false; }
}
async function acCopyTo(text, done) {
  if (await acCopy(text)) toast(done, "done");
  else toast("Не удалось скопировать — попробуй ещё раз.", "error");
}

/** Лист «Позвать»: в Telegram, «Поделиться…», «Скопировать» (showInviteSheet). */
window.openInvite = async function openInvite() {
  let d;
  try {
    d = await Api.get("/invite");
    if (!String((d && d.link) || "")) throw new ApiError("Не получилось взять ссылку — попробуй позже");
  } catch (e) { toast(errorText(e), "error"); return; }
  const link = String(d.link), text = String(d.share_text || "").trim();
  const message = text ? `${text}\n${link}` : link;
  const bonus = acInt(d.bonus_days), need = acInt(d.friend_days), limit = acInviteLimit(d);
  await Sheet.show(`
    <div class="ttl" style="--sz:24px">Позвать друга</div>
    <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Друг получит готовое сообщение с твоей ссылкой:</div>
    <div style="height:var(--m)"></div>
    <div class="tile" id="invite-preview"><div class="bd" style="--sz:14px;line-height:1.4;white-space:pre-wrap;word-break:break-word">${esc(message)}</div></div>
    ${bonus > 0 ? `<div class="bd mut" style="--sz:13px;margin-top:var(--s)">+${acDays(bonus)} Капибары+ ${acInviteDone(d) ? "другу" : "вам обоим"}, когда друг попользуется ${need} ${plural(need, "день", "дня", "дней")}</div>
      ${limit !== null ? `<div class="bd mut" style="--sz:13px">${esc(limit)}</div>` : ""}` : ""}
    <div style="height:var(--xl)"></div>
    <button class="btn primary" style="min-height:50px" data-act="tg">${icon("send", "", "font-size:20px")}Отправить в Telegram</button>
    <div style="height:var(--s)"></div>
    <button class="ac-ob" data-act="share">${icon("ios_share", "", "font-size:20px")}Поделиться…</button>
    <div style="height:var(--s)"></div>
    <button class="ac-ob" data-act="copy">${icon("content_copy", "", "font-size:20px")}Скопировать</button>`,
  (body, close) => on(body, {
    tg: async () => {
      tick(); close();
      const tg = String(d.tg_share || "");
      if (!(tg && acOpen(tg))) await acCopyTo(message, "Telegram не открылся — сообщение скопировано, вставь его в чат");
    },
    share: async () => {
      tick(); close();
      try {
        if (!navigator.share) throw new Error("нет");
        await navigator.share({ text: message });
      } catch (e) {
        if (e && e.name === "AbortError") return;
        await acCopyTo(message, "Не вышло поделиться — сообщение скопировано");
      }
    },
    copy: async () => { tick(); close(); await acCopyTo(message, "Скопировано — вставь в чат другу"); },
  }));
};

// ── «Поддержать проект» ─────────────────────────────────────────────────

/** Лист доната: ссылка свежая (живёт сутки) — спрашиваем каждый раз. */
window.openDonate = async function openDonate() {
  let d;
  try { d = await Api.get("/donate"); } catch (e) { toast(errorText(e), "error"); return; }
  if (!d || d.hidden !== false) return;
  const url = String(d.url || "");
  const amounts = (Array.isArray(d.amounts) ? d.amounts : []).map((a) => `${a} ₽`);
  const min = acInt(d.min);
  await Sheet.show(`
    <div class="ttl" style="--sz:24px">Поддержать проект</div>
    <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Если Капибара помогает тебе учиться — можно сказать спасибо рублём: на сервер, ИИ и новые функции.</div>
    <div style="height:var(--m)"></div>
    <div class="tile" id="donate-note"><div class="row">${icon("favorite_border", "", "color:var(--accent)")}
      <div class="grow"><div class="bd b6" style="--sz:15px">Это не подписка — просто спасибо. В ответ откроется роадмап: что я делаю сейчас и что дальше.</div>
      <div class="bd mut" style="--sz:13px;margin-top:2px">Всё бесплатное остаётся бесплатным, «Капибара+» — отдельно: дней подписки донат не даёт.</div></div></div></div>
    ${amounts.length ? `<div class="bd mut" id="donate-amounts" style="--sz:13px;margin-top:var(--m)">Сумма — на выбор: ${esc(amounts.join(" · "))}${min > 0 ? ` или своя, от ${min} ₽` : ""}. Разово, без автосписаний; чек — из «Мой налог».</div>` : ""}
    <div style="height:var(--xl)"></div>
    ${url ? `<button class="btn primary" id="donate-go" data-act="go">${icon("open_in_new", "", "font-size:20px")}Поддержать на сайте</button>`
      : `<div class="tile" id="donate-soon"><div class="row">${icon("schedule", "", "color:var(--muted)")}<div class="bd mut grow" style="--sz:14px">Поддержать можно будет совсем скоро — оплата ещё подключается.</div></div></div>`}`,
  (body, close) => on(body, { go: () => { tick(); close(); if (!acOpen(url)) toast("Не открылось — попробуй ещё раз", "error"); } }));
};

// ── «Роадмап» ───────────────────────────────────────────────────────────

window.openRoadmap = async function openRoadmap() {
  let d;
  try { d = await Api.get("/roadmap"); } catch (e) { toast(errorText(e), "error"); return; }
  if (!d || d.hidden !== false) return;
  const locked = d.locked !== false;
  if (!locked && d.page_url) { openLink(d.page_url); return; }   // страница роадмапа (roadmap_page.py)
  const statuses = d.statuses && typeof d.statuses === "object" ? d.statuses : {};
  const items = Array.isArray(d.items) ? d.items : [];
  const ic = (st) => (st === "done" ? ["check_circle_outline", ""] : st === "idea" ? ["lightbulb_outline", ""] : ["push_pin", "o"]);
  let inner;
  if (locked) {
    inner = `<div class="tile" id="roadmap-locked"><div class="row">${icon("favorite_border", "", "color:var(--accent)")}
      <div class="grow"><div class="bd b6" style="--sz:15px">Для тех, кто поддержал проект</div>
      <div class="bd mut" style="--sz:13px;margin-top:2px">Любая сумма от ${esc(d.min ?? 50)} ₽ — это спасибо, а не покупка. Роадмап откроется сам.</div></div></div></div>
      <div style="height:var(--xl)"></div>
      <button class="btn primary" id="roadmap-donate" data-act="donate">${icon("favorite_border", "", "font-size:20px")}Поддержать проект</button>`;
  } else {
    inner = Object.keys(statuses).filter((st) => items.some((i) => i.status === st)).map((st) => {
      const [n, v] = ic(st);
      return `<div class="bd b6 mut" style="--sz:12px;padding:var(--m) 0 var(--s)">${esc(String(statuses[st]).toUpperCase())}</div>`
        + items.filter((i) => i.status === st).map((i) => `<div class="tile" style="margin-bottom:var(--s)"><div class="row" style="align-items:flex-start">
          ${icon(n, v, `font-size:22px;color:var(--${st === "done" ? "muted" : "accent"})`)}
          <div class="grow"><div class="bd b6" style="--sz:15px">${esc(i.title)}</div><div class="bd mut" style="--sz:13px;margin-top:2px">${esc(i.about)}</div></div></div></div>`).join("");
    }).join("") + `<div style="height:var(--s)"></div><div class="bd mut" style="--sz:13px">Спасибо, что поддержал! Планы — не обещания: что-то может сдвинуться.</div>`;
  }
  await Sheet.show(`<div class="ttl" style="--sz:24px">Роадмап</div>
    <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Что я делаю сейчас и что дальше</div>
    <div style="height:var(--m)"></div>${inner}`,
  (body, close) => on(body, { donate: () => { tick(); close(); openDonate(); } }));
};

// ── Бонусы (plus.dart: PlusBonus) ───────────────────────────────────────

const PlusBonus = {
  _tried: new Set(),
  /** После входа: отдать серверу код «кто позвал» один раз и забыть. */
  async sendRef() {
    const code = Prefs.get("uib_ref");
    if (!code) return;
    try { await Api.post("/plus/ref", { code }); }
    catch (e) {
      if (!e.status) return; // нет сети — до следующего раза
      if (e.status >= 500 || e.status === 403) return; // сервер упал или согласия ещё нет
    }
    Prefs.set("uib_ref", null);
  },
  _done() { try { const v = JSON.parse(Prefs.get("uib_plus_ranks") || "[]"); return new Set(v.map(String)); } catch (e) { return new Set(); } },
  _markDone(r) { Prefs.set("uib_plus_ranks", JSON.stringify([...this._done(), r])); },
  /** Все ачивки ранга открыты? */
  complete(r) { return AC_ACH.filter((a) => a.rank === r).every((a) => AcStore.has(a.id)); },
  async checkAll() { for (const r of AC_RANKS) await this.claim(r.id); },
  /** Ранг закрыт и ещё не получен — POST /plus/rank; дали дни — плашка. */
  async claim(r) {
    if (!Api.token || this._tried.has(r) || !this.complete(r)) return;
    this._tried.add(r);
    if (this._done().has(r)) return;
    try {
      const res = await Api.post("/plus/rank", { rank: r });
      this._markDone(r);
      const days = res && Number.isInteger(res.days) ? res.days : 0;
      if (days > 0) toast(`+${days} ${plural(days, "день", "дня", "дней")} Капибары+ за ранг «${acRank(r).title}»`, "done");
    } catch (e) {
      if (e.status === 400 && (String(e.message).includes("уже") || String(e.message).includes("нет такого"))) this._markDone(r);
    }
  },
};

/** shell.js afterStart: «кто позвал» — после согласия. */
window.sendRef = () => PlusBonus.sendRef();
