// Предложение показаться в рейтинге (screens/rating_offer.dart): карточка на
// «Рейтинге», лист с двумя выключенными тумблерами при входе. Когда спрашивать —
// решает сервер (rating_offer.py). Ничего не включается само; «Не сейчас» и
// «Показать» — одного размера.

const roHidden = (me) => me && me.show !== true && me.show_all !== true;

function roAct(action, source) {
  return Api.post("/rating/offer", { action, ...(source ? { source } : {}) }).catch(() => null);
}

/** Карточка (место в разметке — #rating-offer, заполняет roMountCard). */
function roCardHtml() {
  const words = `<div class="bd b6" style="--sz:16px">Тебя не видно в рейтинге группы</div>
    <div class="bd mut" style="--sz:14px;margin-top:4px">Покажешься? Вместо имени — ник или «Капибара\u00A0№…».</div>`;
  return `<div class="hx"><div class="tile ro-card" id="rating-offer">
    ${words}
    <div class="ro-btns"><button class="btn primary" id="rating-offer-show" data-act="ro-show">Показать</button>
      <button class="btn outline" id="rating-offer-later" data-act="ro-later">Не сейчас</button></div>
    <button class="btn text ro-stop" id="rating-offer-stop" data-act="ro-stop">Больше не предлагать</button></div></div>`;
}

/** После отрисовки «Я»: спросить сервер (один раз за открытие экрана) и показать карточку. */
async function roMountCard(body, st, me) {
  const slot = body.querySelector("#rating-offer-slot");
  if (!slot || !roHidden(me)) return;
  if (st.offer === undefined) {
    st.offer = null;
    try { st.offer = await Api.get("/rating/offer"); } catch (e) {}
    if (!body.isConnected) return;
  }
  const again = body.querySelector("#rating-offer-slot");
  if (again && st.offer && st.offer.card === true) again.innerHTML = roCardHtml();
}

/** Лист: оба тумблера выключены; «Группе» — сразу, «Всем» — через отдельное согласие. */
function roSheet(me0, source) {
  let me = me0, busy = false, accepted = false;
  return Sheet.show('<div class="ro-sheet"></div>', (body, close) => {
    const el = body.querySelector(".ro-sheet");
    const row = (title, sub, onS, id) => `<div class="row" style="padding:var(--m) var(--m) var(--m) var(--l)">
      <div class="grow"><div class="bd b6" style="--sz:15px">${esc(title)}</div><div class="bd mut" style="--sz:12.5px;margin-top:2px">${esc(sub)}</div></div>${acSwitch(onS, id)}</div>`;
    const draw = () => {
      const g = me.show === true, a = me.show_all === true, any = g || a;
      el.innerHTML = `<div class="ttl" style="--sz:24px">Показаться в рейтинге?</div>
        <div class="bd mut" style="--sz:15px;margin-top:var(--s)">${any
          ? "Включено то, что ты выбрал. Выключить можно в любой момент в «Мой опыт»."
          : "Сейчас тебя никто не видит. Не включишь — ничего не изменится."}</div>
        <div class="tile p0" style="margin-top:var(--l)">
          ${row("Группе", g ? "группа видит твой ник и опыт" : "одногруппники увидят твой ник и опыт", g, "rating-offer-group")}
          <div class="divider"></div>
          ${row("Всем", a ? `все видят тебя как «${me.public_nick ?? "Капибара №…"}»` : "другие группы увидят ник или «Капибара №…» · нужно отдельное согласие", a, "rating-offer-all")}
        </div>
        <div class="bd mut" style="--sz:12.5px;margin-top:var(--xs)">Имя и фамилию не показываем. Тумблер «Всем» сначала покажет текст согласия.</div>
        <button class="btn ${any ? "primary" : "outline ro-keep"}" id="rating-offer-done" data-act="ro-done" style="margin-top:var(--l);min-height:50px">${any ? "Готово" : "Оставить скрытым"}</button>
        ${any ? "" : `<button class="btn text ro-stop" id="rating-offer-sheet-stop" data-act="ro-sstop">Больше не предлагать</button>`}`;
    };
    const reload = async () => { try { const d = await Api.get("/rating"); if (d && d.me) me = d.me; } catch (e) {} };
    const after = async (ok) => {
      if (ok) {
        await reload();
        if (roHidden(me) === false && !accepted) { accepted = true; roAct("accepted", source); }
      }
      busy = false; draw();
    };
    on(body, {
      "rating-offer-group": async () => {
        if (busy) return; busy = true; tick();
        let ok = true;
        try { await Api.put("/rating/me", { show: me.show !== true }); } catch (e) { toast(errorText(e), "error"); ok = false; }
        after(ok);
      },
      "rating-offer-all": async () => {
        if (busy) return; busy = true; tick();
        let ok = false;
        try {
          if (me.show_all === true) { await Api.put("/rating/me", { show_all: false }); ok = true; }
          else {
            const doc = await Api.get("/legal/rating_all");
            const version = await acShowAllSheet(doc, me.public_nick ?? null);
            if (version != null) { await Api.put("/rating/me", { show_all: true, consent: version }); ok = true; }
          }
        } catch (e) { toast(errorText(e), "error"); }
        after(ok);
      },
      "ro-done": () => { tick(); close(me.show === true || me.show_all === true); },
      "ro-sstop": () => { tick(); roAct("stop"); close(false); },
    });
    draw();
  });
}

let roAsked = false;
/** После входа и тура: лист, если сервер говорит «пора» (только в «Новом»). */
window.maybeOfferRating = async function maybeOfferRating() {
  if (roAsked || !Theme.fresh) return;
  roAsked = true;
  let st, d;
  try { st = await Api.get("/rating/offer"); } catch (e) { return; }
  if (!st || st.sheet !== true) return;
  try { d = await Api.get("/rating"); } catch (e) { return; }
  if (!d || !roHidden(d.me)) return;
  await roAct("shown");
  await roSheet(d.me, "sheet");
};
