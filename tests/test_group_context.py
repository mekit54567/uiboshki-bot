"""Контекст группы для чата WebApp: дата, дедлайны (как их видит студент), ДЗ."""
from datetime import timedelta

import aiosqlite
import pytest

import group_context
from utils import today_msk


@pytest.mark.asyncio
async def test_group_context_has_date_deadlines_and_homework(db, monkeypatch):
    async def no_schedule(days=2):
        return ["Сегодня: <пары>"]

    monkeypatch.setattr(group_context, "_schedule_lines", no_schedule)
    soon = (today_msk() + timedelta(days=3)).isoformat()
    later = (today_msk() + timedelta(days=60)).isoformat()
    await db.add_deadline("СР-2 (Анализ данных)", "", soon, "23:59", 0)
    await db.add_deadline("Курсовая", "", later, None, 0)
    await db.add_deadline("Чужой личный", "", soon, None, 999)
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        await con.execute("CREATE TABLE homework (id INTEGER PRIMARY KEY, subject TEXT, content TEXT, file_id TEXT, "
                          "file_type TEXT, created_by INTEGER, created_at TEXT DEFAULT (datetime('now')), lesson_date TEXT)")
        await con.execute("INSERT INTO homework (subject, content, lesson_date) VALUES ('Архитектура', 'Прочитать гл. 3', ?)", (soon,))
        await con.commit()

    text = await group_context.build_group_context(222)
    assert today_msk().strftime("%d.%m.%Y") in text
    assert "СР-2 (Анализ данных)" in text and "23:59" in text
    assert "Курсовая" not in text            # за пределами трёх недель
    assert "Чужой личный" not in text        # личный дедлайн другого студента
    assert "Архитектура" in text and "Прочитать гл. 3" in text


@pytest.mark.asyncio
async def test_group_context_without_homework_table(db, monkeypatch):
    async def no_schedule(days=2):
        return []

    monkeypatch.setattr(group_context, "_schedule_lines", no_schedule)
    assert await group_context.list_homework() == []
    assert "дедлайнов на ближайшие три недели нет" in await group_context.build_group_context(1)
