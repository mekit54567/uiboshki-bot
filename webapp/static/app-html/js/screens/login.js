// Вход (app/lib/screens/login.dart): код → ссылка в бота → «Да, это я» в
// Telegram → токен сессии устройства; или VK ID / Яндекс ID (уходим к
// провайдеру в этом же окне, назад — /app#token=…); вход по коду для
// проверяющих магазинов; «Расписание без входа» (api/guest.dart).
// Здесь же правовое (screens/legal.dart): текст согласия и политики
// (openLegal), галочка согласия (acConsentCheck), экран «Твои данные»
// (openConsent) и «Удалить мои данные» (deleteMyData).
"use strict";

// ── До запуска (как app/web/index.html): VK/Яндекс вернули на /app#token=… —
// берём, только если вход начат в этом браузере не дольше 15 минут назад:
// чужая ссылка с токеном не должна переключать в чужой аккаунт. ──
(function acTakeHashToken() {
  try {
    const ls = localStorage;
    if (location.hash.indexOf("#token=") === 0) {
      const at = Math.max(+JSON.parse(ls.getItem("flutter.uib_oauth_at") || "0") || 0, +(ls.getItem("uib_oauth_at") || 0) || 0);
      ls.removeItem("flutter.uib_oauth_at");
      ls.removeItem("uib_oauth_at");
      if (Date.now() - at < 15 * 60 * 1000) ls.setItem("flutter.uib_token", JSON.stringify(decodeURIComponent(location.hash.slice(7))));
      history.replaceState(null, "", location.pathname + location.search);
    }
  } catch (e) {}
  // /app?ref=<код> — кто позвал (PlusBonus.rememberRef): помним до входа
  try {
    const code = (new URLSearchParams(location.search).get("ref") || "").trim();
    if (code && code.length <= 64) Prefs.set("uib_ref", code);
  } catch (e) {}
})();

/** Приписка для магазинов (api/links.dart: unofficialNote). */
const AC_UNOFFICIAL = "Неофициальное приложение для студентов РТУ МИРЭА. Его сделали студенты, а не университет.";

/** Официальные знаки на кнопках входа (design/brands/*.svg, widgets/brand_logo.dart). */
const AC_BRANDS = {
  telegram: `<svg viewBox="0 0 256 256"><defs><linearGradient id="ac-tg" x1="50%" x2="50%" y1="0%" y2="100%"><stop offset="0%" stop-color="#2aabee"/><stop offset="100%" stop-color="#229ed9"/></linearGradient></defs><circle cx="128" cy="128" r="128" fill="url(#ac-tg)"/><path fill="#fff" d="M57.94 126.648q55.98-24.384 74.64-32.152c35.56-14.786 42.94-17.354 47.76-17.441c1.06-.017 3.42.245 4.96 1.49c1.28 1.05 1.64 2.47 1.82 3.467c.16.996.38 3.266.2 5.038c-1.92 20.24-10.26 69.356-14.5 92.026c-1.78 9.592-5.32 12.808-8.74 13.122c-7.44.684-13.08-4.912-20.28-9.63c-11.26-7.386-17.62-11.982-28.56-19.188c-12.64-8.328-4.44-12.906 2.76-20.386c1.88-1.958 34.64-31.748 35.26-34.45c.08-.338.16-1.598-.6-2.262c-.74-.666-1.84-.438-2.64-.258c-1.14.256-19.12 12.152-54 35.686c-5.1 3.508-9.72 5.218-13.88 5.128c-4.56-.098-13.36-2.584-19.9-4.708c-8-2.606-14.38-3.984-13.82-8.41c.28-2.304 3.46-4.662 9.52-7.072"/></svg>`,
  vk: `<svg viewBox="3.33331 3 22 22" fill="none"><path d="M3.33331 13.56C3.33331 8.58197 3.33331 6.09295 4.87979 4.54648C6.42627 3 8.91528 3 13.8933 3H14.7733C19.7513 3 22.2404 3 23.7868 4.54648C25.3333 6.09295 25.3333 8.58197 25.3333 13.56V14.44C25.3333 19.418 25.3333 21.907 23.7868 23.4535C22.2404 25 19.7513 25 14.7733 25H13.8933C8.91528 25 6.42627 25 4.87979 23.4535C3.33331 21.907 3.33331 19.418 3.33331 14.44V13.56Z" fill="#0077FF"/><path d="M15.0398 18.9C10.0174 18.9 7.15269 15.4466 7.03333 9.70001H9.54912C9.63175 13.9178 11.4864 15.7044 12.9555 16.0728V9.70001H15.3245V13.3376C16.7752 13.1811 18.2992 11.5234 18.8134 9.70001H21.1823C20.7875 11.9471 19.1348 13.6047 17.9595 14.2862C19.1348 14.8387 21.0171 16.2846 21.7333 18.9H19.1256C18.5655 17.1503 17.17 15.7965 15.3245 15.6123V18.9H15.0398Z" fill="#fff"/></svg>`,
  yandex: `<svg viewBox="0.378 0.77 32 32" fill="none"><circle cx="16.378" cy="16.77" r="16" fill="#FC3F1D"/><path d="M18.737 9.731h-1.62c-2.775 0-4.163 1.388-4.163 3.47 0 2.313.925 3.47 3.007 4.858l1.62 1.156-4.627 7.172H9.253l4.395-6.478c-2.545-1.85-3.933-3.47-3.933-6.477 0-3.7 2.545-6.245 7.403-6.245h4.858v19.2h-3.239V9.73z" fill="#fff"/></svg>`,
};
function acBrand(id, size = 22) {
  return AC_BRANDS[id] ? `<span class="ac-brand" style="width:${size}px;height:${size}px">${AC_BRANDS[id]}</span>` : "";
}

/** Ссылка наружу (PlusLinks.open / launchUrl): true — окно открылось. */
function acOpen(url) {
  try {
    const w = window.open(url, "_blank");
    if (w) { try { w.opener = null; } catch (e) {} return true; }
  } catch (e) {}
  return false;
}

/**
 * Загрузка экрана (Loader в widgets/common.dart): сразу — из запаса телефона,
 * свежие следом; ошибка без данных — «Не загрузилось» и «Ещё раз».
 * render(data) рисует; возвращает reload().
 */
function acLoad(body, path, render) {
  let data;
  const fail = (e) => {
    if (data !== undefined) return;
    body.innerHTML = backRow() + '<div style="height:80px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "ac-retry" });
    const b = body.querySelector('[data-act="ac-retry"]');
    if (b) b.addEventListener("click", () => { body.innerHTML = spinner(); reload(); });
  };
  const reload = async () => {
    try {
      const d = await Api.get(path);
      data = d;
      render(d);
    } catch (e) { fail(e); }
  };
  const c = Api.cached(path);
  if (c !== undefined && c !== null) { data = c; render(c); } else body.innerHTML = spinner();
  reload();
  return reload;
}

// ── Экран входа ──────────────────────────────────────────────────────────

/** Ссылка в бота: PWA на телефоне — сразу tg:// (botUri в login.dart). */
function acBotUri(link) {
  const m = /^https:\/\/t\.me\/(\w+)\?start=([\w-]+)$/.exec(link || "");
  const phone = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  return phone && m ? `tg://resolve?domain=${m[1]}&start=${m[2]}` : link;
}
function acOpenBot(link) {
  const uri = acBotUri(link);
  if (uri.startsWith("tg:")) location.href = uri;
  else acOpen(uri);
}

const AC_PENDING = "uib_login";
Screens.login = {
  mount(body, screen, onDone) {
    document.body.classList.add("ac-login");
    let poll = 0, code = null, link = null, pick = null, note = null, busy = false;
    let providers = [], codeLogin = false, gone = false, busyOauth = null;

    body.innerHTML = `<div class="ac-login-page">
      <div class="ac-sp"></div>
      <span style="color:var(--accent)">${capy("splash", 120)}</span>
      <div style="height:var(--xl)"></div>
      <div class="ttl ac-fit" style="--sz:54px">Капибара</div>
      <div style="height:10px"></div>
      <div style="width:34px;height:3px;border-radius:2px;background:var(--accent)"></div>
      <div style="height:var(--l)"></div>
      <div class="bd mut" style="--sz:16px">Расписание, сроки и баллы МИРЭА. Без паролей и кодов из SMS: через бота в Telegram, VK или Яндекс.</div>
      <div class="ac-sp"></div>
      <div class="ac-bottom"></div>
    </div>`;
    const bottom = body.querySelector(".ac-bottom");

    const savePending = () => {
      if (code === null) Prefs.set(AC_PENDING, null);
      else Prefs.set(AC_PENDING, JSON.stringify({ code, link, pick, until: Date.now() + 10 * 60 * 1000 }));
    };
    const waitNote = () => (pick === null ? "Подтверди вход в боте — «Да, это я»" : "В боте — «Да, это я», потом это число:");
    const draw = () => {
      if (gone) return;
      const disabled = busy && link === null;
      bottom.innerHTML = `
        ${note !== null ? `<div class="bd mut" style="--sz:14px;margin-bottom:var(--m)">${esc(note)}</div>` : ""}
        ${pick !== null && busy ? `<div class="ttl" id="login-pick" style="--sz:48px;margin-bottom:var(--m)">${esc(pick)}</div>` : ""}
        <button class="btn primary ac-tg" data-act="tg"${disabled ? " disabled" : ""}>${acBrand("telegram", 24)}<span>${busy ? "Открыть бота ещё раз" : "Войти через Telegram"}</span></button>
        ${providers.map((p) => `<div style="height:var(--s)"></div>
          <button class="ac-ob ac-prov" data-act="oauth" data-id="${esc(p.id)}"${busyOauth ? " disabled" : ""}>${acBrand(p.id)}<span>${busyOauth === p.id ? "Открываю…" : `Войти через ${esc(p.name)}`}</span></button>`).join("")}
        <div style="height:var(--m)"></div>
        <div class="bd mut" style="--sz:12px;text-align:center">${esc(AC_UNOFFICIAL)}</div>
        ${codeLogin ? `<div class="ac-center"><button class="ac-tb" data-act="code"><span class="bd mut" style="--sz:14px">Вход по коду доступа</span></button></div>` : ""}
        <div style="height:var(--s)"></div>
        <div class="ac-center"><button class="ac-tb" data-act="guest"><span class="bd b6" style="--sz:15px">Расписание без входа</span></button></div>
        <div class="bd mut" style="--sz:12px;text-align:center;margin-top:var(--s)"><a href="/about" style="color:inherit">О проекте</a> · <a href="/plus" style="color:inherit">Капибара+ и оплата</a> · <a href="/offer" style="color:inherit">Оферта</a> · <a href="/privacy" style="color:inherit">Политика</a></div>`;
    };

    const finish = () => {
      if (gone) return;
      gone = true;
      clearInterval(poll);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pageshow", onVisible);
      window.removeEventListener("focus", onVisible);
      document.body.classList.remove("ac-login");
      onDone();
    };
    let checking = false;
    const check = async () => {
      const c = code;
      if (c === null || checking) return;
      checking = true;
      try {
        // коротко: вернулся из Telegram — первый запрос на iPhone может повиснуть
        const r = await Api.post("/auth/poll", { code: c }, 6000);
        const status = r && r.status;
        if (!status || status === "wait") return;
        if (status === "ok") Api.token = r.token;
        clearInterval(poll);
        code = null;
        savePending();
        if (status === "ok") { finish(); return; }
        busy = false;
        note = status === "denied" ? "Вход отклонён в боте." : "Код устарел — попробуй ещё раз.";
        draw();
      } catch (e) { /* сеть моргнула — спросим ещё раз через 2 с */ }
      finally { checking = false; }
    };
    // вернулся из Telegram — проверить вход сразу, не ждать таймера
    // (iPhone останавливает таймеры, пока приложение в фоне)
    const onVisible = () => { if (document.visibilityState === "visible" && code !== null) check(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("pageshow", onVisible);
    window.addEventListener("focus", onVisible);

    const start = async () => {
      tick();
      busy = true; note = null;
      draw();
      try {
        const r = await Api.post("/auth/start", {}, 8000);
        code = r.code; link = r.link; pick = typeof r.pick === "number" ? r.pick : null;
        savePending();
        acOpenBot(r.link);
        clearInterval(poll);
        poll = setInterval(check, 2000);
        note = waitNote();
      } catch (e) {
        busy = false;
        note = errorText(e);
      }
      draw();
    };
    const oauth = async (id) => {
      if (busyOauth) return;
      tick();
      busyOauth = id; draw(); // нажатие видно сразу, пока сервер даёт ссылку
      try {
        const r = await Api.post(`/auth/${id}/start`, { client: location.pathname.startsWith("/app-html") ? "html" : "web" }, 8000);
        Prefs.set("uib_oauth_at", Date.now());
        location.href = r.url;
      } catch (e) { note = errorText(e); }
      busyOauth = null; draw();
    };
    const byCode = async () => {
      tick();
      const v = await inputSheet({ title: "Вход по коду доступа",
        text: "Код выдаём проверяющим App Store и RuStore. Внутри — пример данных, не настоящий студент.", hint: "Код", action: "Войти" });
      if (!v || gone) return;
      try {
        const r = await Api.post("/auth/review", { code: v.trim() });
        Api.token = r.token;
        finish();
      } catch (e) { note = errorText(e); draw(); }
    };

    on(body, {
      tg: () => (busy ? acOpenBot(link) : start()),
      oauth: (b) => oauth(b.dataset.id),
      code: byCode,
      // правило Apple 5.1.1(v): чужое расписание — публичное, смотреть можно без входа
      guest: () => { tick(); if (window.openSearch) openSearch(); },
    });

    // начатый вход помним 10 минут: iPhone часто перезапускает PWA, пока человек в Telegram
    try {
      const raw = Prefs.get(AC_PENDING);
      const j = raw ? JSON.parse(raw) : null;
      if (j && j.until >= Date.now() && j.code) {
        code = j.code; link = j.link || null; pick = typeof j.pick === "number" ? j.pick : null;
        busy = true; note = waitNote();
        poll = setInterval(check, 2000);
        check();
      }
    } catch (e) {}
    draw();
    Api.get("/auth/providers").then((r) => {
      providers = ((r && r.items) || []).map((p) => ({ id: String(p.id), name: String(p.name) }));
      codeLogin = !!(r && r.code === true);
      draw();
    }).catch(() => {});
    return () => {
      gone = true; clearInterval(poll);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pageshow", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  },
};

// ── Правовое (screens/legal.dart) ────────────────────────────────────────

/** Раздел текста: у длинного есть short — главное коротко, «Подробнее» — полный. */
function acLegalBlocks(blocks) {
  return (blocks || []).map((b) => b.ul
    ? b.ul.map((item) => `<div class="ac-li"><i></i><div class="bd" style="--sz:14px">${esc(item)}</div></div>`).join("")
    : `<div class="bd" style="--sz:14px;margin-bottom:var(--s)">${esc(b.p)}</div>`).join("");
}
function acLegalSection(sec) {
  const short = Array.isArray(sec.short) ? sec.short : null;
  return `<div class="ac-lsec">${acLegalBlocks(short || sec.blocks)}${short
    ? `<button class="bd ac-link ac-more" style="--sz:14px;margin-bottom:var(--s)" data-act="full">Подробнее</button>` : ""}</div>`;
}

/** Текст согласия или политики (LegalScreen): /legal/<имя>. */
window.openLegal = function openLegal(name) {
  tick();
  Nav.push((body) => {
    let doc = null;
    acLoad(body, `/legal/${name}`, (d) => {
      doc = d;
      body.innerHTML = backRow() + screenTitle(d.title || "", { sub: `Версия ${d.version} от ${d.date}` })
        + `<div class="bd mut" style="--sz:15px;padding:0 var(--xl)">${esc(d.lead || "")}</div>`
        + (d.sections || []).map((s, i) => section(s.title) + `<div class="hx"><div class="tile" data-i="${i}">${acLegalSection(s)}</div></div>`).join("")
        + `<div style="height:var(--xxl)"></div>`;
    });
    on(body, {
      full: (b) => {
        tick();
        const t = b.closest(".tile"), s = doc && doc.sections[+t.dataset.i];
        if (s) t.innerHTML = `<div class="ac-lsec">${acLegalBlocks(s.blocks)}</div>`;
      },
    });
  });
};

/** Галочка «Даю согласие…» и «Подробнее — в Политике…» (ConsentCheck). on — стоит ли. */
function acConsentCheck(onState, extra = "") {
  return `<div class="ac-check-wrap">
    <div class="ac-check" role="checkbox" aria-checked="${onState}" data-act="ac-agree">
      <span class="ac-box${onState ? " on" : ""}">${onState ? icon("check") : ""}</span>
      <span class="bd" style="--sz:14px">Даю <a class="ac-link" data-act="ac-legal" data-name="consent">согласие на обработку персональных данных</a>${esc(extra)}</span>
    </div>
    <div class="bd mut" style="--sz:12.5px;padding-left:34px">Подробнее — в <a class="ac-link" data-act="ac-legal" data-name="privacy">Политике обработки персональных данных</a></div>
  </div>`;
}
/** Обработчики галочки: el — где она; onChange(value). Ссылки открывают текст поверх. */
function acBindConsent(el, get, onChange) {
  el.addEventListener("click", (e) => {
    const l = e.target.closest('[data-act="ac-legal"]');
    if (l) { e.preventDefault(); e.stopPropagation(); openLegal(l.dataset.name); return; }
    const c = e.target.closest('[data-act="ac-agree"]');
    if (c) { tick(); onChange(!get()); }
  });
}

/**
 * «Твои данные» (ConsentScreen): первый вход и новая версия текста.
 * required — новый человек: без согласия дальше нельзя (назад не уйти).
 * → Promise: true — согласился, false — отказался (данные удалены), undefined — «Не сейчас».
 */
window.openConsent = function openConsent({ required = true } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (done) return; done = true; Nav.pop(); resolve(v); };
    // показали тому, кто был до согласий, — больше не показывать (и бот не спросит)
    if (!required) Api.post("/consent/asked", {}).catch(() => {});
    Nav.push((body) => {
      let agree = false, busy = false;
      const draw = () => {
        body.innerHTML = `<div style="padding:var(--xxl) var(--l)">
          ${icon("verified_user", "o", "font-size:44px;color:var(--accent)")}
          <div style="height:var(--l)"></div>
          <div class="ttl" style="--sz:30px">Твои данные</div>
          <div style="height:var(--m)"></div>
          <div class="bd mut" style="--sz:15px">Чтобы показывать расписание, дедлайны и баллы, приложению нужно хранить твой id, группу и настройки. Что именно и сколько — в политике. Удалить всё можно в любой момент: «Ещё → Безопасность».</div>
          <div style="height:var(--l)"></div>
          <div class="ac-consent">${acConsentCheck(agree)}</div>
          <div style="height:var(--xl)"></div>
          <button class="btn primary" style="min-height:50px;font-size:14px;font-weight:500" data-act="go"${agree && !busy ? "" : " disabled"}>Продолжить</button>
          <div style="height:var(--s)"></div>
          <button class="btn text" data-act="no"${busy ? " disabled" : ""}><span class="bd b6 mut" style="--sz:15px">${required ? "Не даю согласие" : "Не сейчас"}</span></button>
        </div>`;
      };
      draw();
      acBindConsent(body, () => agree, (v) => { agree = v; draw(); });
      on(body, {
        go: async () => {
          busy = true; draw();
          try { await Api.post("/consent", { kind: "pd" }); }
          catch (e) { busy = false; draw(); toast(errorText(e), "error"); return; }
          finish(true);
        },
        no: async () => {
          if (!required) { finish(undefined); return; }
          const ok = await confirmSheet({ title: "Без согласия — никак",
            text: "Приложение не может хранить твои данные без согласия. Удалить то, что уже есть, и выйти?",
            action: "Удалить и выйти", cancel: "Назад", danger: true });
          if (!ok || done) return;
          if (await deleteMyData({ confirmed: true })) finish(false);
        },
      });
      // назад (свайп, кнопка браузера): «Не сейчас»; новому — нельзя, экран встаёт снова
      return () => {
        if (done) return;
        if (required) setTimeout(() => { if (!done) openConsent({ required }).then((v) => { done = true; resolve(v); }); }, 320);
        else { done = true; resolve(undefined); }
      };
    });
  });
};

/** Фраза, которую вписывают руками (privacy.ERASE_PHRASE). */
const AC_ERASE_PHRASE = "удалить мои данные";
function acErasePhraseOk(text) {
  const t = String(text).toLowerCase().replace(/ё/g, "е").split(/\s+/).filter(Boolean).join(" ");
  return t.replace(/^[\s.!«»"']+|[\s.!«»"']+$/g, "") === AC_ERASE_PHRASE;
}

/**
 * «Удалить все мои данные» (deleteMyData): фразой руками (без вставки);
 * confirmed — отказ от согласия до первого входа, сразу насовсем.
 * → Promise<true> — удалено, вход на этом устройстве уже недействителен.
 */
window.deleteMyData = async function deleteMyData({ confirmed = false } = {}) {
  let body = { confirm: true };
  if (!confirmed) {
    const typed = await Sheet.show(`
      <div class="ttl" style="--sz:24px">Удалить все твои данные?</div>
      <div class="bd mut" style="--sz:15px;margin-top:8px;white-space:pre-line">${esc("Профиль, группу, вход в СДО, историю баллов и посещений, личные дедлайны, устройства, входы через VK, Яндекс и Apple. Сразу — выход со всех устройств и из СДО, рассылки и ИИ остановятся. Полностью всё сотрём через 7 дней: если удалил по ошибке, до этого можно написать Никите (@Partykq) — вернём вручную, если получится, без гарантии.\n\nЧтобы удалить, впиши: " + AC_ERASE_PHRASE)}</div>
      <div style="height:var(--l)"></div>
      <input class="field" type="text" autocomplete="off" placeholder="${AC_ERASE_PHRASE}">
      <div style="height:var(--l)"></div>
      <button class="btn primary" data-act="ok">Удалить</button>`,
    (b, close) => {
      const f = b.querySelector(".field");
      f.addEventListener("paste", (e) => e.preventDefault());
      f.addEventListener("drop", (e) => e.preventDefault());
      setTimeout(() => f.focus(), 300);
      on(b, { ok: () => close(f.value) });
      f.addEventListener("keydown", (e) => { if (e.key === "Enter") close(f.value); });
    });
    if (typeof typed !== "string") return false;
    if (!acErasePhraseOk(typed)) { toast("Фраза не совпала — ничего не удаляю", "error"); return false; }
    body = { phrase: typed };
  }
  let r;
  try { r = await Api.post("/me/delete", body); }
  catch (e) { toast(errorText(e), "error"); return false; }
  Api.token = null;
  Api.clearCache();
  const text = String((r && r.text) || "");
  if (!text) toast("Готово: всё о тебе удалено", "done");
  else await confirmSheet({ title: "Данные удаляются", text, action: "Понятно", cancel: "Закрыть" });
  return true;
};

/**
 * После входа (shell.dart: _ensureGroup до выбора группы): данные удаляются —
 * сказать и ко входу; нужно согласие — экран «Твои данные».
 * → Promise<boolean>: true — работаем дальше, false — уже вышли ко входу.
 * me — ответ /me (если уже есть).
 */
window.ensureConsent = async function ensureConsent(me) {
  if (!me) { try { me = await Api.get("/me"); } catch (e) { return true; } }
  if (!me) return true;
  if (me.erasing && typeof me.erasing === "object") {
    await confirmSheet({ title: "Данные удаляются", text: String(me.erasing.text || ""), action: "Понятно", cancel: "Закрыть" });
    await logout();
    return false;
  }
  if (me.consent_needed === true) {
    const blocked = me.consent_blocked === true;
    const ok = await openConsent({ required: blocked });
    if (ok === false || (blocked && ok !== true)) { await logout(); return false; }
    // до согласия API был закрыт — экраны загрузить заново
    if (blocked && typeof Tabs !== "undefined") Tabs.rebuild();
  }
  return true;
};
