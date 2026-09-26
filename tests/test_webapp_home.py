"""Главная WebApp: пары структурой со статусами, /api/today и /api/day."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

TZ = ZoneInfo("Europe/Moscow")


def _ical(day) -> bytes:
    d = day.strftime("%Y%m%d")
    ev = lambda s, e, summ, loc, uid: (
        f"BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Moscow:{d}T{s}\r\nDTEND;TZID=Europe/Moscow:{d}T{e}\r\n"
        f"SUMMARY:{summ}\r\nLOCATION:{loc}\r\nDESCRIPTION:Преподаватель: Иванов Иван Иванович\\n\r\nUID:{uid}\r\nEND:VEVENT\r\n")
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            + ev("090000", "103000", "ЛК Анализ данных", "А-17", "a")
            + ev("104000", "121000", "ПР Архитектура", "А-223", "b")
            + ev("124000", "141000", "ПР Архитектура", "А-223", "c")
            + "END:VCALENDAR\r\n").encode()


def test_lessons_for_date_statuses_and_merge():
    from schedule_parser import lessons_for_date
    day = datetime(2026, 9, 24, tzinfo=TZ).date()
    lessons = lessons_for_date(_ical(day), day, now=datetime(2026, 9, 24, 11, 0, tzinfo=TZ))
    assert [(l["num"], l["start"], l["end"], l["status"]) for l in lessons] == [
        (1, "09:00", "10:30", "past"),
        ("2–3", "10:40", "14:10", "now"),   # две подряд — одним блоком
    ]
    assert lessons[0]["title"] == "Анализ данных" and lessons[0]["kind"] == "лекция"
    assert lessons[0]["teacher"] == "Иванов И. И." and lessons[1]["pairs"] == 2


@pytest.fixture
def client(monkeypatch):
    import webapp.server as server
    monkeypatch.setattr(server, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_api_today(db, client, monkeypatch):
    import handlers.weather as weather
    import schedule_parser
    from utils import today_msk
    today = today_msk()

    async def raw():
        return _ical(today)

    async def w():
        return "☁️ +12°, пасмурно"

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(weather, "get_weather_for_morning", w)
    await db.add_deadline("СР-2", "", (today + timedelta(days=2)).isoformat(), "23:59", 0)
    await db.add_lesson_note(today.isoformat(), "Архитектура", "контрольная", 1)

    c, headers = client
    data = c.get("/api/today", headers=headers).json()
    assert data["date"] == today.isoformat() and data["schedule_ok"] is True
    assert [l["title"] for l in data["lessons"]] == ["Анализ данных", "Архитектура"]
    assert data["weather"] == "☁️ +12°, пасмурно"
    assert data["deadlines"]["active"] == 1 and data["deadlines"]["soon"][0]["days"] == 2
    assert data["notes"] == [{"subject": "Архитектура", "text": "контрольная"}]
    assert c.get("/api/today").status_code == 401


@pytest.mark.asyncio
async def test_api_today_survives_schedule_outage(db, client, monkeypatch):
    import handlers.weather as weather
    import schedule_parser

    async def down():
        raise RuntimeError("english.mirea.ru не отвечает")

    async def w():
        return ""

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", down)
    monkeypatch.setattr(weather, "get_weather_for_morning", w)
    c, headers = client
    data = c.get("/api/today", headers=headers).json()
    assert data["schedule_ok"] is False and data["lessons"] == []


def test_api_day(db, client, monkeypatch):
    import schedule_parser
    day = datetime(2026, 9, 24, tzinfo=TZ).date()

    async def raw():
        return _ical(day)

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    c, headers = client
    data = c.get("/api/day", params={"date": "2026-09-24"}, headers=headers).json()
    assert data["weekday"] == "Четверг" and data["label"] == "24 сентября"
    assert len(data["lessons"]) == 2
    assert c.get("/api/day", params={"date": "24.09"}, headers=headers).status_code == 400
