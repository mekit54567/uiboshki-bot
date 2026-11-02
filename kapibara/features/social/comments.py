"""Комментарии под парой (Никита 19.10): группа обсуждает пару прямо под ней —
перенесли, где аудитория, что задали. Видит и пишет только своя группа (как
заметки и реакции), пара — тот же ключ «начало|название», что у реакций
(lesson_reactions.lesson_key).

Правило Apple 1.2 (записи людей): мат и оскорбления не пропускает фильтр
(nick_filter.rude), под чужим комментарием — «Пожаловаться» и «Скрыть автора»
(ugc.py, вид «comment»), убрать — автор или староста группы. Писать — за
неделю до пары и две недели после; храним KEEP_DAYS.
"""

from datetime import datetime, timedelta

import aiosqlite

from database._conn import connect

TEXT_MAX = 500
BEFORE_DAYS, AFTER_DAYS = 7, 14
KEEP_DAYS = 120
PAGE = 200


def is_open(start: datetime, now: datetime) -> bool:
    return start - timedelta(days=BEFORE_DAYS) <= now <= start + timedelta(days=AFTER_DAYS)


def problem(text: str) -> str | None:
    """Почему комментарий не принять (текст для человека) или None."""
    import nick_filter
    if not text:
        return "напиши комментарий"
    if len(text) > TEXT_MAX:
        return f"длинновато — до {TEXT_MAX} знаков"
    if nick_filter.rude(text):
        return "без мата и оскорблений — комментарий видит вся группа"
    return None


async def add(group_id: int, key: str, user_id: int, text: str) -> int:
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO lesson_comments (group_id, lesson, user_id, text, day) VALUES (?, ?, ?, ?, ?)",
            (group_id, key, user_id, text, key[:10]))
        await db.execute("DELETE FROM lesson_comments WHERE day < date('now', ?)", (f"-{KEEP_DAYS} days",))
        await db.commit()
        return cur.lastrowid


async def get(comment_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM lesson_comments WHERE id = ?", (comment_id,))).fetchone()
        return dict(row) if row else None


async def delete(comment_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM lesson_comments WHERE id = ?", (comment_id,))
        await db.commit()


async def items(group_id: int, key: str, viewer_id: int) -> list[dict]:
    """Комментарии пары по порядку, без скрытых зрителем авторов и без тех, кто
    удаляет данные (privacy). Автор — ник рейтинга или «Имя Ф.»."""
    import nick_filter
    import ugc
    from database.privacy import NOT_ERASING_FOR
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        try:
            rows = await (await db.execute(
                "SELECT c.id, c.user_id, c.text, c.created_at, COALESCE(u.full_name, '') AS name, p.nick "
                "FROM lesson_comments c LEFT JOIN users u ON u.user_id = c.user_id "
                "LEFT JOIN rating_profiles p ON p.user_id = c.user_id "
                f"WHERE c.group_id = ? AND c.lesson = ? AND {NOT_ERASING_FOR('c.user_id')} "
                "ORDER BY c.created_at, c.id LIMIT ?", (group_id, key, PAGE))).fetchall()
        except aiosqlite.OperationalError:          # rating_profiles ещё нет (старая база)
            rows = await (await db.execute(
                "SELECT c.id, c.user_id, c.text, c.created_at, COALESCE(u.full_name, '') AS name, NULL AS nick "
                "FROM lesson_comments c LEFT JOIN users u ON u.user_id = c.user_id "
                f"WHERE c.group_id = ? AND c.lesson = ? AND {NOT_ERASING_FOR('c.user_id')} "
                "ORDER BY c.created_at, c.id LIMIT ?", (group_id, key, PAGE))).fetchall()
    out = ugc.without_hidden([dict(r) for r in rows], await ugc.hidden(viewer_id), "user_id")
    for c in out:
        c["author"] = c.pop("nick") or nick_filter.default(c.pop("name")) or "Одногруппник"
        c.pop("name", None)
        c["mine"] = c.pop("user_id") == viewer_id
    return out
