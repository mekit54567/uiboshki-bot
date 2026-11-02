"""Предметы по выбору: военную кафедру видят только те, кто ответил «хожу»."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from tests.test_solver_render import RecordingSession
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

TZ = ZoneInfo("Europe/Moscow")
DAY = datetime(2026, 9, 24, tzinfo=TZ).date()


def _ical() -> bytes:
    d = DAY.strftime("%Y%m%d")
    ev = lambda s, e, summ, uid: (f"BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Moscow:{d}T{s}\r\n"
                                  f"DTEND;TZID=Europe/Moscow:{d}T{e}\r\nSUMMARY:{summ}\r\nUID:{uid}\r\nEND:VEVENT\r\n")
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + ev("090000", "103000", "ЛК Анализ данных", "a")
            + ev("104000", "121000", "ПР Военная кафедра", "b") + "END:VCALENDAR\r\n").encode()


def test_parse_filter_and_search_unfiltered():
    from kapibara.features.groups.optional_subjects import HIDE
    from kapibara.features.schedule.parser import lessons_for_date, target_weeks
    token = HIDE.set(frozenset({"Военная кафедра"}))
    try:
        assert [l["title"] for l in lessons_for_date(_ical(), DAY)] == ["Анализ данных"]
        # расписание чужой группы/препода из поиска — без фильтра
        week = target_weeks(_ical(), DAY, weeks=1)[0]["days"][0]
        assert [l["title"] for l in week["lessons"]] == ["Анализ данных", "Военная кафедра"]
    finally:
        HIDE.reset(token)


@pytest.mark.asyncio
async def test_webapp_asks_and_hides_until_attend(db, monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.server as server

    async def raw():
        return _ical()

    async def subjects(**_):
        return ["Анализ данных", "Военная кафедра"]

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    day = lambda: [l["title"] for l in c.get("/api/day", params={"date": DAY.isoformat()}, headers=h).json()["lessons"]]

    assert c.get("/api/optional", headers=h).json() == {"pending": ["Военная кафедра"], "answers": {}}
    assert day() == ["Анализ данных"]                      # пока не ответил — скрыто
    assert c.post("/api/optional", json={"subject": "Военная кафедра", "attend": True}, headers=h).json() == {"ok": True}
    assert day() == ["Анализ данных", "Военная кафедра"]
    assert c.get("/api/optional", headers=h).json() == {"pending": [], "answers": {"Военная кафедра": True}}
    assert c.post("/api/optional", json={"subject": "Матан", "attend": True}, headers=h).status_code == 400


@pytest.mark.asyncio
async def test_bot_button_saves_answer(db):
    from database import get_optional_answers
    from handlers.start import router
    user = User(id=333, is_bot=False, first_name="Bob")
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    msg = Message(message_id=1, date=0, chat=Chat(id=user.id, type="private"), from_user=user, text="?")
    try:
        cb = CallbackQuery(id="1", from_user=user, chat_instance="x", data="opt:0:0", message=msg)
        await dp.feed_update(bot, Update(update_id=int(time.time()), callback_query=cb))
    finally:
        router._parent_router = None
    assert await get_optional_answers(user.id) == {"Военная кафедра": False}
