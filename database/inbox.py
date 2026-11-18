"""Лента уведомлений (новый дизайн, шаг 8, макет У1): всё, что приходило
пушем и в Telegram, лежит лентой и ведёт в нужную вкладку. Пишет
delivery.deliver, читает /api/inbox. Хранится KEEP_DAYS дней, не больше
KEEP_ITEMS на человека; с удалением данных уходит вместе с ним (колонка
user_id, privacy.erase_user)."""

import aiosqlite

from database._conn import connect

KEEP_DAYS = 30
KEEP_ITEMS = 100


async def add(user_id: int, kind: str, title: str, body: str, tab: str | None, at: str, *,
              quiet: bool = False) -> int:
    """Запись в ленту; at — время по Москве ISO. Старое и лишнее — вон. → id."""
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO inbox (user_id, kind, title, body, tab, at, quiet) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, kind, title[:200], body[:500], tab, at, 1 if quiet else 0))
        await db.execute("DELETE FROM inbox WHERE user_id = ? AND id NOT IN "
                         "(SELECT id FROM inbox WHERE user_id = ? ORDER BY id DESC LIMIT ?)",
                         (user_id, user_id, KEEP_ITEMS))
        await db.execute("DELETE FROM inbox WHERE user_id = ? AND substr(at, 1, 10) < date(?, ?)",
                         (user_id, at[:10], f"-{KEEP_DAYS} days"))
        await db.commit()
        return int(cur.lastrowid or 0)


async def items(user_id: int, limit: int = KEEP_ITEMS) -> list[dict]:
    """Лента, новые сверху."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, kind, title, body, tab, at, quiet, read FROM inbox WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?", (user_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def unread(user_id: int) -> int:
    async with connect() as db:
        row = await (await db.execute("SELECT COUNT(*) FROM inbox WHERE user_id = ? AND read = 0",
                                      (user_id,))).fetchone()
        return int(row[0]) if row else 0


async def mark_read(user_id: int) -> int:
    """Открыл ленту — всё прочитано. → сколько отметили."""
    async with connect() as db:
        cur = await db.execute("UPDATE inbox SET read = 1 WHERE user_id = ? AND read = 0", (user_id,))
        await db.commit()
        return cur.rowcount
