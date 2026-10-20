"""Страница роадмапа (Никита 20.10, макет — вариант «Г», доработан в ChatGPT):
/roadmap?k=<личный ключ> — тем, кто хоть раз поддержал проект, и Никите.

Сверху — итоги прошлого номера («Сделано N из M», кольцо), фильтры, лента
пунктов с отметками и ссылками на посты в канале разработки (как сделано или
почему не вышло), ниже — «Дальше». Светлая и тёмная тема — по системе. Данные —
roadmap.json (roadmap.py); бот, Mini App, PWA и приложение ведут сюда по личной
ссылке (roadmap.page_link). Стиль — /site/roadmap.css, фильтры — /site/roadmap.js."""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря")
KIND = {"done": ("Вышло", "Как сделано"), "failed": ("Не вышло", "Почему не вышло"), "now": ("В работе", "Ход работы")}
ICONS = {"done": '<path d="M7 12.5l3.2 3.2L17 9"/>', "failed": '<path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>',
         "now": '<circle cx="12" cy="12" r="4.2"/><path d="M12 7.8v4.2h4.2" class="fill"/>'}

_SHELL = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex">
<title>{title}</title>
<link rel="stylesheet" href="/site/roadmap.css?v=1">
</head>
<body><main>{body}</main><script src="/site/roadmap.js?v=1" defer></script></body>
</html>"""


def _page(body: str, title: str = "Роадмап Капибары", status: int = 200) -> HTMLResponse:
    return HTMLResponse(_SHELL.format(title=escape(title), body=body), status_code=status,
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def _day(iso: str) -> str:
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return f"{d} {MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return ""


def _head(title: str, sub: str) -> str:
    return (f'<header class="hd"><span class="capy" aria-hidden="true"></span>'
            f'<div><h1>{escape(title)}</h1><p>{escape(sub)}</p></div></header>')


def _ring(done: int, total: int) -> str:
    pct = round(done * 100 / total) if total else 0
    return (f'<section class="score"><div><h2>Сделано {done} из {total}</h2><p class="from">Из прошлого роадмапа</p>'
            f'<p>По каждому пункту — пост в канале разработки, как сделано или почему не вышло.</p></div>'
            f'<svg class="ring" viewBox="0 0 36 36" aria-label="{pct}%"><circle cx="18" cy="18" r="15.9" class="bg"/>'
            f'<circle cx="18" cy="18" r="15.9" class="fg" pathLength="100" stroke-dasharray="{pct} 100"/>'
            f'<text x="18" y="21.2" text-anchor="middle">{pct}%</text></svg></section>')


def _card(i: dict) -> str:
    st = i["status"]
    badge, more = KIND[st]
    bar = ""
    if st == "now" and isinstance(i.get("progress"), int):
        p = max(0, min(100, i["progress"]))
        bar = f'<div class="bar"><i style="width:{p}%"></i></div><span class="pc">{p}%</span>'
    link = f'<a class="more" href="{escape(i["link"])}" target="_blank" rel="noopener">{more} →</a>' if i.get("link") else ""
    return (f'<li class="it {st}" data-st="{st}"><span class="dot"><svg viewBox="0 0 24 24">{ICONS[st]}</svg></span>'
            f'<div class="card"><span class="badge">{badge}</span><h3>{escape(i["title"])}</h3>'
            f'<p>{escape(i["about"])}</p><div class="prog">{bar}</div>{link}</div></li>')


def render(data: dict) -> str:
    import roadmap
    done, total = roadmap.score(data)
    res = roadmap.results(data)
    line = res + [i for i in data["items"] if i["status"] == "now" and i not in res]
    later = [i for i in data["items"] if i["status"] in ("next", "idea")]
    have = {i["status"] for i in line} | ({"next"} if later else set())
    chips = [("all", "Все"), ("done", "Вышло"), ("failed", "Не вышло"), ("now", "В работе"), ("next", "Дальше")]
    chips_html = "".join(f'<button data-f="{k}"{" class=on" if k == "all" else ""}>{t}</button>'
                         for k, t in chips if k == "all" or k in have)
    body = _head(f"Роадмап №{data['edition']}", "Для тех, кто поддержал · " + _day(data["updated"]))
    if total:
        body += _ring(done, total)
    body += f'<nav class="chips">{chips_html}</nav>'
    if line:
        body += '<ol class="line">' + "".join(_card(i) for i in line) + "</ol>"
    if later:
        body += '<section class="later" data-st="next"><h2>Дальше</h2><ol>' + "".join(
            f'<li><span class="n">{n}</span><div><b>{escape(i["title"])}</b>'
            f'{"<em>попробую</em>" if i["status"] == "idea" else ""}<p>{escape(i["about"])}</p></div></li>'
            for n, i in enumerate(later, 1)) + "</ol></section>"
    body += '<footer><p class="thanks">Спасибо за поддержку.</p><p>— Никита</p></footer>'
    return body


@router.get("/roadmap", response_class=HTMLResponse, include_in_schema=False)
async def roadmap_page(k: str = ""):
    import billing
    import config
    import roadmap
    uid = billing.read_key(k)
    if not uid:
        return _page(_head("Роадмап", "Что я делаю сейчас и что дальше")
                     + f'<p class="note">Роадмап открывается по личной ссылке — она живёт сутки. Её дают бот '
                       f'(команда /roadmap) и приложение: «Ещё → Роадмап».</p><p class="note">'
                       f'<a class="btn" href="https://t.me/{escape(config.BOT_USERNAME)}?start=roadmap">Открыть бота</a></p>',
                     status=403)
    if not await roadmap.can_see(uid):
        url = billing.donate_link(uid) if billing.provider() else ""
        btn = (f'<a class="btn" href="{escape(url)}">Поддержать проект</a>' if url
               else '<span class="note">Поддержать можно будет совсем скоро — оплата ещё подключается.</span>')
        return _page(_head("Роадмап", "Что я делаю сейчас и что дальше")
                     + f'<p class="note">Роадмап открывается тем, кто поддержал проект любой суммой от '
                       f'{billing.DONATE_MIN}&nbsp;₽. Это спасибо, а не покупка.</p><p class="note">{btn}</p>')
    return _page(render(await roadmap.with_links(roadmap.load())))
