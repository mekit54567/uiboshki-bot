import re
import time
import httpx
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events

from config import ICAL_URL, TIMEZONE, SCHEDULE_CACHE_TTL_SECONDS
from utils import esc

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

DAY_NAMES = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]

# ── Простой TTL-кэш сырого ical-фида ────────────────────────────────────────────
# Раньше fetch_schedule_raw() дёргался без кэша отовсюду: каждую минуту из
# check_lesson_reminders (scheduler.py), плюс из каждой команды /today, /tomorrow
# и т.д. — десятки одинаковых HTTP-запросов к стороннему серверу в минуту.
_cache_data: bytes | None = None
_cache_time: float = 0.0


async def fetch_schedule_raw(force: bool = False) -> bytes:
    global _cache_data, _cache_time
    now = time.monotonic()
    if not force and _cache_data is not None and (now - _cache_time) < SCHEDULE_CACHE_TTL_SECONDS:
        return _cache_data

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(ICAL_URL)
        resp.raise_for_status()
        _cache_data = resp.content
        _cache_time = now
        return _cache_data


TEACHER_RE = re.compile(r"Преподаватель:\s*([^\n\\]+)")


def _extract_teacher(component) -> str:
    """Имя преподавателя зашито в DESCRIPTION у пар типа ЛК/ПР
    ("Преподаватель: Фамилия Имя Отчество\n..."). У "СР"/доп. занятий
    его может не быть вовсе — тогда просто пустая строка."""
    desc = str(component.get("DESCRIPTION", ""))
    m = TEACHER_RE.search(desc)
    return m.group(1).strip() if m else ""


def parse_events_for_date(ical_data: bytes, target: date) -> list[dict]:
    cal = Calendar.from_ical(ical_data)
    events_raw = recurring_ical_events.of(cal).at(target)
    events = []

    for component in events_raw:
        summary = str(component.get("SUMMARY", "Без названия"))
        if summary.strip().endswith("неделя"):
            continue

        location = str(component.get("LOCATION", ""))
        teacher  = _extract_teacher(component)
        dtstart  = component.get("DTSTART")
        dtend    = component.get("DTEND")

        time_str = ""
        time_start = None
        time_end = None
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
                        te_msk = te.astimezone(TZ)
                        time_end = te_msk
                        time_str += "–" + te_msk.strftime("%H:%M")

        events.append({
            "summary":    summary,
            "time":       time_str,
            "time_start": time_start,
            "time_end":   time_end,
            "location":   location,
            "teacher":    teacher,
        })

    events.sort(key=lambda e: e["time"] or "99:99")
    return events


MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
_KEYCAPS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

# Тип занятия — первым словом в SUMMARY ical МИРЭА ("ЛК Матан", "ПР ...").
_KINDS = {
    "ЛК": ("лекция", "лк"), "ПР": ("практика", "пр"), "ЛАБ": ("лабораторная", "лаб"),
    "ЛР": ("лабораторная", "лаб"), "СР": ("сам. работа", "ср"), "ДОП": ("доп. занятие", "доп"),
    "ЭКЗ": ("экзамен", "экз"), "ЗАЧ": ("зачёт", "зач"), "КОНС": ("консультация", "конс"),
    "КП": ("курсовой проект", "кп"), "КР": ("курсовая работа", "кр"),
}


def _human_date(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def _keycap(n: int) -> str:
    return _KEYCAPS[n] if 0 <= n < len(_KEYCAPS) else f"{n}."


def _pairs_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} пара"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} пары"
    return f"{n} пар"


def _split_kind(summary: str) -> tuple[str, str, str]:
    """"ЛК Основы бизнес-анализа" -> ("Основы бизнес-анализа", "лекция", "лк")."""
    head, _, rest = summary.strip().partition(" ")
    kind = _KINDS.get(head.upper())
    if kind and rest.strip():
        return rest.strip(), kind[0], kind[1]
    return summary.strip(), "", ""


def _short_teacher(name: str) -> str:
    """"Иванов Иван Иванович" -> "Иванов И. И."."""
    parts = (name or "").split()
    if len(parts) < 2:
        return name or ""
    return parts[0] + " " + " ".join(p[0] + "." for p in parts[1:3] if p)


def _merge_runs(events: list[dict]) -> list[dict]:
    """Подряд идущие одинаковые пары (5 пар практики, 4 пары военки) —
    одним блоком «1️⃣–4️⃣ 09:00–15:50», а не четырьмя копиями подряд."""
    runs: list[dict] = []
    for i, e in enumerate(events, 1):
        prev = runs[-1] if runs else None
        if prev and prev["summary"] == e["summary"] and prev["location"] == e["location"]:
            prev["last"] = i
            prev["time_end"] = e.get("time_end")
            prev["end_str"] = (e.get("time") or "").split("–")[-1]
            continue
        runs.append({**e, "first": i, "last": i,
                     "start_str": (e.get("time") or "").split("–")[0],
                     "end_str": (e.get("time") or "").split("–")[-1]})
    return runs


def _run_time(r: dict) -> str:
    if not r["start_str"]:
        return ""
    return r["start_str"] if r["start_str"] == r["end_str"] else f"{r['start_str']}–{r['end_str']}"


def _run_num(r: dict) -> str:
    return _keycap(r["first"]) if r["first"] == r["last"] else f"{_keycap(r['first'])}–{_keycap(r['last'])}"


def format_lesson(e: dict, num: str = "", now: datetime | None = None) -> str:
    """Одна пара (или блок подряд идущих) — три строки: время и аудитория,
    название, тип и преподаватель. Без рамок ┌│└: в Telegram шрифт не
    моноширинный, и они съезжали."""
    r = e if "start_str" in e else {**e, "start_str": (e.get("time") or "").split("–")[0],
                                     "end_str": (e.get("time") or "").split("–")[-1]}
    title, kind, _ = _split_kind(e["summary"])
    time_str = _run_time(r)
    status, past = "", False
    if now and e.get("time_start"):
        end = r.get("time_end") or e["time_start"]
        if e["time_start"] <= now < end:
            status = " · 🟢 <b>сейчас</b>"
        elif end <= now:
            past = True
    if time_str:
        time_str = f"<s>{time_str}</s>" if past else f"<b>{time_str}</b>"
    head = " ".join(x for x in (num, time_str) if x)
    loc = esc(e.get("location") or "")
    line1 = head + (f"  📍 {loc}" if loc else "") + status
    extra = [kind] if kind else []
    if e.get("teacher"):
        extra.append(esc(_short_teacher(e["teacher"])))
    if "first" in r and r["last"] > r["first"]:
        extra.append(f"{_pairs_word(r['last'] - r['first'] + 1)} подряд")
    lines = [line1, esc(title)]
    if extra:
        lines.append(f"<i>{' · '.join(extra)}</i>")
    return "\n".join(lines)


def format_day(events: list[dict], target: date, show_date=True,
               now: datetime | None = None, compact: bool = False) -> str:
    weekday = DAY_NAMES[target.weekday()]
    title = f"{weekday}, {_human_date(target)}" if show_date else weekday

    if compact:
        if not events:
            return f"<b>{title}</b> — пар нет 🎉"
        lines = [f"<b>{title}</b>"]
        for r in _merge_runs(events):
            name, _, short = _split_kind(r["summary"])
            name = esc(name) + (f" ({short})" if short else "")
            loc = f" · {esc(r['location'])}" if r.get("location") else ""
            lines.append(f"{_run_num(r)} {_run_time(r)} · {name}{loc}")
        return "\n".join(lines)

    if not events:
        return f"📅 <b>{title}</b>\n🎉 Пар нет!"
    runs = _merge_runs(events)
    first = runs[0]["start_str"]
    last = runs[-1]["end_str"]
    span = f" · {first}–{last}" if first and last else ""
    blocks = [f"📅 <b>{title}</b>\n{_pairs_word(len(events))}{span}"]
    blocks += [format_lesson(r, _run_num(r), now) for r in runs]
    return "\n\n".join(blocks)


async def get_today_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        now   = datetime.now(TZ)
        return format_day(parse_events_for_date(raw, now.date()), now.date(), now=now)
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


def _format_week(raw: bytes, monday: date, label: str) -> str:
    saturday = monday + timedelta(days=5)
    span = (f"{monday.day}–{_human_date(saturday)}" if monday.month == saturday.month
            else f"{_human_date(monday)} – {_human_date(saturday)}")
    days = [format_day(parse_events_for_date(raw, monday + timedelta(days=i)), monday + timedelta(days=i), compact=True)
            for i in range(6)]
    return f"📆 <b>{label}</b> · {span}\n\n" + "\n\n".join(days)


async def get_week_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        monday = today - timedelta(days=today.weekday())

        return _format_week(raw, monday, "Эта неделя")
    except Exception as e:
        logger.error(f"Ошибка расписания: {e}")
        return "⚠️ Не удалось загрузить расписание."


async def get_next_week_schedule() -> str:
    try:
        raw   = await fetch_schedule_raw()
        today = datetime.now(TZ).date()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)

        return _format_week(raw, next_monday, "Следующая неделя")
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
                time_left = f"{hrs} ч {mins} мин" if hrs else f"{mins} мин"
                num = _keycap(events.index(e) + 1)
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
                + format_lesson(e, _keycap(1))
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


def list_upcoming_events(raw: bytes, days_ahead: int = 14) -> list[dict]:
    """Плоский список всех пар на ближайшие days_ahead дней из произвольного
    ical (не обязательно своей группы — годится и для чужого препода/
    аудитории, полученных через mirea_schedule_api.fetch_ical)."""
    today = datetime.now(TZ).date()
    results = []
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        for e in parse_events_for_date(raw, d):
            results.append({**e, "date": d})
    return results

# ── Форматирование результатов поиска (преподаватель/аудитория) ────────────
# Раньше здесь же жили search_by_teacher/search_by_room, искавшие только
# в рамках расписания своей группы — заменены на mirea_schedule_api.py
# (нашёлся настоящий публичный поиск по всему университету). Форматирование
# результатов осталось общим — им пользуется handlers/schedule.py.

def format_search_results(results: list[dict], empty_text: str) -> str:
    if not results:
        return empty_text
    lines = []
    last_date = None
    for e in results[:15]:
        if e["date"] != last_date:
            lines.append(f"\n📅 <b>{DAY_NAMES[e['date'].weekday()]}, {e['date'].strftime('%d.%m')}</b>")
            last_date = e["date"]
        teacher_part = f" · {esc(e['teacher'])}" if e.get("teacher") else ""
        lines.append(f"⏰ {e['time']} — {esc(e['summary'])}{teacher_part}\n📍 {esc(e['location']) or '—'}")
    if len(results) > 15:
        lines.append(f"\n… и ещё {len(results) - 15}")
    return "\n".join(lines).strip()
