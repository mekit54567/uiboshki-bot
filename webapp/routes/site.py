"""Сайт-презентация бота: /about (и «Было и стало» — /history).

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
import re
import zlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from webapp.pages import FLUTTER_DIR, STATIC_DIR, digest, index_page, og_meta  # noqa: F401 — og_meta брали отсюда

router = APIRouter()

def _site_dir():
    return STATIC_DIR / "site"


def _allow(action: str, request: Request):
    from kapibara.core import ratelimit
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


_PROMO_FILE = re.compile(r"[a-z0-9-]+\.(mp4|jpg)")
_PROMO_TYPES = {"mp4": "video/mp4", "jpg": "image/jpeg"}


@router.get("/site/promo/{name}", include_in_schema=False)
def promo_file(name: str, request: Request):
    """Промо-ролик сайта (site/promo/). Отдаётся тут, а не общей статикой: Safari
    и iPhone играют видео только с ответами на Range (206), а StaticFiles нашей
    версии Starlette Range не понимает. Обычная функция — FastAPI зовёт её в
    своём пуле потоков, чтение файла не держит цикл событий."""
    if not _PROMO_FILE.fullmatch(name):
        raise HTTPException(status_code=404)
    path = _site_dir() / "promo" / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    size, kind = path.stat().st_size, _PROMO_TYPES[name.rsplit(".", 1)[1]]
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", request.headers.get("range", "").strip())
    if not m or not (m[1] or m[2]):
        return FileResponse(path, media_type=kind, headers=headers)
    if m[1]:
        start, end = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
    else:                                              # bytes=-N — последние N байт
        start, end = max(0, size - int(m[2])), size - 1
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with path.open("rb") as f:
        f.seek(start)
        data = f.read(end - start + 1)
    return Response(data, status_code=206, media_type=kind,
                    headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}"})


@router.get("/about", include_in_schema=False)
@router.get("/about/", include_in_schema=False)
async def about_page(request: Request):
    """Страница сайта. Превью ссылки (og:image) Telegram берёт только по
    абсолютному адресу — подставляем свой домен (WEBAPP_URL, иначе адрес
    запроса)."""
    from webapp import deps
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    from kapibara.core import config
    from kapibara.features.privacy import privacy
    from html import escape
    html = ((_site_dir() / "index.html").read_text(encoding="utf-8")
            .replace("__BASE__", base).replace("__BOT__", config.BOT_USERNAME)
            .replace("__CONTRACTOR__", escape(privacy.contractor()))
            .replace("__OGV__", digest("site/og.jpg")))
    # стили и скрипт сайта — по ссылке с хэшем: после обновления браузер не
    # склеит новую страницу со старым site.js (и кэширует их надолго)
    for rel in ("site/site.css", "site/site.js"):
        html = html.replace(f'"/{rel}"', f'"/{rel}?v={digest(rel)}"')
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/history", include_in_schema=False)
async def history_page(request: Request):
    """«Было и стало» (Никита 29.10): бот из апреля 2026 — в чате Telegram,
    тексты восстановлены из кода первых коммитов (site/history.js), рядом —
    экраны приложения сейчас (демо-данные). Ниже — лента по датам и цифры."""
    from webapp import deps
    from kapibara.core import config
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    html = ((_site_dir() / "history.html").read_text(encoding="utf-8")
            .replace("__BASE__", base).replace("__BOT__", config.BOT_USERNAME)
            .replace("__OGV__", digest("site/og.jpg")))
    for rel in ("site/history.css", "site/history.js"):
        html = html.replace(f'"/{rel}"', f'"/{rel}?v={digest(rel)}"')
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/about/demo", include_in_schema=False)
async def about_demo(request: Request):
    """Демо на сайте — само приложение (веб-сборка Flutter, как на iPhone и в
    PWA; Никита 19.10) на демо-данных: первым скриптом — site/demo-app.js
    (время, вход «demo» в памяти, ответы /api/v1/…). Сборки нет (тесты,
    разработка) — прежний Mini App."""
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
    from kapibara.features.schedule import index as schedule_index
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
