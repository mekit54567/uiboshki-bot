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


# ── дедлайны, ДЗ и файлы в WebApp ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_delete_personal_deadline(db, client):
    c, headers = client
    resp = c.post("/api/deadlines", headers=headers,
                  json={"subject": "Лаба 3", "due_date": "2099-10-03", "due_time": "23:59", "description": "в СДО"})
    assert resp.status_code == 200
    did = resp.json()["id"]
    items = c.get("/api/deadlines", headers=headers).json()["items"]
    mine = next(i for i in items if i["id"] == did)
    assert mine["personal"] and mine["mine"] and mine["due_time"] == "23:59"

    assert c.post("/api/deadlines", headers=headers, json={"subject": "", "due_date": "2099-10-03"}).status_code == 400
    assert c.post("/api/deadlines", headers=headers, json={"subject": "x", "due_date": "03.10"}).status_code == 400
    assert c.post("/api/deadlines", headers=headers,
                  json={"subject": "x", "due_date": "2099-10-03", "due_time": "25:00"}).status_code == 400

    shared = await db.add_deadline("Общий", "", "2099-10-01", None, 0)
    assert c.delete(f"/api/deadlines/{shared}", headers=headers).status_code == 403  # общий — только староста
    assert c.delete(f"/api/deadlines/{did}", headers=headers).json() == {"ok": True}
    assert await db.get_deadline(did) is None


@pytest.mark.asyncio
async def test_homework_and_files_api(db, client):
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        await con.execute("CREATE TABLE homework (id INTEGER PRIMARY KEY, subject TEXT, content TEXT, file_id TEXT, "
                          "file_type TEXT, created_by INTEGER, created_at TEXT DEFAULT (datetime('now')), lesson_date TEXT)")
        await con.execute("INSERT INTO homework (subject, content, file_id, lesson_date) VALUES ('Анализ', 'задачи 1–5', 'tg', '2099-09-29')")
        await con.commit()
    fid = await db.add_file("Лекция 1", "Анализ", "tg1", "l1.pdf", 1)
    await db.save_file_text(fid, "текст")
    await db.add_file("Фото", "Анализ", "tg2", "p.jpg", 1)

    c, headers = client
    hw = c.get("/api/homework", headers=headers).json()["items"]
    assert hw == [{"id": 1, "subject": "Анализ", "content": "задачи 1–5", "lesson_date": "2099-09-29",
                   "created_at": hw[0]["created_at"], "has_file": True}]
    files = {f["title"]: f["has_text"] for f in c.get("/api/files", headers=headers).json()["items"]}
    assert files == {"Лекция 1": True, "Фото": False}


# ── правка дедлайнов и защита от автосинка ─────────────────────────────────

def _headers_for(uid):
    return {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "U"})}


@pytest.mark.asyncio
async def test_edit_permissions_and_sdo_does_not_overwrite(db, client, monkeypatch):
    import sdo_parser
    from tests.conftest import STAROSTA_ID
    c, _ = client
    shared = await db.add_deadline("Практическая работа №1 - срок сдачи (Архитектура_Экзамен [I.26-27])",
                                   "https://sdo/x", "2099-09-30", "23:59", 0, external_id="sdo:1")
    body = {"subject": "ПР-1 Архитектура", "due_date": "2099-10-02", "due_time": "18:00", "description": ""}

    assert c.patch(f"/api/deadlines/{shared}", headers=_headers_for(222), json=body).status_code == 403
    items = {i["id"]: i for i in c.get("/api/deadlines", headers=_headers_for(222)).json()["items"]}
    assert items[shared]["can_edit"] is False

    st = _headers_for(STAROSTA_ID)
    assert c.get("/api/deadlines", headers=st).json()["items"][0]["can_edit"] is True
    assert c.patch(f"/api/deadlines/{shared}", headers=st, json=body).json()["ok"]
    edited = await db.get_deadline(shared)
    assert (edited["subject"], edited["due_date"], edited["due_time"], edited["manual_edit"]) == \
           ("ПР-1 Архитектура", "2099-10-02", "18:00", 1)

    # СДО снова отдаёт старое название/срок — ручная правка старосты главнее
    async def sdo_page():
        return "<html>usermenu</html>"

    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")
    monkeypatch.setattr(sdo_parser, "fetch_upcoming_html", sdo_page)
    monkeypatch.setattr(sdo_parser, "parse_deadlines", lambda html: [{
        "external_id": "sdo:1", "subject": "Практическая работа №1 - срок сдачи (Архитектура_Экзамен [I.26-27])",
        "description": "https://sdo/x", "due_date": "2099-09-30", "due_time": "23:59"}])
    res = await sdo_parser.sync_deadlines()
    assert res["updated"] == 0 and res["skipped"] == 1
    assert (await db.get_deadline(shared))["subject"] == "ПР-1 Архитектура"

    # староста может и удалить общий
    assert c.delete(f"/api/deadlines/{shared}", headers=st).json() == {"ok": True}


@pytest.mark.asyncio
async def test_bot_undone_returns_deadline(db):
    import time
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    from handlers.deadlines import router
    from tests.test_solver_render import RecordingSession
    user = User(id=222, is_bot=False, first_name="A")
    did = await db.add_deadline("СР-2", "", "2099-10-01", None, 0)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router)
    try:
        for i, text in enumerate(("/done %d" % did, "/deadlines", "/undone %d" % did, "/deadlines")):
            msg = Message(message_id=900 + i, date=0, chat=Chat(id=222, type="private"), from_user=user, text=text)
            await dp.feed_update(bot, Update(update_id=int(time.time()) + i, message=msg))
    finally:
        router._parent_router = None
    sent = [t for t, _ in bot.session.sent]
    assert f"/undone {did}" in sent[0]                          # подсказка сразу после /done
    assert "Выполнено: 1" in sent[1] and "/undone ID" in sent[1]  # /deadlines показывает выполненные
    assert "снова в активных" in sent[2]
    assert "Выполнено" not in sent[3] and "СР-2" in sent[3]


@pytest.mark.asyncio
async def test_files_have_categories_and_edit_permissions(db, client):
    from tests.conftest import STAROSTA_ID
    c, _ = client
    lec = await db.add_file("Лекция 1", "ОБА", "a", "l1.pdf", 222)
    kr = await db.add_file("вариант 7", "ОБА", "b", "v7.pdf", 333, category="control")

    data = c.get("/api/files", headers=_headers_for(222)).json()
    items = {i["id"]: i for i in data["items"]}
    assert (items[lec]["category"], items[lec]["category_label"]) == ("lecture", "📓 Лекции")
    assert items[kr]["category"] == "control"
    assert items[lec]["can_edit"] and not items[kr]["can_edit"]   # своё — да, чужое — нет
    assert [x["key"] for x in data["categories"]][:3] == ["lecture", "practice", "control"]

    body = {"title": "КР 1", "subject": "Анализ данных", "category": "control"}
    assert c.patch(f"/api/files/{kr}", headers=_headers_for(222), json=body).status_code == 403
    assert c.patch(f"/api/files/{kr}", headers=_headers_for(STAROSTA_ID), json=body).json()["ok"]
    assert c.patch(f"/api/files/{lec}", headers=_headers_for(222),
                   json={"title": "Л1", "category": "nope"}).status_code == 400
    assert c.patch(f"/api/files/{lec}", headers=_headers_for(222),
                   json={"title": "Лекция 1", "subject": "ОБА", "category": "method"}).json()["ok"]

    [f] = await db.get_files("Анализ данных")
    assert (f["title"], f["category"]) == ("КР 1", "control")
    assert (await db.get_files("ОБА"))[0]["category"] == "method"
    assert c.patch("/api/files/9999", headers=_headers_for(STAROSTA_ID), json=body).status_code == 404
