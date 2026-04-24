import httpx
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events

from config import ICAL_URL, TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

DAY_NAMES = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]


async def fetch_schedule_raw() -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(ICAL_URL)
        resp.raise_for_status()
        return resp.content


def parse_events_for_date(ical_data: bytes, target: date) -> list[dict]:
    cal = Calendar.from_ical(ical_data)
    events_raw = recurring_ical_events.of(cal).at(target)
    events = []

    for component in events_raw:
        summary = str(component.get("SUMMARY", "Без названия"))
        if summary.strip().endswith("неделя"):
            continue

        location = str(component.get("LOCATION", ""))
        dtstart  = component.get("DTSTART")
        dtend    = component.get("DTEND")

        time_str = ""
        time_start = None
        if dtstart:
            t = dtstart.dt
            if isinstance(t, datetime):
                if t.tzinfo is None:
                    t = t.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                t_msk = t.astimezone(TZ)
                time_start = t_msk
                time_str = t_msk.strftime("%H:%M")
                if dtend:
                    te = dtend.dt
                    if isinstance(te, datetime):
                        if te.tzinfo is None:
                            te = te.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                        time_str += "–" + te.astimezone(TZ).strftime("%H:%M")

        events.append({
            "summary":    summary,
            "time":       time_str,
            "time_start": time_start,
            "location":   location,
        })

    events.sort(key=lambda e: e["time"] or "99:99")
    return events


def format_day(events: list[dict], target: date, show_date=True) -> str:
    weekday  = DAY_NAMES[target.weekday()]
    date_fmt = target.strftime("%d.%m.%Y")

    header = f"📅 <b>{weekday}</b>"
    if show_date:
        header += f", {date_fmt}"

    if not events:
        return f"{header}\n🎉 Пар нет!"

    lines = [header, ""]
    for i, e in enumerate(events, 1):
        lines.append(
            f"┌ <b>Пара {i}</b>  ⏰ {e['time']}\n"
            f"│ 📖 {e['summary']}\n"
            f"└ 📍 {e['location'] or '—'}"
        )
    return "\n\n".join(lines)


async def get_today_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        return format_day(parse_events_for_date(raw, today), today)
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_tomorrow_schedule() -> str:
    try:
        raw      = await fetch_schedule_raw()
        tomorrow = datetime.now(TZ).date() + timedelta(days=1)
        return format_day(parse_events_for_date(raw, tomorrow), tomorrow)
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_week_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        monday = today - timedelta(days=today.weekday())

        lines = ["📆 <b>Расписание на эту неделю</b>\n"]
        for i in range(6):
            day    = monday + timedelta(days=i)
            events = parse_events_for_date(raw, day)
            lines.append(format_day(events, day))
            lines.append("─────────────────")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_next_week_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)

        lines = ["📆 <b>Расписание на следующую неделю</b>\n"]
        for i in range(6):
            day    = next_monday + timedelta(days=i)
            events = parse_events_for_date(raw, day)
            lines.append(format_day(events, day))
            lines.append("─────────────────")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_next_lesson() -> str:
    try:
        raw  = await fetch_schedule_raw()
        now  = datetime.now(TZ)
        today = now.date()
        events = parse_events_for_date(raw, today)

        for e in events:
            if e["time_start"] and e["time_start"] > now:
                delta = e["time_start"] - now
                mins  = int(delta.total_seconds() // 60)
                hrs   = mins // 60
                mins  = mins % 60
                time_left = f"{hrs}ч {mins}мин" if hrs else f"{mins} мин"
                return (
                    f"⏭ <b>Следующая пара</b>\n\n"
                    f"┌ ⏰ {e['time']}\n"
                    f"│ 📖 {e['summary']}\n"
                    f"└ 📍 {e['location'] or '—'}\n\n"
                    f"⏳ Через {time_left}"
                )

        tomorrow = today + timedelta(days=1)
        t_events = parse_events_for_date(raw, tomorrow)
        if t_events:
            e = t_events[0]
            return (
                f"✅ На сегодня пары закончились!\n\n"
                f"<b>Завтра первая пара:</b>\n"
                f"┌ ⏰ {e['time']}\n"
                f"│ 📖 {e['summary']}\n"
                f"└ 📍 {e['location'] or '—'}"
            )
        return "✅ Пар больше нет ни сегодня, ни завтра!"
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "⚠️ Не удалось получить расписание."


async def get_first_lesson_today() -> dict | None:
    try:
        raw    = await fetch_schedule_raw()
        today  = datetime.now(TZ).date()
        events = parse_events_for_date(raw, today)
        for e in events:
            if e["time_start"]:
                return e
        return None
    except Exception:
        return None
