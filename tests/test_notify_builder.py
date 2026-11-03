"""Конструктор уведомлений (notify_prefs.py, /api/notify, scheduler): дни
недели, погода, другой корпус, «только если есть пары»."""
from datetime import datetime, timedelta

import pytest

from kapibara.features.notifications import prefs as notify_prefs

RAW = ("BEGIN:VCALENDAR\r\n" + "".join(
    f"BEGIN:VEVENT\r\nLOCATION:{loc}\r\nEND:VEVENT\r\n" for loc in
    ["А-1 (В-78)", "Б-2 (В-78)", "В-3 (В-78)", "И-201 (МП-1)", "Дистанционно", "А-4 (В-7\r\n 8)"]
) + "END:VCALENDAR\r\n").encode()


def test_merge_defaults_and_garbage():
    p = notify_prefs.merge('{"weather": false, "morning_days": [1, 9, "x", true, 1], "junk": 1}')
    assert p["weather"] is False and p["morning_days"] == [1] and "junk" not in p
    assert notify_prefs.merge(None) == notify_prefs.merge("не json") == notify_prefs.merge({})
    assert notify_prefs.merge(None)["lesson_days"] == [0, 1, 2, 3, 4, 5, 6]   # как раньше: каждый день
    assert notify_prefs.allowed(p, "morning", 1) and not notify_prefs.allowed(p, "morning", 0)
    assert not notify_prefs.allowed({**p, "lessons": False}, "lessons", 1)


def test_campus():
    assert notify_prefs.campus_of("И-201 (МП-1)") == "МП-1"
    assert notify_prefs.campus_of("Дистанционно") is None
    assert notify_prefs.home_campus(RAW) == "В-78"     # и перенос строки ical не мешает
    t = datetime(2026, 10, 1, 9, 0)
    mp = {"location": "И-201 (МП-1)", "time_start": t + timedelta(hours=3)}
    v = {"location": "А-1 (В-78)", "time_start": t}
    assert notify_prefs.campus_note([v], "В-78") == ""
    assert notify_prefs.campus_note([mp], "В-78") == "📍 <b>Сегодня пары на МП-1</b> — не на В-78"
    assert notify_prefs.campus_note([v, mp], "В-78") == "📍 <b>Сегодня часть пар на МП-1</b> с 12:00 — не только на В-78"
    assert notify_prefs.campus_note([mp], None) == ""


async def _morning(monkeypatch, events, weekday_date=datetime(2026, 10, 1, 7, 0)):
    """Прогнать утреннюю рассылку (четверг) и вернуть, что ушло в личку."""
    from kapibara.jobs import scheduler
    from kapibara.features.weather import forecast as weather

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return weekday_date.replace(tzinfo=scheduler.TZ)

    async def fake_raw():
        return RAW

    async def fake_weather():
        return "☁️ +12°"

    sent = []

    class FakeBot:
        async def send_message(self, uid, text, **kw):
            sent.append((uid, text))

    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(scheduler, "parse_events_for_date", lambda raw, day: events)
    monkeypatch.setattr(weather, "get_weather_for_morning", fake_weather)
    await scheduler.send_morning_schedule(FakeBot())
    return sent


@pytest.mark.asyncio
async def test_morning_follows_prefs(db, monkeypatch):
    from kapibara.jobs import scheduler
    from database import set_notify, upsert_user
    start = datetime(2026, 10, 1, 9, 0, tzinfo=scheduler.TZ)
    mp = [{"summary": "ЛК Физика", "location": "И-201 (МП-1)", "teacher": "", "time": "09:00–10:30",
           "time_start": start, "time_end": start + timedelta(minutes=90)}]
    for uid in (1, 2, 3, 4):
        await upsert_user(uid, "", "X")
    await set_notify(2, {"weather": False, "campus": False})
    await set_notify(3, {"morning_days": [0, 1, 2]})          # четверг (3) выключен
    await set_notify(4, {"morning": False})

    sent = dict(await _morning(monkeypatch, mp))
    assert set(sent) == {1, 2}
    assert "☁️ +12°" in sent[1] and "Сегодня пары на МП-1" in sent[1]
    assert "☁️" not in sent[2] and "МП-1</b> —" not in sent[2]


@pytest.mark.asyncio
async def test_morning_skip_empty(db, monkeypatch):
    from database import set_notify, upsert_user
    await upsert_user(1, "", "X")
    await upsert_user(2, "", "Y")
    await set_notify(2, {"skip_empty": True})
    sent = dict(await _morning(monkeypatch, []))
    assert set(sent) == {1}


@pytest.mark.asyncio
async def test_lesson_reminder_respects_days(db, monkeypatch):
    from kapibara.jobs import scheduler
    from database import set_notify, upsert_user
    now = datetime(2026, 10, 1, 8, 45, tzinfo=scheduler.TZ)   # четверг

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    start = now + timedelta(minutes=15)
    ev = [{"summary": "ЛК Физика", "location": "А-1 (В-78)", "teacher": "", "time": "09:00–10:30",
           "time_start": start, "time_end": start + timedelta(minutes=90)}]

    async def fake_raw():
        return b""

    sent = []

    class FakeBot:
        async def send_message(self, uid, text, **kw):
            sent.append(uid)

    for uid in (1, 2):
        await upsert_user(uid, "", "X")
    await set_notify(1, {"remind_first": 15})
    await set_notify(2, {"lesson_days": [0, 1, 2, 4], "remind_first": 15})
    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(scheduler, "parse_events_for_date", lambda raw, day: ev)
    monkeypatch.setattr(scheduler, "_sent_reminders", set())
    await scheduler.check_lesson_reminders(FakeBot())
    assert sent == [1]


@pytest.mark.asyncio
async def test_api_notify(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data

    async def fake_raw():
        return RAW

    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", fake_raw)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    r = c.get("/api/notify", headers=h).json()
    assert r["subscribed"] and r["home_campus"] == "В-78" and r["prefs"]["weather"] is True

    r = c.post("/api/notify", headers=h, json={"prefs": {"weather": False, "deadline_days": [5, 6]}}).json()
    assert r["prefs"]["weather"] is False and r["prefs"]["deadline_days"] == [5, 6]
    r = c.post("/api/notify", headers=h, json={"prefs": {"campus": False}}).json()
    assert r["prefs"]["weather"] is False and r["prefs"]["campus"] is False   # частичное — не затирает
    r = c.post("/api/notify", headers=h, json={"subscribed": False, "reminder_minutes": 30}).json()
    assert r["subscribed"] is False and r["reminder_minutes"] == 30
    assert c.post("/api/notify", headers=h, json={"reminder_minutes": 7}).status_code == 400
    r = c.post("/api/notify", headers=h, json={"prefs": {"remind_first": 180, "remind_short": 0, "remind_long": 500}}).json()
    assert (r["prefs"]["remind_first"], r["prefs"]["remind_short"], r["prefs"]["remind_long"]) == (180, 0, 10)
    assert [x["key"] for x in r["remind"]] == ["remind_first", "remind_short", "remind_long"]


def _day(*spans, tz=None):
    out = []
    for summary, h1, m1, h2, m2 in spans:
        out.append({"summary": summary, "location": "", "teacher": "", "time": "",
                    "time_start": datetime(2026, 10, 1, h1, m1, tzinfo=tz),
                    "time_end": datetime(2026, 10, 1, h2, m2, tzinfo=tz)})
    return out


def test_reminder_scenarios():
    # 1-я пара, через 10 мин 2-я (короткая перемена), через 30 мин 3-я (большой перерыв)
    day = _day(("ЛК Физика", 9, 0, 10, 30), ("ПР Физика", 10, 40, 12, 10),
               ("ЛК Матан", 12, 40, 14, 10), ("СР Практика", 7, 0, 8, 0))
    plan = notify_prefs.plan_reminders(day, notify_prefs.merge({}))
    assert [(e["summary"], m, k) for e, m, k in plan] == [
        ("ЛК Физика", 60, "remind_first"), ("ПР Физика", 5, "remind_short"), ("ЛК Матан", 10, "remind_long")]
    # «своё» время и выключенный сценарий
    plan = notify_prefs.plan_reminders(day, notify_prefs.merge({"remind_first": 180, "remind_short": 0}))
    assert [(e["summary"], m) for e, m, _ in plan] == [("ЛК Физика", 180), ("ЛК Матан", 10)]
    assert notify_prefs.merge({"remind_long": 999})["remind_long"] == 10      # больше предела — умолчание
    assert notify_prefs.minutes_text(180) == "3 ч" and notify_prefs.minutes_text(90) == "1 ч 30 мин"


@pytest.mark.asyncio
async def test_first_pair_reminder_hour_before(db, monkeypatch):
    from kapibara.jobs import scheduler
    from database import upsert_user
    now = datetime(2026, 10, 1, 8, 0, tzinfo=scheduler.TZ)   # пара в 9:00, по умолчанию — за 1 ч

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    async def fake_raw():
        return b""

    sent = []

    class FakeBot:
        async def send_message(self, uid, text, **kw):
            sent.append(text)

    await upsert_user(1, "", "X")
    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(scheduler, "parse_events_for_date",
                        lambda raw, d: _day(("ЛК Физика", 9, 0, 10, 30), ("ПР Физика", 10, 40, 12, 10), tz=scheduler.TZ))
    monkeypatch.setattr(scheduler, "_sent_reminders", set())
    await scheduler.check_lesson_reminders(FakeBot())
    assert len(sent) == 1 and "Через 1 ч первая пара" in sent[0]


@pytest.mark.asyncio
async def test_reminders_batch_and_quiet_without_pairs(db, monkeypatch):
    """Напоминания: нет пар в ближайшие часы — база не читается вовсе; есть —
    пользователи двумя запросами на всех, расписание разбирается по разу на
    набор скрытых предметов, у каждого свой фильтр предметов по выбору."""
    import database
    from kapibara.jobs import scheduler
    from database import set_optional_answer, upsert_user
    now = datetime(2026, 10, 1, 8, 0, tzinfo=scheduler.TZ)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    async def fake_raw():
        return b""

    parses = []

    def events(raw, day):
        from kapibara.features.groups.optional_subjects import HIDE
        parses.append(HIDE.get())
        day_ = _day(("ЛК Военная кафедра", 9, 0, 10, 30), tz=scheduler.TZ)
        return [e for e in day_ if not any(h in e["summary"] for h in HIDE.get())]

    sent = []

    class FakeBot:
        async def send_message(self, uid, text, **kw):
            sent.append(uid)

    for uid in (1, 2, 3):
        await upsert_user(uid, "", "X")
    await set_optional_answer(3, "Военная кафедра", True)          # третий ходит на военку
    monkeypatch.setattr(scheduler, "datetime", FakeDatetime)
    monkeypatch.setattr(scheduler, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(scheduler, "parse_events_for_date", events)
    monkeypatch.setattr(scheduler, "_sent_reminders", set())
    await scheduler.check_lesson_reminders(FakeBot())
    assert sent == [3]                                             # остальным военка скрыта
    assert len(parses) == 3                                        # без фильтра + 2 набора, не по человеку

    reads = []

    async def spy():
        reads.append(1)
        return []

    monkeypatch.setattr(database, "get_reminder_users", spy)
    now = datetime(2026, 10, 1, 20, 0, tzinfo=scheduler.TZ)        # вечер — пар впереди нет
    await scheduler.check_lesson_reminders(FakeBot())
    assert reads == []
