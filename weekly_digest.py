"""
Обзор недели — в воскресенье вечером (тумблер «Обзор недели» в
уведомлениях, notify_prefs: weekly). Одним сообщением: номер недели, пары по
дням (во сколько первая, где — если не в своём корпусе), свободные дни и
дедлайны на неделе. Пар и дедлайнов нет — не шлём. Предметы по выбору — как
у человека (optional_subjects).
"""

import logging
from datetime import date, datetime, timedelta

from utils import TZ, esc

logger = logging.getLogger(__name__)
DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MAX_DEADLINES = 6


def next_monday(today: date) -> date:
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


async def week_grades(user_id: int) -> list[tuple[str, float]]:
    """Прирост баллов за неделю по предметам — у кого подключён свой вход в
    СДО: [(«Анализ данных», 5.0), …], по убыванию, только рост. Сбой СДО —
    пусто (обзор недели уходит и без этой строки)."""
    import sdo_grades
    import sdo_history
    from sdo_accounts import cookie_for
    cookie = await cookie_for(user_id)
    if not cookie:
        return []
    try:
        courses = (await sdo_grades.overview(user_id, cookie)).get("courses") or []
    except Exception as e:
        logger.info(f"обзор недели {user_id}: баллы не загрузились: {type(e).__name__}")
        return []
    out = []
    for c in courses:
        if c.get("id") is None or c.get("score") is None:
            continue
        delta = (await sdo_history.series(user_id, c["id"], c["score"]))["week_delta"]
        if delta and delta > 0:
            out.append((c.get("title") or c.get("name") or "", delta))
    return sorted(out, key=lambda x: -x[1])


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _week(raw: bytes, monday: date, deadlines: list[dict], home: str | None):
    """Разбор недели: (дни [(день, пар, начало, чужие корпуса)], всего, свободные, сроки недели)."""
    import notify_prefs
    from schedule_parser import lessons_for_date
    days, total, free = [], 0, []
    for i in range(6):
        d = monday + timedelta(days=i)
        lessons = lessons_for_date(raw, d)
        pairs = sum(l["pairs"] for l in lessons)
        if not pairs:
            free.append(DAYS[i])
            continue
        total += pairs
        campuses = sorted({c for c in (notify_prefs.campus_of(l["room"]) for l in lessons) if c and c != home})
        days.append((DAYS[i], pairs, lessons[0]["start"], campuses))
    week_dl = sorted([d for d in deadlines if not d.get("done")
                      and monday.isoformat() <= d["due_date"] <= (monday + timedelta(days=6)).isoformat()],
                     key=lambda x: (x["due_date"], x.get("due_time") or "99"))
    return days, total, free, week_dl


def headline(raw: bytes, monday: date, deadlines: list[dict], home: str | None,
             grades: list[tuple[str, float]] | None = None) -> tuple[str, str] | None:
    """Пуш (Никита 25.10: разбивка по дням в пуше — «смысла ноль»):
    заголовок «Неделя 9: 21 пара, свободен вт», текст — что сдать, куда
    ехать не в свой корпус, самый плотный день, рост баллов. None — пусто."""
    from push_text import split_subject, word
    from schedule_parser import week_number
    days, total, free, week_dl = _week(raw, monday, deadlines, home)
    if not total and not week_dl:
        return None
    num = week_number(raw, monday)
    title = f"Неделя {num}" if num else "Неделя"
    if total:
        title += f": {total} {word(total, 'пара', 'пары', 'пар')}"
        low = [f.lower() for f in free]
        if len(low) == 1:
            title += f", свободен {low[0]}"
        elif 1 < len(low) <= 3:
            title += f", свободны {', '.join(low)}"
        elif low:
            title += f", {len(low)} {word(len(low), 'день', 'дня', 'дней')} без пар"
    else:
        title += ": пар нет"
    parts = []
    if week_dl:
        first = week_dl[0]
        due = DAYS[date.fromisoformat(first["due_date"]).weekday()].lower()
        due += f" {first['due_time']}" if first.get("due_time") else ""
        name = split_subject(first["subject"])[0]
        n = len(week_dl)
        parts.append(f"Сдать: {name}, {due}" if n == 1
                     else f"Сдать {n} {word(n, 'работу', 'работы', 'работ')}, первая — {name}, {due}")
    away = [(day.lower(), c) for day, _, _, cs in days for c in cs]
    if away:
        parts.append("Не в своём корпусе: " + ", ".join(f"{d} — {c}" for d, c in away))
    if days:
        day, pairs, start, _ = max(days, key=lambda x: x[1])
        if pairs >= 4 and len({p for _, p, _, _ in days}) > 1:
            parts.append(f"Самый плотный — {day.lower()}, {pairs} {word(pairs, 'пара', 'пары', 'пар')}")
    if grades:
        parts.append("Баллы: " + ", ".join(f"{n} +{_num(d)}" for n, d in grades[:2]))
    return title, " · ".join(parts) or "Сроков на неделе нет"


def build(raw: bytes, monday: date, deadlines: list[dict], home: str | None,
          grades: list[tuple[str, float]] | None = None) -> str | None:
    """Сообщение в Telegram; None — неделя пустая. Первой строкой — то же,
    что в заголовке пуша, дальше сроки (что делать), потом дни.
    grades — прирост баллов за прошедшую неделю (week_grades)."""
    from schedule_parser import MONTHS_GEN
    head = headline(raw, monday, deadlines, home, grades)
    if not head:
        return None
    days, total, free, week_dl = _week(raw, monday, deadlines, home)
    sunday = monday + timedelta(days=6)
    span = (f"{monday.day}–{sunday.day} {MONTHS_GEN[sunday.month - 1]}" if monday.month == sunday.month
            else f"{monday.day} {MONTHS_GEN[monday.month - 1]} – {sunday.day} {MONTHS_GEN[sunday.month - 1]}")
    out = [f"🗓 <b>{esc(head[0])}</b> · {span}"]
    if week_dl:
        out.append("\n⏳ <b>Сдать на неделе</b>")
        for d in week_dl[:MAX_DEADLINES]:
            day = DAYS[date.fromisoformat(d["due_date"]).weekday()]
            out.append(f"• {esc(d['subject'])} — {day}{' ' + d['due_time'] if d.get('due_time') else ''}")
        if len(week_dl) > MAX_DEADLINES:
            out.append(f"…и ещё {len(week_dl) - MAX_DEADLINES}")
    if total:
        out.append("")
        for day, pairs, start, campuses in days:
            word = "пара" if pairs == 1 else ("пары" if pairs < 5 else "пар")
            where = f" · 📍 {', '.join(campuses)}" if campuses else ""
            out.append(f"<b>{day}</b> — {pairs} {word}, с {start}{where}")
    else:
        out.append("Пар на неделе нет 🎉")
    if grades:
        out.append("\n📈 <b>Баллы за неделю</b>: " + " · ".join(f"{esc(n)} +{_num(d)}" for n, d in grades[:4]))
    return "\n".join(out)


async def send_all(bot, now: datetime | None = None):
    """Воскресенье вечером: обзор следующей недели каждому, у кого включено."""
    import notify_prefs
    from config import OPTIONAL_SUBJECTS
    from database import get_active_deadlines, get_all_optional_answers, get_reminder_users
    from keyboards import app_button
    from optional_subjects import HIDE
    from scheduler import _group_raws, pace
    now = now or datetime.now(TZ)
    monday = next_monday(now.date())
    import schedule_parser
    # у каждого — неделя его группы (этап 1 (г)); своя — schedule_parser.fetch_schedule_raw
    raw_of = await _group_raws(lambda: schedule_parser.fetch_schedule_raw())
    answers = await get_all_optional_answers()
    for user in await get_reminder_users():
        uid = user["user_id"]
        prefs = notify_prefs.merge(user.get("notify"))
        if not prefs.get("weekly"):
            continue
        raw, home = await raw_of(user.get("group_id"))
        if raw is None:
            continue
        hidden = frozenset(s for s in OPTIONAL_SUBJECTS if not answers.get(uid, {}).get(s))
        token = HIDE.set(hidden)
        try:
            deadlines = await get_active_deadlines(uid)
            grades = []
            text = build(raw, monday, deadlines, home)
            # баллы — только если обзор вообще уйдёт (это запросы в СДО), и без
            # предметов по выбору, куда человек не ходит
            if text and prefs.get("grades"):
                grades = [(n, d) for n, d in await week_grades(uid)
                          if not any(s.lower() in n.lower() for s in hidden)]
                if grades:
                    text = build(raw, monday, deadlines, home, grades)
            head = headline(raw, monday, deadlines, home, grades) if text else None
        finally:
            HIDE.reset(token)
        if not text:
            continue
        try:
            import delivery
            title, body = head
            await delivery.deliver(bot, uid, text, kind="weekly", tab="today", title=title, body=body,
                                   reply_markup=app_button("📅 Открыть неделю", "today"))
            await pace()
        except Exception as e:
            logger.info(f"обзор недели {uid}: {e}")
