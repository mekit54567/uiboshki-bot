"""«Капибара+»: статус и бонусы (/api/plus…), страница оплаты /plus и
уведомления касс (billing.py, referrals.py).

Оплата — только на странице /plus по личной ссылке ?k= (подписана, живёт
сутки): её открывают бот, Mini App, PWA и Android-приложение. iPhone-
приложению (X-App: ios) подписки не видно вовсе — правила App Store."""

import logging
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

from webapp import deps
from webapp.deps import CurrentUser

router = APIRouter()
logger = logging.getLogger(__name__)


# ── API приложения ───────────────────────────────────────────────────────────

@router.get("/api/plus")
async def api_plus(user: dict = CurrentUser, x_app: str = Header(default="")):
    """Подписка, цены, ссылка на оплату, приглашения и бонусы за ранги."""
    import billing
    import referrals
    if x_app == "ios":
        # App Store вне США (3.1.1, 3.1.3): ни цен, ни экрана подписки, ни «купить» —
        # в iOS-сборке «Капибары+» не видно (тред «Выход в App Store», 16.10)
        return {"hidden": True}
    st = await billing.status(user["id"])
    st["hidden"] = False
    st["pay_url"] = billing.pay_link(user["id"]) if st["provider"] else ""
    st["offer_url"] = f"{billing.site()}/offer"
    st["invite"] = await referrals.summary(user["id"])
    return st


@router.get("/api/invite")
async def api_invite(user: dict = CurrentUser, x_app: str = Header(default="")):
    """«Позвать друга»: готовый текст, картинка и личная ссылка — на всех
    платформах; про дни подписки — только не в iOS-сборке."""
    import referrals
    d = await referrals.summary(user["id"])
    out = {"link": d["link"], "share_text": d["share_text"], "share_image": d["share_image"],
           "tg_share": referrals.tg_share_url(d["link"])}
    if x_app != "ios":
        out.update({k: d[k] for k in ("came", "rewarded", "bonus_days", "friend_days", "ref_max", "ref_counted")})
    return out


class RankBody(BaseModel):
    rank: str


@router.post("/api/plus/rank")
async def api_plus_rank(body: RankBody, user: dict = CurrentUser):
    """Закрыл ранг ачивок на телефоне — забрать дни подписки (один раз)."""
    import referrals
    try:
        got = await referrals.claim_rank(user["id"], body.rank)
    except referrals.BonusError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **got}


class RefBody(BaseModel):
    code: str


@router.post("/api/plus/ref")
async def api_plus_ref(body: RefBody, user: dict = CurrentUser):
    """PWA и приложение: пришёл по /app?ref=<код> — запомнить, кто позвал."""
    import referrals
    return {"ok": await referrals.bind(user["id"], body.code)}


# ── Страница оплаты ──────────────────────────────────────────────────────────

_SHELL = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex">
<title>Капибара+</title>
<style>
@font-face{{font-family:SourceSerif;src:url('/site/fonts/serif-cyrillic.woff2') format('woff2');font-weight:200 900;font-display:swap;unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:Onest;src:url('/site/fonts/sans-cyrillic.woff2') format('woff2');font-weight:100 900;font-display:swap;unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:Onest;src:url('/site/fonts/sans-latin.woff2') format('woff2');font-weight:100 900;font-display:swap;unicode-range:U+0000-00FF,U+2000-206F,U+2116}}
:root{{--paper:#f8f6f0;--ink:#282720;--secondary:#66635b;--line:#dcd8ce;--accent:#5a5ee0;--card:#fffdf8;--link:#2f6fd6}}
@media(prefers-color-scheme:dark){{:root{{--paper:#24211a;--ink:#d3d2c8;--secondary:#a19d95;--line:#423d30;--accent:#8b8ef5;--card:#2c2920;--link:#7fb0ff}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 Onest,Arial,sans-serif;-webkit-font-smoothing:antialiased}}
main{{max-width:560px;margin:0 auto;padding:28px 16px 48px}}
h1{{font-family:SourceSerif,Georgia,serif;font-weight:400;letter-spacing:-.03em;font-size:36px;line-height:1.1;margin:0 0 6px}}
.lead{{color:var(--secondary);margin:0 0 22px}}
.state{{border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0 0 18px;background:var(--card)}}
ul.perks{{padding-left:20px;margin:0 0 22px}} ul.perks li{{margin:0 0 6px}}
form{{display:grid;gap:10px;margin:0 0 18px}}
button{{font:inherit;display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;text-align:left;
  padding:14px 16px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}}
button:hover{{border-color:var(--accent)}}
button b{{font-size:20px;white-space:nowrap}}
button s{{color:var(--secondary);font-size:14px;margin-right:6px}}
.tag{{display:inline-block;font-size:12px;background:var(--accent);color:#fff;border-radius:999px;padding:1px 8px;margin-left:6px}}
.small{{color:var(--secondary);font-size:13px}}
a{{color:var(--link)}}
</style>
</head>
<body>
<main>
<h1>Капибара+</h1>
{body}
</main>
</body>
</html>
"""

PERKS = ["ИИ сверх пробы для любой группы МИРЭА (твоей группе он и так бесплатный)",
         "иконки приложения и наряды капибары «только по подписке»",
         "значок «друг Капибары» в профиле",
         "дальше: ответы на экзаменационные билеты, «Пульс группы», «Архив потока»"]


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(_SHELL.format(body=body), status_code=status,
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def _no_key() -> HTMLResponse:
    import config
    return _page(f'<p class="lead">Оплата — по личной ссылке, она живёт сутки. Её дают бот (команда /plus) '
                 f'и приложение: «Ещё → Капибара+» в Telegram, на Android и на сайте uiboshki.ru/app. '
                 f'Подписка работает везде, и на iPhone.</p>'
                 f'<p><a href="https://t.me/{escape(config.BOT_USERNAME)}?start=plus">Открыть бота</a> · '
                 f'<a href="/app">Открыть приложение</a></p>', 403)


def _plans_form(key: str, st: dict) -> str:
    rows = []
    for p in st["prices"]:
        old = f"<s>{p['full']} ₽</s>" if p["price"] < p["full"] else ""
        tag = '<span class="tag">Основатель</span>' if p["founder"] else ""
        rows.append(f'<button name="plan" value="{p["plan"]}"><span>{escape(p["title"])} · {p["days"]} дней{tag}'
                    f'</span><span>{old}<b>{p["price"]} ₽</b></span></button>')
    return (f'<form method="post" action="/plus/pay"><input type="hidden" name="k" value="{escape(key)}">'
            + "".join(rows) + "</form>")


@router.get("/plus", response_class=HTMLResponse)
async def plus_page(k: str = ""):
    import billing
    uid = billing.read_key(k)
    if not uid:
        return _no_key()
    st = await billing.status(uid)
    if st["paid_until"]:
        state = f"Подписка действует до <b>{billing.fmt_day(st['until'])}</b>. Оплата добавит дни к этому сроку."
    elif st["gift"]:
        state = (f"У твоей группы «Капибара+» в подарок до <b>{billing.fmt_day(st['gift'])}</b>. Оплата "
                 f"нужна только тем, кто хочет продлить заранее: дни добавятся после подарка.")
    else:
        state = "Подписки сейчас нет."
    if st["founder"]:
        state += " Ты «Основатель»: цена первых пользователей остаётся за тобой навсегда."
    elif st["prices"][0]["founder"]:
        state += " Сейчас действует цена первых пользователей: кто оплатит по ней, так и платит всегда."
    perks = "".join(f"<li>{escape(x)}</li>" for x in PERKS)
    import referrals
    inv = {"ref_max": referrals.REF_MAX, "ref_counted": await referrals.counted(uid)}
    friend = (f'<p class="small">Позови друга — команда /invite в боте или «Позвать» в приложении. '
              f'{escape(referrals.invite_line(inv))}</p>')
    if not st["provider"]:
        pay = '<p class="state">Оплата скоро заработает. Бонусные дни за ранги и друзей уже начисляются.</p>'
    else:
        pay = (_plans_form(k, st) +
               '<p class="small">Списаний без твоего ведома нет: каждый срок оплачивается отдельно. '
               'Июль и август в срок не считаются — дни переносятся на сентябрь. Нажимая на тариф, ты '
               'принимаешь <a href="/offer">оферту</a>. Чек придёт от ФНС («Мой налог»).</p>')
    return _page(f'<p class="lead">Подписка на Капибару — помощника студентов МИРЭА.</p>'
                 f'<p class="state">{state}</p><ul class="perks">{perks}</ul>{pay}{friend}')


@router.post("/plus/pay")
async def plus_pay(request: Request):
    import billing
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    key = (form.get("k") or [""])[0]
    plan = (form.get("plan") or [""])[0]
    uid = billing.read_key(key)
    if not uid:
        return _no_key()
    try:
        url = await billing.create(uid, plan, f"{billing.site()}/plus/done?k={key}")
    except billing.PayError as e:
        return _page(f'<p class="state">{escape(str(e))}</p><p><a href="/plus?k={escape(key)}">Назад</a></p>', 400)
    return RedirectResponse(url, status_code=303)


@router.get("/plus/done", response_class=HTMLResponse)
async def plus_done(k: str = ""):
    """Сюда касса возвращает после оплаты. Подписку продлевает уведомление
    кассы; если оно опаздывает — спросим ЮKassa сами (/plus/state)."""
    key = escape(k)
    return _page(f'<p class="state" id="s">Проверяем оплату…</p>'
                 f'<p class="small">Можно закрыть страницу: когда оплата пройдёт, бот напишет.</p>'
                 f'<script>(function(){{var k="{key}",n=0;if(!k){{document.getElementById("s").textContent='
                 f'"Спасибо! Когда оплата пройдёт, бот напишет.";return}}function t(){{fetch("/plus/state?k="+'
                 f'encodeURIComponent(k)).then(function(r){{return r.json()}}).then(function(d){{if(d.active)'
                 f'{{document.getElementById("s").innerHTML="Готово: «Капибара+» до <b>"+d.until_text+"</b>. '
                 f'Вернись в приложение.";return}}if(++n<20)setTimeout(t,3000);else document.getElementById("s")'
                 f'.textContent="Касса ещё не ответила. Когда оплата пройдёт, бот напишет."}}).catch(function()'
                 f'{{if(++n<20)setTimeout(t,3000)}})}}t()}})()</script>')


@router.get("/plus/state")
async def plus_state(k: str = ""):
    import billing
    from database.billing import user_payments
    uid = billing.read_key(k)
    if not uid:
        raise HTTPException(403, "ссылка устарела")
    if billing.provider() == "yookassa":
        for p in await user_payments(uid, 3):
            if p["status"] == "pending" and not p["id"].startswith("local-"):
                if await billing.yookassa_check(p["id"]) == "succeeded":
                    await billing.paid(p["id"], deps.tg_bot() if deps.BOT_TOKEN else None)
    st = await billing.status(uid)
    return {"active": st["active"], "until": st["until"],
            "until_text": billing.fmt_day(st["until"]) if st["until"] else ""}


# ── Уведомления касс ─────────────────────────────────────────────────────────

@router.post("/api/billing/yookassa")
async def yookassa_hook(request: Request):
    """ЮKassa: payment.succeeded / payment.canceled. Телу не верим — статус
    спрашиваем у ЮKassa по id."""
    import billing
    from database.billing import get_payment, mark_payment
    try:
        data = await request.json()
        pid = str(data["object"]["id"])
    except Exception:
        raise HTTPException(400, "не то")
    if not await get_payment(pid):
        return {"ok": True}           # не наш платёж — не дёргаем кассу зря
    st = await billing.yookassa_check(pid)
    if st == "succeeded":
        await billing.paid(pid, deps.tg_bot() if deps.BOT_TOKEN else None)
    elif st == "canceled":
        await mark_payment(pid, "canceled")
    elif st is None:
        raise HTTPException(503, "ЮKassa не ответила — пришлёт ещё раз")
    return {"ok": True}


@router.api_route("/api/billing/robokassa", methods=["GET", "POST"])
async def robokassa_hook(request: Request):
    """Robokassa ResultURL: OutSum, InvId, SignatureValue (Пароль №2)."""
    import billing
    from database.billing import get_payment
    q = dict(request.query_params)
    if request.method == "POST":
        q.update({k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")).items()})
    out_sum, inv, sig = q.get("OutSum", ""), q.get("InvId", ""), q.get("SignatureValue", "")
    if not billing.robokassa_ok(out_sum, inv, sig):
        raise HTTPException(400, "bad sign")
    pay = await get_payment(inv)
    try:
        enough = pay and float(out_sum) + 0.001 >= pay["amount"]
    except ValueError:
        enough = False
    if not enough:
        logger.warning(f"Robokassa: платёж {inv} не наш или сумма {out_sum} не та")
        raise HTTPException(400, "bad payment")
    await billing.paid(inv, deps.tg_bot() if deps.BOT_TOKEN else None)
    return PlainTextResponse(f"OK{inv}")
