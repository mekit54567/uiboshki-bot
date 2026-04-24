import httpx
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar
from icalendar.prop import vDDDLists
from dateutil.rrule import rruleset, rrulestr
import recurring_ical_events

from config import ICAL_URL, TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


async def fetch_schedule_raw() -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(ICAL_URL)
        resp.raise_for_status()
        return resp.content


def parse_events_for_date(ical_data: bytes, target: date) -> list[dict]:
    cal = Calendar.from_ical(ical_data)

    # recurring_ical_events разворачивает RRULE/RDATE автоматически
    events_raw = recurring_ical_events.of(cal).at(target)

    events = []
    for component in events_raw:
        summary = str(component.get("SUMMARY", "Без названия"))

        # Пропускаем служебные события типа "1 неделя", "2 неделя"
        if summary.strip().endswith("неделя"):
            continue

        location = str(component.get("LOCATION", ""))
        desc     = str(component.get("DESCRIPTION", ""))

        dtstart = component.get("DTSTART")
        dtend   = component.get("DTEND")

        time_str = ""
        if dtstart:
            t = dtstart.dt
            if isinstance(t, datetime):
                # Приводим к московскому времени
                if t.tzinfo is None:
                    t = t.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                t_msk = t.astimezone(TZ)
                time_str = t_msk.strftime("%H:%M")
                if dtend:
                    te = dtend.dt
                    if isinstance(te, datetime):
                        if te.tzinfo is None:
                            te = te.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                        time_str += "–" + te.astimezone(TZ).strftime("%H:%M")

        events.append({
            "summary":  summary,
            "time":     time_str,
            "location": location,
            "desc":     desc,
        })

    # Сортируем по времени
    events.sort(key=lambda e: e["time"] or "99:99")
    return events


def format_schedule(events: list[dict], target: date) -> str:
    day_names = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    weekday  = day_names[target.weekday()]
    date_fmt = target.strftime("%d.%m.%Y")

    if not events:
        return (
            f"📅 <b>{weekday}, {date_fmt}</b>\n\n"
            "🎉 Пар нет! Можно отдыхать."
        )

    lines = [f"📅 <b>{weekday}, {date_fmt}</b>\n"]
    for i, e in enumerate(events, 1):
        time_part = f"⏰ {e['time']}  " if e["time"] else ""
        loc_part  = f"📍 {e['location']}" if e["location"] else ""
        lines.append(f"{i}. {time_part}<b>{e['summary']}</b>")
        if loc_part:
            lines.append(f"   {loc_part}")
    return "\n".join(lines)


async def get_today_schedule() -> str:
    try:
        raw = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        events = parse_events_for_date(raw, today)
        return format_schedule(events, today)
    except Exception as e:
        logger.error(f"Ошибка при получении расписания: {e}")
        return "⚠️ Не удалось загрузить расписание. Попробуй позже."


async def get_next_week_schedule() -> str:
    """Расписание на следующую неделю."""
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        # Начало следующей недели
        days_until_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)

        lines = ["📆 <b>Расписание на следующую неделю</b>\n"]
        for i in range(6):  # Пн–Сб
            day    = next_monday + timedelta(days=i)
            events = parse_events_for_date(raw, day)
            lines.append(format_day(events, day))
            lines.append("─────────────────")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."
