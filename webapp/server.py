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

CORS открыт всем источникам (allow_origins=["*"]) — это нормально именно
потому, что данные защищены не происхождением запроса, а initData: сам по
себе домен фронтенда ничего не даёт без валидной подписи.
"""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import BOT_TOKEN, STAROSTA_ID
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


# ── Здоровье сервиса ─────────────────────────────────────────────────────────
# Без initData и без БД — чтобы внешний аптайм-чекер (UptimeRobot/Better
# Uptime и т.п., бесплатные тарифы) мог пинговать раз в N минут и растить
# алерт (email/telegram-бот того сервиса) при падении процесса, не будучи
# сам пользователем бота. Год без такого пинга — падение узнаёшь только от
# жалоб студентов; с ним — от сервиса, обычно за 1-5 минут.
@app.get("/health")
async def health():
    return {"ok": True}


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
    # full_name — как у бота (aiogram User.full_name = "first last"), иначе каждый
    # заход в WebApp перетирал в users фамилию, записанную ботом.
    full_name = " ".join(p for p in (user.get("first_name", ""), user.get("last_name", "")) if p)
    await upsert_user(user["id"], user.get("username", ""), full_name)
    return user


CurrentUser = Depends(get_current_user)


@app.get("/api/me")
async def api_me(user: dict = CurrentUser):
    return {"id": user["id"], "first_name": user.get("first_name", ""), "username": user.get("username", "")}


# ── Расписание ───────────────────────────────────────────────────────────────

@app.get("/api/schedule/today")
async def api_schedule_today(user: dict = CurrentUser):
    from schedule_parser import get_today_schedule
    from handlers.schedule import _notes_block
    from utils import today_msk
    html = await get_today_schedule()
    html += await _notes_block(today_msk().isoformat())
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


# ── Поиск расписания преподавателя / группы / аудитории ─────────────────────
# Свой справочник (schedule_index.py, собран с зеркала english.mirea.ru):
# официальный поиск МИРЭА из-за рубежа не отвечает. Пока справочник
# собирается — пробуем официальный, иначе честно говорим «ещё собирается».

@app.get("/api/search")
async def api_search(q: str = "", type: int = 0, user: dict = CurrentUser):
    import schedule_index
    from mirea_schedule_api import _official_search
    types = (type,) if type in schedule_index.TYPES else schedule_index.TYPES
    q = q.strip()
    if len(q) < 2:
        return {"items": [], "ready": await schedule_index.is_ready()}
    items = await schedule_index.search(q, types, limit=30)
    ready = await schedule_index.is_ready()
    if not items and not ready:
        for t in types:
            try:
                items += [{"type": t, "id": d["id"], "title": d["fullTitle"]}
                          for d in await _official_search(q, t, 10)]
            except Exception:
                break
    return {"items": items, "ready": ready}


@app.get("/api/target/{target_type}/{target_id}")
async def api_target(target_type: int, target_id: int, user: dict = CurrentUser):
    from mirea_schedule_api import get_baseinfo, fetch_ical
    from schedule_parser import format_target_schedule
    if target_type not in (1, 2, 3):
        raise HTTPException(status_code=404, detail="нет такого типа")
    info = await get_baseinfo(target_id, target_type)
    ical = await fetch_ical(target_id, target_type)
    if ical is None:
        raise HTTPException(status_code=502, detail="расписание МИРЭА сейчас недоступно")
    return {
        "type": target_type, "id": target_id,
        "title": info["fullTitle"] if info else str(target_id),
        "html": format_target_schedule(ical, target_type),
    }


# ── Дедлайны (общие + личные, "done" персональный для каждого) ──────────────

@app.get("/api/deadlines")
async def api_deadlines(include_done: bool = False, user: dict = CurrentUser):
    from database import get_active_deadlines, get_deadline_stats
    items = await get_active_deadlines(user["id"], include_done=include_done)
    stats = await get_deadline_stats(user["id"])
    return {"items": items, "stats": stats}


class ToggleBody(BaseModel):
    done: bool


@app.post("/api/deadlines/{deadline_id}/toggle")
async def api_deadline_toggle(deadline_id: int, body: ToggleBody, user: dict = CurrentUser):
    from database import get_deadline, set_deadline_done
    existing = await get_deadline(deadline_id)
    if not existing:
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    is_shared = existing["created_by"] in (0, STAROSTA_ID)
    if not is_shared and existing["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="это чужой личный дедлайн")
    # Персонально для user["id"] — не трогает статус остальных по этому же дедлайну.
    await set_deadline_done(deadline_id, user["id"], body.done)
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
    from database import get_lesson_notes
    from utils import today_msk
    date_str = date or today_msk().isoformat()
    items = await get_lesson_notes(date_str)
    return {"date": date_str, "items": items}


# ── Чат с ИИ (DeepSeek с трейсом рассуждений, без его ключа — Gemini) ─────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatAttachment(BaseModel):
    name: str = "файл"
    mime: str = ""
    data: str  # base64


class ChatBody(BaseModel):
    history: list[ChatMessage]
    subject: str = ""
    attachment: ChatAttachment | None = None


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
DOC_TEXT_LIMIT = 60_000


@app.get("/api/subjects")
async def api_subjects(user: dict = CurrentUser):
    """Предметы для чата: с загруженными лекциями (чат будет опираться на
    них) — сверху, дальше остальные предметы группы из расписания."""
    from database import get_subjects_with_lecture_text
    from schedule_parser import get_group_subjects
    with_lectures = await get_subjects_with_lecture_text()
    rest = [s for s in await get_group_subjects() if s not in with_lectures]
    return {"subjects": [{"name": s, "lectures": True} for s in with_lectures]
                        + [{"name": s, "lectures": False} for s in rest]}


@app.post("/api/chat")
async def api_chat(body: ChatBody, user: dict = CurrentUser):
    """Чат WebApp: история (последние 20), по желанию предмет (если по нему
    есть лекции — ответ опирается на них) и одно вложение — фото (решает
    Gemini по картинке) или документ PDF/DOCX/PPTX/TXT (его текст уходит в
    сообщение). В системный промпт — контекст группы: пары, дедлайны, ДЗ."""
    import asyncio
    import base64
    from ai_solver import chat_with_reasoning, solve_image
    from database import get_subject_lecture_context, get_subjects_with_lecture_text
    from file_text import SUPPORTED_EXTENSIONS, extract_text
    from group_context import build_group_context
    from utils import md_to_tg_html_chunks

    if not body.history:
        raise HTTPException(status_code=400, detail="пустая история")
    history = [{"role": m.role, "content": m.content} for m in body.history[-20:]]
    subject = body.subject.strip()
    lectures = ""
    if subject and subject in await get_subjects_with_lecture_text():
        lectures = await get_subject_lecture_context(subject)
    context = await build_group_context(user["id"])

    try:
        if body.attachment:
            try:
                raw = base64.b64decode(body.attachment.data, validate=False)
            except Exception:
                raise HTTPException(status_code=400, detail="вложение повреждено")
            if len(raw) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(status_code=413, detail="файл больше 10 МБ")
            name = body.attachment.name or "файл"
            if body.attachment.mime.startswith("image/"):
                question = history[-1]["content"].strip() or "Реши задание на фото с подробным объяснением."
                earlier = "\n".join(f"{'Студент' if m['role'] == 'user' else 'Ты'}: {m['content'][:500]}"
                                     for m in history[-7:-1])
                prompt = (f"Предыдущий разговор:\n{earlier}\n\n" if earlier else "") + f"Сообщение студента: {question}"
                content = await solve_image(raw, body.attachment.mime, subject=subject,
                                            lectures=lectures, prompt=prompt + "\n\n" + context)
                result = {"content": content, "reasoning": ""}
            else:
                if not name.lower().endswith(SUPPORTED_EXTENSIONS):
                    raise HTTPException(status_code=415, detail="умею читать PDF, DOCX, PPTX и TXT, а ещё фото")
                text = (await asyncio.to_thread(extract_text, raw, name)).strip()
                if not text:
                    raise HTTPException(status_code=422, detail="не смог достать текст из файла (скан без текстового слоя?)")
                note = "\n\n(файл обрезан — слишком длинный)" if len(text) > DOC_TEXT_LIMIT else ""
                history[-1]["content"] = (
                    (history[-1]["content"].strip() or "Разбери этот файл.")
                    + f"\n\n=== Файл «{name}» ===\n{text[:DOC_TEXT_LIMIT]}{note}"
                )
                result = await chat_with_reasoning(history, subject=subject, extra_system=context, lectures=lectures)
        else:
            result = await chat_with_reasoning(history, subject=subject, extra_system=context, lectures=lectures)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"webapp chat failed: {e}")
        raise HTTPException(status_code=502, detail="ИИ сейчас недоступен, попробуй чуть позже")
    # Тот же вид, что и в боте: жирный, код, x² вместо x^2 (всё экранировано).
    result["html"] = "\n".join(md_to_tg_html_chunks(result.get("content", "")))
    return result


# ── Персональный ICS-календарь (Фаза 12) ────────────────────────────────────
# /api/calendar/link — за initData (фронт WebApp узнаёт свою ссылку и может
# показать кнопку "скопировать"). /ics/{token} — БЕЗ initData: календарные
# приложения (Google/Apple/Outlook) сами периодически переопрашивают
# webcal-подписку и не умеют слать кастомные заголовки — секретность держится
# на непредсказуемости токена в самом пути (см. database.get_or_create_calendar_token).

@app.get("/api/calendar/link")
async def api_calendar_link(user: dict = CurrentUser):
    from database import get_or_create_calendar_token
    token = await get_or_create_calendar_token(user["id"])
    return {"token": token, "ics_path": f"/ics/{token}"}


@app.get("/ics/{token}")
async def ics_feed(token: str):
    from database import get_user_by_calendar_token
    from webapp.calendar_feed import build_ics_for_user
    owner = await get_user_by_calendar_token(token)
    if not owner:
        raise HTTPException(status_code=404, detail="ссылка недействительна")
    body = await build_ics_for_user(token)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": "inline; filename=schedule.ics"},
    )


# ── Статика фронтенда (должна идти последней — ловит всё остальное) ─────────

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
