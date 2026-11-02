"""Расписание группы: загрузка календаря МИРЭА с кэшем и запасной копией,
готовые ответы бота (сегодня, завтра, неделя, ближайшая пара), предметы
группы. Разбор ical — schedule_events.py, оформление — schedule_format.py."""

import asyncio
import time
import httpx
import logging
from datetime import date, datetime, timedelta

from config import ICAL_URL, SCHEDULE_CACHE_TTL_SECONDS

from optional_subjects import unfiltered
logger = logging.getLogger(__name__)

# Разбор и оформление — в schedule_events.py и schedule_format.py (v5.0.2);
# здесь — загрузка календаря с кэшем и сборка готовых ответов. Снаружи всё
# по-старому: from schedule_parser import lessons_for_date, MONTHS_GEN, …
from schedule_format import (  # noqa: F401
    TZ, DAY_NAMES, MONTHS_GEN, DAY_SHORT, PAIR_SLOTS, format_day, format_lesson, is_self_study,
    _human_date, _keycap, _split_kind,
)
from schedule_events import (  # noqa: F401
    TEACHER_RE, parse_events_for_date, lessons_for_date, week_number, week_overview, target_weeks,
    summarize_target, list_upcoming_events, _calendar_query,
)

# ── Простой TTL-кэш сырого ical-фида ────────────────────────────────────────────
# Раньше fetch_schedule_raw() дёргался без кэша отовсюду: каждую минуту из
# check_lesson_reminders (scheduler.py), плюс из каждой команды /today, /tomorrow
# и т.д. — десятки одинаковых HTTP-запросов к стороннему серверу в минуту.
_cache_data: bytes | None = None
_cache_time: float = 0.0


# Зеркало МИРЭА иногда лежит. Тогда отдаём последний удачный календарь (из
# памяти или из базы — после перезапуска) и помним, от какого он времени:
# stale_label() → «14:20», и бот/приложение честно пишут «данные от 14:20».
_ok_at: datetime | None = None        # когда последний раз календарь скачался
_stale = False                        # сейчас отдаём сохранённое, а не свежее
_backup_hash: int | None = None


def stale_label() -> str | None:
    """None — расписание свежее; иначе «14:20» или «1 окт, 14:20»."""
    if not _stale or not _ok_at:
        return None
    t = _ok_at.astimezone(TZ)
    if t.date() == datetime.now(TZ).date():
        return f"{t:%H:%M}"
    months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{t.day} {months[t.month - 1]}, {t:%H:%M}"


def stale_note() -> str:
    lbl = stale_label()
    return f"\n\n⚠️ <i>Сайт расписания МИРЭА не отвечает — показываю сохранённое от {lbl}.</i>" if lbl else ""


def _check_calendar(data: bytes):
    """Календарь целиком и с парами, а не страница ошибки, обрывок или пустой
    файл: обрезанный ical затирал запасную копию и потом падал при каждом
    разборе, пустой — рассылал ложные «❌ Отменена пара»."""
    from icalendar import Calendar
    if b"BEGIN:VCALENDAR" not in data[:512]:
        raise ValueError("зеркало ответило не календарём")   # страница ошибки с кодом 200
    try:
        cal = Calendar.from_ical(data)
    except Exception as e:
        raise ValueError(f"календарь не разбирается: {e}") from e
    if not cal.walk("VEVENT"):
        raise ValueError("в календаре нет ни одного события")


async def _download() -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(ICAL_URL)
        resp.raise_for_status()
        await asyncio.to_thread(_check_calendar, resp.content)
        return resp.content


async def _save_backup(data: bytes):
    global _backup_hash
    h = hash(data)
    if h == _backup_hash:
        return
    try:
        from database import save_schedule_backup
        await save_schedule_backup(data, _ok_at.isoformat())
        _backup_hash = h
    except Exception as e:
        logger.info(f"Копия расписания не сохранилась: {e}")


# Одна загрузка на всех (single-flight): при висящем зеркале раньше каждый
# вызов после истечения кэша ждал свои 30 с, а параллельные качали каждый сам.
_inflight: asyncio.Task | None = None
_fail_at: float | None = None          # когда загрузка последний раз не удалась
_fail_exc: BaseException | None = None
RETRY_AFTER_FAIL = 60                  # с: следующая попытка — через минуту после сбоя


async def _refresh() -> bytes:
    global _cache_data, _cache_time, _ok_at, _stale, _fail_at, _fail_exc
    try:
        data = await _download()
    except Exception as e:
        _fail_at, _fail_exc = time.monotonic(), e
        if _cache_data is None:
            try:
                from database import load_schedule_backup
                saved = await load_schedule_backup()
            except Exception as be:
                logger.warning(f"запасная копия расписания не прочиталась: {be!r}")
                saved = None
            if not saved:
                raise
            _cache_data, _ok_at = saved[0], datetime.fromisoformat(saved[1])
        logger.warning(f"Расписание: зеркало не отвечает ({type(e).__name__}) — отдаю сохранённое")
        _stale = True
        # повторить через минуту от момента сбоя (а не от начала запроса,
        # который сам висел 30 с), а не ждать весь TTL
        _cache_time = _fail_at - SCHEDULE_CACHE_TTL_SECONDS + RETRY_AFTER_FAIL
        return _cache_data
    _cache_data, _cache_time, _ok_at, _stale = data, time.monotonic(), datetime.now(TZ), False
    _fail_at = _fail_exc = None
    await _save_backup(data)
    return _cache_data


def _start_refresh() -> asyncio.Task:
    global _inflight
    loop = asyncio.get_running_loop()
    if _inflight is None or _inflight.done() or _inflight.get_loop() is not loop:
        _inflight = loop.create_task(_refresh())
        # ошибку забирает тот, кто ждёт; у фонового обновления ждущих нет — гасим «never retrieved»
        _inflight.add_done_callback(lambda t: t.cancelled() or t.exception())
    return _inflight


def _other_group(group_id: int | None) -> bool:
    """Чужая группа (этап 1: любая группа института) — не своя из ICAL_URL."""
    if not group_id:
        return False
    import groups
    return group_id != groups.home_id()


async def fetch_schedule_raw(force: bool = False, group_id: int | None = None) -> bytes:
    """Календарь группы: своей (ICAL_URL) — с кэшем, запасной копией в базе и
    single-flight ниже; другой — через общий кэш календарей МИРЭА
    (mirea_schedule_api.fetch_ical, 10 минут, при сбое — последний удачный)."""
    if _other_group(group_id):
        from mirea_schedule_api import fetch_ical
        raw = await fetch_ical(int(group_id), 1)
        if raw is None:
            raise RuntimeError("расписание группы не загрузилось")
        return raw
    now = time.monotonic()
    if not force and _cache_data is not None:
        if now - _cache_time >= SCHEDULE_CACHE_TTL_SECONDS:
            _start_refresh()          # протухло — отдаём старое сразу, свежее качается в фоне
        return _cache_data
    if not force and _fail_exc is not None and _fail_at is not None and now - _fail_at < RETRY_AFTER_FAIL:
        raise _fail_exc               # ни кэша, ни копии, и только что не вышло — не ждём снова 30 с
    if not force and _fail_exc is None and await _from_backup():
        return _cache_data
    return await asyncio.shield(_start_refresh())


async def _from_backup() -> bool:
    """Сразу после перезапуска (память пуста) — копия из базы, а свежее — в
    фоне. Раньше первый заход ждал зеркало до 30 с (Никита 17.10, /status:
    дедлайны, ДЗ и СДО по 30–35 с в первые минуты после деплоя)."""
    global _cache_data, _cache_time, _ok_at
    try:
        from database import load_schedule_backup
        saved = await load_schedule_backup()
    except Exception as e:
        logger.info(f"запасная копия расписания не прочиталась: {e!r}")
        return False
    if not saved:
        return False
    if _cache_data is None:           # пока читали, могло скачаться свежее
        _cache_data, _ok_at = saved[0], datetime.fromisoformat(saved[1])
        _cache_time = time.monotonic() - SCHEDULE_CACHE_TTL_SECONDS - 1
        _start_refresh()
    return True


async def _raw(group_id: int | None = None, force: bool = False) -> bytes:
    """Календарь группы; своя — прежним вызовом (его подменяют тесты и он с кэшем)."""
    if _other_group(group_id):
        return await fetch_schedule_raw(force, group_id=group_id)
    return await fetch_schedule_raw(force) if force else await fetch_schedule_raw()


async def get_today_schedule(group_id: int | None = None) -> str:
    try:
        raw   = await _raw(group_id)
        now   = datetime.now(TZ)
        return format_day(parse_events_for_date(raw, now.date()), now.date(), now=now) + ("" if _other_group(group_id) else stale_note())
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_tomorrow_schedule(group_id: int | None = None) -> str:
    try:
        raw      = await _raw(group_id)
        tomorrow = datetime.now(TZ).date() + timedelta(days=1)
        return format_day(parse_events_for_date(raw, tomorrow), tomorrow) + ("" if _other_group(group_id) else stale_note())
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


_subjects_cache: dict[tuple, list[str]] = {}


async def get_group_subjects(days_back: int = 14, days_ahead: int = 28, group_id: int | None = None) -> list[str]:
    """Настоящие названия предметов группы (без «ЛК/ПР») из её расписания —
    для кнопок выбора предмета при загрузке файлов и в решалке, чтобы файлы
    лекций и решалка говорили на одном языке, а не «Математика» против
    «Основы бизнес-анализа в ИТ-сфере». Пустой список, если расписание
    не загрузилось."""
    try:
        raw = await _raw(group_id)
    except Exception as e:
        logger.warning(f"get_group_subjects: {e}")
        return []
    today = datetime.now(TZ).date()
    key = (id(raw), today, days_back, days_ahead)
    if key in _subjects_cache:
        return _subjects_cache[key]
    start = datetime.combine(today - timedelta(days=days_back), datetime.min.time(), TZ)
    end = datetime.combine(today + timedelta(days=days_ahead), datetime.min.time(), TZ)
    names = set()
    for component in _calendar_query(raw).between(start, end):
        summary = str(component.get("SUMMARY", ""))
        if not summary or summary.strip().endswith("неделя"):
            continue
        title, _, _ = _split_kind(summary)
        if title:
            names.add(title)
    _subjects_cache.clear()
    _subjects_cache[key] = sorted(names)
    return _subjects_cache[key]


@unfiltered
def format_target_schedule(raw: bytes, target_type: int, days: int = 14) -> str:
    """Расписание найденного преподавателя/группы/аудитории на days дней
    вперёд, пустые дни пропускаются. У преподавателя и аудитории в строке —
    группы, у группы — преподаватель (target_type как в API МИРЭА: 1 группа,
    2 преподаватель, 3 аудитория)."""
    extra = "teacher" if target_type == 1 else "groups"
    today = datetime.now(TZ).date()
    blocks = []
    for i in range(days):
        d = today + timedelta(days=i)
        events = parse_events_for_date(raw, d)
        if events:
            blocks.append(format_day(events, d, compact=True, extra=extra))
    if not blocks:
        return f"Пар в ближайшие {days} дней нет."
    return "\n\n".join(blocks)


def _format_week(raw: bytes, monday: date, label: str) -> str:
    saturday = monday + timedelta(days=5)
    span = (f"{monday.day}–{_human_date(saturday)}" if monday.month == saturday.month
            else f"{_human_date(monday)} – {_human_date(saturday)}")
    days = [format_day(parse_events_for_date(raw, monday + timedelta(days=i)), monday + timedelta(days=i), compact=True)
            for i in range(6)]
    return f"📆 <b>{label}</b> · {span}\n\n" + "\n\n".join(days)


async def get_week_schedule(group_id: int | None = None) -> str:
    try:
        raw   = await _raw(group_id)
        today = datetime.now(TZ).date()
        monday = today - timedelta(days=today.weekday())

        return _format_week(raw, monday, "Эта неделя")
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def raw_for_user(user_id: int, force: bool = False) -> bytes:
    """Календарь группы человека (его группа или своя, если ещё не выбрал)."""
    from database import get_user_group
    return await _raw(await get_user_group(user_id), force)


async def get_next_week_schedule(group_id: int | None = None) -> str:
    try:
        raw   = await _raw(group_id)
        today = datetime.now(TZ).date()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)

        return _format_week(raw, next_monday, "Следующая неделя")
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


def _pair_num(e: dict, pos: int) -> int:
    """Номер пары по звонку (PAIR_SLOTS), а не по месту в списке дня: в день
    с «окном» с утра первая пара — третья. Нестандартное время — по месту."""
    return PAIR_SLOTS.get((e.get("time") or "").split("–")[0], pos)


async def get_next_lesson(group_id: int | None = None) -> str:
    try:
        raw  = await _raw(group_id)
        now  = datetime.now(TZ)
        today = now.date()
        events = parse_events_for_date(raw, today)

        for e in events:
            if e["time_start"] and e["time_start"] > now:
                delta = e["time_start"] - now
                mins  = int(delta.total_seconds() // 60)
                hrs   = mins // 60
                mins  = mins % 60
                time_left = f"{hrs} ч {mins} мин" if hrs else f"{mins} мин"
                num = _keycap(_pair_num(e, events.index(e) + 1))
                return (
                    f"⏭ <b>Следующая пара — через {time_left}</b>\n\n"
                    + format_lesson(e, num)
                )

        tomorrow = today + timedelta(days=1)
        t_events = parse_events_for_date(raw, tomorrow)
        if t_events:
            e = t_events[0]
            return (
                "✅ На сегодня пары закончились!\n\n"
                "<b>Завтра первая пара:</b>\n"
                + format_lesson(e, _keycap(_pair_num(e, 1)))
            )
        return "✅ Пар больше нет ни сегодня, ни завтра!"
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "⚠️ Не удалось получить расписание."


async def get_first_lesson_today(group_id: int | None = None) -> dict | None:
    try:
        raw    = await _raw(group_id)
        today  = datetime.now(TZ).date()
        events = parse_events_for_date(raw, today)
        for e in events:
            if e["time_start"]:
                return e
        return None
    except Exception:
        return None
