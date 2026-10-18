"""152-ФЗ: страницы /consent (согласие на обработку персональных данных) и
/privacy (политика), согласия через API и «удалить все мои данные».

Тексты — legal_texts.py: здесь они рисуются страницей в стиле сайта, а
/api/legal/<имя> отдаёт их JSON — лист в Mini App, PWA и своём приложении
рисует текст сам, в своём дизайне, не уводя с экрана (поле с кукой не
теряется). ?embed=1 — страница без шапки и подвала."""

from html import escape

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()

PAGES = {"consent": "Согласие на обработку персональных данных",
         "privacy": "Политика обработки персональных данных"}

_SHELL = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title} · Капибара</title>
<style>
@font-face{{font-family:SourceSerif;src:url('/site/fonts/serif-cyrillic.woff2') format('woff2');font-weight:200 900;font-display:swap;unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:Onest;src:url('/site/fonts/sans-cyrillic.woff2') format('woff2');font-weight:100 900;font-display:swap;unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:Onest;src:url('/site/fonts/sans-latin.woff2') format('woff2');font-weight:100 900;font-display:swap;unicode-range:U+0000-00FF,U+2000-206F,U+2116}}
:root{{--paper:#f8f6f0;--ink:#282720;--secondary:#66635b;--line:#dcd8ce;--accent:#b75438;--link:#2f6fd6}}
@media(prefers-color-scheme:dark){{:root{{--paper:#24211a;--ink:#d3d2c8;--secondary:#a19d95;--line:#423d30;--accent:#d17e67;--link:#7fb0ff}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 Onest,Arial,sans-serif;-webkit-font-smoothing:antialiased}}
main{{max-width:760px;margin:0 auto;padding:28px 20px 48px}}
header{{max-width:760px;margin:0 auto;padding:18px 20px 0;display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:14px}}
header a{{color:var(--ink);text-decoration:none;font-weight:600}}
h1{{font-family:SourceSerif,Georgia,serif;font-weight:400;letter-spacing:-.03em;font-size:34px;line-height:1.15;margin:0 0 8px}}
h2{{font-family:SourceSerif,Georgia,serif;font-weight:500;font-size:22px;line-height:1.3;margin:30px 0 8px}}
p,li{{margin:0 0 10px}}
ul{{padding-left:22px;margin:0 0 10px}}
a{{color:var(--link)}}
.meta{{color:var(--secondary);font-size:14px;margin-bottom:22px}}
.lead{{font-size:17px}}
footer{{max-width:760px;margin:0 auto;padding:0 20px 32px;color:var(--secondary);font-size:13px}}
.embed header,.embed footer{{display:none}}
.embed main{{padding-top:8px}}
</style>
</head>
<body class="{cls}">
<header><a href="/about">Капибара</a><span><a href="/consent">Согласие</a> · <a href="/privacy">Политика</a></span></header>
<main>
<h1>{title}</h1>
<p class="meta">Версия {version} от {date}</p>
{body}
</main>
<footer>Вопросы — <a href="{contact_url}">{contact}</a>. Удалить свои данные — «Ещё → Безопасность» в приложении или /deleteme в боте.</footer>
</body>
</html>
"""


def _html(d: dict) -> str:
    out = [f'<p class="lead">{escape(d["lead"])}</p>']
    for sec in d["sections"]:
        out.append(f"<h2>{escape(sec['title'])}</h2>")
        for b in sec["blocks"]:
            if "ul" in b:
                out.append("<ul>" + "".join(f"<li>{escape(i)}</li>" for i in b["ul"]) + "</ul>")
            else:
                out.append(f"<p>{escape(b['p'])}</p>")
    return "\n".join(out)


def render(name: str, embed: bool = False) -> str:
    import legal_texts
    import privacy
    d = legal_texts.doc(name)
    return _SHELL.format(title=escape(d["title"]), version=d["version"], date=d["date"], body=_html(d),
                         cls="embed" if embed else "", contact=escape(privacy.CONTACT),
                         contact_url=escape(privacy.CONTACT_URL))


@router.get("/consent", response_class=HTMLResponse)
async def consent_page(embed: int = 0):
    return HTMLResponse(render("consent", bool(embed)))


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(embed: int = 0):
    return HTMLResponse(render("privacy", bool(embed)))


@router.get("/api/legal/{name}")
async def api_legal(name: str):
    """Текст согласия или политики — JSON: лист в приложении рисует его сам,
    в своём дизайне (без входа: это публичный текст)."""
    import legal_texts
    if name not in legal_texts.DOCS:
        raise HTTPException(404, "нет такого документа")
    return legal_texts.doc(name)


def _via(init_data: str, x_app: str) -> str:
    if init_data:
        return "tg"
    return "app" if x_app in ("ios", "android") else "pwa"


@router.get("/api/consent")
async def api_consent(user: dict = CurrentUser):
    """Что человек уже принял (текущей версии) — для листа согласия."""
    import privacy
    return {"version": privacy.VERSION, "date": privacy.DATE,
            "pd": not await privacy.needs(user["id"], "pd"),
            "sdo": not await privacy.needs(user["id"], "sdo")}


class ConsentBody(BaseModel):
    kind: str = "pd"


@router.post("/api/consent")
async def api_give_consent(body: ConsentBody, user: dict = CurrentUser,
                           x_telegram_init_data: str = Header(default=""), x_app: str = Header(default="")):
    import privacy
    if body.kind not in privacy.KINDS:
        raise HTTPException(400, "нет такого согласия")
    try:
        await privacy.give(user["id"], body.kind, _via(x_telegram_init_data, x_app))
    except privacy.Erasing as e:
        raise HTTPException(409, str(e))
    return await api_consent(user)


@router.post("/api/consent/asked")
async def api_consent_asked(user: dict = CurrentUser):
    """Лист согласия показан тому, кто был до согласий, — больше не показывать
    (как и бот, один раз на версию текста — privacy.ask_once)."""
    import privacy
    await privacy.ask_once(user["id"])
    return {"ok": True}


class DeleteBody(BaseModel):
    confirm: bool = False
    phrase: str = ""


@router.post("/api/me/delete")
async def api_delete_me(body: DeleteBody, user: dict = CurrentUser):
    """«Удалить все мои данные» (152-ФЗ, ст. 21), Никита 18.10: фраза
    privacy.ERASE_PHRASE руками; сразу — входы и устройства (после ответа
    сессия недействительна), полностью — через ERASE_DAYS дней. Не давал
    согласия (отказ на листе согласия) — confirm и сразу насовсем."""
    import privacy
    import ratelimit
    uid = user["id"]
    due = await privacy.erasing(uid)
    if not due and await privacy.blocked(uid):
        if not body.confirm:
            raise HTTPException(400, "нужно подтверждение")
        await privacy.erase(uid)
        return {"ok": True, "now": True}
    if not due and not privacy.phrase_ok(body.phrase):
        raise HTTPException(400, f"Введи фразу: {privacy.ERASE_PHRASE}")
    if not ratelimit.allow("deadline", uid):
        raise HTTPException(429, "Подожди пару минут")
    from webapp import deps
    due = await privacy.request_erase(uid, deps.tg_bot() if deps.BOT_TOKEN else None)
    return {"ok": True, "due": due, "days": privacy.ERASE_DAYS, "text": privacy.erasing_text(due)}
