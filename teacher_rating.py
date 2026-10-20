"""Оценка преподавателя в капибарах (Никита 19.10): от 1 до 5, только цифра —
без отзывов и комментариев (правило Apple 1.2: о живых людях — ничего, что можно
написать, а значит, и нечего модерировать). Оценка — одна на человека, её
можно поменять или убрать.

- Ставить — только тем, у кого этот преподаватель есть в расписании своей
  группы (семестр календаря группы): чужих не оценивают.
- Видно всем, но среднее — когда оценок не меньше SHOW_MIN: по одной-двум
  легко понять, кто поставил.
- Преподаватель — по короткому имени «Фамилия И. О.», как в расписании.
"""

import re

from database._conn import connect

SHOW_MIN = 3
SCORES = range(1, 6)


def key(name: str) -> str:
    """«Сиганьков Алексей Андреевич» и «Сиганьков А. А.» → «сиганьков а.а.»."""
    from schedule_format import _short_teacher
    name = " ".join((name or "").split())
    if name and not re.search(r"\b\w\.", name):
        name = _short_teacher(name)
    return re.sub(r"\.\s+", ".", name.lower().replace("ё", "е")).strip()


def teachers_in(raw: bytes) -> set[str]:
    """Ключи преподавателей из календаря группы."""
    from icalendar import Calendar
    from schedule_events import _extract_teacher
    try:
        cal = Calendar.from_ical(raw)
    except Exception:
        return set()
    return {key(t) for e in cal.walk("VEVENT") if (t := _extract_teacher(e))}


async def can_rate(user_id: int, name: str) -> bool:
    import schedule_parser
    try:
        raw = await schedule_parser.raw_for_user(user_id)
    except Exception:
        return False
    return key(name) in teachers_in(raw)


async def summary(name: str, user_id: int) -> dict:
    k = key(name)
    async with connect() as db:
        n, total = await (await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(score), 0) FROM teacher_ratings WHERE teacher = ?", (k,))).fetchone()
        mine = await (await db.execute(
            "SELECT score FROM teacher_ratings WHERE teacher = ? AND user_id = ?", (k, user_id))).fetchone()
    shown = n >= SHOW_MIN
    return {"count": n, "avg": round(total / n, 1) if shown else None, "mine": mine[0] if mine else None,
            "show_min": SHOW_MIN}


async def put(name: str, user_id: int, score: int | None):
    k = key(name)
    async with connect() as db:
        if score is None:
            await db.execute("DELETE FROM teacher_ratings WHERE teacher = ? AND user_id = ?", (k, user_id))
        else:
            await db.execute(
                "INSERT INTO teacher_ratings (teacher, user_id, score) VALUES (?, ?, ?) "
                "ON CONFLICT(teacher, user_id) DO UPDATE SET score = excluded.score, updated_at = datetime('now')",
                (k, user_id, score))
        await db.commit()
