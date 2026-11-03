"""Доска ДЗ (таблица homework) и зам старосты (настройки — database/settings);
is_editor — кто правит доску ДЗ и общие дедлайны: староста и зам.
Раньше жило в handlers/announce.py со своей копией DATABASE_PATH."""

import logging
import sqlite3

import aiosqlite

from kapibara.core.config import is_starosta
from database import _conn
from database._conn import connect
from database.settings import get_setting, init_settings_table, set_setting  # noqa: F401 — их брали отсюда

logger = logging.getLogger(__name__)

# Базы, где таблицы уже проверены. Раньше init_hw_table шёл перед каждым
# get_setting — лишнее открытие базы на каждое чтение настройки (по 8 на
# запрос приложения; на медленном диске Amvera 19.10 — секунды).
_ready: set[str] = set()


async def init_hw_table():
    if _conn.DATABASE_PATH in _ready:
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
        for column in ("lesson_date TEXT", "group_id INTEGER"):     # group_id — этап 1 (б); NULL — своя
            try:
                await db.execute(f"ALTER TABLE homework ADD COLUMN {column}")
            except sqlite3.OperationalError as e:      # колонка уже есть — так при каждом запуске
                logger.debug(f"homework: {column}: {e}")
        await db.commit()
    await init_settings_table()
    _ready.add(_conn.DATABASE_PATH)


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
