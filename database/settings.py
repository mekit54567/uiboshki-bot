"""Настройки (таблица settings: ключ → строка): зам старосты, отметки
здоровья, запомненный чат группы и прочее. Жили в database/homework, но их
читают все (и database/members), а homework сам смотрит группы — выходил
клубок groups → members → homework → groups (03.11)."""

from database import _conn
from database._conn import connect

# Базы, где таблица уже есть. Раньше проверка шла перед каждым get_setting —
# лишнее открытие базы на каждое чтение (по 8 на запрос приложения; на
# медленном диске Amvera 19.10 — секунды).
_ready: set[str] = set()


async def init_settings_table():
    if _conn.DATABASE_PATH in _ready:
        return
    async with connect() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    _ready.add(_conn.DATABASE_PATH)


async def get_setting(key: str) -> str | None:
    # settings создаётся лениво — без этого на свежей базе первый is_editor
    # (первый /addhw до любого /hw) падал с "no such table".
    await init_settings_table()
    async with connect() as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()
