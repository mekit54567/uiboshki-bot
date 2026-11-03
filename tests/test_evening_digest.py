"""Вечерняя сводка на завтра (evening_digest.py, Никита 12.10): пары, погода,
корпус и сроки; пустой день не шлём; тумблер и время в уведомлениях; при
DESIGN2=0 — ни рассылки, ни пункта в /api/notify."""
from pathlib import Path
from datetime import date, datetime

import pytest

from kapibara.features.notifications import evening_digest
from kapibara.features.notifications import prefs as notify_prefs
from kapibara.core.utils import TZ

TUE = date(2026, 10, 13)                      # завтра
NOW = datetime(2026, 10, 12, 20, 0, tzinfo=TZ)


def _lessons(by_date):
    def fake(raw, d, now=None):
        return [{"start": s, "pairs": 1, "room": room, "kind": kind, "title": title}
                for s, room, kind, title in by_date.get(d, [])]
    return fake


@pytest.fixture
def day(monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser

    def set_day(items):
        monkeypatch.setattr(schedule_parser, "lessons_for_date", _lessons({TUE: items}))
    return set_day


PAIRS = [("10:40", "А-2 (В-78)", "практика", "Анализ данных"), ("09:00", "А-1 (В-78)", "лекция", "Физика"),
         ("12:40", "А-3 (В-78)", "лекция", "Матан")]


def test_merge_evening_time():
    p = notify_prefs.merge({})
    assert p["evening"] is False and p["evening_time"] == "20:00"        # у всех выключено
    assert notify_prefs.merge({"evening": True, "evening_time": "21:30"})["evening_time"] == "21:30"
    for bad in ("20:15", "16:30", "24:00", "8:00", 2000, None, "мусор"):
        assert notify_prefs.merge({"evening_time": bad})["evening_time"] == "20:00"
    assert notify_prefs.merge({"evening": "да"})["evening"] is False
    assert "17:00" in notify_prefs.EVENING_TIMES and "23:30" in notify_prefs.EVENING_TIMES


def test_build_pairs_weather_deadlines(day):
    day(PAIRS)
    dls = [{"subject": "Лаба 3 · Анализ данных (Экз)", "due_date": "2026-10-13", "due_time": "23:59"},
           {"subject": "Практика <2>", "due_date": "2026-10-15", "due_time": None}]
    title, text = evening_digest.build(b"", TUE, dls, "В-78", "+2…+6°, дождь")
    assert title == "Завтра: 3 пары с 09:00, В-78"
    lines = text.split("\n")
    assert lines[0] == "🌙 <b>Завтра: 3 пары с 09:00, В-78</b>"
    assert lines[1] == "+2…+6°, дождь. Сдать: Лаба 3 до 23:59, Практика &lt;2&gt; до чт."
    assert lines[2] == "Первая — Физика, лекция · А-1 (В-78)"
    # без погоды и корпуса (тумблеры утренней рассылки) — строки нет
    title, text = evening_digest.build(b"", TUE, [], "В-78", "", campus=False)
    assert title == "Завтра: 3 пары с 09:00" and len(text.split("\n")) == 2


def test_build_other_campus(day):
    day([("09:00", "И-201 (МП-1)", "лекция", "Физика")])
    title, _ = evening_digest.build(b"", TUE, [], "В-78")
    assert title == "Завтра: 1 пара с 09:00, МП-1 (не В-78)"


def test_build_no_pairs_but_deadline(day):
    day([("", "", "сам. работа", "Практика")])                    # сам. работа без времени — не пара
    dls = [{"subject": "Практика 2", "due_date": "2026-10-19", "due_time": "18:00"}]
    title, text = evening_digest.build(b"", TUE, dls, "В-78", "+2°, дождь")
    assert title == "Завтра пар нет"
    assert text == "🌙 <b>Завтра пар нет</b>\nСдать до пн: Практика 2. Отдыхай."


def test_build_nothing(day):
    day([])
    assert evening_digest.build(b"", TUE, [], "В-78", "+2°, дождь") is None


def test_tomorrow_weather_text():
    from handlers.weather import tomorrow_text
    assert tomorrow_text({"tmin": 2, "tmax": 6, "code": 63}) == "+2…+6°, дождь"
    assert tomorrow_text({"tmin": -1, "tmax": -1, "code": 0}) == "-1°, ясно"
    assert tomorrow_text(None) == ""                                     # сбой — строки погоды нет


def test_card_in_webapp():
    """Пункт в листе «Уведомления» — только если сервер отдал ключ evening."""
    src = Path("webapp/static/js/more.js").read_text(encoding="utf-8")
    assert "toggleNotify('evening')" in src and '!("evening" in p)' in src


def test_slot():
    assert evening_digest.slot(datetime(2026, 10, 12, 20, 0)) == "20:00"
    assert evening_digest.slot(datetime(2026, 10, 12, 21, 31)) == "21:30"


@pytest.fixture
def world(db, day, monkeypatch):
    """Бот, своя группа, погода без сети, «сегодня» — 12.10."""
    import database.deadlines
    import handlers.weather
    from kapibara.features.schedule import parser as schedule_parser

    async def raw(*a, **k):
        return b""

    async def weather():
        return "+2°, дождь"

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(handlers.weather, "get_weather_for_tomorrow", weather)
    monkeypatch.setattr(database.deadlines, "today_msk", lambda: NOW.date())
    monkeypatch.delenv("DESIGN2", raising=False)
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append((uid, text))

    return Bot(), sent


@pytest.mark.asyncio
async def test_send_only_enabled_and_at_their_time(db, world, day):
    bot, sent = world
    day(PAIRS)
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "X")
    await db.set_notify(1, {"evening": True})                          # 20:00 по умолчанию
    await db.set_notify(2, {"evening": True, "evening_time": "21:00"})  # другое время
    # 3 — выключено (как у всех по умолчанию)
    await db.add_deadline("Лаба 3", "", "2026-10-13", "23:59", 0, external_id="sdo:1")
    await db.add_deadline("Сегодняшнее", "", "2026-10-12", "23:59", 0, external_id="sdo:2")
    await evening_digest.send_all(bot, NOW)
    assert [u for u, _ in sent] == [1]
    text = sent[0][1]
    assert "Завтра: 3 пары с 09:00, В-78" in text and "+2°, дождь. Сдать: Лаба 3 до 23:59." in text
    assert "Сегодняшнее" not in text
    sent.clear()
    await evening_digest.send_all(bot, datetime(2026, 10, 12, 21, 0, tzinfo=TZ))
    assert [u for u, _ in sent] == [2]


@pytest.mark.asyncio
async def test_send_empty_day_and_far_deadline(db, world, day):
    bot, sent = world
    day([])
    await db.upsert_user(1, "", "X")
    await db.set_notify(1, {"evening": True})
    await db.add_deadline("Курсовая", "", "2026-10-20", "18:00", 0, external_id="sdo:1")   # не в ближайшие дни
    await evening_digest.send_all(bot, NOW)
    assert sent == []
    await db.add_deadline("Практика 2", "", "2026-10-14", None, 0, external_id="sdo:2")
    await evening_digest.send_all(bot, NOW)
    assert sent == [(1, "🌙 <b>Завтра пар нет</b>\nСдать до ср: Практика 2. Отдыхай.")]


@pytest.mark.asyncio
async def test_design2_off_sends_nothing(db, world, day, monkeypatch):
    bot, sent = world
    day(PAIRS)
    await db.upsert_user(1, "", "X")
    await db.set_notify(1, {"evening": True})
    monkeypatch.setenv("DESIGN2", "0")
    await evening_digest.send_all(bot, NOW)
    assert sent == []


@pytest.mark.asyncio
async def test_push_title_is_summary(db, world, day, monkeypatch):
    """Пуш: заголовок — «Завтра: …», текст — без повтора заголовка."""
    from kapibara.features.notifications import delivery
    bot, sent = world
    day(PAIRS)
    await db.upsert_user(1, "", "X")
    await db.set_notify(1, {"evening": True})
    pushed = []

    async def push(user_id, kind, html, tab=None, title=None):
        pushed.append((kind, title, delivery._body(html, title)))

    monkeypatch.setattr(delivery, "push", push)
    await evening_digest.send_all(bot, NOW)
    kind, title, body = pushed[0]
    assert kind == "evening" and title == "Завтра: 3 пары с 09:00, В-78"
    assert body.startswith("+2°, дождь.") and "Завтра:" not in body


@pytest.mark.asyncio
async def test_api_notify_evening(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data

    async def fake_raw():
        return b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", fake_raw)
    monkeypatch.delenv("DESIGN2", raising=False)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    r = c.get("/api/notify", headers=h).json()
    assert r["prefs"]["evening"] is False and r["prefs"]["evening_time"] == "20:00"
    r = c.post("/api/notify", headers=h, json={"prefs": {"evening": True, "evening_time": "22:00"}}).json()
    assert r["prefs"]["evening"] is True and r["prefs"]["evening_time"] == "22:00"
    r = c.post("/api/notify", headers=h, json={"prefs": {"evening_time": "22:15"}}).json()
    assert r["prefs"]["evening_time"] == "20:00"                      # не через полчаса — умолчание

    monkeypatch.setenv("DESIGN2", "0")                               # откат: пункта нет, запись не принимается
    r = c.get("/api/notify", headers=h).json()
    assert "evening" not in r["prefs"] and "evening_time" not in r["prefs"]
    r = c.post("/api/notify", headers=h, json={"prefs": {"evening": False, "weather": False}}).json()
    assert "evening" not in r["prefs"] and r["prefs"]["weather"] is False
    monkeypatch.delenv("DESIGN2")
    assert c.get("/api/notify", headers=h).json()["prefs"]["evening"] is True   # сохранённое не тронуто
