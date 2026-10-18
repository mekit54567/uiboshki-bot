"""
HTTP-бэкенд для Telegram WebApp (Mini App) бота УИБО-03-24.

Поднимается в том же процессе, что и бот (bot.py: run_webapp, порт — $PORT),
а локально можно и отдельно: `uvicorn webapp.server:app --port 8000`. Общая с ботом
SQLite-база (config.DATABASE_PATH) и все существующие модули (database.py,
schedule_parser.py, ai_solver.py) переиспользуются как есть — WebApp не
дублирует логику, а просто даёт ей HTTP-фасад.

Каждый запрос обязан нести initData (см. webapp/auth.py) в заголовке
X-Telegram-Init-Data — без неё 401. Это не "логин с паролем", а способ
доказать, что запрос действительно пришёл из тг-клиента с этим ботом:
подпись считается на стороне Telegram при открытии WebApp и не может быть
подделана без знания токена бота.

CORS — только свой адрес (WEBAPP_URL), без него (локальный запуск) — любые.
Главная защита всё равно не происхождение запроса, а initData: сам по себе
домен фронтенда ничего не даёт без валидной подписи.

Здесь — только каркас: приложение, CORS, заголовки безопасности, /health,
index и статика. Обработчики разнесены по темам в webapp/routes/*, вход по
initData и общее для них — webapp/deps.py.
"""

import logging
import re
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import health as bot_health
from webapp import deps
from webapp.routes import (account, achievements, aitest, auth, billing, channel, chat, deadlines, files, legal, meta,
                           push, rating, reactions, reports, schedule, sdo, site)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
# httpx на INFO пишет полный адрес каждого запроса — с sesskey СДО в query.
# Секрету в логах не место (и шума меньше).
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="uiboshki-bot webapp")

def _allowed_origins() -> list[str]:
    """Приложение открывается со своего же адреса — чужим сайтам API не нужен.
    Без WEBAPP_URL (локальный запуск) — как раньше, любые."""
    from urllib.parse import urlsplit
    if not deps.WEBAPP_URL:
        return ["*"]
    u = urlsplit(deps.WEBAPP_URL)
    return [f"{u.scheme}://{u.netloc}"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Сколько можно прислать в одном запросе: сдача работ — до 3 файлов по 20 МБ
# (в base64 ~80 МБ), чат с вложением — 10 МБ (~14 МБ), остальное — мелочь.
BODY_LIMITS = (("/api/sdo/submit", 90 * 1024 * 1024), ("/api/chat", 16 * 1024 * 1024))
BODY_LIMIT_DEFAULT = 1024 * 1024


class BodyLimit:
    """Предел тела запроса по факту прочитанных байт. Заголовка Content-Length
    при Transfer-Encoding: chunked нет — проверка по нему пропускала 50 МБ
    без initData (FastAPI читает тело до проверки входа). Здесь чтение
    обрывается на пределе: 413, лишнее не читается."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.exceptions import HTTPException as StarletteHTTPException
        limit = next((n for p, n in BODY_LIMITS if scope["path"].startswith(p)), BODY_LIMIT_DEFAULT)
        got = 0

        async def limited():
            nonlocal got
            msg = await receive()
            if msg["type"] == "http.request":
                got += len(msg.get("body") or b"")
                if got > limit:
                    raise StarletteHTTPException(413, "слишком большой запрос")
            return msg

        await self.app(scope, limited, send)


app.add_middleware(BodyLimit)


class ApiV1:
    """«/api/v1/…» — то же, что «/api/…» (этап 2: API как контракт). Своё
    приложение и PWA ходят по /api/v1: когда понадобится ломающее изменение,
    появится /api/v2, а старые версии приложения в магазинах продолжат
    работать. Mini App — по-прежнему /api/…"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/v1/"):
            scope = dict(scope, path="/api/" + scope["path"][8:],
                         raw_path=b"/api/" + scope.get("raw_path", b"")[8:])
        await self.app(scope, receive, send)


from review_demo import ReviewDemo  # noqa: E402 — демо-вход проверяющих магазинов: ответы из записи стенда

app.add_middleware(ReviewDemo)      # внутри ApiV1: пути уже без /v1
app.add_middleware(ApiV1)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Заголовки безопасности и ограничение размера запроса.
    - nosniff: браузер не «угадывает» тип файла (картинка не станет скриптом);
    - no-referrer: подписанные ссылки /dl и /sdl не утекают в Referer;
    - no-store для API и ссылок на файлы: ответы с баллами и файлами не
      оседают в кэше устройства/прокси."""
    from fastapi.responses import JSONResponse
    length = request.headers.get("content-length")
    if length and length.isdigit():
        limit = next((n for p, n in BODY_LIMITS if request.url.path.startswith(p)), BODY_LIMIT_DEFAULT)
        if int(length) > limit:
            return JSONResponse({"detail": "слишком большой запрос"}, status_code=413)
    started = time.monotonic()
    resp = await call_next(request)
    if request.url.path.startswith("/api/"):
        # путь шаблоном (/api/sdo/task/{cmid}), чтобы долгие сводились по разделам
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path).replace("/api/v1/", "/api/", 1)
        bot_health.note_request(path, time.monotonic() - started)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith(("/api/", "/dl/", "/sdl/")):
        resp.headers["Cache-Control"] = "no-store"
    elif "v" in request.query_params and request.url.path.endswith((".js", ".css")) and resp.status_code == 200:
        # js/… и app.css со ссылкой ?v=<хэш содержимого> (index_page): новое
        # содержимое — новая ссылка, так что старую можно не перепроверять.
        # Иначе каждое открытие приложения — дюжина запросов «не изменилось?»
        # до сервера в США.
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

STATIC_DIR = Path(__file__).parent / "static"


# ── Здоровье сервиса ─────────────────────────────────────────────────────────
# Без initData и без БД — чтобы внешний аптайм-чекер (UptimeRobot/Better
# Uptime и т.п., бесплатные тарифы) мог пинговать раз в N минут и растить
# алерт (email/telegram-бот того сервиса) при падении процесса, не будучи
# сам пользователем бота. Год без такого пинга — падение узнаёшь только от
# жалоб студентов; с ним — от сервиса, обычно за 1-5 минут.
@app.get("/health")
async def health():
    return {"ok": True}


# ── Обработчики по темам (webapp/routes/*) ──────────────────────────────────
# Пути у них не пересекаются, так что порядок не важен; важно только, что
# статика ниже — последней.
for _module in (schedule, account, achievements, deadlines, files, chat, sdo, channel, site, legal, aitest, auth, meta, push,
                billing, reports, reactions, rating):
    app.include_router(_module.router)


# ── Статика фронтенда (должна идти последней — ловит всё остальное) ─────────

_ASSET_RE = re.compile(r'(src|href)="((?:js/[\w-]+\.js)|app\.css)"')


GUIDE_SLUG = "13-sdo-guide-pinned"      # пост-гайд «как подключить СДО» (channel/posts)


async def _guide_link() -> str:
    """Ссылка на выпущенный пост-гайд по СДО в канале — для экрана «Подключить
    СДО». Номер сообщения — из channel:published (после /channel redo он
    другой), канал — из CHANNEL_URL (t.me/<имя> или @имя). Нет — пусто."""
    import config
    try:
        from channel_posts import published
        ids = ((await published()).get(GUIDE_SLUG) or {}).get("ids") or []
    except Exception:
        return ""
    m = re.search(r"(?:t\.me/|^@)(\w+)", config.CHANNEL_URL or "")
    return f"https://t.me/{m.group(1)}/{ids[0]}" if ids and m else ""


_DIGESTS: dict[str, tuple[float, str]] = {}


def _digest(rel: str) -> str:
    """Хэш содержимого файла статики — пересчитывается, только если файл
    поменялся (раньше — дюжина sha1 на каждое открытие приложения)."""
    import hashlib
    f = STATIC_DIR / rel
    mtime = f.stat().st_mtime
    hit = _DIGESTS.get(rel)
    if not hit or hit[0] != mtime:
        hit = _DIGESTS[rel] = (mtime, hashlib.sha1(f.read_bytes()).hexdigest()[:10])
    return hit[1]


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def index_page(request: Request):
    """index.html со ссылками на стили и скрипты с меткой версии (?v=хэш
    содержимого): WebApp Telegram держит старые файлы в кэше, и после
    выкатки у части людей был бы новый HTML со старым JS."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def versioned(m):
        return f'{m.group(1)}="{m.group(2)}?v={_digest(m.group(2))}"'

    # имя группы и бота — из переменных (config.py): одна и та же вёрстка
    # годится для копии бота у другой группы
    import json
    from html import escape
    import config
    # канал бота и «написать нам» — для плиток меню «Ещё» (дизайн-ревью, п. 18)
    cfg = json.dumps({"group": config.GROUP_NAME, "bot": config.BOT_USERNAME,
                      "channel": config.CHANNEL_URL, "contact": config.CONTACT_URL,
                      "guide": await _guide_link()},
                     ensure_ascii=False).replace("</", "<\\/")
    # превью ссылки на корень — как у сайта (гость по www.uiboshki.ru уйдёт на /about);
    # вставляем до подстановки имени группы — в описании оно тоже есть
    from webapp.routes.site import og_meta
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    html = html.replace("</head>", og_meta(base) + "\n</head>", 1)
    html = html.replace("УИБО-03-24", escape(config.GROUP_NAME)).replace(
        '<script src="js/core.js"', f'<script>window.APP_CONFIG = {cfg};</script>\n<script src="js/core.js"', 1)
    return Response(_ASSET_RE.sub(versioned, html), media_type="text/html",
                    headers={"Cache-Control": "no-cache"})


# PWA (/app) — то же приложение, что на iPhone: веб-сборка Flutter из app/
# (Никита 14.10: «дизайн у приложений на iPhone и PWA одинаковый»). Собирает
# её GitHub Actions после мержа (app-web.yml) в webapp/flutter; сборки нет
# (тесты, разработка) — /app отдаёт прежний WebApp, как раньше.
FLUTTER_DIR = Path(__file__).parent / "flutter"


class _NoCacheStatic(StaticFiles):
    """У файлов Flutter нет метки версии в адресе — браузер каждый раз
    сверяет их с сервером (ETag), иначе после выпуска оставался бы старый код."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
async def pwa_page(request: Request):
    index = FLUTTER_DIR / "index.html"
    if not index.is_file():
        return await index_page(request)
    return Response(index.read_bytes(), media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    """Service worker PWA (этап 2): без кэша — обновление приложения доходит сразу."""
    return Response((STATIC_DIR / "sw.js").read_bytes(), media_type="text/javascript",
                    headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/manifest.webmanifest", include_in_schema=False)
async def web_manifest():
    return Response((STATIC_DIR / "manifest.webmanifest").read_bytes(), media_type="application/manifest+json",
                    headers={"Cache-Control": "no-cache"})


if FLUTTER_DIR.is_dir():
    app.mount("/app", _NoCacheStatic(directory=str(FLUTTER_DIR)), name="pwa")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
