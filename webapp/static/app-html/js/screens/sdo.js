// «Вход в СДО» (app/lib/screens/sdo_connect.dart): свой вход студента
// (MoodleSession) — баллы, работы и сдача файлом. Статус, подключить по
// шагам, делиться заданиями с группой, отключить. В браузере чужую куку не
// прочитать, поэтому страницы входа СДО (sdo_login.dart) и тихого обновления
// (sdo_relogin.dart) тут нет — как в веб-сборке Flutter: только вставка.
// openSdoConnect() → Promise, который исполняется, когда экран закрыли.
"use strict";

/** «Проверено 5 мин назад» — checked_at приходит в UTC (checkedAgo). */
function stCheckedAgo(at) {
  if (!at) return "";
  const t = Date.parse(String(at).replace(" ", "T") + "Z");
  if (isNaN(t)) return "";
  const min = Math.floor((now().getTime() - t) / 60000);
  if (min < 1) return "Проверено только что";
  if (min < 60) return `Проверено ${min} мин назад`;
  if (min < 48 * 60) return `Проверено ${Math.round(min / 60)} ч назад`;
  return `Проверено ${Math.round(min / 1440)} дн. назад`;
}

/** Ссылки из /api/meta (api/links.dart: appLinks) — один запрос на запуск. */
let _stLinks = null;
function stAppLinks() {
  if (!_stLinks) {
    _stLinks = Api.get("/meta").then((m) => {
      const links = (m && m.links) || {};
      const out = {};
      for (const k of Object.keys(links)) out[k] = links[k] == null ? "" : String(links[k]);
      return out;
    }).catch((e) => { _stLinks = null; throw e; });
  }
  return _stLinks;
}

/**
 * Галочка согласия (legal.dart: ConsentCheck): «Даю [согласие…]» и «Подробнее —
 * в [Политике…]», ссылки синие и открывают текст поверх экрана.
 */
function stConsentCheck(on, extra = "") {
  return `<div class="st-consent"><button class="st-check-row" data-act="agree" role="checkbox" aria-checked="${on}">
      <i class="st-box${on ? " on" : ""}">${on ? icon("check", "", "font-size:16px") : ""}</i>
      <span class="bd grow" style="--sz:14px">Даю <a class="st-link" data-act="legal" data-v="consent">согласие на обработку персональных данных</a>${esc(extra)}</span></button>
    <div class="bd mut" style="--sz:12.5px;padding-left:34px">Подробнее — в <a class="st-link" data-act="legal" data-v="privacy">Политике обработки персональных данных</a></div></div>`;
}
/** Текст согласия или политики (legal.dart: LegalScreen); общий openLegal — если есть. */
function stOpenLegal(name) {
  tick();
  if (window.openLegal) { window.openLegal(name); return; }
  Nav.push((body) => {
    let alive = true;
    const load = async () => {
      try {
        const d = await Api.get(`/legal/${name}`);
        if (!alive) return;
        body.innerHTML = backRow() + screenTitle(d.title || "", { sub: `Версия ${d.version} от ${d.date}` })
          + `<div class="bd mut" style="--sz:15px;padding:0 var(--xl)">${esc(d.lead || "")}</div>`
          + (d.sections || []).map((sec, i) => section(sec.title) + `<div class="hx"><div class="tile st-legal" data-i="${i}"></div></div>`).join("")
          + '<div style="height:var(--xxl)"></div>';
        (d.sections || []).forEach((sec, i) => {
          const el = body.querySelector(`.st-legal[data-i="${i}"]`);
          const paint = (full) => {
            const blocks = sec.short && !full ? sec.short : sec.blocks || [];
            el.innerHTML = blocks.map((b) => b.ul
              ? b.ul.map((it) => `<div class="row" style="align-items:flex-start;gap:var(--m);margin-bottom:var(--s)"><i class="st-bullet"></i><div class="grow bd" style="--sz:14px">${esc(it)}</div></div>`).join("")
              : `<div class="bd" style="--sz:14px;margin-bottom:var(--s)">${esc(b.p)}</div>`).join("")
              + (sec.short && !full ? '<button class="bd st-link" style="--sz:14px;margin-bottom:var(--s)" data-act="more">Подробнее</button>' : "");
          };
          paint(false);
          on(el, { more: () => { tick(); paint(true); } });
        });
      } catch (e) {
        if (!alive) return;
        body.innerHTML = backRow() + '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(e), { pose: "sad", retry: "retry" });
      }
    };
    on(body, { retry: () => { body.innerHTML = backRow() + spinner(); load(); } });
    body.innerHTML = backRow() + spinner();
    load();
    return () => { alive = false; };
  });
}

/** Как достать MoodleSession — три шага (_Steps). */
const ST_STEPS = [
  ["Открой ", "online-edu.mirea.ru", " на компьютере и войди в свой аккаунт"],
  ["F12 → Application → Cookies → строка ", "MoodleSession", ""],
  ["Скопируй значение и вставь сюда", "", ""],
];

function openSdoConnect() {
  return new Promise((resolve) => {
    Nav.push((body) => {
      let st = null, loadError = null, error = null, busy = false, agree = false, cookie = "", guide = "", alive = true;
      const statusCard = (color, title, text) => `<div class="hx"><div class="tile row" style="gap:var(--l)">
        <i class="st-sdot" style="background:${color};box-shadow:0 0 8px color-mix(in srgb, ${color} 50%, transparent)"></i>
        <div class="grow"><div class="bd b6" style="--sz:16px">${esc(title)}</div>${text ? `<div class="bd mut" style="--sz:13px">${esc(text)}</div>` : ""}</div></div></div>`;
      const errLine = () => (error ? `<div class="bd" style="--sz:14px;color:var(--danger);padding:var(--m) var(--xl) 0">${esc(error)}</div>` : "");
      const draw = () => {
        const focused = document.activeElement && body.contains(document.activeElement) && document.activeElement.classList.contains("st-cookie");
        let html = backRow() + screenTitle("Вход в СДО");
        if (!st && !loadError) html += `<div style="padding:var(--xxl)">${spinner()}</div>`;
        else if (!st) html += notice("Не загрузилось", loadError, { retry: "reload" });
        else {
          const state = st.state || "off", shared = st.shared === true;
          html += state === "ok" ? statusCard("var(--ok)", "Подключено, работает", shared ? "Вход старосты из настроек бота" : stCheckedAgo(st.checked_at))
            : state === "expired" ? statusCard("var(--danger)", "Вход устарел", "СДО разлогинил сессию — подключи заново")
            : statusCard("var(--muted)", "Не подключено", "Сроки группы видны и без этого");
          if (state === "ok") {
            html += `<div class="bd mut" style="--sz:14px;padding:var(--l) var(--xl) 0">У работ из СДО есть кнопка «Сдать»: выбираешь файл — бот загружает его в нужное задание.</div>`;
            if (st.can_share === true) {
              html += section("Группа") + `<div class="hx"><div class="tile row" style="gap:var(--m)"><div class="grow">
                <div class="bd b6" style="--sz:15px">Делиться заданиями с группой</div>
                <div class="bd mut" style="--sz:13px;margin-top:4px">Бот возьмёт из твоего СДО задания и сроки для всей ${esc(st.group ? st.group : "группы")}. Баллы и работы никто не увидит.</div></div>
                <button class="switch st-sw${st.share === true ? " on" : ""}" role="switch" aria-checked="${st.share === true}" aria-label="Делиться заданиями с группой" data-act="share"${busy ? " disabled" : ""}></button></div></div>`;
            }
            html += errLine();
            if (!shared) html += `<div style="padding:var(--xl) var(--l) 0"><button class="st-tbtn" data-act="disconnect"${busy ? " disabled" : ""} style="color:var(--danger)">
              ${icon("link_off", "", "font-size:24px")}<span class="bd b6" style="--sz:15px">Отключить СДО</span></button></div>`;
          } else {
            if (state === "off") {
              html += section("Что даст вход") + `<div class="hx"><div class="tile">${ST_PERKS.map(([ic, v, t]) =>
                `<div class="row" style="padding:6px 0">${icon(ic, v, "font-size:20px;color:var(--accent)")}<div class="grow bd" style="--sz:14px">${esc(t)}</div></div>`).join("")}</div></div>`;
            }
            html += section("Как подключить") + `<div class="hx"><div class="tile">${ST_STEPS.map((s, i) =>
              `<div class="row" style="align-items:flex-start;${i ? "margin-top:var(--m)" : ""}"><i class="st-step">${i + 1}</i>
                <div class="grow bd" style="--sz:14px">${esc(s[0])}<b>${esc(s[1])}</b>${esc(s[2])}</div></div>`).join("")}</div></div>`;
            if (guide) html += `<div class="hx"><button class="st-tbtn acc" data-act="guide">${icon("photo_library", "o", "font-size:24px")}<span class="bd b6" style="--sz:15px">Гайд со скринами — в канале</span></button></div>`;
            html += `<div style="padding:var(--l) var(--l) 0"><div class="st-field">
                <input class="st-cookie" placeholder="Вставь MoodleSession…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" enterkeyhint="done" value="${esc(cookie)}">
                <button data-act="paste" aria-label="Вставить">${icon("content_paste", "", "font-size:20px;color:var(--muted)")}</button></div></div>
              <div style="padding:var(--m) var(--l) 0">${stConsentCheck(agree, ", в том числе из СДО: баллы, посещения, задания")}</div>
              ${errLine()}
              <div style="padding:var(--l) var(--l) 0"><button class="btn primary st-btn50" data-act="connect"${busy || !agree ? " disabled" : ""}>${busy ? "Проверяю…" : "Проверить и сохранить"}</button></div>
              <div class="row" style="align-items:flex-start;gap:var(--s);padding:var(--m) var(--xl) 0">${icon("shield", "o", "font-size:16px;color:var(--muted);margin-top:1px")}
                <div class="grow bd mut" style="--sz:13px">Это как «оставаться в системе». Значение сразу шифруется, в переписке и логах не остаётся. Отключить — одной кнопкой в любой момент.</div></div>`;
            if (state === "expired") html += `<div style="padding:var(--l) var(--l) 0"><button class="st-tbtn" style="width:100%;justify-content:center;color:var(--danger)" data-act="disconnect"${busy ? " disabled" : ""}>
              <span class="bd b6" style="--sz:15px">Убрать вход</span></button></div>`;
          }
        }
        body.innerHTML = html + '<div style="height:var(--xxl)"></div>';
        const f = body.querySelector(".st-cookie");
        if (f) {
          f.addEventListener("input", () => { cookie = f.value; });
          f.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); connect(); } });
          if (focused) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); }
        }
      };
      const load = async () => {
        try {
          const r = await Api.get("/sdo/status");
          if (!alive) return;
          st = Object.assign({}, r);
        } catch (e) {
          if (!alive) return;
          loadError = errorText(e);
        }
        draw();
      };
      /** Запрос, который меняет вход: ответ — новый статус. */
      const act = async (call) => {
        busy = true; error = null; draw();
        try {
          const r = await call();
          if (r && typeof r === "object" && alive) st = Object.assign({}, r);
        } catch (e) { error = errorText(e); }
        finally { busy = false; if (alive) draw(); }
      };
      const connect = async () => {
        const v = cookie.trim();
        if (!v || !agree || busy) return;
        tick();
        if (document.activeElement) document.activeElement.blur();
        await act(() => Api.post("/sdo/connect", { cookie: v, agree: true, via: "paste" }));
        if (st && st.state === "ok" && !error) { cookie = ""; draw(); }
      };
      on(body, {
        back: () => Nav.pop(),
        reload: () => { loadError = null; draw(); load(); },
        agree: (b, e) => {
          if (e.target.closest(".st-link")) return;
          tick(); agree = !agree; draw();
        },
        legal: (b, e) => { e.stopPropagation(); stOpenLegal(b.dataset.v); },
        paste: async () => {
          tick();
          try {
            const t = await navigator.clipboard.readText();
            if (t != null) { cookie = t.trim(); draw(); }
          } catch (e) {}
        },
        connect,
        share: (b) => {
          if (busy) return;
          tick();
          const v = !(st && st.share === true);
          act(() => Api.post("/sdo/share", { share: v })).then(() => {
            if (v && st && st.share === true && alive) toast("Спасибо! Задания группы появятся в сроках через минуту", "done");
          });
        },
        disconnect: async () => {
          if (busy) return;
          const ok = await confirmSheet({ title: "Отключить СДО?", text: "Сдавать работы отсюда будет нельзя, пока не подключишь снова.",
            action: "Отключить", cancel: "Оставить", danger: true });
          if (ok) await act(() => Api.post("/sdo/disconnect"));
        },
        guide: () => { tick(); openLink(guide); },
      });
      // ссылки «согласие» и «политика» внутри строки галочки — не переключают её
      body.addEventListener("click", (e) => {
        const a = e.target.closest(".st-link[data-act=legal]");
        if (a) { e.preventDefault(); e.stopPropagation(); stOpenLegal(a.dataset.v); }
      }, true);
      stAppLinks().then((l) => { guide = l.sdo_guide || ""; if (alive && guide && st && st.state !== "ok") draw(); }).catch(() => {});
      draw();
      load();
      return () => { alive = false; resolve(); };
    });
  });
}
window.openSdoConnect = openSdoConnect;
