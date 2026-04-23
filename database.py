import aiosqlite
from config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица пользователей (кто подписан на уведомления)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT,
                full_name TEXT,
                subscribed INTEGER DEFAULT 1,
                joined_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # Таблица дедлайнов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                description TEXT,
                due_date    TEXT NOT NULL,   -- ISO формат: YYYY-MM-DD
                due_time    TEXT,             -- HH:MM или NULL
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                done        INTEGER DEFAULT 0
            )
        """)
        await db.commit()


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()


async def get_all_subscribed_users() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE subscribed = 1"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def set_subscription(user_id: int, value: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET subscribed = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()


# ── Deadlines ─────────────────────────────────────────────────────────────────

async def add_deadline(subject: str, description: str,
                       due_date: str, due_time: str | None,
                       created_by: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO deadlines (subject, description, due_date, due_time, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (subject, description, due_date, due_time, created_by))
        await db.commit()
        return cursor.lastrowid


async def get_active_deadlines() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM deadlines
            WHERE done = 0
            ORDER BY due_date, due_time
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_deadlines_for_date(date_str: str) -> list[dict]:
    """Дедлайны на конкретную дату."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM deadlines
            WHERE done = 0 AND due_date = ?
            ORDER BY due_time
        """, (date_str,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_deadlines_soon(days: int = 3) -> list[dict]:
    """Дедлайны в ближайшие N дней."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM deadlines
            WHERE done = 0
              AND due_date BETWEEN date('now') AND date('now', ? || ' days')
            ORDER BY due_date, due_time
        """, (str(days),))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_deadline_done(deadline_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE deadlines SET done = 1 WHERE id = ?", (deadline_id,)
        )
        await db.commit()


async def delete_deadline(deadline_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
        await db.commit()
