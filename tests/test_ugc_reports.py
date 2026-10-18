"""Записи людей (ugc.py, правило Apple 1.2): жалоба уходит владельцу с
«Удалить / Оставить», «Скрыть автора» — только у себя, правила — /rules и
/api/legal/rules; расписание без входа — /api/guest/… (5.1.1(v))."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from tests.test_deadlines_routing import FakeSession
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

ME, AUTHOR, OWNER = 222, 333, 999
DAY = "2099-09-29"


@pytest.fixture
def env(db, monkeypatch):
    import config
    import webapp.server as server
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(config, "STAROSTA_ID", OWNER)
    monkeypatch.setattr(config, "STAROSTA_IDS", [OWNER])
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    monkeypatch.setattr(server.deps, "tg_bot", lambda: bot)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}, bot


async def _press(bot, data, uid=OWNER):
    import handlers.reports as reports
    dp = Dispatcher()
    dp.include_router(reports.router)
    user = User(id=uid, is_bot=False, first_name="Никита")
    msg = Message(message_id=1, date=0, chat=Chat(id=uid, type="private"), from_user=user, text="🚩 Жалоба")
    try:
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, callback_query=CallbackQuery(
            id="1", from_user=user, chat_instance="c", data=data, message=msg)))
    finally:
        reports.router._parent_router = None


@pytest.mark.asyncio
async def test_report_note_goes_to_owner_and_delete_removes_it(env, db):
    c, h, bot = env
    await db.upsert_user(AUTHOR, "troll", "Тролль Троллев")
    nid = await db.add_lesson_note(DAY, "Анализ", "плохие слова", AUTHOR)
    r = c.post("/api/report", json={"kind": "note", "id": nid, "reason": "оскорбление"}, headers=h)
    assert r.json() == {"ok": True}
    chat, text = bot.session.sent_texts[-1]
    assert chat == OWNER and "плохие слова" in text and "Тролль Троллев" in text and "оскорбление" in text
    # повтор — та же жалоба, второго сообщения нет
    c.post("/api/report", json={"kind": "note", "id": nid}, headers=h)
    assert len(bot.session.sent_texts) == 1

    import ugc
    from database import get_lesson_note
    rid = (await ugc.get_report(1))["id"]
    await _press(bot, f"rep:del:{rid}", uid=ME)                      # не владелец — ничего
    assert await get_lesson_note(nid)
    await _press(bot, f"rep:del:{rid}")
    assert await get_lesson_note(nid) is None
    assert (await ugc.get_report(rid))["status"] == "removed"
    assert c.get(f"/api/notes?date={DAY}", headers=h).json()["items"] == []


@pytest.mark.asyncio
async def test_keep_closes_report_only(env, db):
    c, h, bot = env
    hid = await db.add_hw("Анализ", "задачи 1–5", "", "", AUTHOR, DAY)
    assert c.post("/api/report", json={"kind": "hw", "id": hid}, headers=h).json() == {"ok": True}
    await _press(bot, "rep:keep:1")
    import ugc
    from database.homework import get_hw
    assert await get_hw(hid) and (await ugc.get_report(1))["status"] == "kept"


@pytest.mark.asyncio
async def test_cannot_report_own_or_missing(env, db):
    c, h, _ = env
    nid = await db.add_lesson_note(DAY, "", "моя", ME)
    assert c.post("/api/report", json={"kind": "note", "id": nid}, headers=h).status_code == 400
    assert c.post("/api/report", json={"kind": "note", "id": 999}, headers=h).status_code == 404
    assert c.post("/api/report", json={"kind": "vote", "id": 1}, headers=h).status_code == 400


@pytest.mark.asyncio
async def test_hide_author_only_for_me(env, db):
    c, h, _ = env
    nid = await db.add_lesson_note(DAY, "", "спам", AUTHOR)
    await db.add_lesson_note(DAY, "", "по делу", 444)
    await db.add_hw("Анализ", "реклама", "", "", AUTHOR, DAY)
    await db.add_file("Реклама", "Анализ", "tg1", "a.pdf", AUTHOR)
    assert c.post("/api/hide-author", json={"kind": "note", "id": nid}, headers=h).json() == {"ok": True}

    assert [n["text"] for n in c.get(f"/api/notes?date={DAY}", headers=h).json()["items"]] == ["по делу"]
    assert c.get("/api/homework", headers=h).json()["items"] == []
    assert c.get("/api/files", headers=h).json()["items"] == []
    assert c.get("/api/hidden-authors", headers=h).json() == {"count": 1}

    other = {"X-Telegram-Init-Data": _make_init_data(user={"id": 555, "first_name": "Боря"})}
    assert len(c.get(f"/api/notes?date={DAY}", headers=other).json()["items"]) == 2   # у других — как было

    assert c.delete("/api/hidden-authors", headers=h).json() == {"ok": True, "count": 1}
    assert len(c.get(f"/api/notes?date={DAY}", headers=h).json()["items"]) == 2


@pytest.mark.asyncio
async def test_owner_cannot_be_hidden(env, db):
    c, h, _ = env
    nid = await db.add_lesson_note(DAY, "", "объявление", OWNER)
    r = c.post("/api/hide-author", json={"kind": "note", "id": nid}, headers=h)
    assert r.status_code == 400 and "пожаловаться" in r.json()["detail"]


@pytest.mark.asyncio
async def test_erase_forgets_reports_and_blocks(env, db):
    import privacy
    import ugc
    c, h, _ = env
    nid = await db.add_lesson_note(DAY, "", "спам", AUTHOR)
    c.post("/api/report", json={"kind": "note", "id": nid}, headers=h)
    c.post("/api/hide-author", json={"kind": "note", "id": nid}, headers=h)
    await privacy.erase(AUTHOR)
    assert await ugc.hidden(ME) == set() and (await ugc.get_report(1))["author_id"] is None
    await privacy.erase(ME)
    assert await ugc.get_report(1) is None


def test_rules_text_and_page(db):
    import webapp.server as server
    c = TestClient(server.app)
    d = c.get("/api/legal/rules").json()
    text = str(d)
    assert d["title"] == "Правила Капибары" and "оскорбления" in text and "удаляем" in text
    assert "Правила Капибары" in c.get("/rules").text


@pytest.mark.asyncio
async def test_guest_schedule_without_login(db, monkeypatch):
    import webapp.routes.schedule as sched
    import webapp.server as server

    async def fake_search(q="", type=0, user=None):
        assert user == {"id": 0}
        return {"items": [{"type": 1, "id": 7, "title": "УИБО-03-24"}], "ready": True}
    monkeypatch.setattr(sched, "api_search", fake_search)
    c = TestClient(server.app)
    r = c.get("/api/v1/guest/search?q=уибо")
    assert r.status_code == 200 and r.json()["items"][0]["title"] == "УИБО-03-24"
    assert c.get("/api/v1/guest/target/9/1").status_code == 404
