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

// ── «Уведомления» — что бот присылает и в какие дни (/api/notify): сохраняется сразу ──
window.openNotify = function openNotify() {
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
          <div style="margin-top:var(--s)">${row("Тест открылся", "напишу, когда преподаватель откроет тест", "quiz_open", open, "qopen")}</div>` : ""}
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
        children: row("Дублировать в Telegram", tg ? "приходят и сюда, и в Telegram" : "только сюда; не дошло — тогда в Telegram", "tg_copy", tg) });
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
        + card({ title: "Присылать уведомления", sub: on ? "Включены — ниже, что именно" : "Выключены — бот ничего не пришлёт сам", key: "subscribed", on });
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
        html += card({ ic: "hourglass_bottom", title: "Срок скоро", sub: `за ${soonLabel(soonH)} до срока, если работа не сдана`, key: "deadline_soon",
          on: p.deadline_soon === true, children: `<div class="mr-wrap" style="margin-top:0">${(s.deadline_soon_choices || [1, 3, 6, 12, 24]).map((h) =>
            mrPill(soonLabel(h), soonH === h, "soon", ` data-v="${h}"`, { wide: true })).join("")}</div>` });
        html += card({ ic: "view_week", title: "Обзор недели", sub: "в воскресенье в 19:00 — сколько пар и что сдать", key: "weekly", on: p.weekly === true });
        html += card({ ic: "military_tech", title: "Новые баллы", sub: "когда проверят работу или изменятся баллы (если подключён вход в СДО)", key: "grades", on: p.grades === true });
        html += card({ ic: "assignment", title: "Новые задания", sub: "когда в СДО появится задание или перенесут срок", key: "new_tasks", on: p.new_tasks === true });
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
  setLook(l) { Ach.unlock("look"); Look.save(l); Theme.apply(); this.dirty = true; },
  done() { if (this.dirty) { this.dirty = false; Tabs.rebuild(); } },
};
const MR_FONTS = [["book", "SourceSerif", 500, 26, "Книжный", "с засечками"], ["strict", "Onest", 800, 26, "Строгий", "ровный"],
  ["hand", "Neucha", 400, 28, "Рукописный", "как от руки"], ["wide", "Unbounded", 500, 21, "Широкий", "плакатный"]];

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
    const preview = () => {
      const iso = isoDay();
      const mk = (h, m, title, kind, room, teacher, n) => {
        const a = new Date(`${iso}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00+03:00`), b = new Date(a.getTime() + 90 * 60000);
        return lessonOf({ start: hm(a), end: hm(b), title, kind, room, teacher, num: n, start_iso: a.toISOString(), end_iso: b.toISOString() });
      };
      const lessons = [mk(9, 0, "Анализ данных", "лекция", "А-332 (МП-1)", "Иванова А. С.", 1), mk(10, 40, "Основы предпринимательства", "практика", "Г-412 (МП-1)", "", 2)];
      const at = new Date(`${iso}T09:40:00+03:00`);
      const look = Look.load();
      return `<div class="mr-prev"><div class="ttl" style="--sz:26px">Идёт первая пара</div><div style="height:var(--m)"></div>
        ${look.day === "rows" ? lessonList(lessons, at, { tappable: false }) : lessons.map((l) => `<div style="margin-bottom:var(--s)">${lessonCard(l, at)}</div>`).join("")}</div>`;
    };
    const draw = () => {
      const look = Look.load(), theme = mrLook.theme(), font = mrLook.font();
      const classic = Look.classic;
      const changed = ["light", "dark", "paper", "card", "day", "cheer", "icon"].some((k) => look[k] !== classic[k]) || font === "hand" || font === "wide" || theme === "sunset";
      const sun = moscowSun(now());
      const hint = (t) => `<div class="bd mut mr-hint">${esc(t)}</div>`;
      const fonts = MR_FONTS.map(([id, fam, w, size, title, sub]) => `<button class="tile mr-font${font === id ? " on" : ""}" data-act="font" data-v="${id}" aria-pressed="${font === id}">
        <span style="font-family:${fam};font-weight:${w};font-size:${size}px;line-height:1">Аа</span>
        <div class="grow" style="min-width:0"><div class="bd b6 ell" style="--sz:14px">${title}</div><div class="bd mut ell" style="--sz:12px">${sub}</div></div></button>`).join("");
      body.innerHTML = backRow() + screenTitle("Оформление")
        + `<div class="hx" style="padding-top:var(--s)">${preview()}</div>`
        + section("когда тёмная") + `<div class="hx">${seg("theme", theme, [["system", "Как в телефоне"], ["sunset", "По закату"], ["light", "Светлая"], ["dark", "Тёмная"]])}</div>`
        + (theme === "sunset" ? hint(`Сегодня тёмная с ${hm(sun.set)} до ${hm(sun.rise)} завтра, за час до заката фон мягко темнеет.`) : "")
        + section("светлая тема") + `<div class="hx mr-two">${swatch("light", "notebook", "Тетрадь", "тёплая бумага", look.light === "notebook", look.paper)}
            ${swatch("light", "campus", "Кампус", "белая, синий акцент", look.light === "campus", "smooth")}</div>`
        + (look.light === "notebook" ? `<div class="hx" style="margin-top:var(--s)">${seg("paper", look.paper, [["smooth", "Гладкая"], ["cell", "Клетка"], ["line", "Линейка"], ["dots", "Точки"], ["grid", "Милли­метровка"]], true)}</div>` : "")
        + section("тёмная тема") + `<div class="hx mr-two">${swatch("dark", "depth", "Глубина", "синее свечение", look.dark === "depth", "smooth")}
            ${swatch("dark", "library", "Библиотека", "тёмно-зелёная", look.dark === "library", "smooth")}</div>`
        + section("шрифт заголовков") + `<div class="hx mr-fonts">${fonts}</div>`
        + section("пары на «сегодня»") + `<div class="hx">${seg("day", look.day, [["cards", "Карточками"], ["rows", "Строками"]])}</div>`
        + (look.day === "cards" ? `<div class="hx" style="margin-top:var(--s)">${seg("card", look.card, [["tint", "С цветом"], ["stripe", "С полоской"]])}</div>` : "")
        + section("когда отметил «сдано»") + `<div class="hx">${seg("cheer", look.cheer, [["quiet", "Тихо"], ["capy", "Капибара"], ["confetti", "Конфетти"]])}</div>`
        + (changed ? `<div style="height:var(--xl)"></div><div style="text-align:center"><button class="mr-reset" data-act="reset">${icon("undo", "", "color:var(--muted)")}
            <span class="bd mut" style="--sz:15px">Вернуть как было</span></button></div>` : "")
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
          look[id] = v;
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
        mrLook.setLook({ ...Look.classic });
        const f = mrLook.font();
        if (f === "hand" || f === "wide") mrLook.setFont("book");
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
      "ИИ не узнает, кто спрашивал. Но личное в вопросы лучше не писать."],
    ["dns", "Сервер — в России", "Бот, приложение и база — на своём сервере в Москве.",
      "За границу уходят только сообщения Telegram, уведомления и вопросы к ИИ — в зашифрованном виде."],
    ["insights", "Статистика — без содержимого", `Только «кто, что открыл и когда». Через ${s.events_days ?? 180} дней удаляется сама.`,
      "Что ты спрашивал и какие файлы смотрел, никто не видит."],
    ["speed", "Защита от перегруза", `Не больше ${ai} вопросов ИИ в минуту и ${sub.count ?? 6} сдач за ${sub.minutes ?? 10} минут.`,
      "Никто не завалит бота запросами — он не тормозит ни у кого."],
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
          <div class="grow"><div class="bd b7" style="--sz:16px;color:var(--ok)">Всё под защитой</div>
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
      setTimeout(() => input.focus(), 350);
      return () => { clearTimeout(timer); if (!done) resolve(null); };
    });
  });
};

// ── Знакомство: пять шагов поверх самих экранов, капсула подсвечена ──
const MR_TOUR = [
  ["space_dashboard", "Что где", "Сегодня — пары и что дальше. Неделя — всё расписание. Сдать — сроки и заметки. Учёба — баллы и цели. Ещё — настройки.", 0],
  ["swipe", "Листай недели", "Проведи по неделе влево или вправо — откроется соседняя. Нажми на день сверху — лента приедет к нему.", 1],
  ["task_alt", "Сдал — смахни вправо", "Смахни срок вправо — он отметится «Сдано». Нажми на срок — сдать файлом, напомнить или изменить.", 2],
  ["touch_app", "Нажми на пару", "Откроется карточка пары: кабинет и корпус, преподаватель, файлы и баллы по предмету.", 0],
  ["flag", "Цель по предмету", "Открой предмет и выбери оценку — капибара посчитает, сколько баллов и работ не хватает.", 3],
];
window.showTour = function showTour() {
  return new Promise((resolve) => {
    let i = 0;
    const open = (tab) => { if (Tabs.index !== tab) Tabs.show(tab); Tabs.setHidden(false); };
    open(MR_TOUR[0][3]);
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
    };
    const draw = (animate) => {
      const [ic, title, text] = MR_TOUR[i], last = i === MR_TOUR.length - 1;
      ov.innerHTML = `<div class="mr-hole"></div><div class="mr-tbox"><div class="mr-tcard${animate ? " in" : ""}">
        <div class="row"><span class="mr-ticon">${icon(ic, "o")}</span><span class="grow"></span>
          <span style="display:flex">${MR_TOUR.map((_, k) => `<i class="mr-dot${k === i ? " on" : ""}"></i>`).join("")}</span></div>
        <div class="ttl" style="--sz:26px;margin-top:var(--m)">${esc(title)}</div>
        <div class="bd mut" style="--sz:15px;margin-top:var(--s)">${esc(text)}</div>
        <div class="row" style="justify-content:space-between;margin-top:var(--m)">
          ${last ? "<span></span>" : '<button class="mr-skip" data-act="skip">Пропустить</button>'}
          <button class="mr-next" data-act="next">${last ? "Понятно" : "Дальше"}</button></div></div></div>`;
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
        if (i + 1 >= MR_TOUR.length) { close(); return; }
        i++;
        open(MR_TOUR[i][3]);
        draw(true);
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
