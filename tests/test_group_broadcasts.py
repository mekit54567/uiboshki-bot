"""Этап 1 (г): рассылки по расписанию группы каждого — утро, напоминание
перед парой, обзор недели; паузы между сообщениями."""
from datetime import datetime, timedelta

import pytest

from kapibara.core import config

HOME = config.HOME_GROUP_ID
OTHER = 5001
HOME_USER, OTHER_USER = 501, 502


def _ical(summary: str, start: datetime) -> bytes:
    end = start + timedelta(minutes=90)
    fmt = "%Y%m%dT%H%M%S"
    return ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
            f"SUMMARY:ЛК {summary}\r\nDTSTART;TZID=Europe/Moscow:{start.strftime(fmt)}\r\n"
            f"DTEND;TZID=Europe/Moscow:{end.strftime(fmt)}\r\nLOCATION:А-1 (В-78)\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n").encode()


@pytest.fixture
async def two_groups(db, monkeypatch):
    from kapibara.features.schedule import mirea_api as mirea_schedule_api
    from kapibara.jobs import scheduler
    from database.groups import upsert_group
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((HOME_USER, HOME), (OTHER_USER, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    day = datetime.now(scheduler.TZ).replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=None)

    async def home_raw(*a, **k):
        return _ical("Своя пара", day)

    async def fetch_ical(tid, ttype):
        assert (ttype, tid) == (1, OTHER)
        return _ical("Пара УИБО-01", day)

    monkeypatch.setattr(scheduler, "fetch_schedule_raw", home_raw)
    monkeypatch.setattr(mirea_schedule_api, "fetch_ical", fetch_ical)
    from kapibara.features.notifications import broadcast
    monkeypatch.setattr(broadcast, "PACE_SECONDS", 0)
    return day


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text, **kw):
        self.sent.append((uid, text))


@pytest.mark.asyncio
async def test_morning_uses_each_users_group(two_groups, monkeypatch):
    import handlers.weather as weather
    from kapibara.jobs import scheduler

    async def no_weather():
        return ""

    monkeypatch.setattr(weather, "get_weather_for_morning", no_weather)
    bot = FakeBot()
    await scheduler.send_morning_schedule(bot)
    by = dict(bot.sent)
    assert "Своя пара" in by[HOME_USER] and "Пара УИБО-01" not in by[HOME_USER]
    assert "Пара УИБО-01" in by[OTHER_USER] and "Своя пара" not in by[OTHER_USER]


@pytest.mark.asyncio
async def test_lesson_reminder_for_other_group(two_groups, monkeypatch):
    from kapibara.jobs import scheduler
    day = two_groups

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (day - timedelta(minutes=60)).replace(tzinfo=scheduler.TZ)   # «первая пара» — за 60 мин

    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "_sent_reminders", set())
    bot = FakeBot()
    await scheduler.check_lesson_reminders(bot)
    texts = {uid: t for uid, t in bot.sent}
    assert "Пара УИБО-01" in texts.get(OTHER_USER, "")
    assert "Своя пара" in texts.get(HOME_USER, "")
