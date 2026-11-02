"""
Вечерняя сводка на завтра (второй круг дизайна, Никита 12.10: варианты Б, В, Г).
Тумблер «Вечерняя сводка» и время в уведомлениях (notify_prefs: evening,
evening_time; по умолчанию выключено, 20:00). Одним коротким сообщением:

    🌙 Завтра: 3 пары с 09:00, В-78
    +2…+6°, дождь. Сдать: Лаба 3 до 23:59.
    Первая — Анализ данных, лекция · А-1 (В-78)

Пар нет, но есть сроки в ближайшие дни — «Завтра пар нет», «Сдать до пн:
Практика 2. Отдыхай.»; нет ни пар, ни сроков — не шлём. Погода и корпус — по
тем же тумблерам, что у утренней рассылки. При DESIGN2=0 — ничего не шлём.
"""

import logging
from datetime import date, datetime, timedelta

from utils import TZ, esc

logger = logging.getLogger(__name__)
DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MAX_DEADLINES = 3
DEADLINE_DAYS = 3          # сроки: завтра и ещё два дня (в пятницу вечером — до понедельника)


def _word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "пара"
    return "пары" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "пар"


def _deadlines_text(deadlines: list[dict], tomorrow: date) -> str:
    """«Сдать: Лаба 3 до 23:59, Практика 2 до пн.» / «Сдать до пн: Практика 2.»"""
    items = sorted(deadlines, key=lambda d: (d["due_date"], d.get("due_time") or "99"))
    if not items:
        return ""

    def name(d):        # «Практика 2 · Анализ данных (Экз)» → «Практика 2»: сводка короткая
        return esc((d.get("subject") or "").split(" · ")[0].strip() or d.get("subject") or "")

    def day(d):
        return DAYS[date.fromisoformat(d["due_date"]).weekday()]

    shown, more = items[:MAX_DEADLINES], len(items) - MAX_DEADLINES
    tail = f" и ещё {more}" if more > 0 else ""
    dates = {d["due_date"] for d in items}
    if len(dates) == 1 and tomorrow.isoformat() not in dates:
        return f"Сдать до {day(items[0])}: {', '.join(name(d) for d in shown)}{tail}."
    parts = []
    for d in shown:
        if d["due_date"] == tomorrow.isoformat():
            when = f"до {d['due_time']}" if d.get("due_time") else "завтра"
        else:
            when = f"до {day(d)}"
        parts.append(f"{name(d)} {when}")
    return f"Сдать: {', '.join(parts)}{tail}."


def day_title(lessons: list[dict], day: str, home: str | None, campus: bool = True) -> str:
    """«Завтра: 3 пары с 09:00, В-78» / «Сегодня: 5 пар с 09:00, МП-1 (не В-78)».
    lessons — lessons_for_date, отсортированы по началу."""
    import notify_prefs
    pairs = sum(l.get("pairs") or 1 for l in lessons)
    title = f"{day}: {pairs} {_word(pairs)} с {lessons[0]['start']}"
    if campus:
        found = list(dict.fromkeys(c for c in (notify_prefs.campus_of(l.get("room")) for l in lessons) if c))
        if found:
            title += ", " + ", ".join(found) + (f" (не {home})" if home and home not in found else "")
    return title


def first_pair(lessons: list[dict]) -> str:
    """«Первая — Анализ данных, лекция · А-1 (В-78)» (без HTML-экранирования)."""
    first = lessons[0]
    pair = f"Первая — {first.get('title') or ''}"
    if first.get("kind"):
        pair += f", {first['kind']}"
    if first.get("room"):
        pair += f" · {first['room']}"
    return pair


def build(raw: bytes, tomorrow: date, deadlines: list[dict], home: str | None, weather: str = "",
          campus: bool = True) -> tuple[str, str] | None:
    """(заголовок для пуша, HTML для Telegram) или None — завтра пусто.
    deadlines — не сданные сроки с завтрашнего дня на DEADLINE_DAYS дней."""
    from schedule_parser import lessons_for_date
    lessons = [l for l in lessons_for_date(raw, tomorrow) if l.get("start") and l.get("kind") != "сам. работа"]
    dl = _deadlines_text(deadlines, tomorrow)
    if not lessons and not dl:
        return None
    if not lessons:
        title = "Завтра пар нет"
        return title, f"🌙 <b>{title}</b>\n{dl} Отдыхай."
    lessons.sort(key=lambda l: l["start"])
    title = day_title(lessons, "Завтра", home, campus)
    line = " ".join(x for x in ((weather + ".") if weather else "", dl) if x)
    pair = esc(first_pair(lessons))
    return title, "\n".join(x for x in (f"🌙 <b>{esc(title)}</b>", line, pair) if x)


def slot(now: datetime) -> str:
    """Какое время сводки сейчас: задача раз в 30 минут → «20:00» / «20:30»."""
    return f"{now.hour:02d}:{'00' if now.minute < 30 else '30'}"


async def send_all(bot, now: datetime | None = None):
    """Раз в 30 минут: сводка на завтра тем, у кого включена и выбрано это время."""
    import config
    if not config.design2_on():
        return                                    # DESIGN2=0 — откат нового дизайна целиком
    import delivery
    import notify_prefs
    import schedule_parser
    from database import get_all_optional_answers, get_deadlines_soon, get_reminder_users
    from keyboards import app_button
    from optional_subjects import HIDE
    from scheduler import _group_raws, pace
    now = now or datetime.now(TZ)
    at = slot(now)
    users = []
    for user in await get_reminder_users():
        prefs = notify_prefs.merge(user.get("notify"))
        if prefs.get("evening") and prefs.get("evening_time") == at:
            users.append((user, prefs))
    if not users:
        return                                    # в это время никому — календари не качаем
    tomorrow = now.date() + timedelta(days=1)
    raw_of = await _group_raws(lambda: schedule_parser.fetch_schedule_raw())
    answers = await get_all_optional_answers()
    weather = None                                # погоду берём один раз и только если кому-то нужна
    from config import OPTIONAL_SUBJECTS
    for user, prefs in users:
        uid = user["user_id"]
        try:
            raw, home = await raw_of(user.get("group_id"))
            if raw is None:
                continue                          # не знаем, есть ли пары, — не пишем «пар нет»
            deadlines = [d for d in await get_deadlines_soon(days=DEADLINE_DAYS, viewer_id=uid)
                         if d["due_date"] >= tomorrow.isoformat()]
            if prefs.get("weather") and weather is None:
                try:
                    from handlers.weather import get_weather_for_tomorrow
                    weather = await get_weather_for_tomorrow() or ""
                except Exception as e:
                    logger.info(f"вечерняя сводка: погода не загрузилась: {e}")
                    weather = ""
            hidden = frozenset(s for s in OPTIONAL_SUBJECTS if not answers.get(uid, {}).get(s))
            token = HIDE.set(hidden)              # предметы по выбору — как у человека
            try:
                built = build(raw, tomorrow, deadlines, home, (weather or "") if prefs.get("weather") else "",
                              campus=prefs.get("campus", True))
            finally:
                HIDE.reset(token)
            if not built:
                continue
            title, text = built
            await delivery.deliver(bot, uid, text, kind="evening", tab="today", title=title,
                                   reply_markup=app_button("📅 Открыть расписание", "today"))
            await pace()
        except Exception as e:
            logger.info(f"вечерняя сводка {uid}: {e}")
