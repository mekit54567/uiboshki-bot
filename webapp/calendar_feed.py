"""
Генерация персонального ICS-фида (подписка на календарь) — Фаза 12.

Идея: не RRULE-повторение "пара каждую неделю", а конкретное VEVENT на
каждое реальное занятие (list_upcoming_events уже разворачивает recurring
ical в плоский список конкретных дат) — потому что ДЗ и заметки различаются
от пары к паре, а RRULE-событие в календарных приложениях одно на все
повторения и не может нести разное DESCRIPTION для разных дат.

Ссылка привязана к user_id через непредсказуемый токен (database.py:
get_or_create_calendar_token/get_user_by_calendar_token) — сам .ics-эндпоинт
не требует initData, потому что календарные приложения не умеют слать
кастомные заголовки при периодическом автообновлении подписки.
"""

import hashlib
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from config import TIMEZONE, GROUP_NAME
from database import get_lesson_notes
from handlers.announce import get_hw_for_date
from schedule_parser import fetch_schedule_raw, list_upcoming_events

TZ = ZoneInfo(TIMEZONE)

# Горизонт фида вперёд. list_upcoming_events всегда считает от today() и
# прошлых дат не отдаёт (это ОК — прошедшая пара в подписке никому не нужна).
DAYS_AHEAD = 45


def _matches_subject(item_subject: str | None, lesson_summary: str) -> bool:
    """ДЗ/заметка без привязки к предмету (NULL/пусто) считается общей — цепляем
    её ко всем парам этого дня. Иначе — по вхождению подстроки, без учёта
    регистра. ВАЖНО: это буквальная подстрока, не фонетическое/морфологическое
    сравнение — студенческое сокращение вроде "Матан" НЕ считается подстрокой
    "Математический анализ" (расходится с 5-й буквы). Чтобы ДЗ гарантированно
    попало в нужную пару календаря, /addhw стоит вводить предмет словом,
    которое реально встречается в названии пары из расписания (например
    "анализ" или полное "Математический анализ"), см. подсказку в самом /addhw."""
    if not item_subject:
        return True
    s = item_subject.strip().lower()
    return s in lesson_summary.lower() or lesson_summary.lower() in s


def _event_uid(token: str, ev: dict) -> str:
    raw = f"{token}:{ev['date'].isoformat()}:{ev['summary']}:{ev['time_start'].isoformat()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"{digest}@uiboshkibot"


async def build_ics_for_user(token: str) -> bytes:
    raw = await fetch_schedule_raw()
    events = list_upcoming_events(raw, days_ahead=DAYS_AHEAD)

    cal = Calendar()
    cal.add("prodid", "-//uiboshkibot//calendar//ru")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"{GROUP_NAME} — расписание")
    cal.add("method", "PUBLISH")

    hw_cache: dict[str, list[dict]] = {}
    notes_cache: dict[str, list[dict]] = {}

    for ev in events:
        if not ev.get("time_start"):
            continue  # без времени начала (весь день?) — редкость, пропускаем, не строим кривое событие
        date_str = ev["date"].isoformat()

        if date_str not in hw_cache:
            hw_cache[date_str] = await get_hw_for_date(date_str)
        if date_str not in notes_cache:
            notes_cache[date_str] = await get_lesson_notes(date_str)

        desc_lines = []
        if ev.get("teacher"):
            desc_lines.append(f"Преподаватель: {ev['teacher']}")

        matched_hw = [h for h in hw_cache[date_str] if _matches_subject(h.get("subject"), ev["summary"])]
        for h in matched_hw:
            if h.get("content"):
                desc_lines.append(f"ДЗ: {h['content']}")
            elif h.get("file_id"):
                desc_lines.append("ДЗ: см. файл в боте (/hw)")

        matched_notes = [n for n in notes_cache[date_str] if _matches_subject(n.get("subject"), ev["summary"])]
        for n in matched_notes:
            desc_lines.append(f"Заметка: {n['text']}")

        event = Event()
        event.add("uid", _event_uid(token, ev))
        event.add("summary", ev["summary"])
        event.add("dtstart", ev["time_start"])
        event.add("dtend", ev.get("time_end") or (ev["time_start"] + timedelta(hours=1, minutes=30)))
        event.add("dtstamp", datetime.now(TZ))
        if ev.get("location"):
            event.add("location", ev["location"])
        if desc_lines:
            event.add("description", "\n".join(desc_lines))
        cal.add_component(event)

    return cal.to_ical()
