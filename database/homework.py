"""Доска ДЗ (таблица homework) и настройки группы (settings: зам старосты);
is_editor — кто правит доску ДЗ и общие дедлайны: староста и зам.
Раньше жило в handlers/announce.py со своей копией DATABASE_PATH."""

import aiosqlite

import database
from config import is_starosta
from database._conn import connect

# Базы, где таблицы уже проверены. Раньше init_hw_table шёл перед каждым
# get_setting — лишнее открытие базы на каждое чтение настройки (по 8 на
# запрос приложения; на медленном диске Amvera 19.10 — секунды).
_ready: set[str] = set()


async def init_hw_table():
    if database.DATABASE_PATH in _ready:
        return
    async with connect() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                content     TEXT,
                file_id     TEXT,
                file_type   TEXT,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # lesson_date — привязка ДЗ к конкретной дате/паре (Фаза 12, календарь),
        # а не только к предмету "вообще". NULL — старое поведение (общее ДЗ по
        # предмету без даты), как было раньше и остаётся по умолчанию.
        try:
            await db.execute("ALTER TABLE homework ADD COLUMN lesson_date TEXT")
        except Exception:
            pass  # колонка уже есть
        try:
            await db.execute("ALTER TABLE homework ADD COLUMN group_id INTEGER")   # этап 1 (б); NULL — своя
        except Exception:
            pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    _ready.add(database.DATABASE_PATH)


async def get_setting(key: str) -> str | None:
    # settings создаётся лениво в init_hw_table — без этого вызова is_editor
    # на свежей базе (первый /addhw до любого /hw) падал с "no such table".
    await init_hw_table()
    async with connect() as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def is_editor(user_id: int, group_id: int | None = None) -> bool:
    """Может править общие данные группы (дедлайны, ДЗ, файлы, заметки):
    староста бота — любой группы; зам — своей; старосты групп (group_admins)
    — своей. group_id не задан — группа самого человека."""
    if is_starosta(user_id):
        return True
    from database.groups import home, is_group_admin, viewer_group
    gid = group_id if group_id is not None else await viewer_group(user_id)
    if gid == home() or not home():
        zam = await get_setting("zam_id")
        # Без isdigit() одно кривое значение (например "/setzam @username" до
        # появления проверки в cmd_setzam) навсегда роняло ValueError в каждом
        # /hw и /addhw у всех.
        zam_id = int(zam) if zam and zam.isdigit() else 0
        if user_id == zam_id:
            return True
    return gid > 0 and await is_group_admin(user_id, gid)


async def add_hw(subject: str, content: str, file_id: str, file_type: str, created_by: int,
                  lesson_date: str | None = None, group_id: int | None = None) -> int:
    from database.groups import stored
    await init_hw_table()
    async with connect() as db:
        cur = await db.execute("""
            INSERT INTO homework (subject, content, file_id, file_type, created_by, lesson_date, group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (subject, content, file_id, file_type, created_by, lesson_date, stored(group_id)))
        await db.commit()
        return cur.lastrowid


async def get_hw_for_date(date_str: str, group_id: int | None = None) -> list[dict]:
    """ДЗ, привязанные к конкретной дате (используется генератором ICS-фида,
    см. webapp/calendar_feed.py — матчинг по дате + вхождению предмета в
    название пары из расписания)."""
    await init_hw_table()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        from database.groups import g_or_home, scope_sql
        cur = await db.execute(
            f"SELECT * FROM homework WHERE lesson_date=? AND {scope_sql()} ORDER BY created_at",
            (date_str, g_or_home(group_id))
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_hw_subjects(group_id: int | None = None) -> list[str]:
    from database.groups import g_or_home, scope_sql
    await init_hw_table()
    async with connect() as db:
        cur = await db.execute(f"SELECT DISTINCT subject FROM homework WHERE {scope_sql()} ORDER BY subject",
                               (g_or_home(group_id),))
        return [r[0] for r in await cur.fetchall()]


async def get_hw_by_subject(subject: str, group_id: int | None = None) -> list[dict]:
    from database.groups import g_or_home, scope_sql
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(f"""
            SELECT * FROM homework WHERE subject=? AND {scope_sql()} ORDER BY created_at DESC, id DESC
        """, (subject, g_or_home(group_id)))
        return [dict(r) for r in await cur.fetchall()]


async def get_hw(hw_id: int) -> dict | None:
    await init_hw_table()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM homework WHERE id=?", (hw_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def delete_hw(hw_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM homework WHERE id=?", (hw_id,))
        await db.commit()
