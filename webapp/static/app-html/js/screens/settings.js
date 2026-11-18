// Экраны настроек из «Ещё»: «Уведомления» (screens/notify.dart, веб-пуш —
// web_push_web.dart и uibPush из app/web/index.html), «Оформление»
// (look_screen.dart, theme/look.dart; при выключенном новом дизайне — лист
// «Тема и шрифт» из more.dart), «Безопасность» (security.dart), «Из какой ты
// группы?» (group_pick.dart) и тур по приложению (tour.dart).
// Наружу: openNotify(), openLook(), openSecurity(), openGroupPick({required}),
// showTour(), maybeTour().
"use strict";

/** Переключатель в цветах темы (AppSwitch). */
function mrSwitch(on, act, attrs = "") {
  return `<button class="mr-sw${on ? " on" : ""}" role="switch" aria-checked="${on}" data-act="${act}"${attrs}></button>`;
}
/** Плашка выбора (_Pill): on — залита акцентом, dim — выходной, wide — с отступами. */
function mrPill(text, on, act, attrs = "", { dim = false, wide = false } = {}) {
  return `<button class="mr-pill${on ? " on" : ""}${dim ? " dim" : ""}${wide ? " wide" : ""}" data-act="${act}"${attrs}>${esc(text)}</button>`;
}
/** «1 ч 30 мин», «5 мин» (minText). */
function mrMin(m) { return [Math.floor(m / 60) > 0 ? `${Math.floor(m / 60)} ч` : "", m % 60 > 0 ? `${m % 60} мин` : ""].filter(Boolean).join(" "); }
const MR_QUIZ = [1440, 180, 60, 30, 10];
function mrQuizLabel(m) { return m >= 1440 ? "1 день" : mrMin(m); }
/** «за 1 день и 10 мин до закрытия · когда откроют» (quizSummary). */
function mrQuizSummary(remind, open) {
  const names = remind.slice().sort((a, b) => b - a).map(mrQuizLabel);
  const parts = [];
  if (names.length === 1) parts.push(`за ${names[0]} до закрытия`);
  if (names.length > 1) parts.push(`за ${names.slice(0, -1).join(", ")} и ${names[names.length - 1]} до закрытия`);
  if (open) parts.push("когда откроют");
  return parts.length ? parts.join(" · ") : "выключено";
}
/** Время сводки из любого: до получаса, в пределах 17:00–23:30 (eveningSlot). */
function mrEveningSlot(hour, minute) {
  let m = hour * 60 + Math.floor((minute + 15) / 30) * 30;
  m = Math.max(17 * 60, Math.min(23 * 60 + 30, m));
  return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
}

// ── Веб-пуш (window.uibPush в app/web/index.html): on / off / denied / install / unsupported ──
const mrPush = {
  async state() {
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        return /iPhone|iPad|iPod/.test(navigator.userAgent) && !navigator.standalone ? "install" : "unsupported";
      }
      if (Notification.permission === "denied") return "denied";
      const reg = await navigator.serviceWorker.getRegistration("/");
      const sub = reg && await reg.pushManager.getSubscription();
      return sub ? "on" : "off";
    } catch (e) { return "unsupported"; }
  },
  async enable(key) {
    if (await Notification.requestPermission() !== "granted") return "";
    await navigator.serviceWorker.register("/sw.js");
    const reg = await navigator.serviceWorker.ready;
    const pad = "=".repeat((4 - key.length % 4) % 4);
    const raw = Uint8Array.from(atob((key + pad).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
    const sub = await reg.pushManager.getSubscription() || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: raw });
    return JSON.stringify(sub.toJSON());
  },
  async disable() {
    const reg = await navigator.serviceWorker.getRegistration("/");
    const sub = reg && await reg.pushManager.getSubscription();
    if (!sub) return "";
    await sub.unsubscribe();
    return sub.endpoint;
  },
};

// ── Уведомления нового дизайна (notify_fresh.dart, макеты У1 и У2) ──
/** «23:00 – 07:30» (quietRange). */
function nfQuietRange(d) { const q = (d && d.quiet_hours) || {}; return `${q.from || "23:00"} – ${q.to || "07:30"}`; }
/** Куда ведёт строка ленты (inboxAction). */
function nfAction(tab) {
  return { today: "Открыть «Сегодня»", week: "Открыть «Неделю»", deadlines: "Открыть «Сдать»", sdo: "Открыть «Учёбу»", study: "Открыть «Учёбу»" }[tab] || null;
}
/** «Сегодня», «Вчера», «8 октября» (inboxDay). */
function nfDay(at, today) {
  const day = String(at || "").slice(0, 10);
  if (day === today) return "Сегодня";
  if (day === addDays(today, -1)) return "Вчера";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  return m ? `${+m[3]} ${MONTHS[+m[2] - 1]}` : day;
}
/** У1: лента уведомлений; открыл — всё прочитано. onClose — вернулся назад. */
window.openInbox = function openInbox(onClose) {
  Nav.push((body) => {
    let d = null, error = null;
    const draw = () => {
      const head = backRow(`<button class="ls-ask sf-ask" data-act="settings" id="inbox-settings">${icon("tune", "", "font-size:17px;color:var(--accent)")}Настроить</button>`)
        + screenTitle("Уведомления");
      if (!d) {
        body.innerHTML = head + (error ? notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner());
        return;
      }
      const items = d.items || [], keep = d.keep_days || 30, today = isoDay(now());
      if (!items.length) {
        body.innerHTML = head + '<div style="height:var(--xl)"></div>' + freshEmpty("day", "Пока пусто",
          `Здесь будет всё, что пришло пушем или в Telegram: сроки, баллы, новые задания. Хранится ${keep}\u00A0дней.`, { id: "inbox-empty" });
        return;
      }
      const days = [];
      for (const it of items) {
        const label = nfDay(it.at, today);
        if (!days.length || days[days.length - 1][0] !== label) days.push([label, []]);
        days[days.length - 1][1].push(it);
      }
      const row = (it) => {
        const act = nfAction(it.tab), time = String(it.at || "").slice(11, 16), b = String(it.body || "").trim();
        return `<button class="nf-row" data-act="open" data-tab="${esc(it.tab || "")}" id="inbox-${it.id}"${act ? "" : " disabled"}>
          <i class="nf-dot${it.read ? "" : " on"}"></i>
          <div class="grow" style="min-width:0"><div class="bd b7" style="--sz:15px">${esc(it.title)}</div>
            ${b ? `<div class="bd mut clamp3" style="--sz:13px;margin-top:2px">${esc(b)}</div>` : ""}
            ${act ? `<div class="bd b7" style="--sz:13px;margin-top:4px;color:var(--accent)">${esc(act)}</div>` : ""}</div>
          <div class="nf-time"><span class="bd mut" style="--sz:12.5px">${esc(time)}</span>
            ${it.quiet ? icon("bedtime", "o", "font-size:14px;color:var(--muted);margin-top:4px") : ""}</div></button>`;
      };
      body.innerHTML = head + days.map(([label, list]) => section(label)
        + `<div class="hx"><div class="tile p0 nf-list">${list.map(row).join('<div class="divider"></div>')}</div></div>`).join("")
        + `<div class="bd mut" style="--sz:13px;padding:var(--l) var(--xl) 0">${esc(d.quiet
          ? `Ночью в тихие часы уведомления не приходят, а ждут здесь. Лента хранится ${keep}\u00A0дней.` : `Лента хранится ${keep}\u00A0дней.`)}</div>`
        + '<div style="height:var(--xxl)"></div>';
    };
    const load = () => Api.get("/inbox").then((v) => {
      d = v; draw();
      if (v && v.unread > 0) Api.post("/inbox/read", {}).catch(() => {});   // точка погаснет
    }, (e) => { error = e; draw(); });
    on(body, {
      settings() { tick(); window.openNotifyHome(); },
      open(b) {
        const tab = b.dataset.tab;
        if (!nfAction(tab)) return;
        tick();
        Nav.popAll();                       // как нажатый пуш: экраны поверх закрыть, открыть вкладку
        Tabs.show(tabByName(tab));
      },
      retry() { error = null; draw(); load(); },
    });
    draw();
    load();
    return () => { if (onClose) onClose(); };
  });
};
/** У2: «Что присылать» — три набора, тихие часы, куда присылать. onClose — вернулся назад. */
window.openNotifyHome = function openNotifyHome(onClose) {
  Nav.push((body) => {
    let s = null, error = null, queue = Promise.resolve();
    const prefs = () => (s && s.prefs) || {};
    const save = (patch, optimistic) => {
      tick();
      s = { ...s, ...optimistic, prefs: { ...prefs(), ...((optimistic && optimistic.prefs) || {}) } };
      draw();
      queue = queue.then(async () => {
        try { const fresh = await Api.post("/notify", patch); if (fresh && fresh.prefs) { s = fresh; draw(); } }
        catch (e) { toast("Не сохранилось: " + errorText(e), "error"); load(); }
      });
    };
    const choice = (id, title, sub, sel, chevron = false) => `<button class="nf-choice${sel ? " on" : ""}" data-act="${chevron ? "custom" : "pick"}" data-v="${id}"
        id="notify-profile-${id}" aria-pressed="${sel}"><div class="grow"><div class="bd b7" style="--sz:16px">${esc(title)}</div>
        <div class="bd mut" style="--sz:13.5px;margin-top:2px">${esc(sub)}</div></div>
        ${chevron ? icon("chevron_right", "", `color:var(${sel ? "--accent" : "--muted"})`) : sel ? icon("check_circle", "", "color:var(--accent)") : ""}</button>`;
    const draw = () => {
      if (!s || !s.prefs) {
        body.innerHTML = backRow() + (error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner());
        return;
      }
      const on = s.subscribed === true, profile = on ? s.profile : "", p = prefs(), hasQuiet = "quiet" in p;
      body.innerHTML = backRow() + screenTitle("Что присылать")
        + (on ? "" : '<div class="bd mut" style="--sz:14px;padding:0 var(--xl) var(--m)">Сейчас уведомления выключены. Выбери, что присылать, и они включатся.</div>')
        + `<div class="hx nf-choices">${choice("important", "Только важное", "Сроки, новые задания, баллы. Около\u00A03\u00A0в\u00A0день", profile === "important")}
          ${choice("daily", "Помощь каждый день", "Плюс утро, пары и обзор недели. Около\u00A08\u00A0в\u00A0день", profile === "daily")}
          ${choice("custom", "Настроить самому", profile === "custom" ? "Сейчас своя настройка. Каждый вид отдельно" : "Каждый вид отдельно", profile === "custom", true)}</div>`
        + `<div class="hx" style="margin-top:var(--l)"><div class="tile p0 nf-list">
          ${hasQuiet ? `<div class="nf-line" id="notify-quiet">${icon("bedtime", "o", "color:var(--accent)")}<div class="grow"><div class="bd b7" style="--sz:15px">Тихие часы</div>
            <div class="bd mut" style="--sz:13px">${esc(nfQuietRange(s))}, по Москве</div></div>${mrSwitch(p.quiet === true, "quiet")}</div><div class="divider"></div>` : ""}
          <button class="nf-line" data-act="where" id="notify-where">${icon("notifications_none", "", "color:var(--accent)")}<div class="grow"><div class="bd b7" style="--sz:15px">Куда присылать</div>
            <div class="bd mut" style="--sz:13px">${p.tg_copy !== false ? "Пуш и Telegram" : "Пуш. Telegram, если пуш не\u00A0дошёл"}</div></div>${icon("chevron_right", "", "color:var(--muted)")}</button></div></div>`
        + `<div class="bd mut" style="--sz:13px;padding:var(--m) var(--xl) 0">${hasQuiet
          ? "Всё время в приложении московское. Срочное про тест, который закрывается ночью, придёт и в тихие часы." : "Всё время в приложении московское."}</div>`
        + '<div style="height:var(--xxl)"></div>';
    };
    const load = () => Api.get("/notify").then((v) => { s = v; error = null; draw(); }, (e) => { error = e; draw(); });
    on(body, {
      pick(b) {
        const v = b.dataset.v;
        if (s.profile === v && s.subscribed === true) return;
        save({ profile: v }, { profile: v, subscribed: true });
      },
      custom() { tick(); window.openNotify(() => load()); },
      quiet() { const q = prefs().quiet === true; save({ prefs: { quiet: !q } }, { prefs: { quiet: !q } }); },
      async where() {
        tick();
        const copy = prefs().tg_copy !== false;
        const opt = (v, title, sub) => `<button class="nf-where" data-act="w" data-v="${v ? 1 : 0}" id="notify-where-${v ? "both" : "push"}">
          <div class="grow"><div class="bd b7" style="--sz:15px">${title}</div><div class="bd mut" style="--sz:13px">${sub}</div></div>
          ${icon(v === copy ? "check_circle" : "radio_button_unchecked", "", `color:var(${v === copy ? "--accent" : "--muted"})`)}</button>`;
        const got = await Sheet.show(`<div class="ttl" style="--sz:24px">Куда присылать</div><div style="height:var(--s)"></div>
          ${opt(true, "Пуш и Telegram", "Одно и то же приходит в оба места")}${opt(false, "Только пуш", "Telegram — только если пуш не\u00A0дошёл")}
          <div class="bd mut" style="--sz:13px;margin-top:var(--s)">Пуши на этом устройстве включаются в «Настроить самому».</div>`,
        (sb, close) => on(sb, { w: (x) => close(x.dataset.v === "1") }));
        if (typeof got !== "boolean" || got === copy) return;
        save({ prefs: { tg_copy: got } }, { prefs: { tg_copy: got } });
      },
      retry() { error = null; draw(); load(); },
    });
    draw();
    load();
    return () => { if (onClose) onClose(); };
  });
};

// ── «Уведомления» — что бот присылает и в какие дни (/api/notify): сохраняется сразу ──
window.openNotify = function openNotify(onClose) {
  Nav.push((body) => {
    let s = Api.cached("/notify") || null, error = null, pending = 0, queue = Promise.resolve();
    let quizOpen = false, push = "", pushBusy = false;
    const prefs = () => s.prefs;

    const save = (patch) => {
      tick();
      if ("subscribed" in patch) s.subscribed = patch.subscribed;
      if (patch.prefs) Object.assign(s.prefs, patch.prefs);
      draw();
      pending++;
      queue = queue.then(async () => {
        let fresh = null;
        try { fresh = await Api.post("/notify", patch); }
        catch (e) {
          toast("Не сохранилось: " + errorText(e), "error");
          try { fresh = await Api.get("/notify"); } catch (e2) {}   // что на самом деле сохранено
        }
        if (--pending === 0 && fresh && typeof fresh === "object" && fresh.prefs && typeof fresh.prefs === "object") { s = fresh; draw(); }
      });
    };
    const toggle = (k) => save({ prefs: { [k]: !(prefs()[k] === true) } });

    const card = ({ ic = "", title, sub, key, on, children = "" }) => `<div class="hx mr-gap"><div class="tile">
      <div class="row">${ic ? `<span class="mr-nbox${on ? " on" : ""}">${icon(ic, "o")}</span>` : ""}
        <div class="grow"><div class="bd b6" style="--sz:16px;color:${on ? "var(--text)" : "var(--muted)"}">${esc(title)}</div>
        <div class="bd mut" style="--sz:13px">${esc(sub)}</div></div>${mrSwitch(on, "sw", ` data-k="${key}"`)}</div>
      ${on && children ? `<div style="height:var(--m)"></div>${children}` : ""}</div></div>`;
    const row = (title, sub, k, on, act = "sw") => `<div class="row mr-nrow"><div class="grow"><div class="bd b5" style="--sz:15px">${esc(title)}</div>
      <div class="bd mut" style="--sz:12px">${esc(sub)}</div></div>${mrSwitch(on, act, ` data-k="${k}"`)}</div>`;
    const days = (list, key) => `<div class="mr-days">${WD_SHORT.map((d, i) =>
      mrPill(d, list.includes(i), "day", ` data-k="${key}" data-i="${i}"`, { dim: i >= 5 })).join("")}</div>`;
    const remind = (r) => {
      const value = prefs()[r.key] || 0, presets = r.presets || [];
      const own = value > 0 && !presets.includes(value);
      return `<div style="margin-top:var(--m)"><div class="bd b6 mut" style="--sz:13px">${esc(r.title)}</div>
        <div class="mr-wrap">${mrPill("выкл", value === 0, "rm", ` data-k="${esc(r.key)}" data-v="0"`, { wide: true })}
        ${presets.map((m) => mrPill(mrMin(m), value === m, "rm", ` data-k="${esc(r.key)}" data-v="${m}"`, { wide: true })).join("")}
        ${mrPill(own ? mrMin(value) : "своё", own, "rm-own", ` data-k="${esc(r.key)}"`, { wide: true })}</div></div>`;
    };
    const quiz = () => {
      const choices = (s.quiz_choices || MR_QUIZ).map(Number), list = (prefs().quiz_remind || []).map(Number);
      const open = prefs().quiz_open !== false, on = list.length > 0 || open;
      return `<div class="hx mr-gap"><div class="tile">
        <button class="row mr-qhead" data-act="quiz"><span class="mr-nbox${on ? " on" : ""}">${icon("timer", "o")}</span>
          <div class="grow"><div class="bd b6" style="--sz:16px;color:${on ? "var(--text)" : "var(--muted)"}">Тесты СДО</div>
          <div class="bd mut" style="--sz:13px">${esc(mrQuizSummary(list, open))}</div></div>
          <span class="mr-chev${quizOpen ? " open" : ""}">${icon("chevron_right", "", "color:var(--muted)")}</span></button>
        ${quizOpen ? `<div class="bd b6 mut" style="--sz:13px;margin-top:var(--m)">Напомнить до закрытия · можно несколько</div>
          <div class="mr-wrap">${choices.map((m) => mrPill(mrQuizLabel(m), list.includes(m), "qz", ` data-v="${m}"`, { wide: true })).join("")}</div>
          <div style="margin-top:var(--s)">${row("Тест открылся", "напишу, когда замечу, что тест открыли. Смотрю СДО примерно раз в час", "quiz_open", open, "qopen")}</div>` : ""}
      </div></div>`;
    };
    const evening = () => {
      const v = prefs().evening_time || "20:00", presets = ["19:00", "20:00", "21:00", "22:00"], own = !presets.includes(v);
      return `<div class="mr-wrap" style="margin-top:0">${presets.map((t) => mrPill(t, v === t, "ev", ` data-v="${t}"`, { wide: true })).join("")}
        ${mrPill(own ? v : "своё", own, "ev-own", "", { wide: true })}</div>`;
    };
    const pushCard = () => {
      if (!push || push === "unsupported") return "";
      const tg = prefs().tg_copy !== false;
      const sub = { on: "Включены — приходят на это устройство", denied: "Запрещены в настройках браузера — разреши там, потом включи здесь",
        install: "Добавь Капибару на экран «Домой» (Поделиться → На экран «Домой») и открой оттуда" }[push]
        || "Включи — и уведомления придут сюда, как у приложения";
      return card({ ic: "notifications_active", title: "На этом устройстве", sub, key: "push", on: push === "on",
        children: row("Дублировать в Telegram", tg ? "пуш сюда и копия в Telegram" : "только пуш (есть приложение на телефоне — только в него); не получилось отправить — уйдёт в Telegram", "tg_copy", tg) });
    };

    const draw = () => {
      if (!s || !s.prefs) {
        body.innerHTML = backRow() + (error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner());
        return;
      }
      const p = prefs(), on = s.subscribed === true, campus = s.home_campus;
      let html = backRow() + screenTitle("Уведомления")
        + `<div class="row mr-info">${icon("info_outline", "", "font-size:18px;color:var(--muted)")}
          <div class="bd mut grow" style="--sz:13px">Уведомления приходят в Telegram, а сюда — когда включишь их ниже.</div></div>`
        + pushCard()
        + card({ title: "Присылать уведомления", sub: on ? "Включены — ниже, что именно" : "Выключены — бот ничего не пришлёт сам", key: "subscribed", on })
        // тихие часы (шаг 8) — в новом виде; старый сервер ключа не знает
        + (on && Theme.fresh && "quiet" in p ? card({ ic: "bedtime", title: "Тихие часы", key: "quiet", on: p.quiet === true,
            sub: `${nfQuietRange(s)} по Москве: уведомления ждут в ленте, срочное про тесты и сроки приходит` }) : "");
      if (on) {
        html += card({ ic: "wb_sunny", title: "Утреннее расписание", sub: `в ${s.morning_time || "8:00"} — пары на сегодня`, key: "morning", on: p.morning === true,
          children: days(p.morning_days || [], "morning_days")
            + row("Погода", "строчка с погодой в начале", "weather", p.weather === true)
            + row("Другой корпус", campus ? `если пары не на ${campus} — напишу, где` : "если пары в другом корпусе — напишу", "campus", p.campus === true)
            + row("Только если есть пары", "в свободный день — тишина", "skip_empty", p.skip_empty === true) });
        html += card({ ic: "alarm", title: "Перед парой", sub: "своё время для первой пары и после перемены", key: "lessons", on: p.lessons === true,
          children: days(p.lesson_days || [], "lesson_days") + (s.remind || []).map(remind).join("") });
        html += card({ ic: "flag", title: "Дедлайны", sub: `в ${s.deadline_time || "19:00"} — что сдать в ближайшие 3 дня`, key: "deadlines",
          on: p.deadlines === true, children: days(p.deadline_days || [], "deadline_days") });
        // «Срок скоро» (deadline_soon.py, Никита 25.10): за сколько часов до срока, если не сдано
        const soonH = p.deadline_soon_hours || 3, soonLabel = (h) => h >= 24 ? "1 день" : `${h} ч`;
        html += card({ ic: "hourglass_bottom", title: "Срок скоро", sub: `за ${soonLabel(soonH)} до срока, если у работы нет отметки о сдаче`, key: "deadline_soon",
          on: p.deadline_soon === true, children: `<div class="mr-wrap" style="margin-top:0">${(s.deadline_soon_choices || [1, 3, 6, 12, 24]).map((h) =>
            mrPill(soonLabel(h), soonH === h, "soon", ` data-v="${h}"`, { wide: true })).join("")}</div>` });
        html += card({ ic: "view_week", title: "Обзор недели", sub: "в воскресенье в 19:00 — сколько пар и что сдать", key: "weekly", on: p.weekly === true });
        html += card({ ic: "military_tech", title: "Новые баллы", sub: "когда проверят работу или изменятся баллы. Смотрю СДО примерно раз в час с 8 до 23, нужен вход в СДО", key: "grades", on: p.grades === true });
        html += card({ ic: "assignment", title: "Новые задания", sub: "когда в СДО появится задание или перенесут срок. Сверяюсь с СДО несколько раз в день", key: "new_tasks", on: p.new_tasks === true });
        html += quiz();
        if (Theme.design2 && "evening" in p) {
          const t = p.evening_time || "20:00";
          html += card({ ic: "bedtime", title: "Вечерняя сводка", sub: `Пары и сроки на завтра · ${t}`, key: "evening", on: p.evening === true, children: evening() });
        }
      }
      body.innerHTML = html + '<div style="height:var(--xxl)"></div>';
    };

    const switchPush = async () => {
      if (pushBusy) return;
      tick();
      pushBusy = true;
      try {
        if (push === "on") {
          const endpoint = await mrPush.disable();
          if (endpoint) await Api.post("/push/unsubscribe", { endpoint });
        } else {
          const key = (await Api.get("/push/key")).key;
          const sub = await mrPush.enable(key);
          if (sub) await Api.post("/push/subscribe", JSON.parse(sub));
        }
      } catch (e) { toast("Не получилось: " + errorText(e), "error"); }
      push = await mrPush.state();
      pushBusy = false;
      draw();
    };
    const customRemind = async (key) => {
      const r = (s.remind || []).find((x) => x.key === key);
      if (!r) return;
      const v = prefs()[key] || 0, max = r.max;
      const got = await inputSheet({ title: r.title, text: "За сколько минут до пары напомнить", hint: `минут, до ${max}`,
        initial: v > 0 && !(r.presets || []).includes(v) ? String(v) : "", type: "number" });
      if (got === null) return;
      const n = /^\d+$/.test(got.trim()) ? parseInt(got.trim(), 10) : -1;
      if (n < 1 || n > max) { toast(`Число минут от 1 до ${max}`, "error"); return; }
      save({ prefs: { [key]: n } });
    };
    // «своё» время сводки: часы — от 17 до 23, минуты — до получаса (сервер проверяет раз в 30 минут)
    const customEvening = async () => {
      const cur = prefs().evening_time || "20:00";
      const got = await Sheet.show(`<div class="ttl" style="--sz:24px">Во сколько прислать сводку</div>
        <div style="height:var(--l)"></div><input class="field mr-time" type="time" value="${esc(cur)}" step="1800">
        <div style="height:var(--l)"></div><button class="btn primary" data-act="ok">Готово</button>`,
      (b, close) => { const f = b.querySelector("input"); on(b, { ok: () => close(f.value) }); });
      if (typeof got !== "string" || !/^\d{1,2}:\d{2}/.test(got)) return;
      const [h, m] = got.split(":").map(Number);
      save({ prefs: { evening_time: mrEveningSlot(h, m) } });
    };

    on(body, {
      retry() { error = null; draw(); load(); },
      sw(b) {
        const k = b.dataset.k;
        if (k === "subscribed") save({ subscribed: !(s.subscribed === true) });
        else if (k === "push") { if (push !== "install" && push !== "denied") switchPush(); }
        else if (k === "tg_copy") toggle("tg_copy");
        else toggle(k);
      },
      day(b) {
        const k = b.dataset.k, i = +b.dataset.i, list = (prefs()[k] || []).slice();
        const at = list.indexOf(i);
        if (at >= 0) list.splice(at, 1); else list.push(i);
        list.sort((x, y) => x - y);
        save({ prefs: { [k]: list } });
      },
      rm(b) { save({ prefs: { [b.dataset.k]: +b.dataset.v } }); },
      "rm-own"(b) { customRemind(b.dataset.k); },
      quiz() { tick(); quizOpen = !quizOpen; draw(); },
      qz(b) {
        const m = +b.dataset.v, list = (prefs().quiz_remind || []).map(Number);
        const at = list.indexOf(m);
        if (at >= 0) list.splice(at, 1); else list.push(m);
        list.sort((x, y) => y - x);
        save({ prefs: { quiz_remind: list } });
      },
      qopen() { save({ prefs: { quiz_open: prefs().quiz_open === false } }); },
      ev(b) { save({ prefs: { evening_time: b.dataset.v } }); },
      soon(b) { save({ prefs: { deadline_soon_hours: +b.dataset.v } }); },
      "ev-own"() { customEvening(); },
    });

    const load = async () => {
      try {
        const fresh = await Api.get("/notify");
        if (pending === 0) s = fresh;
        error = null;
      } catch (e) { if (e.status === 401) return; error = e; }
      draw();
    };
    draw();
    load();
    mrPush.state().then((v) => { push = v; if (s && s.prefs) draw(); });
    return () => { if (onClose) onClose(); };
  });
};

// ── «Оформление» ──
/** Тема, шрифт и вид меняются сразу; вкладки строятся заново, когда закрыл экран. */
const mrLook = {
  dirty: false,
  theme() { return Prefs.get("uib_theme") || "system"; },
  font() {
    const f = Prefs.get("uib_font") || "book";
    return !Theme.design2 && (f === "hand" || f === "wide") ? "book" : f;
  },
  setTheme(t) { Ach.unlock("look"); Prefs.set("uib_theme", t); Theme.apply(); this.dirty = true; },
  setFont(f) { Ach.unlock("look"); Prefs.set("uib_font", f); Theme.apply(); this.dirty = true; },
  setLook(l) { Ach.unlock("look"); DarkVote.manual(Look.load(), l); Look.save(l); Theme.apply(); this.dirty = true; },
  done() { if (this.dirty) { this.dirty = false; Tabs.rebuild(); } },
};
const MR_FONTS = [["book", "SourceSerif", 500, 26, "Книжный", "с засечками"], ["strict", "Onest", 800, 26, "Строгий", "ровный"],
  ["hand", "Neucha", 400, 28, "Рукописный", "как от руки"], ["wide", "Unbounded", 500, 21, "Широкий", "плакатный"]];

/** Живой пример: фон темы, заголовок и пары так, как они будут на «Сегодня»
 *  (LookPreview); day — карточками или строками. */
function mrPreview(day = "cards") {
  const iso = isoDay();
  const mk = (h, m, title, kind, room, teacher, n) => {
    const a = new Date(`${iso}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00+03:00`), b = new Date(a.getTime() + 90 * 60000);
    return lessonOf({ start: hm(a), end: hm(b), title, kind, room, teacher, num: n, start_iso: a.toISOString(), end_iso: b.toISOString() });
  };
  const lessons = [mk(9, 0, "Анализ данных", "лекция", "А-332 (МП-1)", "Иванова А. С.", 1), mk(10, 40, "Основы предпринимательства", "практика", "Г-412 (МП-1)", "", 2)];
  const at = new Date(`${iso}T09:40:00+03:00`);
  return `<div class="mr-prev"><div class="ttl" style="--sz:26px">Идёт первая пара</div><div style="height:var(--m)"></div>
    ${day === "rows" ? lessonList(lessons, at, { tappable: false }) : lessons.map((l) => `<div style="margin-bottom:var(--s)">${lessonCard(l, at)}</div>`).join("")}</div>`;
}

// ── Переход на новый дизайн (шаг 9, dark_intro.dart; логика — DarkVote в core.js) ──
let dkOpen = false;
/** В тёмной — один раз экран «Мы обновили дизайн». */
window.maybeDarkIntro = function maybeDarkIntro() {
  if (dkOpen || !Theme.dark || !Theme.fresh || DarkVote.stage() !== "intro") return;
  window.openDarkIntro();
};
window.openDarkIntro = function openDarkIntro() {
  dkOpen = true;
  Nav.push((body, screen) => {
    const look = Look.load(), library = look.dark === "library", old = DarkVote.oldName(look);
    // кабинеты и подсветка пар красятся по светлой или тёмной теме — пример
    // светлой «Тетради» рисуем как в светлой, хотя вокруг сейчас тёмная
    const preview = (dark) => { const was = Theme.dark; Theme.dark = dark; try { return mrPreview("cards"); } finally { Theme.dark = was; } };
    const shot = (theme, title, id) => `<div class="dk-shot-col"><div class="dk-shot" data-app-theme="${theme}" id="${id}" aria-hidden="true">
      <div class="dk-shot-in">${preview(theme === "night")}</div></div><div class="bd b6" style="--sz:13px;text-align:center;margin-top:var(--s)">${esc(title)}</div></div>`;
    body.innerHTML = `<div class="dk-intro">
      <div class="ttl" style="--sz:30px">Мы обновили дизайн</div>
      <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Теперь по умолчанию так:</div>
      <div class="dk-shots">${shot("paper", "Тетрадь", "intro-paper")}${shot("night", "Ночная тетрадь", "intro-night")}</div>
      <div class="bd" style="--sz:15px">${esc(library
        ? "У тебя стояла тёмная «Библиотека». Она осталась в\u00A0«Классике», прежнем виде приложения."
        : `У тебя стояла прежняя тёмная «${old}». Она никуда не делась, но теперь не\u00A0основная.`)}</div>
      <div class="grow"></div>
      <button class="btn primary" data-act="fresh" id="intro-new">Попробовать новую</button>
      <button class="btn text dk-second" data-act="old" id="intro-old">${library ? "Оставить прежний вид" : "Оставить прежнюю"}</button>
      <div class="bd mut" style="--sz:13px;text-align:center;margin-top:var(--xs)">Поменять можно в любой момент: «Ещё», «Оформление».</div></div>`;
    // пример рисуется шириной 330 и уменьшается до колонки (как в приложении)
    const fit = () => body.querySelectorAll(".dk-shot").forEach((el) => {
      const w = el.clientWidth;
      if (w) el.querySelector(".dk-shot-in").style.zoom = String(w / 330);
    });
    fit();
    addEventListener("resize", fit);
    const answer = (fn) => { tick(); fn(); Nav.pop(); Tabs.rebuild(); };
    on(body, { fresh: () => answer(() => DarkVote.tryNew()), old: () => answer(() => DarkVote.keepOld()) });
    return () => { removeEventListener("resize", fit); dkOpen = false; };
  }, { cls: "dk-screen" });
};
/** Карточка опроса на «Сегодня» — только в тёмной и только когда пора. */
window.darkAskCard = function darkAskCard() {
  const ask = Theme.dark ? DarkVote.ask() : null;
  if (!ask) return "";
  const old = DarkVote.oldName(Look.load());
  const [title, text, a, b] = {
    howNew: ["Как тебе новая тёмная?", `Можно на пару дней вернуть прежнюю, «${old === "Глубина" ? "Глубину" : "Библиотеку"}», и\u00A0сравнить.`,
      ["likeNew", "Нравится новая"], ["compare", "Сравнить"]],
    which: ["Какая тёмная лучше?", "Обе уже знакомы. Что выберешь, то\u00A0и\u00A0останется, а мы посчитаем голоса.",
      ["pickNew", "Ночная тетрадь"], ["pickOld", old]],
    retry: ["Попробуешь новую тёмную?", "«Ночная тетрадь» теперь основная. Вернуть прежнюю можно в\u00A0любой момент.",
      ["retry", "Попробовать"], ["stayOld", "Нет, спасибо"]],
  }[ask];
  // «какая лучше» — обе кнопки одинаковые, чтобы не подсказывать
  const btn = ([v, label], main) => `<button class="dk-ask-btn${main ? " main" : ""}" data-act="dark" data-v="${v}" id="dark-${ask}-${v}">${esc(label)}</button>`;
  return `<div class="hx" style="padding-top:var(--m)"><div class="tile dk-ask" id="dark-${ask}">
    <div class="ttl" style="--sz:20px">${esc(title)}</div><div class="bd mut" style="--sz:14px;margin-top:var(--xs)">${esc(text)}</div>
    <div class="dk-ask-row">${btn(a, true)}${btn(b, ask === "which")}</div></div></div>`;
};
/** Ответ на карточку: вид меняется, голос уходит; экраны строятся заново. */
window.darkAnswer = function darkAnswer(v) {
  const run = { likeNew: () => DarkVote.likeNew(), compare: () => DarkVote.compare(), pickNew: () => DarkVote.pick(true),
    pickOld: () => DarkVote.pick(false), retry: () => DarkVote.retry(), stayOld: () => DarkVote.stayOld() }[v];
  if (!run) return;
  tick();
  run();
  Tabs.rebuild();
};

window.openLook = function openLook() {
  if (!Theme.design2) { mrThemeSheet(); return; }
  Nav.push((body) => {
    const seg = (id, value, items, small = false) => `<div class="mr-seg${small ? " small" : ""}">${items.map(([v, label]) =>
      `<button class="${v === value ? "on" : ""}" data-act="seg" data-id="${id}" data-v="${v}" aria-pressed="${v === value}">${esc(label)}</button>`).join("")}</div>`;
    const swatch = (kind, theme, title, sub, selected, paper) => `<button class="mr-swatch${selected ? " on" : ""}" data-act="swatch" data-k="${kind}" data-v="${theme}" aria-pressed="${selected}">
      <div class="mr-sw-bg mr-paper-${paper}" data-app-theme="${theme}"><div class="mr-sw-card">
        <i style="width:54px;background:var(--t-text)"></i><i style="width:34px;background:var(--t-muted);margin-top:5px"></i>
        <div class="row" style="gap:4px;margin-top:7px"><i style="width:22px;height:8px;border-radius:4px;background:var(--t-accent)"></i>
          <i style="width:8px;height:8px;border-radius:50%;background:var(--t-ok)"></i></div></div></div>
      <div style="padding:8px 6px 4px"><div class="bd b6" style="--sz:14.5px">${esc(title)}</div><div class="bd mut" style="--sz:12px">${esc(sub)}</div></div></button>`;
    const preview = () => mrPreview(Look.load().day);
    const draw = () => {
      const look = Look.load(), theme = mrLook.theme(), font = mrLook.font();
      const classic = Look.classic, fresh = Theme.fresh;
      const changed = ["light", "dark", "paper", "card", "day", "cheer", "icon"].some((k) => look[k] !== classic[k]) || look.freshDepth || look.tabLabels
        || (!fresh && (font === "hand" || font === "wide")) || theme === "sunset";
      const sun = moscowSun(now());
      const hint = (t) => `<div class="bd mut mr-hint">${esc(t)}</div>`;
      const fonts = MR_FONTS.map(([id, fam, w, size, title, sub]) => `<button class="tile mr-font${font === id ? " on" : ""}" data-act="font" data-v="${id}" aria-pressed="${font === id}">
        <span style="font-family:${fam};font-weight:${w};font-size:${size}px;line-height:1">Аа</span>
        <div class="grow" style="min-width:0"><div class="bd b6 ell" style="--sz:14px">${title}</div><div class="bd mut ell" style="--sz:12px">${sub}</div></div></button>`).join("");
      body.innerHTML = backRow() + screenTitle("Оформление")
        + `<div class="hx" style="padding-top:var(--s)">${preview()}</div>`
        // дизайн по брендбуку v1: «Новое / Классика»; сервер выключил (DESIGN3=0) — строки нет
        + (Theme.design3 !== "off" ? section("вид приложения") + `<div class="hx">${seg("mode", fresh ? "fresh" : "classic", [["fresh", "Новое"], ["classic", "Классика"]])}</div>`
            + hint(fresh ? "Новый вид приложения: бумага «Тетради» и шрифт с засечками. Экраны обновляются по одному." : "Прежний вид: четыре темы и четыре шрифта на выбор.") : "")
        + section("когда тёмная") + `<div class="hx">${seg("theme", theme, [["system", "Как в телефоне"], ["sunset", "По закату"], ["light", "Светлая"], ["dark", "Тёмная"]])}</div>`
        + (theme === "sunset" ? hint(`Сегодня тёмная с ${hm(sun.set)} до ${hm(sun.rise)} завтра, за час до заката фон мягко темнеет.`) : "")
        + (fresh ? section("бумага") : section("светлая тема") + `<div class="hx mr-two">${swatch("light", "notebook", "Тетрадь", "тёплая бумага", look.light === "notebook", look.paper)}
            ${swatch("light", "campus", "Кампус", "белая, синий акцент", look.light === "campus", "smooth")}</div>`)
        + (fresh || look.light === "notebook" ? `<div class="hx" style="margin-top:${fresh ? 0 : "var(--s)"}">${seg("paper", look.paper, [["smooth", "Гладкая"], ["cell", "Клетка"], ["line", "Линейка"], ["dots", "Точки"], ["grid", "Милли­метровка"]], true)}</div>` : "")
        + section("тёмная тема") + (fresh ? `<div class="hx">${seg("night", look.freshDepth ? "depth" : "night", [["night", "Ночная тетрадь"], ["depth", "Глубина"]])}</div>`
          : `<div class="hx mr-two">${swatch("dark", "depth", "Глубина", "синее свечение", look.dark === "depth", "smooth")}
            ${swatch("dark", "library", "Библиотека", "тёмно-зелёная", look.dark === "library", "smooth")}</div>`)
        + (fresh ? "" : section("шрифт заголовков") + `<div class="hx mr-fonts">${fonts}</div>`)
        + (fresh ? section("меню внизу") + `<div class="hx">${seg("tabs", look.tabLabels ? "labels" : "short", [["short", "Коротко"], ["labels", "С подписями"]])}</div>` : "")
        + section("пары на «сегодня»") + `<div class="hx">${seg("day", look.day, [["cards", "Карточками"], ["rows", "Строками"]])}</div>`
        + (look.day === "cards" ? `<div class="hx" style="margin-top:var(--s)">${seg("card", look.card, [["tint", "С цветом"], ["stripe", "С полоской"]])}</div>` : "")
        + section("когда отметил «сдано»") + `<div class="hx">${seg("cheer", look.cheer, [["quiet", "Тихо"], ["capy", "Капибара"], ["confetti", "Конфетти"]])}</div>`
        + (changed ? `<div style="height:var(--xl)"></div><div style="text-align:center"><button class="mr-reset" data-act="reset">${icon("undo", "", "color:var(--muted)")}
            <span class="bd mut" style="--sz:15px">Сбросить оформление</span></button></div>` : "")
        + '<div style="height:var(--xxl)"></div>';
    };
    on(body, {
      seg(b) {
        const id = b.dataset.id, v = b.dataset.v;
        if (b.classList.contains("on")) return;
        tick();
        if (id === "theme") mrLook.setTheme(v);
        else {
          const look = Look.load();
          if (id === "mode") look.fresh = v === "fresh";
          else if (id === "night") look.freshDepth = v === "depth";
          else if (id === "tabs") look.tabLabels = v === "labels";
          else look[id] = v;
          mrLook.setLook(look);
        }
        draw();
        // сразу показать, как это будет
        if (id === "cheer") { const f = window.cheer || window.showCheer; if (typeof f === "function") setTimeout(() => f(), 50); }
      },
      swatch(b) {
        if (b.classList.contains("on")) return;
        tick();
        const look = Look.load();
        look[b.dataset.k] = b.dataset.v;
        mrLook.setLook(look);
        draw();
      },
      font(b) { if (b.classList.contains("on")) return; tick(); mrLook.setFont(b.dataset.v); draw(); },
      reset() {
        tick();
        // «как было» внутри выбранного вида: «Новое / Классика» сброс не трогает
        mrLook.setLook({ ...Look.classic, fresh: Look.load().fresh });
        const f = mrLook.font();
        if (!Theme.fresh && (f === "hand" || f === "wide")) mrLook.setFont("book");
        if (mrLook.theme() === "sunset") mrLook.setTheme("system");
        draw();
      },
    });
    draw();
    return () => mrLook.done();
  });
};

/** Лист «Тема и шрифт» (сервер выключил новый дизайн): шрифт и тема — как в телефоне, светлая, тёмная. */
function mrThemeSheet() {
  Sheet.show('<div class="mr-tsheet"></div>', (body) => {
    const box = body.querySelector(".mr-tsheet");
    const draw = () => {
      const font = mrLook.font(), theme = mrLook.theme();
      const fontCard = (f) => {
        const book = f === "book";
        return `<button class="tile mr-fcard${font === f ? " on" : ""}" data-act="font" data-v="${f}">
          <div style="font-family:${book ? "SourceSerif" : "Onest"};font-weight:${book ? 500 : 800};font-size:30px;line-height:1.2">Аа 73</div>
          <div class="bd b6" style="--sz:14px;margin-top:4px">${book ? "Книжный" : "Строгий"}</div>
          <div class="bd mut" style="--sz:12px">${book ? "с засечками" : "ровный, Onest"}</div></button>`;
      };
      const rows = [["system", "brightness_auto", "Как в телефоне", Theme.dark ? "сейчас тёмная «Глубина»" : "сейчас светлая «Тетрадь»"],
        ["light", "light_mode", "Светлая", "«Тетрадь»"], ["dark", "dark_mode", "Тёмная", "«Глубина»"]];
      box.innerHTML = `<div class="ttl" style="--sz:22px">Тема и шрифт</div><div style="height:var(--m)"></div>
        <div class="mr-two">${fontCard("book")}${fontCard("strict")}</div><div style="height:var(--s)"></div>
        <div class="tile p0">${rows.map(([t, ic, title, sub], i) => `${i ? '<div class="divider"></div>' : ""}
          <button class="mr-mrow" data-act="theme" data-v="${t}" aria-pressed="${theme === t}">${icon(ic, "o", "color:var(--accent)")}
          <div class="grow"><div class="bd b6" style="--sz:16px">${title}</div><div class="bd mut" style="--sz:13px">${sub}</div></div>
          ${icon("check_circle", "", `color:var(--accent);opacity:${theme === t ? 1 : 0};transition:opacity .18s`)}</button>`).join("")}</div>`;
    };
    on(box, {
      font(b) { tick(); mrLook.setFont(b.dataset.v); draw(); },
      theme(b) { tick(); mrLook.setTheme(b.dataset.v); draw(); },
    });
    draw();
  }).then(() => mrLook.done());
}

// ── «Безопасность» — устройства, вход без Telegram, как защищены данные (/api/security) ──
const MR_BRANDS = {
  vk: '<svg viewBox="0 0 48 48" width="22" height="22" aria-hidden="true"><rect width="48" height="48" rx="11" fill="#0077FF"/><path fill="#fff" d="M25.5 34.6c-10.9 0-17.2-7.5-17.4-20h5.5c.2 9.2 4.2 13.1 7.4 13.9V14.6h5.2v7.9c3.1-.3 6.4-3.9 7.5-7.9h5.2c-.9 4.9-4.5 8.5-7 10 2.6 1.2 6.7 4.3 8.3 10h-5.7c-1.2-3.8-4.3-6.7-8.3-7.1v7.1h-.7Z"/></svg>',
  yandex: '<svg viewBox="0 0 48 48" width="22" height="22" aria-hidden="true"><circle cx="24" cy="24" r="24" fill="#FC3F1D"/><path fill="#fff" d="M27.1 12.5h-3.2c-5.6 0-8.6 2.9-8.6 7.1 0 3.4 1.6 5.5 4.6 7.6l-5.2 7.8h4.2l5.8-8.7-2-1.3c-2.4-1.6-3.6-2.9-3.6-5.6 0-2.4 1.7-4 4.9-4h3v19.6h3.9V12.5h-3.8Z"/></svg>',
};
function mrSeen(at) {
  const t = at ? new Date(String(at).replace(" ", "T") + "Z") : null;
  if (!t || isNaN(t)) return "давно";
  const a = msk(now()), b = msk(t);
  const days = Math.round((Date.UTC(a.y, a.m - 1, a.d) - Date.UTC(b.y, b.m - 1, b.d)) / 864e5);
  if (days <= 0) return "сегодня";
  if (days === 1) return "вчера";
  return `${b.d} ${MONTHS[b.m - 1]}`;
}
/** Коротко о защите простыми словами; цифры с сервера (_facts). */
function mrFacts(s) {
  const lim = s.limits || {}, ai = (lim.ai && lim.ai.count) ?? 15, sub = lim.submit || {}, minutes = s.link_minutes ?? 10;
  return [
    ["lock", "Вход в СДО зашифрован", `${s.sdo === "ok" ? "Твой вход подключён. " : ""}Пароль не хранится — только «оставаться в системе», и тот зашифрован. Ключ лежит отдельно от базы.`,
      "Даже если базу украдут, без ключа вход не прочитать."],
    ["phonelink_lock", "Вход в приложение", "Через бота, без пароля. Ключ входа есть только на этом телефоне, на сервере — его отпечаток.",
      "Потерял телефон — выйди на нём кнопкой выше, и ключ перестанет работать."],
    ["download", "Файлы — по коротким ссылкам", `Ссылка на скачивание подписана и живёт ${minutes} минут.`, `Переслал ссылку — через ${minutes} минут по ней уже ничего не скачать.`],
    ["auto_awesome", "Вопросы к ИИ", "Уходит только вопрос, история чата и нужные куски лекций. Имя и вход в СДО — нет.",
      "Имя и вход с вопросом не уходят. Но сам вопрос и файл ИИ читает — личное в них лучше не писать."],
    ["dns", "Сервер — в России", "Бот, приложение и база — на своём сервере в Москве.",
      "За границу уходят только сообщения Telegram, уведомления и вопросы к ИИ — в зашифрованном виде."],
    ["insights", "Статистика — без содержимого", `Только «кто, что открыл и когда». Через ${s.events_days ?? 180} дней удаляется сама.`,
      "Что ты спрашивал и какие файлы смотрел, никто не видит."],
    ["speed", "Защита от перегруза", `Не больше ${ai} вопросов ИИ в минуту и ${sub.count ?? 6} сдач за ${sub.minutes ?? 10} минут.`,
      "Один человек не займёт бота целиком — остальным он отвечает как обычно."],
  ];
}

window.openSecurity = function openSecurity() {
  Nav.push((body) => {
    let d = null, error = null, hidden = 0, seq = 0;
    const read = (sessions, ids, sec) => ({ sessions: (sessions && sessions.items) || [], identities: ids && typeof ids === "object" ? ids : null,
      security: sec && typeof sec === "object" ? sec : {} });
    const load = async () => {
      const my = ++seq;
      try {
        const r = await Promise.all([Api.get("/auth/sessions"), Api.get("/auth/identities").catch(() => null), Api.get("/security").catch(() => ({}))]);
        if (my !== seq) return;
        d = read(...r);
        error = null;
      } catch (e) { if (e.status === 401) return; error = e; }
      draw();
    };
    const leave = () => { Nav.popAll(); logout(); };   // вышли на этом устройстве — ко входу
    const action = (ic, title, sub, label, act, attrs, { danger = false, brand = "" } = {}) => `<div class="row mr-arow">
      ${brand && MR_BRANDS[brand] ? MR_BRANDS[brand] : icon(ic, "o", "font-size:20px;color:var(--muted)")}
      <div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div><div class="bd mut" style="--sz:12px">${esc(sub)}</div></div>
      <button class="mr-tbtn" style="color:${danger ? "var(--danger)" : "var(--accent)"}" data-act="${act}"${attrs}>${esc(label)}</button></div>`;
    const draw = () => {
      if (!d) {
        body.innerHTML = backRow() + (error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner());
        return;
      }
      const sec = d.security, n = d.sessions.length;
      const ids = d.identities, available = (ids && ids.available) || [];
      const linked = new Set(((ids && ids.items) || []).map((i) => i.provider));
      const summary = [sec.sdo === "ok" ? "Вход в СДО зашифрован, пароль не хранится" : "Пароль от СДО не хранится",
        `ссылки на файлы живут ${sec.link_minutes ?? 10} минут`, n > 0 ? `устройств вне Telegram: ${n}` : ""].filter(Boolean).join(", ");
      let html = backRow() + screenTitle("Безопасность")
        + `<div class="hx"><div class="tile row mr-safe"><span class="mr-safe-ic">${icon("verified_user", "o")}</span>
          <div class="grow"><div class="bd b7" style="--sz:16px;color:var(--ok)">Как защищены твои данные</div>
          <div class="bd mut" style="--sz:13px;margin-top:2px">${esc(summary)}.</div></div></div></div>`
        + section("Устройства")
        + `<div class="hx"><div class="tile p0">${d.sessions.map((x, i) => (i ? '<div class="divider"></div>' : "")
            + action("smartphone", `${x.device || "Устройство"}${x.current === true ? " · это" : ""}`, `заходил ${mrSeen(x.last_seen)}`, "Выйти", "revoke", ` data-i="${i}"`, { danger: true })).join("")}
          ${n ? "" : '<div class="bd mut" style="--sz:14px;padding:var(--l)">Входов вне Telegram нет</div>'}</div></div>`;
      if (n > 1) {
        html += `<div class="hx" style="padding-top:var(--xs)"><button class="mr-every" data-act="everywhere">${icon("logout", "", "font-size:18px;color:var(--danger)")}
          <span class="bd b6" style="--sz:15px;color:var(--danger)">Выйти везде</span></button></div>`;
      }
      if (available.length) {
        html += section("Вход без Telegram")
          + '<div class="bd mut" style="--sz:13px;padding:0 var(--xl) var(--s)">Привяжи VK или Яндекс — войдёшь, даже если Telegram не откроется.</div>'
          + `<div class="hx"><div class="tile p0">${available.map((a, i) => (i ? '<div class="divider"></div>' : "")
              + (linked.has(a.id) ? action("link", a.name, "привязан", "Отвязать", "unlink", ` data-p="${esc(a.id)}"`, { danger: true, brand: a.id })
                : action("add_link", a.name, "не привязан", "Привязать", "link", ` data-p="${esc(a.id)}"`, { brand: a.id }))).join("")}</div></div>`;
      }
      html += section("Как защищены данные") + mrFacts(sec).map(([ic, title, text, meaning]) => `<div class="hx mr-gap"><div class="tile row" style="align-items:flex-start">
          ${icon(ic, "o", "font-size:22px;color:var(--accent)")}<div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div>
          <div class="bd mut" style="--sz:13px;margin-top:2px">${esc(text)}</div><div class="bd b6" style="--sz:13px;margin-top:4px">${esc(meaning)}</div></div></div></div>`).join("");
      if (hidden > 0) {
        html += `<div class="hx" style="padding-top:var(--m)"><div class="tile row">${icon("visibility_off", "o", "font-size:22px;color:var(--accent)")}
          <div class="bd grow" style="--sz:14px">Скрытые авторы: ${hidden} — их записей ты не видишь</div>
          <button class="mr-tbtn" data-act="unhide">Показать</button></div></div>`;
      }
      html += section("Твои данные") + `<div class="hx"><div class="tile">
        <div class="bd mut" style="--sz:14px">Что храним, сколько и кому передаём — в <a class="mr-a" data-act="legal" data-v="privacy">Политике обработки персональных данных</a>.
          Твоё <a class="mr-a" data-act="legal" data-v="consent">согласие на обработку персональных данных</a> можно отозвать — удалив всё.</div>
        <button class="mr-erase" data-act="erase">${icon("delete_outline", "", "font-size:20px;color:var(--danger)")}
          <span class="bd b6" style="--sz:15px;color:var(--danger)">Удалить все мои данные</span></button></div></div>`;
      body.innerHTML = html + '<div style="height:var(--xxl)"></div>';
    };
    on(body, {
      retry() { error = null; draw(); load(); },
      async revoke(b) {
        tick();
        const x = d.sessions[+b.dataset.i];
        try { await Api.del(`/auth/sessions/${x.id}`); }
        catch (e) { toast(errorText(e), "error"); return; }
        if (x.current === true) { leave(); return; }
        load();
      },
      async everywhere() {
        const ok = await confirmSheet({ title: "Выйти везде?", text: "На всех устройствах, и на этом тоже. Войти снова — через бота.",
          action: "Выйти везде", cancel: "Остаться", danger: true });
        if (!ok) return;
        try { await Api.post("/auth/logout?everywhere=true"); }
        catch (e) { toast(errorText(e), "error"); return; }
        leave();
      },
      async link(b) {
        tick();
        try {
          const r = await Api.post(`/auth/${b.dataset.p}/link`, { client: "web" });
          openLink(r.url);
        } catch (e) { toast(errorText(e), "error"); }
      },
      async unlink(b) {
        tick();
        try { await Api.del(`/auth/identities/${b.dataset.p}`); }
        catch (e) { toast(errorText(e), "error"); return; }
        load();
      },
      async unhide() {
        tick();
        try { await Api.del("/hidden-authors"); }
        catch (e) { toast(errorText(e), "error"); return; }
        hidden = 0;
        draw();
        toast("Снова видны все записи группы", "done");
      },
      legal(b) { tick(); if (typeof window.openLegal === "function") window.openLegal(b.dataset.v); else toast("Скоро"); },
      async erase() {
        if (typeof window.deleteMyData !== "function") { toast("Скоро"); return; }
        if (await window.deleteMyData()) leave();
      },
    });
    // вернулись из браузера после «Да, привязать» — список входов обновится сам
    const onVisible = () => { if (document.visibilityState === "visible" && d) load(); };
    document.addEventListener("visibilitychange", onVisible);
    const c = [Api.cached("/auth/sessions"), Api.cached("/auth/identities"), Api.cached("/security")];
    if (c[0]) d = read(c[0], c[1] ?? null, c[2] ?? {});
    draw();
    load();
    Api.get("/hidden-authors").then((r) => { hidden = Number((r && r.count) || 0); if (d) draw(); }, () => {});
    return () => document.removeEventListener("visibilitychange", onVisible);
  });
};

// ── «Из какой ты группы?» — поиск по справочнику групп МИРЭА ──
/** → Promise: выбранная группа {id, name, own} или null (вернулся назад). required — первый вход, без «назад». */
window.openGroupPick = function openGroupPick({ required = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    Nav.push((body) => {
      let items = [], note = null, current = null, adminNote = null, seq = 0, timer = 0;
      body.innerHTML = (required ? '<div style="height:var(--xl)"></div>' : backRow()) + screenTitle("Из какой ты группы?")
        + '<div class="mr-gcur"></div>'
        + `<div class="hx"><label class="mr-gfield">${icon("search", "", "color:var(--muted)")}
          <input type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Например, УИБО-03-24"></label></div>
          <div style="height:var(--m)"></div><div class="mr-gout"></div>`;
      const input = body.querySelector("input"), out = body.querySelector(".mr-gout"), cur = body.querySelector(".mr-gcur");
      const draw = () => {
        cur.innerHTML = current ? `<div class="bd mut" style="--sz:17px;padding:0 var(--xl) var(--m)">Сейчас: <b style="color:var(--text)">${esc(current.name)}</b></div>` : "";
        out.innerHTML = items.map((g, i) => `<div class="hx mr-gap"><button class="tile row mr-grow" data-act="pick" data-i="${i}">
            ${icon("groups", "o", "color:var(--accent)")}<span class="bd b6 grow" style="--sz:16px">${esc(g.name)}</span>
            ${icon("chevron_right", "", "color:var(--muted)")}</button></div>`).join("")
          + (note ? `<div class="bd mut" style="--sz:14px;padding:var(--s) var(--xl)">${esc(note)}</div>` : "")
          // «Посмотреть демо» на первом шаге (Никита 11.11): приложение на примере, без выбора группы
          + (required ? `<div class="hx" style="padding-top:var(--l);text-align:center">
              <div class="bd mut" style="--sz:13px">Пока просто смотришь? Открой пример — приложение с демо-данными.</div>
              <a class="dl-retry bd b6" data-demo href="/about/demo" target="_blank" rel="noopener" style="--sz:15px;color:var(--accent);display:inline-flex;align-items:center;gap:6px;min-height:44px;text-decoration:none">${icon("play_circle", "o", "font-size:20px")}Посмотреть демо</a></div>` : "")
          + (current && current.own !== true ? `<div class="hx" style="padding-top:var(--m)"><${adminNote ? "div" : "button"} class="tile row mr-grow"${adminNote ? "" : ' data-act="admin"'}>
              ${icon("verified_user", "o", "color:var(--accent)")}<div class="grow"><div class="bd b6" style="--sz:16px">Я староста этой группы</div>
              <div class="bd mut" style="--sz:13px">${esc(adminNote || "спрошу владельца бота — сможешь вести общие сроки и ДЗ")}</div></div></${adminNote ? "div" : "button"}></div>` : "");
      };
      const search = async (text) => {
        const my = ++seq;   // ответ на старый запрос не перетирает новый
        if (text.trim().length < 2) { items = []; draw(); return; }
        try {
          const r = await Api.get("/groups/search?q=" + encodeURIComponent(text.trim()));
          if (my !== seq) return;
          items = (r && r.items) || [];
          note = items.length ? null : "Такой группы не нашёл — проверь, как написано: «УИБО-03-24».";
        } catch (e) { note = errorText(e); }
        draw();
      };
      input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => search(input.value), 300); });
      on(body, {
        async pick(b) {
          tick();
          const g = items[+b.dataset.i];
          // из «Ещё» нажатие сразу меняло основную группу (UX-аудит 02.11, п. 30) — сначала спросим
          if (current && current.id !== g.id && !(await confirmSheet({ title: `Сменить группу на ${g.name}?`,
            text: "Расписание, сроки и файлы станут как у этой группы. Просто посмотреть чужое расписание можно поиском во вкладке «Неделя».", action: "Сменить" }))) return;
          try {
            const r = await Api.post("/me/group", { id: g.id });
            done = true;
            resolve(r.group || g);
            Nav.pop();
          } catch (e) { note = errorText(e); draw(); }
        },
        async admin() {
          tick();
          try { await Api.post("/me/group/admin"); adminNote = "Запрос отправлен — ответ придёт в бота."; }
          catch (e) { adminNote = errorText(e); }
          draw();
        },
      });
      if (!required) {
        Api.get("/me").then((me) => { if (me && me.group && typeof me.group === "object") { current = me.group; draw(); } }, () => {});
      }
      draw();   // «Посмотреть демо» видно сразу, до первого поиска
      setTimeout(() => input.focus(), 350);
      return () => { clearTimeout(timer); if (!done) resolve(null); };
    });
  });
};

// ── Знакомство: пять шагов поверх самих экранов, капсула подсвечена; в
// «Новом» шестой — «Каким сделать меню» (tour.dart: tourMenuStep) ──
const MR_TOUR = [
  ["space_dashboard", "Что где", "Сегодня — пары и что дальше. Неделя — всё расписание. Сдать — сроки и заметки. Учёба — баллы и цели. Ещё — настройки.", 0],
  ["swipe", "Листай недели", "Проведи по неделе влево или вправо — откроется соседняя. Нажми на день сверху — лента приедет к нему.", 1],
  ["task_alt", "Сдал — смахни вправо", "Смахни срок вправо — он отметится «Сдано». Нажми на срок — сдать файлом, напомнить или изменить.", 2],
  ["touch_app", "Нажми на пару", "Откроется карточка пары: кабинет и корпус, преподаватель, файлы и баллы по предмету.", 0],
  ["flag", "Цель по предмету", "Открой предмет и выбери оценку — капибара посчитает, сколько баллов и работ не хватает.", 3],
];
const MR_TOUR_MENU = ["view_week", "Каким сделать меню", "", 0];
/** Образец меню: та же капсула, уменьшенная копия настоящей (не сжатая). */
function mrTabSample(labels) {
  return `<div class="tr-sample" aria-hidden="true"><nav class="capsule${labels ? " labels" : ""}">${TABS.map((t, k) =>
    `<span class="slot${k === 0 ? " on" : ""}">${icon(t.icon, t.variant || "")}<span class="lbl">${t.label}</span></span>`).join("")}</nav></div>`;
}
window.showTour = function showTour() {
  return new Promise((resolve) => {
    let i = 0;
    const steps = Theme.fresh ? [...MR_TOUR, MR_TOUR_MENU] : MR_TOUR;
    const open = (tab) => { if (Tabs.index !== tab) Tabs.show(tab); Tabs.setHidden(false); };
    open(steps[0][3]);
    const ov = document.createElement("div");
    ov.className = "mr-tour";
    document.body.appendChild(ov);
    const place = () => {
      const cap = document.querySelector("#tabbar .capsule");
      const r = cap && cap.getBoundingClientRect();
      const hole = ov.querySelector(".mr-hole"), box = ov.querySelector(".mr-tbox");
      if (r && r.height) {
        Object.assign(hole.style, { display: "", left: r.left - 4 + "px", top: r.top - 4 + "px", width: r.width + 8 + "px", height: r.height + 8 + "px" });
        box.style.bottom = innerHeight - r.top + 18 + "px";
      } else { hole.style.display = "none"; box.style.bottom = "calc(var(--sab) + 18px)"; }
      // образцы — во всю ширину настоящего меню и уменьшены под карточку
      const real = r && r.width ? r.width : innerWidth - 36;
      ov.querySelectorAll(".tr-sample").forEach((w) => {
        const nav = w.firstElementChild, k = Math.min(1, w.clientWidth / real);
        nav.style.width = real + "px";
        nav.style.transform = `scale(${k})`;
        w.style.height = 64 * k + "px";
      });
    };
    const draw = (animate) => {
      const [ic, title, text] = steps[i], last = i === steps.length - 1, menu = steps[i] === MR_TOUR_MENU;
      const tabs = Look.load().tabLabels;
      const opt = (v, t, sub) => `<button class="tr-opt${v === tabs ? " on" : ""}" data-act="menu" data-v="${v ? "labels" : "short"}"
          aria-pressed="${v === tabs}" id="tour-menu-${v ? "labels" : "short"}">
        <div class="row"><div class="grow"><div class="bd b7" style="--sz:15px">${t}</div><div class="bd mut" style="--sz:13px">${sub}</div></div>
          ${icon(v === tabs ? "check_circle" : "radio_button_unchecked", "", `color:var(${v === tabs ? "--accent" : "--muted"})`)}</div>
        ${mrTabSample(v)}</button>`;
      ov.innerHTML = `<div class="mr-hole"></div><div class="mr-tbox"><div class="mr-tcard${animate ? " in" : ""}">
        <div class="row"><span class="mr-ticon">${icon(ic, "o")}</span><span class="grow"></span>
          <span style="display:flex">${steps.map((_, k) => `<i class="mr-dot${k === i ? " on" : ""}"></i>`).join("")}</span></div>
        <div class="ttl" style="--sz:26px;margin-top:var(--m)">${esc(title)}</div>
        ${menu ? `<div class="tr-opts">${opt(false, "Коротко", "Подпись только у открытой вкладки")}${opt(true, "С подписями", "Каждая вкладка подписана")}</div>
          <div class="bd mut" style="--sz:13px;margin-top:var(--m)">Поменять можно в любой момент: «Ещё», «Оформление».</div>`
        : `<div class="bd mut" style="--sz:15px;margin-top:var(--s)">${esc(text)}</div>`}
        <div class="row" style="justify-content:space-between;margin-top:var(--m)">
          ${last ? "<span></span>" : '<button class="mr-skip" data-act="skip">Пропустить</button>'}
          <button class="mr-next" data-act="next">${menu ? "Готово" : last ? "Понятно" : "Дальше"}</button></div></div></div>`;
      place();
    };
    const close = () => {
      open(0);
      ov.classList.add("out");
      removeEventListener("resize", place);
      setTimeout(() => ov.remove(), 220);
      resolve();
    };
    on(ov, {
      next() {
        tick();
        if (i + 1 >= steps.length) { close(); return; }
        i++;
        open(steps[i][3]);
        draw(true);
      },
      menu(b) {
        const look = Look.load(), v = b.dataset.v === "labels";
        if (look.tabLabels === v) return;
        tick();
        look.tabLabels = v;
        Look.save(look);
        Theme.apply();   // меню внизу меняется сразу
        draw(false);
      },
      skip() { close(); },
    });
    addEventListener("resize", place);
    draw(false);
  });
};
/** Тур при первом запуске (shell.dart: _maybeTour). */
window.maybeTour = async function maybeTour() {
  if (Prefs.get("uib_toured") === true) return;
  Prefs.set("uib_toured", true);
  await window.showTour();
};
