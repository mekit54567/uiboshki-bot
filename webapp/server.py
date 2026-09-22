"""
HTTP-бэкенд для Telegram WebApp (Mini App) бота УИБО-03-24.

Отдельный процесс от bot.py (тот — чистый long polling, без HTTP), поднимается
рядом: `uvicorn webapp.server:app --host 0.0.0.0 --port 8000`. Общая с ботом
SQLite-база (config.DATABASE_PATH) и все существующие модули (database.py,
schedule_parser.py, groq_solver.py) переиспользуются как есть — WebApp не
дублирует логику, а просто даёт ей HTTP-фасад.

Каждый запрос обязан нести initData (см. webapp/auth.py) в заголовке
X-Telegram-Init-Data — без неё 401. Это не "логин с паролем", а способ
доказать, что запрос действительно пришёл из тг-клиента с этим ботом:
подпись считается на стороне Telegram при открытии WebApp и не может быть
подделана без знания токена бота.

CORS открыт всем источникам (allow_origins=["*"]) — это нормально именно
потому, что данные защищены не происхождением запроса, а initData: сам по
себе домен фронтенда ничего не даёт без валидной подписи.
"""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BOT_TOKEN
from webapp.auth import InitDataError, validate_init_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="uiboshki-bot webapp")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


# ── Аутентификация ──────────────────────────────────────────────────────────

async def get_current_user(x_telegram_init_data: str = Header(default="")) -> dict:
    """FastAPI dependency: валидирует initData, апсертит пользователя в общую
    с ботом таблицу users (тем же способом, что и /start в самом боте — тогда
    и утренний дайджест, и всё остальное видят его одинаково), возвращает
    telegram user dict (id, first_name, username, ...)."""
    try:
        data = validate_init_data(x_telegram_init_data, BOT_TOKEN)
    except InitDataError as e:
        raise HTTPException(status_code=401, detail=str(e))
    user = data.get("user")
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="нет данных пользователя в initData")

    from database import upsert_user
    await upsert_user(user["id"], user.get("username", ""), user.get("first_name", ""))
    return user


CurrentUser = Depends(get_current_user)


@app.get("/api/me")
async def api_me(user: dict = CurrentUser):
    return {"id": user["id"], "first_name": user.get("first_name", ""), "username": user.get("username", "")}


# ── Расписание ───────────────────────────────────────────────────────────────

@app.get("/api/schedule/today")
async def api_schedule_today(user: dict = CurrentUser):
    from datetime import date
    from schedule_parser import get_today_schedule
    from handlers.schedule import _notes_block
    html = await get_today_schedule()
    html += await _notes_block(date.today().isoformat())
    return {"html": html}


@app.get("/api/schedule/tomorrow")
async def api_schedule_tomorrow(user: dict = CurrentUser):
    from schedule_parser import get_tomorrow_schedule
    return {"html": await get_tomorrow_schedule()}


@app.get("/api/schedule/week")
async def api_schedule_week(user: dict = CurrentUser):
    from schedule_parser import get_week_schedule
    return {"html": await get_week_schedule()}


@app.get("/api/schedule/next")
async def api_schedule_next(user: dict = CurrentUser):
    from schedule_parser import get_next_lesson
    return {"html": await get_next_lesson()}


# ── Дедлайны / доска ДЗ (одна и та же таблица, done — это и есть чекбокс) ────

@app.get("/api/deadlines")
async def api_deadlines(include_done: bool = False, user: dict = CurrentUser):
    from database import get_active_deadlines, get_deadline_stats
    import aiosqlite
    from config import DATABASE_PATH
    if include_done:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM deadlines ORDER BY done, due_date, due_time")
            items = [dict(r) for r in await cursor.fetchall()]
    else:
        items = await get_active_deadlines()
    stats = await get_deadline_stats()
    return {"items": items, "stats": stats}


class ToggleBody(BaseModel):
    done: bool


@app.post("/api/deadlines/{deadline_id}/toggle")
async def api_deadline_toggle(deadline_id: int, body: ToggleBody, user: dict = CurrentUser):
    from database import get_deadline, set_deadline_done
    existing = await get_deadline(deadline_id)
    if not existing:
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    await set_deadline_done(deadline_id, body.done)
    return {"ok": True, "id": deadline_id, "done": body.done}


# ── Файлы ────────────────────────────────────────────────────────────────────

@app.get("/api/files")
async def api_files(subject: str = "", q: str = "", user: dict = CurrentUser):
    from database import get_files, search_files
    if q.strip():
        items = await search_files(q.strip())
    else:
        items = await get_files(subject or None)
    # file_id намеренно не отдаём наружу как "ссылку на скачивание" — Telegram
    # file_id не резолвится в прямой URL без похода через getFile от лица
    # бота, а светить его в браузерном JS не хочется. Вместо этого фронт
    # открывает диплинк на сам бот (t.me/<bot>?start=file_<id>), который уже
    # шлёт документ — см. handlers/start.py: cmd_start_deeplink.
    return {"items": [
        {"id": f["id"], "title": f["title"], "subject": f.get("subject") or "", "file_name": f.get("file_name") or ""}
        for f in items
    ]}


# ── Заметки к парам ──────────────────────────────────────────────────────────

@app.get("/api/notes")
async def api_notes(date: str = "", user: dict = CurrentUser):
    from datetime import date as date_cls
    from database import get_lesson_notes
    date_str = date or date_cls.today().isoformat()
    items = await get_lesson_notes(date_str)
    return {"date": date_str, "items": items}


# ── Чат с DeepSeek (с трейсом рассуждений) ──────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    history: list[ChatMessage]
    subject: str = ""


@app.post("/api/chat")
async def api_chat(body: ChatBody, user: dict = CurrentUser):
    from groq_solver import chat_with_reasoning
    if not body.history:
        raise HTTPException(status_code=400, detail="пустая история")
    history = [{"role": m.role, "content": m.content} for m in body.history[-20:]]
    try:
        result = await chat_with_reasoning(history, subject=body.subject)
    except Exception as e:
        logger.warning(f"webapp chat failed: {e}")
        raise HTTPException(status_code=502, detail="DeepSeek сейчас недоступен, попробуй чуть позже")
    return result


# ── Статика фронтенда (должна идти последней — ловит всё остальное) ─────────

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
