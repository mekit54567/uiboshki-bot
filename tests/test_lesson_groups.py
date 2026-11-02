"""С кем эта пара (Никита 12.10): группы, у которых в то же время пара в той
же аудитории, — из календаря аудитории, без своей."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from kapibara.features.schedule import index as schedule_index
from kapibara.features.schedule.events import groups_at
from tests.test_webapp_auth import _make_init_data
from kapibara.core.utils import TZ

DAY = (datetime.now(TZ) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)


def _room_ical(desc: str = "УИБО-01-24\\nУИБО-02-24\\nУИБО-03-24\\nУИБО-02-24 1 п/г") -> bytes:
    d = DAY.strftime("%Y%m%d")
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:А-17 (В-78)\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART;TZID=Europe/Moscow:{d}T090000\r\nDTEND;TZID=Europe/Moscow:{d}T103000\r\n"
        "SUMMARY:ЛК Анализ данных\r\nLOCATION:А-17 (В-78)\r\n"
        f"DESCRIPTION:{desc}\r\nUID:r1\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART;TZID=Europe/Moscow:{d}T104000\r\nDTEND;TZID=Europe/Moscow:{d}T121000\r\n"
        "SUMMARY:ПР Физика\r\nLOCATION:А-17 (В-78)\r\n"
        "DESCRIPTION:КСБО-11-26\\n\r\nUID:r2\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


def test_groups_at_takes_codes_of_the_lesson_going_then():
    raw = _room_ical()
    assert groups_at(raw, DAY) == ["УИБО-01-24", "УИБО-02-24", "УИБО-03-24"]   # подгруппа — та же группа
    assert groups_at(raw, DAY + timedelta(minutes=45)) == ["УИБО-01-24", "УИБО-02-24", "УИБО-03-24"]
    assert groups_at(raw, DAY + timedelta(minutes=100)) == ["КСБО-11-26"]       # следующая пара — другая
    assert groups_at(raw, DAY - timedelta(hours=1)) == []
    # у аудитории в описании бывает и преподаватель — группы всё равно найдутся
    assert groups_at(_room_ical("Преподаватель: Иванов И. И.\\nУИБО-01-24"), DAY) == ["УИБО-01-24"]


@pytest.mark.asyncio
async def test_lesson_groups_endpoint(db, monkeypatch):
    from kapibara.features.schedule import mirea_api as api
    import webapp.server as server

    await schedule_index._save([(3, 501, "А-17 (В-78)"), (3, 502, "А-17 (МП-1)"), (2, 77, "Стебунова О. И.")])
    asked = []

    async def fake_ical(target_id, target_type):
        asked.append((target_type, target_id))
        return _room_ical() if target_type == 3 else None

    monkeypatch.setattr(api, "fetch_ical", fake_ical)
    client = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    start = DAY.isoformat()

    r = client.get("/api/lesson/groups", params={"start": start, "room": "А-17 (В-78)"}, headers=h).json()
    assert r == {"groups": ["УИБО-01-24", "УИБО-02-24"], "source": "room"}        # своей УИБО-03-24 нет
    assert asked == [(3, 501)]                                                    # не аудитория другого корпуса
    # время из приложения — UTC с миллисекундами
    utc = DAY.astimezone(__import__("zoneinfo").ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert client.get("/api/lesson/groups", params={"start": utc, "room": "А-17 (В-78)"},
                      headers=h).json()["groups"] == ["УИБО-01-24", "УИБО-02-24"]
    # аудитории нет в справочнике (кафедра) — пусто, без ошибки
    r = client.get("/api/lesson/groups", params={"start": start, "room": "кафедра (В-78)",
                                                 "teacher": "Стебунова О. И."}, headers=h).json()
    assert r == {"groups": [], "source": ""}
    assert client.get("/api/lesson/groups", params={"start": "вчера"}, headers=h).status_code == 400
    assert client.get("/api/lesson/groups", params={"start": start}).status_code == 401
