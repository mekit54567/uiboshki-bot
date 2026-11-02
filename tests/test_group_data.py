"""Этап 1 (б): у каждой группы своё — расписание, общие дедлайны, ДЗ,
заметки, файлы и поиск по лекциям; старосты групп."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from kapibara.core import config
from tests.conftest import STAROSTA_ID
from tests.test_deadlines_routing import FakeSession

HOME = config.HOME_GROUP_ID
OTHER = 5001
HOME_USER, OTHER_USER, OTHER_MATE = 301, 302, 303


@pytest.fixture
async def people(db):
    from database.groups import upsert_group
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((HOME_USER, HOME), (OTHER_USER, OTHER), (OTHER_MATE, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    return db


@pytest.mark.asyncio
async def test_schedule_of_other_group_comes_from_its_calendar(people, monkeypatch):
    from kapibara.features.schedule import mirea_api as mirea_schedule_api
    from kapibara.features.schedule import parser as schedule_parser
    asked = []

    async def fetch_ical(tid, ttype):
        asked.append((ttype, tid))
        return b"BEGIN:VCALENDAR\nEND:VCALENDAR"

    async def own(*a, **k):
        return b"OWN"

    real = schedule_parser.fetch_schedule_raw
    monkeypatch.setattr(mirea_schedule_api, "fetch_ical", fetch_ical)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", own)          # своя — прежний путь
    assert await schedule_parser.raw_for_user(HOME_USER) == b"OWN"
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", real)
    assert (await schedule_parser.raw_for_user(OTHER_USER)).startswith(b"BEGIN:VCALENDAR")
    assert asked == [(1, OTHER)]


@pytest.mark.asyncio
async def test_shared_deadlines_stay_in_their_group(people):
    db = people
    from database import add_group_admin
    home_shared = await db.add_deadline("Общий УИБО-03", "-", "2099-01-01", None, STAROSTA_ID)
    sdo_home = await db.add_deadline("СДО УИБО-03", "-", "2099-01-01", None, 0, external_id="e1")
    other_shared = await db.add_deadline("Общий УИБО-01", "-", "2099-01-01", None, OTHER_USER, group_id=OTHER)
    mine = await db.add_deadline("Личное", "-", "2099-01-01", None, OTHER_MATE, personal=True)
    async def await_list(uid):
        return {d["id"] for d in await db.get_active_deadlines(uid)}

    assert await await_list(HOME_USER) == {home_shared, sdo_home}
    assert await await_list(OTHER_MATE) == {other_shared, mine}
    d = await db.get_deadline(other_shared)
    assert db.is_shared_deadline(d) and await db.can_see_deadline(d, OTHER_MATE)
    assert not await db.can_see_deadline(d, HOME_USER)
    # править общий своей группы — её староста, чужой — нет
    await add_group_admin(OTHER, OTHER_USER, STAROSTA_ID)
    assert await db.is_editor(OTHER_USER, OTHER) and not await db.is_editor(OTHER_USER, HOME)
    assert not await db.is_editor(OTHER_MATE, OTHER)
    assert await db.is_editor(STAROSTA_ID, OTHER)                            # староста бота — любой группы
    assert (await db.get_deadline_stats(OTHER_MATE))["active"] == 2


@pytest.mark.asyncio
async def test_homework_notes_files_by_group(people):
    db = people
    from database.groups import current_group
    await db.add_hw("Анализ", "задачи", "", "", STAROSTA_ID)                   # своя группа
    await db.add_hw("Финансы", "кейс", "", "", OTHER_USER, group_id=OTHER)
    assert await db.get_hw_subjects() == ["Анализ"]
    assert await db.get_hw_subjects(OTHER) == ["Финансы"]
    await db.add_lesson_note("2099-01-01", "", "свои", STAROSTA_ID)
    await db.add_lesson_note("2099-01-01", "", "их", OTHER_USER, OTHER)
    assert [n["text"] for n in await db.get_lesson_notes("2099-01-01", OTHER)] == ["их"]
    f_home = await db.add_file("Лекция 1", "Анализ", "tg1", "l1.pdf", STAROSTA_ID)
    token = current_group.set(OTHER)                                         # запрос человека из УИБО-01-24
    try:
        assert await db.get_files() == [] and await db.get_hw_subjects() == ["Финансы"]
        from database._conn import connect
        async with connect() as c:                                           # файл общий с их группой (1 (в))
            await c.execute("INSERT INTO file_groups (file_id, group_id) VALUES (?, ?)", (f_home, OTHER))
            await c.commit()
        assert [f["id"] for f in await db.get_files()] == [f_home]
    finally:
        current_group.reset(token)
    assert [f["id"] for f in await db.get_files()] == [f_home]               # своя группа — как раньше


@pytest.mark.asyncio
async def test_webapp_shows_users_group(people, monkeypatch):
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await people.add_hw("Анализ", "задачи", "", "", STAROSTA_ID)               # ДЗ своей группы — им не видно
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data(user={"id": OTHER_MATE, "first_name": "M"})}
    assert c.get("/api/homework", headers=h).json()["items"] == []
    assert c.get("/api/files", headers=h).json()["items"] == []


# ── «Я староста» ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_iam_starosta_goes_to_owner_and_approval_works(people):
    import handlers.group_pick as gp
    db = people
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(gp.router)
    user = User(id=OTHER_USER, is_bot=False, first_name="Оля")
    owner = User(id=STAROSTA_ID, is_bot=False, first_name="Никита")
    try:
        msg = Message(message_id=1, date=0, chat=Chat(id=OTHER_USER, type="private"), from_user=user, text="/iamstarosta")
        await dp.feed_update(bot, Update(update_id=int(time.time()), message=msg))
        to_owner = [t for chat, t in bot.session.sent_texts if chat == STAROSTA_ID]
        assert to_owner and "УИБО-01-24" in to_owner[0]
        cb = CallbackQuery(id="1", from_user=owner, chat_instance="c", data=f"gadm:ok:{OTHER}:{OTHER_USER}",
                           message=Message(message_id=2, date=0, chat=Chat(id=STAROSTA_ID, type="private"),
                                           from_user=owner, text="запрос"))
        await dp.feed_update(bot, Update(update_id=int(time.time()) + 1, callback_query=cb))
        assert await db.is_group_admin(OTHER_USER, OTHER)
        assert any(chat == OTHER_USER and "Теперь ты староста" in t for chat, t in bot.session.sent_texts)
        # не владелец одобрить не может
        cb2 = CallbackQuery(id="2", from_user=user, chat_instance="c", data=f"gadm:ok:{OTHER}:{OTHER_MATE}",
                            message=cb.message)
        await dp.feed_update(bot, Update(update_id=int(time.time()) + 2, callback_query=cb2))
        assert not await db.is_group_admin(OTHER_MATE, OTHER)
    finally:
        gp.router._parent_router = None
