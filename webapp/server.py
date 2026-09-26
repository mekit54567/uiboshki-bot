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


# ── Главная WebApp: структурой, а не готовым HTML ───────────────────────────

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _day_label(d) -> dict:
    from schedule_parser import MONTHS_GEN
    return {"date": d.isoformat(), "weekday": WEEKDAYS_RU[d.weekday()],
            "label": f"{d.day} {MONTHS_GEN[d.month - 1]}"}


@app.get("/api/today")
async def api_today(user: dict = CurrentUser):
    """Всё для главной одним запросом: пары сегодня со статусами, ближайшая
    пара (или завтрашняя первая), погода строкой, дедлайны (сколько и
    ближайшие три), заметки к парам."""
    from datetime import datetime, timedelta, date as date_cls
    from database import get_active_deadlines, get_lesson_notes
    from handlers.weather import get_weather_for_morning
    from schedule_parser import fetch_schedule_raw, lessons_for_date
    from utils import TZ

    now = datetime.now(TZ)
    today = now.date()
    lessons, tomorrow_first, schedule_ok = [], None, True
    try:
        raw = await fetch_schedule_raw()
        lessons = lessons_for_date(raw, today, now=now)
        tomorrow = lessons_for_date(raw, today + timedelta(days=1))
        tomorrow_first = tomorrow[0] if tomorrow else None
    except Exception as e:
        logger.warning(f"api_today: расписание недоступно: {e}")
        schedule_ok = False

    try:
        weather = await get_weather_for_morning()
    except Exception:
        weather = ""

    items = await get_active_deadlines(user["id"])
    soon = []
    for d in items[:3]:
        days = (date_cls.fromisoformat(d["due_date"]) - today).days
        soon.append({"id": d["id"], "subject": d["subject"], "due_date": d["due_date"],
                     "due_time": d.get("due_time") or "", "days": days})
    notes = await get_lesson_notes(today.isoformat())
    return {
        **_day_label(today), "now": now.isoformat(), "hour": now.hour,
        "lessons": lessons, "tomorrow_first": tomorrow_first, "schedule_ok": schedule_ok,
        "weather": weather,
        "deadlines": {"active": len(items), "soon": soon},
        "notes": [{"subject": n.get("subject") or "", "text": n["text"]} for n in notes],
    }


@app.get("/api/day")
async def api_day(date: str, user: dict = CurrentUser):
    """Пары любого дня (для выбора дня недели на главной)."""
    from datetime import date as date_cls, datetime
    from schedule_parser import fetch_schedule_raw, lessons_for_date
    from utils import TZ
    try:
        d = date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    try:
        raw = await fetch_schedule_raw()
    except Exception:
        raise HTTPException(status_code=502, detail="расписание сейчас недоступно")
    now = datetime.now(TZ)
    return {**_day_label(d), "lessons": lessons_for_date(raw, d, now=now if d == now.date() else None)}


@app.get("/api/week")
async def api_week(start: str, user: dict = CurrentUser):
    """Номер учебной недели и точки пар под днями (пн–сб от start)."""
    from datetime import date as date_cls
    from schedule_parser import fetch_schedule_raw, week_overview
    try:
        monday = date_cls.fromisoformat(start)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    try:
        raw = await fetch_schedule_raw()
    except Exception:
        raise HTTPException(status_code=502, detail="расписание сейчас недоступно")
    return week_overview(raw, monday)


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
    if items:
        from mirea_schedule_api import add_hints_for_namesakes
        hinted = await add_hints_for_namesakes(
            [{"id": i["id"], "fullTitle": i["title"], "scheduleTarget": i["type"]} for i in items])
        items = [{"type": h["scheduleTarget"], "id": h["id"], "title": h["fullTitle"],
                  **({"hint": h["hint"]} if h.get("hint") else {})} for h in hinted]
    if not items and not ready:
        for t in types:
            try:
                items += [{"type": t, "id": d["id"], "title": d["fullTitle"]}
                          for d in await _official_search(q, t, 10)]
            except Exception:
                break
    return {"items": items, "ready": ready}


TARGET_WEEKS = 8


@app.get("/api/target/{target_type}/{target_id}")
async def api_target(target_type: int, target_id: int, user: dict = CurrentUser):
    """Расписание группы/преподавателя/аудитории на TARGET_WEEKS недель с
    текущей (в воскресенье — со следующей): WebApp рисует его так же, как
    главную, — недели, точки под днями, карточки пар."""
    from datetime import datetime, timedelta
    from database import get_pins
    from mirea_schedule_api import get_baseinfo, fetch_ical
    from schedule_parser import target_weeks
    from utils import TZ
    if target_type not in (1, 2, 3):
        raise HTTPException(status_code=404, detail="нет такого типа")
    info = await get_baseinfo(target_id, target_type)
    ical = await fetch_ical(target_id, target_type)
    if ical is None:
        raise HTTPException(status_code=502, detail="расписание МИРЭА сейчас недоступно")
    now = datetime.now(TZ)
    today = now.date()
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7 if today.weekday() == 6 else 0)
    pinned = any(p["type"] == target_type and p["id"] == target_id for p in await get_pins(user["id"]))
    return {
        "type": target_type, "id": target_id,
        "title": info["fullTitle"] if info else str(target_id),
        "pinned": pinned,
        "today": today.isoformat(),
        "weeks": target_weeks(ical, monday, TARGET_WEEKS, now=now),
    }


# ── Закреплённые группы / преподаватели / аудитории ─────────────────────────

class PinBody(BaseModel):
    title: str


@app.get("/api/pins")
async def api_pins(user: dict = CurrentUser):
    from database import get_pins
    return {"items": await get_pins(user["id"])}


@app.put("/api/pins/{target_type}/{target_id}")
async def api_pin(target_type: int, target_id: int, body: PinBody, user: dict = CurrentUser):
    from database import MAX_PINS, pin_target
    title = body.title.strip()[:120]
    if target_type not in (1, 2, 3) or not title:
        raise HTTPException(status_code=400, detail="нужны тип цели и название")
    if not await pin_target(user["id"], target_type, target_id, title):
        raise HTTPException(status_code=400, detail=f"закрепить можно до {MAX_PINS}")
    return {"ok": True}


@app.delete("/api/pins/{target_type}/{target_id}")
async def api_unpin(target_type: int, target_id: int, user: dict = CurrentUser):
    from database import unpin_target
    await unpin_target(user["id"], target_type, target_id)
    return {"ok": True}


# ── Дедлайны (общие + личные, "done" персональный для каждого) ──────────────

@app.get("/api/deadlines")
async def api_deadlines(include_done: bool = False, user: dict = CurrentUser):
    from database import get_active_deadlines, get_deadline_stats, is_shared_deadline
    from handlers.announce import is_editor
    items = await get_active_deadlines(user["id"], include_done=include_done)
    editor = await is_editor(user["id"])
    for d in items:
        d["personal"] = not is_shared_deadline(d)
        d["mine"] = d.get("created_by") == user["id"]
        # Править/удалять: свой личный — автор, общий — староста и зам.
        d["can_edit"] = (d["personal"] and d["mine"]) or (not d["personal"] and editor)
    stats = await get_deadline_stats(user["id"])
    return {"items": items, "stats": stats}


class NewDeadline(BaseModel):
    subject: str
    due_date: str
    due_time: str = ""
    description: str = ""


def _validate_deadline(body: NewDeadline) -> tuple[str, str, str | None, str]:
    from datetime import date as date_cls
    from handlers.deadlines import parse_due_time
    subject = body.subject.strip()
    if not subject or len(subject) > 200:
        raise HTTPException(status_code=400, detail="название — от 1 до 200 символов")
    try:
        due = date_cls.fromisoformat(body.due_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    due_time = None
    if body.due_time.strip():
        ok, due_time = parse_due_time(body.due_time)
        if not ok:
            raise HTTPException(status_code=400, detail="время в формате ЧЧ:ММ")
    return subject, due.isoformat(), due_time, body.description.strip()[:1500]


async def _can_edit_deadline(existing: dict, user_id: int) -> bool:
    from database import is_shared_deadline
    from handlers.announce import is_editor
    if is_shared_deadline(existing):
        return await is_editor(user_id)
    return existing["created_by"] == user_id


@app.post("/api/deadlines")
async def api_deadline_add(body: NewDeadline, user: dict = CurrentUser):
    """Свой (личный) дедлайн из WebApp — как /add в боте: виден только
    автору. Общие дедлайны группы по-прежнему заводит староста/СДО."""
    from database import add_deadline
    subject, due, due_time, desc = _validate_deadline(body)
    did = await add_deadline(subject, desc, due, due_time, user["id"])
    return {"ok": True, "id": did}


@app.patch("/api/deadlines/{deadline_id}")
async def api_deadline_edit(deadline_id: int, body: NewDeadline, user: dict = CurrentUser):
    """Правка дедлайна: свой личный — автор, общий (в т.ч. из СДО) —
    староста и зам. Отредактированный общий автосинк СДО больше не трогает."""
    from database import edit_deadline, get_deadline
    existing = await get_deadline(deadline_id)
    if not existing:
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    if not await _can_edit_deadline(existing, user["id"]):
        raise HTTPException(status_code=403, detail="общий дедлайн правит староста, личный — автор")
    subject, due, due_time, desc = _validate_deadline(body)
    await edit_deadline(deadline_id, subject, desc, due, due_time)
    return {"ok": True, "id": deadline_id}


@app.delete("/api/deadlines/{deadline_id}")
async def api_deadline_delete(deadline_id: int, user: dict = CurrentUser):
    """Свой личный — автор, общий — староста и зам."""
    from database import delete_deadline, get_deadline
    existing = await get_deadline(deadline_id)
    if not existing:
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    if not await _can_edit_deadline(existing, user["id"]):
        raise HTTPException(status_code=403, detail="общий дедлайн удаляет староста, личный — автор")
    await delete_deadline(deadline_id)
    return {"ok": True}


@app.get("/api/homework")
async def api_homework(user: dict = CurrentUser):
    """Доска ДЗ (/addhw в боте): свежие сверху. Файл ДЗ WebApp открывает
    диплинком в бота (t.me/<бот>?start=hw_<id>) — file_id наружу не отдаём."""
    from group_context import list_homework
    items = await list_homework(60)
    return {"items": [
        {"id": h["id"], "subject": h["subject"], "content": h.get("content") or "",
         "lesson_date": h.get("lesson_date") or "", "created_at": (h.get("created_at") or "")[:10],
         "has_file": bool(h.get("file_id"))}
        for h in items
    ]}


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
    from database import get_file_ids_with_text
    from file_categories import CATEGORIES, LABELS, category_of
    from handlers.announce import is_editor
    with_text = await get_file_ids_with_text()
    editor = await is_editor(user["id"])
    out = []
    for f in items:
        cat = category_of(f)
        out.append({
            "id": f["id"], "title": f["title"], "subject": f.get("subject") or "",
            "file_name": f.get("file_name") or "", "has_text": f["id"] in with_text,
            "category": cat, "category_label": LABELS[cat],
            # как /delfile в боте: тот, кто загрузил, или староста/зам
            "can_edit": editor or f.get("uploaded_by") == user["id"],
        })
    return {"items": out, "categories": [{"key": k, "label": v} for k, v in CATEGORIES]}


class FileMeta(BaseModel):
    title: str
    subject: str = ""
    category: str


@app.patch("/api/files/{file_id}")
async def api_file_edit(file_id: int, body: FileMeta, user: dict = CurrentUser):
    """Поправить название, предмет и тип файла (например, если тип по
    названию угадан неверно). Предмет меняется вместе с контекстом ИИ:
    текст лекции привязан к файлу, а не к предмету."""
    from database import get_files, update_file_meta
    from file_categories import LABELS
    from handlers.announce import is_editor
    f = next((x for x in await get_files() if x["id"] == file_id), None)
    if not f:
        raise HTTPException(status_code=404, detail="файл не найден")
    if f.get("uploaded_by") != user["id"] and not await is_editor(user["id"]):
        raise HTTPException(status_code=403, detail="править файл может тот, кто его загрузил, или староста")
    title, subject = body.title.strip(), body.subject.strip()
    if not title or len(title) > 120:
        raise HTTPException(status_code=400, detail="название — от 1 до 120 символов")
    if len(subject) > 80:
        raise HTTPException(status_code=400, detail="предмет — до 80 символов")
    if body.category not in LABELS:
        raise HTTPException(status_code=400, detail="неизвестный тип файла")
    await update_file_meta(file_id, title, subject, body.category)
    return {"ok": True, "id": file_id}


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
    # Лекции — только подходящие к вопросу (lecture_picker): после выгрузки
    # СДО их у предмета сотни тысяч символов. Без выбранного предмета — из
    # всех предметов, но только при явном совпадении с вопросом.
    import lecture_picker
    from database import get_all_lecture_context
    query = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    lectures = ""
    if subject and subject in await get_subjects_with_lecture_text():
        lectures = lecture_picker.pick(await get_subject_lecture_context(subject), query)
    elif not subject and query.strip():
        lectures = await asyncio.to_thread(lecture_picker.pick, await get_all_lecture_context(), query,
                                           lecture_picker.AUTO_BUDGET, lecture_picker.AUTO_MIN_SCORE)
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
