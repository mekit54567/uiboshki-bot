"""Своё напоминание о дедлайне: за день / 3 часа / час / своё время; приходит
один раз; если дедлайн уже отмечен сделанным — не приходит."""
from datetime import datetime

import pytest

import deadline_reminders as dr
from utils import TZ

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=TZ)
D = {"id": 1, "due_date": "2026-10-05", "due_time": "18:00"}


def test_resolve_presets_and_custom():
    assert dr.resolve(D, "1d", None, NOW) == "2026-10-04 18:00"
    assert dr.resolve(D, "3h", None, NOW) == "2026-10-05 15:00"
    assert dr.resolve({**D, "due_time": None}, "1h", None, NOW) == "2026-10-05 22:59"   # без времени — конец дня
    assert dr.resolve(D, None, "2026-10-03T09:30", NOW) == "2026-10-03 09:30"
    for preset, at, why in [("2d", None, "нет такого"), (None, "2026-10-01T10:00", "прошло"),
                            (None, "2026-10-09T10:00", "позже срока"), (None, "завтра", "формате")]:
        with pytest.raises(ValueError, match=why):
            dr.resolve(D, preset, at, NOW)


def test_label():
    assert dr.label("2026-10-02 21:00", NOW) == "сегодня в 21:00"
    assert dr.label("2026-10-03 09:05", NOW) == "завтра в 9:05"
    assert dr.label("2026-10-05 18:00", NOW) == "5 октября в 18:00"


@pytest.mark.asyncio
async def test_send_once_and_skip_done(db):
    a = await db.add_deadline("Курсовая", "", "2026-10-05", "18:00", 0)
    b = await db.add_deadline("Эссе", "", "2026-10-05", "18:00", 0)
    for did in (a, b):
        await db.add_deadline_reminder(7, did, "2026-10-04 18:00")
    await db.set_deadline_done(b, 7, True)
    assert (await db.get_user_deadline_reminders(7)) == {a: ["2026-10-04 18:00"], b: ["2026-10-04 18:00"]}
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append((uid, text))

    await dr.send_due(Bot(), datetime(2026, 10, 4, 17, 59, tzinfo=TZ))     # ещё рано
    assert sent == []
    await dr.send_due(Bot(), datetime(2026, 10, 4, 18, 0, tzinfo=TZ))
    await dr.send_due(Bot(), datetime(2026, 10, 4, 18, 1, tzinfo=TZ))      # второй раз — нет
    assert len(sent) == 1 and "Курсовая" in sent[0][1] and sent[0][0] == 7
    assert await db.get_user_deadline_reminders(7) == {}


@pytest.mark.asyncio
async def test_api_remind(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    did = await db.add_deadline("Курсовая", "", "2099-10-05", "18:00", 0)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    r = c.post(f"/api/deadlines/{did}/remind", json={"preset": "1d"}, headers=h)
    assert r.status_code == 200 and r.json()["at"] == "2099-10-04 18:00"
    item = [d for d in c.get("/api/deadlines", headers=h).json()["items"] if d["id"] == did][0]
    assert [x["at"] for x in item["reminders"]] == ["2099-10-04 18:00"]
    assert c.post(f"/api/deadlines/{did}/remind", json={"at": "2000-01-01T10:00"}, headers=h).status_code == 400
    assert c.post("/api/deadlines/99999/remind", json={"preset": "1d"}, headers=h).status_code == 404
    assert c.request("DELETE", f"/api/deadlines/{did}/remind", params={"at": "2099-10-04 18:00"}, headers=h).status_code == 200
    item = [d for d in c.get("/api/deadlines", headers=h).json()["items"] if d["id"] == did][0]
    assert item["reminders"] == []


def test_scheduler_runs_every_minute():
    src = open("scheduler.py", encoding="utf-8").read()
    assert "send_deadline_custom_reminders" in src


@pytest.mark.asyncio
async def test_reminder_goes_through_delivery(db, monkeypatch):
    """Своё напоминание — через слой доставки (пуш в приложение), а не только в Telegram."""
    import delivery
    a = await db.add_deadline("Практика 2 · Анализ данных", "", "2026-10-05", "18:00", 0)
    await db.add_deadline_reminder(7, a, "2026-10-04 18:00")
    got = []

    async def deliver(bot, uid, html, **kw):
        got.append((uid, kw["title"], kw["body"]))

    monkeypatch.setattr(delivery, "deliver", deliver)
    await dr.send_due(object(), datetime(2026, 10, 4, 18, 0, tzinfo=TZ))
    assert got == [(7, "Напоминание: Практика 2", "Анализ данных · срок завтра до 18:00")]
