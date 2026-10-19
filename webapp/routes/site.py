"""Сайт-презентация бота: /about.

Страница — webapp/static/site/index.html (свои стили и скрипт, без
Telegram). На ней два живых места:
  • настоящее приложение в рамке телефона — /about/demo: тот же index.html,
    что в Telegram, но вместо SDK Telegram подключён site/demo.js — заглушка
    Telegram, подменённое время и ответы API из записанных тестовых данных
    (site/demo.json, ничьих настоящих данных там нет);
  • поиск расписания любой группы, преподавателя или аудитории МИРЭА —
    по-настоящему, без входа: /about/api/search и /about/api/target (те же
    обработчики, что в приложении; ограничение частоты — по IP).
"""

import hashlib
import ipaddress
import zlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter()

def _site_dir():
    from webapp.server import STATIC_DIR
    return STATIC_DIR / "site"


def _allow(action: str, request: Request):
    import ratelimit
    # сначала свой лимит по IP: отбитые запросы одного адреса не тратят общий потолок
    if not (ratelimit.allow(action, _client_key(request)) and ratelimit.allow("site_all", 0)):
        raise HTTPException(status_code=429, detail="слишком часто — подожди минуту")


def _public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _client_key(request: Request) -> int:
    """Ключ для ratelimit: IP посетителя — самый правый публичный адрес
    X-Forwarded-For: его дописывает прокси хостинга (свои внутренние адреса
    пропускаем). Начало строки присылает сам посетитель и может подставить
    что угодно — проверено на боевом 05.10: 45 запросов с разными адресами
    прошли мимо лимита 40/мин. Отрицательный — не пересечётся с id."""
    hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    ip = next((h for h in reversed(hops) if _public(h)), "")      # внутренние адреса прокси — мимо
    ip = ip or (request.client.host if request.client else "?")
    return -(zlib.crc32(ip.encode()) + 1)


def og_meta(base: str) -> str:
    """Теги превью ссылки (description, og:*, twitter:*) со страницы сайта —
    их же отдаёт корень: www.uiboshki.ru в Telegram должен выглядеть как
    сайт, а JS-переход на /about ботам-превьюшникам не виден."""
    lines = (_site_dir() / "index.html").read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in lines if ln.startswith(('<meta name="description"', '<meta property="og:',
                                                 '<meta name="twitter:'))]
    return "\n".join(keep).replace("__BASE__", base)


@router.get("/about", include_in_schema=False)
@router.get("/about/", include_in_schema=False)
async def about_page(request: Request):
    """Страница сайта. Превью ссылки (og:image) Telegram берёт только по
    абсолютному адресу — подставляем свой домен (WEBAPP_URL, иначе адрес
    запроса)."""
    from webapp import deps
    from webapp.server import _digest
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    import config
    html = ((_site_dir() / "index.html").read_text(encoding="utf-8")
            .replace("__BASE__", base).replace("__BOT__", config.BOT_USERNAME))
    # стили и скрипт сайта — по ссылке с хэшем: после обновления браузер не
    # склеит новую страницу со старым site.js (и кэширует их надолго)
    for rel in ("site/site.css", "site/site.js"):
        html = html.replace(f'"/{rel}"', f'"/{rel}?v={_digest(rel)}"')
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/about/demo", include_in_schema=False)
async def about_demo(request: Request):
    """Демо на сайте — само приложение (веб-сборка Flutter, как на iPhone и в
    PWA; Никита 19.10) на демо-данных: первым скриптом — site/demo-app.js
    (время, вход «demo» в памяти, ответы /api/v1/…). Сборки нет (тесты,
    разработка) — прежний Mini App."""
    from webapp.server import FLUTTER_DIR
    index = FLUTTER_DIR / "index.html"
    if not index.is_file():
        return await about_demo_tg(request)
    demo = _site_dir() / "demo-app.js"
    v = hashlib.sha1(demo.read_bytes() + (_site_dir() / "demo.json").read_bytes()).hexdigest()[:10]
    html = index.read_text(encoding="utf-8")
    html = html.replace("<head>", f'<head>\n  <script src="/site/demo-app.js?v={v}"></script>', 1)
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/about/demo/tg", include_in_schema=False)
async def about_demo_tg(request: Request):
    """Прежний Mini App как в Telegram, но на демо-данных: base href — чтобы
    относительные js/… и app.css грузились от корня, а SDK Telegram
    заменён на site/demo.js (он же подменяет fetch для /api/…)."""
    from webapp.server import index_page
    page = await index_page(request)
    html = page.body.decode("utf-8")
    demo = _site_dir() / "demo.js"
    v = hashlib.sha1(demo.read_bytes() + (_site_dir() / "demo.json").read_bytes()).hexdigest()[:10]
    html = html.replace("<head>", '<head>\n<base href="/">', 1)
    html = html.replace('<script src="https://telegram.org/js/telegram-web-app.js"></script>',
                        f'<script src="site/demo.js?v={v}"></script>', 1)
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/about/api/search", include_in_schema=False)
async def about_search(request: Request, q: str = "", type: int = 0):
    from webapp.routes.schedule import api_search
    _allow("site_search", request)
    return await api_search(q=q[:60], type=type, user={"id": 0})


@router.get("/about/api/target/{target_type}/{target_id}", include_in_schema=False)
async def about_target(request: Request, target_type: int, target_id: int):
    import schedule_index
    from webapp.routes.schedule import api_target
    _allow("site_target", request)
    # только то, что есть в справочнике (его и показывает поиск): случайный id
    # — это поход за карточкой на официальный сайт МИРЭА (10 с впустую) и на зеркало
    # (пока справочник не собран — поиск идёт запасным официальным, тогда пускаем)
    if target_type not in (1, 2, 3) or (await schedule_index.is_ready()
                                        and not await schedule_index.get_title(target_type, target_id)):
        raise HTTPException(status_code=404, detail="нет такого расписания")
    data = await api_target(target_type, target_id, user={"id": 0})
    data.pop("pinned", None)
    data["weeks"] = data["weeks"][:2]          # сайту хватит этой и следующей недели
    return data


# Расписание без входа в своём приложении (правило Apple 5.1.1(v), 5.99.0):
# то же, что поиск на сайте, — справочник МИРЭА публичный, ничего личного.
@router.get("/api/guest/search")
async def guest_search(request: Request, q: str = "", type: int = 0):
    return await about_search(request, q=q, type=type)


@router.get("/api/guest/target/{target_type}/{target_id}")
async def guest_target(request: Request, target_type: int, target_id: int):
    return await about_target(request, target_type, target_id)
