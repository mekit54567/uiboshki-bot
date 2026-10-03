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
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from webapp import deps
from webapp.routes import account, channel, chat, deadlines, files, plan, schedule, sdo

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
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith(("/api/", "/dl/", "/sdl/")):
        resp.headers["Cache-Control"] = "no-store"
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
for _module in (schedule, account, deadlines, files, chat, sdo, plan, channel):
    app.include_router(_module.router)


# ── Статика фронтенда (должна идти последней — ловит всё остальное) ─────────

_ASSET_RE = re.compile(r'(src|href)="((?:js/[\w-]+\.js)|app\.css)"')


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def index_page():
    """index.html со ссылками на стили и скрипты с меткой версии (?v=хэш
    содержимого): WebApp Telegram держит старые файлы в кэше, и после
    выкатки у части людей был бы новый HTML со старым JS."""
    import hashlib
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def versioned(m):
        digest = hashlib.sha1((STATIC_DIR / m.group(2)).read_bytes()).hexdigest()[:10]
        return f'{m.group(1)}="{m.group(2)}?v={digest}"'

    # имя группы и бота — из переменных (config.py): одна и та же вёрстка
    # годится для копии бота у другой группы
    import json
    from html import escape
    import config
    # канал бота и «написать нам» — для плиток меню «Ещё» (дизайн-ревью, п. 18)
    cfg = json.dumps({"group": config.GROUP_NAME, "bot": config.BOT_USERNAME,
                      "channel": config.CHANNEL_URL, "contact": config.CONTACT_URL},
                     ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("УИБО-03-24", escape(config.GROUP_NAME)).replace(
        '<script src="js/core.js"', f'<script>window.APP_CONFIG = {cfg};</script>\n<script src="js/core.js"', 1)
    return Response(_ASSET_RE.sub(versioned, html), media_type="text/html",
                    headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
