"""Миграции колонок (02.11, database/schema._add_column): колонку добавляем,
только если её нет, а ошибки базы больше не выдаются за «колонка уже есть»."""
import sqlite3

import aiosqlite
import pytest

import database
from database.schema import _add_column


async def test_adds_once_and_reports_it(tmp_path):
    async with aiosqlite.connect(tmp_path / "x.db") as db:
        await db.execute("CREATE TABLE t (id INTEGER)")
        assert await _add_column(db, "t", "note TEXT") is True
        assert await _add_column(db, "t", "note TEXT") is False
        assert await _add_column(db, "nope", "note TEXT") is False      # таблицы ещё нет
        cols = [r[1] for r in await (await db.execute("PRAGMA table_info(t)")).fetchall()]
        assert cols == ["id", "note"]


async def test_real_error_is_not_swallowed(tmp_path):
    async with aiosqlite.connect(tmp_path / "x.db") as db:
        await db.execute("CREATE TABLE t (id INTEGER)")
        with pytest.raises(sqlite3.OperationalError):
            await _add_column(db, "t", "bad TEXT DEFAULT (")             # кривое объявление — видно сразу


async def test_old_base_gets_columns_and_one_time_updates(tmp_path, monkeypatch):
    """База до колонок legacy/notify: init_db добавляет их, старым людям
    legacy=1 ставится один раз; повторный запуск ничего не трогает."""
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, "
                  "subscribed INTEGER DEFAULT 1, reminder_minutes INTEGER DEFAULT 15, joined_at TEXT)")
        c.execute("INSERT INTO users (user_id) VALUES (1)")
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    await database.init_db()
    with sqlite3.connect(path) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        assert {"notify", "legacy", "group_id", "calendar_token", "last_seen"} <= cols
        assert c.execute("SELECT legacy FROM users WHERE user_id = 1").fetchone() == (1,)
        c.execute("UPDATE users SET legacy = NULL")
    await database.init_db()                                             # второй запуск
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT legacy FROM users WHERE user_id = 1").fetchone() == (None,)
