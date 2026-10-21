"""Расписание: своё (главная WebApp, дни, недели), предметы по выбору, поиск
и расписание любой группы/преподавателя/аудитории МИРЭА, закреплённые,
заметки к парам и картинки расписания для inline-режима (/card)."""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from webapp.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Картинки расписания для inline-режима ───────────────────────────────────
# Telegram забирает картинку по URL сам, без initData, поэтому ссылка
# подписана (schedule_card.sign). Готовые картинки — в памяти на 10 минут.
_card_cache: dict[str, tuple[float, bytes]] = {}


@router.get("/card/{key}.jpg")
async def schedule_card_image(key: str, sig: str = "", thumb: int = 0):
    import asyncio
    import time
    from datetime import datetime
    import schedule_card
    from config import BOT_USERNAME, GROUP_NAME
    from utils import TZ
    parsed = schedule_card.parse_key(key, sig)
    if not parsed:
        raise HTTPException(403, "Неверная ссылка")
    hit = _card_cache.get(key)
    if hit and hit[0] > time.time():
        return await _card_response(hit[1], thumb)
    kind, target_type, target_id = parsed
    now = datetime.now(TZ)
    if kind == "target":
        import schedule_index
        from mirea_schedule_api import fetch_ical
        raw = await fetch_ical(target_id, target_type)
        if raw is None:
            raise HTTPException(502, "Расписание не загрузилось")
        title = await schedule_index.get_title(target_type, target_id) or "Расписание"
        data = await asyncio.to_thread(schedule_card.build_target, raw, title, now, BOT_USERNAME)
    elif target_id:                       # «сегодня/завтра/неделя» другой группы (inline, этап 1)
        import schedule_index
        from mirea_schedule_api import fetch_ical
        raw = await fetch_ical(target_id, 1)
        if raw is None:
            raise HTTPException(502, "Расписание не загрузилось")
        name = await schedule_index.get_title(1, target_id) or "Группа"
        data = await asyncio.to_thread(schedule_card.build_own, raw, kind, now, name, BOT_USERNAME)
    else:
        from schedule_parser import fetch_schedule_raw
        raw = await fetch_schedule_raw()
        data = await asyncio.to_thread(schedule_card.build_own, raw, kind, now, GROUP_NAME, BOT_USERNAME)
    if len(_card_cache) > 200:
        _card_cache.clear()
    _card_cache[key] = (time.time() + 600, data)
    return await _card_response(data, thumb)


async def _card_response(data: bytes, thumb: int) -> Response:
    """Картинка целиком или маленькое превью (inline: thumbnail_url — свой адрес).
    Pillow — в отдельном потоке, как и сама карточка: сервер не замирает."""
    if thumb:
        import schedule_card
        data = await asyncio.to_thread(schedule_card.thumbnail, data)
    return Response(data, media_type="image/jpeg")


# ── Расписание ───────────────────────────────────────────────────────────────

async def _user_gid(user: dict) -> int | None:
    from database import get_user_group
    return await get_user_group(user["id"])


@router.get("/api/schedule/today")
async def api_schedule_today(user: dict = CurrentUser):
    from schedule_parser import get_today_schedule
    from handlers.schedule import _notes_block
    from utils import today_msk
    html = await get_today_schedule(await _user_gid(user))
    html += await _notes_block(today_msk().isoformat(), await _user_gid(user))
    return {"html": html}


@router.get("/api/schedule/tomorrow")
async def api_schedule_tomorrow(user: dict = CurrentUser):
    from schedule_parser import get_tomorrow_schedule
    return {"html": await get_tomorrow_schedule(await _user_gid(user))}


@router.get("/api/schedule/week")
async def api_schedule_week(user: dict = CurrentUser):
    from schedule_parser import get_week_schedule
    return {"html": await get_week_schedule(await _user_gid(user))}


@router.get("/api/schedule/next")
async def api_schedule_next(user: dict = CurrentUser):
    from schedule_parser import get_next_lesson
    return {"html": await get_next_lesson(await _user_gid(user))}


# ── Главная WebApp: структурой, а не готовым HTML ───────────────────────────

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _day_label(d) -> dict:
    from schedule_parser import MONTHS_GEN
    return {"date": d.isoformat(), "weekday": WEEKDAYS_RU[d.weekday()],
            "label": f"{d.day} {MONTHS_GEN[d.month - 1]}"}


@router.get("/api/today")
async def api_today(user: dict = CurrentUser):
    """Всё для главной одним запросом: пары сегодня со статусами, ближайшая
    пара (или завтрашняя первая), погода строкой, дедлайны (сколько и
    ближайшие три), заметки к парам."""
    import asyncio
    from datetime import datetime, timedelta, date as date_cls
    from database import get_active_deadlines, get_lesson_notes
    from handlers.schedule import _clip
    from handlers.weather import get_weather_for_morning
    from schedule_parser import lessons_for_date, raw_for_user
    from utils import TZ

    # погода (кэш 20 мин, а без него — внешний запрос) — параллельно с расписанием
    weather_task = asyncio.create_task(get_weather_for_morning())
    now = datetime.now(TZ)
    today = now.date()
    lessons, cancelled, tomorrow_first, schedule_ok, campus = [], [], None, True, ""
    try:
        raw = await raw_for_user(user["id"])
        lessons = lessons_for_date(raw, today, now=now)
        cancelled = await _changes(user["id"], today, lessons)
        tomorrow = lessons_for_date(raw, today + timedelta(days=1))
        tomorrow_first = tomorrow[0] if tomorrow else None
        import notify_prefs        # «сегодня пары на МП-1, не на В-78»
        from schedule_parser import parse_events_for_date
        campus = re.sub(r"<[^>]+>|📍 ", "", notify_prefs.campus_note(parse_events_for_date(raw, today),
                                                                    notify_prefs.home_campus(raw)))
    except Exception as e:
        logger.warning(f"api_today: расписание недоступно: {e}")
        schedule_ok = False

    try:
        weather = await weather_task
    except Exception:
        weather = ""

    items = await get_active_deadlines(user["id"])
    soon = []
    for d in items[:3]:
        days = (date_cls.fromisoformat(d["due_date"]) - today).days
        soon.append({"id": d["id"], "subject": d["subject"], "due_date": d["due_date"],
                     "due_time": d.get("due_time") or "", "days": days})
    from database.groups import viewer_group
    import ugc
    notes = ugc.without_hidden(await get_lesson_notes(today.isoformat(), await viewer_group(user["id"])),
                               await ugc.hidden(user["id"]), "created_by")
    return {
        **_day_label(today), "now": now.isoformat(), "hour": now.hour,
        "lessons": lessons, "cancelled": cancelled, "tomorrow_first": tomorrow_first, "schedule_ok": schedule_ok,
        "weather": weather, "campus": campus, "stale": await _stale_for(user["id"]),
        "deadlines": {"active": len(items), "soon": soon},
        "notes": [{"subject": n.get("subject") or "", "text": _clip(n["text"])} for n in notes],
    }


def _stale_label() -> str | None:
    from schedule_parser import stale_label
    return stale_label()


async def _stale_for(user_id: int) -> str | None:
    """«Данные от 14:20» — только у своей группы (у неё запасная копия в базе)."""
    import groups
    from database import get_user_group
    gid = await get_user_group(user_id)
    return None if gid and gid != groups.home_id() else _stale_label()


class OptionalAnswer(BaseModel):
    subject: str
    attend: bool


@router.get("/api/optional")
async def api_optional(user: dict = CurrentUser):
    """Предметы по выбору: о каких спросить (pending) и что уже ответил."""
    from config import OPTIONAL_SUBJECTS
    from database import get_optional_answers
    from optional_subjects import pending_for
    answers = await get_optional_answers(user["id"])
    return {"pending": await pending_for(user["id"]),
            "answers": {s: answers[s] for s in OPTIONAL_SUBJECTS if s in answers}}


@router.post("/api/optional")
async def api_optional_set(body: OptionalAnswer, user: dict = CurrentUser):
    from config import OPTIONAL_SUBJECTS
    from database import set_optional_answer
    if body.subject not in OPTIONAL_SUBJECTS:
        raise HTTPException(status_code=400, detail="не предмет по выбору")
    await set_optional_answer(user["id"], body.subject, body.attend)
    return {"ok": True}


@router.get("/api/day")
async def api_day(date: str, user: dict = CurrentUser):
    """Пары любого дня (для выбора дня недели на главной)."""
    from datetime import date as date_cls, datetime
    from schedule_parser import lessons_for_date, raw_for_user
    from utils import TZ
    try:
        d = date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    try:
        raw = await raw_for_user(user["id"])
    except Exception:
        raise HTTPException(status_code=502, detail="расписание сейчас недоступно")
    now = datetime.now(TZ)
    lessons = lessons_for_date(raw, d, now=now if d == now.date() else None)
    out = {**_day_label(d), "lessons": lessons, "cancelled": await _changes(user["id"], d, lessons)}
    if d <= now.date():
        # «Итоги дня» (day_summary.py): сданное и баллы; None — пустой день.
        # Сбой — без поля, как у изменений расписания.
        try:
            import day_summary
            out["summary"] = await day_summary.summary(user["id"], d)
        except Exception as e:
            logger.warning(f"итоги дня не прочитались: {e}")
    return out


async def _changes(user_id: int, d, lessons: list[dict]) -> list[dict]:
    """Кабинет изменён (room_was у пары) и отменённые пары (отдельным списком,
    в lessons их нет — счёт пар и «идёт сейчас» не меняются). Сбой — без отметок."""
    try:
        from schedule_diff import day_changes
        return await day_changes(user_id, d, lessons)
    except Exception as e:
        logger.warning(f"изменения расписания не прочитались: {e}")
        return []


@router.get("/api/week")
async def api_week(start: str, user: dict = CurrentUser):
    """Номер учебной недели и точки пар под днями (пн–сб от start)."""
    from datetime import date as date_cls
    from schedule_parser import raw_for_user, week_overview
    try:
        monday = date_cls.fromisoformat(start)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    try:
        raw = await raw_for_user(user["id"])
    except Exception:
        raise HTTPException(status_code=502, detail="расписание сейчас недоступно")
    return week_overview(raw, monday)


# ── Поиск расписания преподавателя / группы / аудитории ─────────────────────
# Свой справочник (schedule_index.py, собран с зеркала english.mirea.ru):
# официальный поиск МИРЭА из-за рубежа не отвечает. Пока справочник
# собирается — пробуем официальный, иначе честно говорим «ещё собирается».

@router.get("/api/search")
async def api_search(q: str = "", type: int = 0, subject: str = "", user: dict = CurrentUser):
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
            [{"id": i["id"], "fullTitle": i["title"], "scheduleTarget": i["type"]} for i in items],
            subject=subject[:200])
        items = [{"type": h["scheduleTarget"], "id": h["id"], "title": h["fullTitle"],
                  **({"hint": h["hint"]} if h.get("hint") else {}),
                  **({"match": True} if h.get("match") else {})} for h in hinted]
    if not items and not ready:
        for t in types:
            try:
                items += [{"type": t, "id": d["id"], "title": d["fullTitle"]}
                          for d in await _official_search(q, t, 10)]
            except Exception:
                break
    return {"items": items, "ready": ready}


TARGET_WEEKS = 8


@router.get("/api/target/{target_type}/{target_id}")
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
    stale = None
    if ical is None and _own_group(target_type, target_id):
        # своя группа — из сохранённой копии, как на главной (дизайн-ревью, п. 6)
        from schedule_parser import fetch_schedule_raw, stale_label
        try:
            ical, stale = await fetch_schedule_raw(), stale_label()
        except Exception as e:
            logger.info(f"api_target: и копии своей группы нет: {e!r}")
    if ical is None:
        raise HTTPException(status_code=502, detail="расписание МИРЭА сейчас недоступно")
    now = datetime.now(TZ)
    today = now.date()
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7 if today.weekday() == 6 else 0)
    try:
        weeks = target_weeks(ical, monday, TARGET_WEEKS, now=now)
    except Exception as e:      # обрывок календаря — не 500, а «недоступно»
        logger.warning(f"api_target: календарь {target_type}/{target_id} не разобрался: {e!r}")
        raise HTTPException(status_code=502, detail="расписание МИРЭА сейчас недоступно")
    pinned = any(p["type"] == target_type and p["id"] == target_id for p in await get_pins(user["id"]))
    return {
        "type": target_type, "id": target_id,
        "title": info["fullTitle"] if info else str(target_id),
        "pinned": pinned,
        "today": today.isoformat(),
        "weeks": weeks,
        "stale": stale,
    }


async def _find_target(query: str, target_type: int) -> int | None:
    """id аудитории или преподавателя в справочнике — только если однозначно:
    «А-17 (В-78)» — точное совпадение, без корпуса — единственная такая;
    однофамильцы — не угадываем."""
    import schedule_index
    q = schedule_index._norm(query)
    if not q:
        return None
    items = await schedule_index.search(query, (target_type,), limit=10)
    exact = [i for i in items if schedule_index._norm(i["title"]) == q]
    if len(exact) == 1:
        return exact[0]["id"]
    if target_type == 3 and (m := re.fullmatch(r"(.+?)\s*\(([^)]+)\)", query.strip())):
        room, campus = m.group(1), schedule_index._norm(m.group(2))
        near = [i for i in await schedule_index.search(room, (3,), limit=20)
                if campus in schedule_index._norm(i["title"])
                and schedule_index._norm(i["title"]).startswith(schedule_index._norm(room))]
        if len(near) == 1:
            return near[0]["id"]
    return items[0]["id"] if len(items) == 1 else None


@router.get("/api/lesson/groups")
async def api_lesson_groups(start: str, room: str = "", teacher: str = "", user: dict = CurrentUser):
    """С кем эта пара: группы, у которых в то же время пара в этой аудитории
    (Никита 12.10: на лекциях — весь поток), без своей. Календарь аудитории,
    нет её в справочнике (кафедра, дистант) — преподавателя. Не нашлось или
    МИРЭА молчит — пустой список, экран просто без строки."""
    from datetime import datetime
    from mirea_schedule_api import fetch_ical
    from schedule_events import groups_at
    from utils import TZ
    import config
    import groups as groups_mod
    try:
        # «…Z» из приложения: fromisoformat до Python 3.11 его не понимает
        start = start.strip()
        when = datetime.fromisoformat(start[:-1] + "+00:00" if start[-1:] in ("Z", "z") else start)
    except ValueError:
        raise HTTPException(status_code=400, detail="start — время ISO")
    if when.tzinfo is None:
        when = when.replace(tzinfo=TZ)
    mine = (await groups_mod.of_user(user["id"]) or {}).get("name") or config.GROUP_NAME
    for query, target_type, source in ((room, 3, "room"), (teacher, 2, "teacher")):
        if not query.strip():
            continue
        target_id = await _find_target(query, target_type)
        if target_id is None:
            continue
        ical = await fetch_ical(target_id, target_type)
        if ical is None:
            continue
        try:
            found = groups_at(ical, when)
        except Exception as e:
            logger.info(f"api_lesson_groups: календарь {target_type}/{target_id} не разобрался: {e!r}")
            continue
        if found:
            return {"groups": [g for g in found if g != mine], "source": source}
    return {"groups": [], "source": ""}


def _own_group(target_type: int, target_id: int) -> bool:
    """Это календарь самой группы бота (ICAL_URL …/ical/1/4928)?"""
    from config import ICAL_URL
    m = re.search(r"/ical/(\d+)/(\d+)", ICAL_URL or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) == (target_type, target_id)


# ── Закреплённые группы / преподаватели / аудитории ─────────────────────────

class PinBody(BaseModel):
    title: str


@router.get("/api/pins")
async def api_pins(user: dict = CurrentUser):
    from database import get_pins
    return {"items": await get_pins(user["id"])}


@router.put("/api/pins/{target_type}/{target_id}")
async def api_pin(target_type: int, target_id: int, body: PinBody, user: dict = CurrentUser):
    from database import MAX_PINS, pin_target
    title = body.title.strip()[:120]
    if target_type not in (1, 2, 3) or not title:
        raise HTTPException(status_code=400, detail="нужны тип цели и название")
    if not await pin_target(user["id"], target_type, target_id, title):
        raise HTTPException(status_code=400, detail=f"закрепить можно до {MAX_PINS}")
    return {"ok": True}


@router.delete("/api/pins/{target_type}/{target_id}")
async def api_unpin(target_type: int, target_id: int, user: dict = CurrentUser):
    from database import unpin_target
    await unpin_target(user["id"], target_type, target_id)
    return {"ok": True}


# ── Заметки к парам ──────────────────────────────────────────────────────────

@router.get("/api/notes")
async def api_notes(date: str = "", user: dict = CurrentUser):
    from database import get_lesson_notes
    from utils import today_msk
    from database.groups import viewer_group
    date_str = date or today_msk().isoformat()
    import ugc
    items = ugc.without_hidden(await get_lesson_notes(date_str, await viewer_group(user["id"])),
                               await ugc.hidden(user["id"]), "created_by")
    for n in items:   # своё (или староста) — можно убрать из приложения
        n["mine"] = n.get("created_by") == user["id"]
    return {"date": date_str, "items": items}


class NoteBody(BaseModel):
    date: str
    text: str
    subject: str = ""


@router.post("/api/notes")
async def api_note_add(body: NoteBody, user: dict = CurrentUser):
    """Заметка к паре или дню из приложения — как /note в боте: видна всей
    группе под расписанием того дня."""
    from datetime import date as _date, timedelta
    import ratelimit
    from database import add_lesson_note
    from database.groups import home, viewer_group
    from handlers.schedule import NOTE_MAX
    from utils import today_msk
    try:
        day = _date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    today = today_msk()
    if not (today - timedelta(days=1) <= day <= today + timedelta(days=180)):
        raise HTTPException(status_code=400, detail="заметку можно на сегодня и вперёд, до полугода")
    text, subject = body.text.strip(), body.subject.strip()
    if not text:
        raise HTTPException(status_code=400, detail="напиши текст заметки")
    if len(text) > NOTE_MAX:
        raise HTTPException(status_code=400, detail=f"длинновато — до {NOTE_MAX} символов")
    if len(subject) > 80:
        raise HTTPException(status_code=400, detail="название пары слишком длинное")
    gid = await viewer_group(user["id"])
    if not gid and home():   # не в чате своей группы — её заметок не видит и не пишет
        raise HTTPException(status_code=403, detail="заметки — для своей группы")
    if not ratelimit.allow("note", user["id"]):
        raise HTTPException(429, "Много заметок подряд — подожди пару минут")
    import ugc
    if why := await ugc.note_spam(user["id"], day.isoformat(), text, gid):
        raise HTTPException(429, why)
    nid = await add_lesson_note(day.isoformat(), subject, text, user["id"], gid)
    return {"ok": True, "id": nid}


@router.delete("/api/notes/{note_id}")
async def api_note_delete(note_id: int, user: dict = CurrentUser):
    """Убрать заметку: свою — автор, любую своей группы — её староста."""
    from database import delete_lesson_note, get_lesson_note, is_editor
    from database.groups import row_group, viewer_group
    note = await get_lesson_note(note_id)
    if not note or row_group(note.get("group_id")) != await viewer_group(user["id"]):
        raise HTTPException(status_code=404, detail="заметка не найдена")
    if note["created_by"] != user["id"] and not await is_editor(user["id"], row_group(note.get("group_id"))):
        raise HTTPException(status_code=403, detail="убрать можно только свою заметку")
    await delete_lesson_note(note_id)
    return {"ok": True}
