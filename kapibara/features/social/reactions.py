"""Реакции на пару (5.100, Никита 18.10): пять поз капибары под парой,
счёт виден группе, кто как отметил — нет. Пара — начало по Москве до минуты
и название без регистра: так одна и та же пара у всех в группе, без id из
календаря (его у пар нет). Отметить — с начала пары и две недели после."""

from datetime import datetime, timedelta

from database._conn import connect
from utils import TZ

# Порядок — как в приложении: капибара радуется, пьёт кофе, грустит, спит,
# злится (5.100.6, Никита 18.10: «препод злой», поза №11).
KINDS = ("joy", "calm", "hard", "sleep", "angry")
OPEN_DAYS = 14
KEEP_DAYS = 120


def lesson_key(start: datetime, title: str) -> str:
    t = " ".join(title.lower().replace("ё", "е").split())
    return f"{start.astimezone(TZ):%Y-%m-%dT%H:%M}|{t}"


def is_open(start: datetime, now: datetime) -> bool:
    return start <= now <= start + timedelta(days=OPEN_DAYS)


async def get(group_id: int, key: str, user_id: int) -> dict:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT kind, COUNT(*) FROM lesson_reactions WHERE group_id = ? AND lesson = ? GROUP BY kind",
            (group_id, key))).fetchall()
        mine = await (await db.execute(
            "SELECT kind FROM lesson_reactions WHERE group_id = ? AND lesson = ? AND user_id = ?",
            (group_id, key, user_id))).fetchone()
    counts = {k: 0 for k in KINDS}
    counts.update({k: n for k, n in rows if k in counts})
    return {"counts": counts, "mine": mine[0] if mine else None}


async def put(group_id: int, key: str, user_id: int, kind: str | None):
    """Своя реакция: новая заменяет прежнюю, None — снять."""
    async with connect() as db:
        if kind is None:
            await db.execute("DELETE FROM lesson_reactions WHERE group_id = ? AND lesson = ? AND user_id = ?",
                             (group_id, key, user_id))
        else:
            await db.execute(
                "INSERT INTO lesson_reactions (group_id, lesson, user_id, kind, day) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(group_id, lesson, user_id) DO UPDATE SET kind = excluded.kind",
                (group_id, key, user_id, kind, key[:10]))
        # старые пары никому не нужны — счёт не копится годами
        await db.execute("DELETE FROM lesson_reactions WHERE day < date('now', ?)", (f"-{KEEP_DAYS} days",))
        await db.commit()
