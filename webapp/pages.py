"""Страницы приложения: index Mini App с метками версий и общие куски.

Пути статики, хэш файла (?v=…), ссылка на пост-гайд по СДО и теги превью
ссылки. Жили в webapp/server и routes/site — каждый брал у другого, и
server с роутами сцеплялись в клубок импортов (03.11). Отсюда берут все:
server (маршрут «/»), routes/site (/about, демо), routes/meta (ссылки).
"""
import sqlite3
import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

from webapp import deps

STATIC_DIR = Path(__file__).parent / "static"
# PWA (/app) — веб-сборка Flutter из app/ (собирает app-web.yml после мержа)
FLUTTER_DIR = Path(__file__).parent / "flutter"

_ASSET_RE = re.compile(r'(src|href)="((?:js/[\w-]+\.js)|app\.css)"')


GUIDE_SLUG = "13-sdo-guide-pinned"      # пост-гайд «как подключить СДО» (channel/posts)


async def guide_link() -> str:
    """Ссылка на выпущенный пост-гайд по СДО в канале — для экрана «Подключить
    СДО». Номер сообщения — из channel:published (после /channel redo он
    другой), канал — из CHANNEL_URL (t.me/<имя> или @имя). Нет — пусто."""
    from kapibara.core import config
    try:
        from kapibara.features.content.channel_posts import published
        ids = ((await published()).get(GUIDE_SLUG) or {}).get("ids") or []
    except (sqlite3.Error, ValueError):
        return ""
    m = re.search(r"(?:t\.me/|^@)(\w+)", config.CHANNEL_URL or "")
    return f"https://t.me/{m.group(1)}/{ids[0]}" if ids and m else ""


_DIGESTS: dict[str, tuple[float, str]] = {}


def digest(rel: str) -> str:
    """Хэш содержимого файла статики — пересчитывается, только если файл
    поменялся (раньше — дюжина sha1 на каждое открытие приложения)."""
    import hashlib
    f = STATIC_DIR / rel
    mtime = f.stat().st_mtime
    hit = _DIGESTS.get(rel)
    if not hit or hit[0] != mtime:
        hit = _DIGESTS[rel] = (mtime, hashlib.sha1(f.read_bytes()).hexdigest()[:10])
    return hit[1]


async def index_page(request: Request):
    """index.html со ссылками на стили и скрипты с меткой версии (?v=хэш
    содержимого): WebApp Telegram держит старые файлы в кэше, и после
    выкатки у части людей был бы новый HTML со старым JS."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def versioned(m):
        return f'{m.group(1)}="{m.group(2)}?v={digest(m.group(2))}"'

    # имя группы и бота — из переменных (config.py): одна и та же вёрстка
    # годится для копии бота у другой группы
    import json
    from html import escape
    from kapibara.core import config
    # канал бота и «написать нам» — для плиток меню «Ещё» (дизайн-ревью, п. 18)
    cfg = json.dumps({"group": config.GROUP_NAME, "bot": config.BOT_USERNAME,
                      "channel": config.CHANNEL_URL, "contact": config.CONTACT_URL,
                      "guide": await guide_link()},
                     ensure_ascii=False).replace("</", "<\\/")
    # превью ссылки на корень — как у сайта (гость по www.uiboshki.ru уйдёт на /about);
    # вставляем до подстановки имени группы — в описании оно тоже есть
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    # корень для поисковиков — та же страница, что /about (Яндекс показывал
    # его заголовком «УИБО-03-24», Никита 09.11)
    canonical = f'<link rel="canonical" href="{base}/about">'
    html = html.replace("</head>", og_meta(base) + "\n" + canonical + "\n</head>", 1)
    html = html.replace("УИБО-03-24", escape(config.GROUP_NAME)).replace(
        '<script src="js/core.js"', f'<script>window.APP_CONFIG = {cfg};</script>\n<script src="js/core.js"', 1)
    return Response(_ASSET_RE.sub(versioned, html), media_type="text/html",
                    headers={"Cache-Control": "no-cache"})


def og_meta(base: str, path: str = "/about", description: bool = True) -> str:
    """Теги превью ссылки (description, og:*, twitter:*) со страницы сайта —
    их же отдаёт корень: www.uiboshki.ru в Telegram должен выглядеть как
    сайт, а JS-переход на /about ботам-превьюшникам не виден. И /app: ссылка
    uiboshki.ru/app из /help без своих тегов держала в Telegram превью
    «УИБО-бот» (Никита 20.10)."""
    lines = (STATIC_DIR / "site" / "index.html").read_text(encoding="utf-8").splitlines()
    heads = ('<meta property="og:', '<meta name="twitter:') + (('<meta name="description"',) if description else ())
    keep = [ln for ln in lines if ln.startswith(heads)]
    if path != "/about":
        keep = [ln.replace("__BASE__/about", "__BASE__" + path) for ln in keep]
    # метка версии у картинки: Telegram помнит превью по адресу — новая og.jpg
    # без неё не показалась бы (19.10, @WebpageBot отдал старую)
    return "\n".join(keep).replace("__BASE__", base).replace("__OGV__", digest("site/og.jpg"))
