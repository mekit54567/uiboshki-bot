"""Записи людей (ugc.py, правило Apple 1.2): жалоба уходит владельцу с
«Удалить / Оставить», «Скрыть автора» — только у себя, правила — /rules и
/api/legal/rules; расписание без входа — /api/guest/… (5.1.1(v))."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
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
    _STORE["fsm"] = MemoryStorage()                     # диалог «Оспорить» живёт между апдейтами
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}, bot


_STORE = {}


async def _feed(bot, **update):
    import handlers.reports as reports
    dp = Dispatcher(storage=_STORE.setdefault("fsm", MemoryStorage()))
    dp.include_router(reports.router)
    try:
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, **update))
    finally:
        reports.router._parent_router = None


async def _press(bot, data, uid=OWNER):
    user = User(id=uid, is_bot=False, first_name="Никита")
    msg = Message(message_id=1, date=0, chat=Chat(id=uid, type="private"), from_user=user, text="🚩 Жалоба")
    await _feed(bot, callback_query=CallbackQuery(id="1", from_user=user, chat_instance="c", data=data, message=msg))


async def _say(bot, text, uid=AUTHOR):
    user = User(id=uid, is_bot=False, first_name="Автор")
    await _feed(bot, message=Message(message_id=2, date=0, chat=Chat(id=uid, type="private"), from_user=user,
                                     text=text))


async def _dispute(bot, why="Это просто дата контрольной, никого не оскорбляет", uid=AUTHOR):
    await _press(bot, "dis:1", uid=uid)
    await _say(bot, why, uid=uid)


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


@pytest.mark.asyncio
async def test_removed_author_can_dispute_and_owner_restores(env, db):
    # Никита 18.10: «добавить возможность оспорить» — автор жмёт «Оспорить»,
    # владельцу заявка «Вернуть» / «Оставить скрытым», автору ответ
    c, h, bot = env
    await db.upsert_user(AUTHOR, "author", "Автор Авторов")
    fid = await db.add_file("Лекция 3", "Анализ", "tg-file-1", "l3.pdf", AUTHOR)
    from database._conn import connect
    async with connect() as d:
        await d.execute("INSERT INTO file_text (file_id, content, char_count) VALUES (?, 'текст лекции', 12)", (fid,))
        await d.commit()
    assert c.post("/api/report", json={"kind": "file", "id": fid, "reason": "спам"}, headers=h).json() == {"ok": True}
    await _press(bot, "rep:del:1")
    from database import get_file_by_id, get_file_text
    assert await get_file_by_id(fid) is None
    to_author = [t for chat, t in bot.session.sent_texts if chat == AUTHOR]
    assert to_author and "убрали по жалобе" in to_author[-1] and "Лекция 3" in to_author[-1]

    await _dispute(bot, uid=ME)                                          # не автор — не оспорить
    import ugc
    assert (await ugc.get_report(1))["status"] == "removed"
    await _dispute(bot, "Это моя лекция с пары, не спам & не реклама")
    assert (await ugc.get_report(1))["status"] == "disputed"
    chat, text = [x for x in bot.session.sent_texts if x[0] == OWNER and "Оспаривают" in x[1]][-1]
    assert "Лекция 3" in text and "не спам &amp; не реклама" in text      # объяснение автора — Никите

    await _press(bot, "rep:back:1")
    row = await get_file_by_id(fid)
    assert row and row["file_id"] == "tg-file-1" and await get_file_text(fid) == "текст лекции"
    assert (await ugc.get_report(1))["status"] == "restored"
    assert "вернули" in [t for chat, t in bot.session.sent_texts if chat == AUTHOR][-1]
    assert (await ugc.get_report(1))["snapshot"] is None                   # копия больше не нужна


@pytest.mark.asyncio
async def test_dispute_upheld_keeps_hidden(env, db):
    c, h, bot = env
    nid = await db.add_lesson_note(DAY, "", "реклама", AUTHOR)
    c.post("/api/report", json={"kind": "note", "id": nid}, headers=h)
    await _press(bot, "rep:del:1")
    await _dispute(bot)
    await _press(bot, "rep:hold:1")
    from database import get_lesson_note
    assert await get_lesson_note(nid) is None
    assert "остаётся скрытой" in [t for chat, t in bot.session.sent_texts if chat == AUTHOR][-1]
    await _dispute(bot)                                                   # второй раз — уже пересмотрели
    import ugc
    assert (await ugc.get_report(1))["status"] == "upheld"


@pytest.mark.asyncio
async def test_dispute_asks_why_with_limits_and_cancel(env, db):
    # Никита 18.10: «пусть в оспаривании человек пишет, что и почему не согласен с удалением»
    import ugc
    c, h, bot = env
    nid = await db.add_lesson_note(DAY, "", "перенос пары", AUTHOR)
    c.post("/api/report", json={"kind": "note", "id": nid}, headers=h)
    await _press(bot, "rep:del:1")

    def owner_disputes():
        return [t for chat, t in bot.session.sent_texts if chat == OWNER and "Оспаривают" in t]

    await _press(bot, "dis:1", uid=AUTHOR)
    assert "с чем ты не согласен" in bot.session.sent_texts[-1][1]
    assert (await ugc.get_report(1))["status"] == "removed" and not owner_disputes()   # пока ждём текст
    await _say(bot, "нет")                                                # слишком коротко
    assert "подробнее" in bot.session.sent_texts[-1][1]
    await _say(bot, "а" * (ugc.APPEAL_MAX + 1))                           # слишком длинно
    assert "Сократи" in bot.session.sent_texts[-1][1] and not owner_disputes()
    await _press(bot, "dis:cancel", uid=AUTHOR)                           # передумал
    await _say(bot, "Заметка про перенос пары, всё по правилам")
    assert not owner_disputes() and (await ugc.get_report(1))["status"] == "removed"

    await _dispute(bot, "Заметка про перенос пары, всё по правилам")      # «Оспорить» можно снова
    assert (await ugc.get_report(1))["appeal"] == "Заметка про перенос пары, всё по правилам"
    assert len(owner_disputes()) == 1 and "Автор не согласен" in owner_disputes()[0]
    assert "пересмотр" in bot.session.sent_texts[-1][1]
    await _press(bot, "dis:1", uid=AUTHOR)                                # заявка уже ушла — второй нет
    assert len(owner_disputes()) == 1


@pytest.mark.asyncio
async def test_pending_dispute_outlives_purge_and_erase_drops_appeal(env, db):
    import privacy
    import ugc
    from database._conn import connect
    c, h, bot = env
    nid = await db.add_lesson_note(DAY, "", "перенос пары", AUTHOR)
    c.post("/api/report", json={"kind": "note", "id": nid}, headers=h)
    await _press(bot, "rep:del:1")
    await _dispute(bot)
    async with connect() as d:                     # спор подали в последний день срока
        await d.execute("UPDATE reports SET created_at=datetime('now', '-40 days') WHERE id=1")
        await d.commit()
    other = await db.add_lesson_note(DAY, "", "ещё заметка", AUTHOR)
    c.post("/api/report", json={"kind": "note", "id": other}, headers=h)
    await _press(bot, "rep:keep:2")                # решение по другой жалобе чистит старые копии
    assert (await ugc.get_report(1))["snapshot"]   # ждущий спор — не трогаем
    await privacy.erase(AUTHOR)
    rep = await ugc.get_report(1)
    assert rep["snapshot"] is None and rep["appeal"] == ""


@pytest.mark.asyncio
async def test_note_spam_limits(env, db, monkeypatch):
    # Никита 18.10: «чтоб не спамили» — повтор того же текста и не больше 10 за сутки
    import ratelimit
    import ugc
    c, h, _ = env
    monkeypatch.setitem(ratelimit.LIMITS, "note", (100, 600))
    from utils import today_msk
    body = {"date": today_msk().isoformat(), "text": "контрольная"}
    assert c.post("/api/notes", json=body, headers=h).status_code == 200
    r = c.post("/api/notes", json={**body, "text": "  Контрольная "}, headers=h)
    assert r.status_code == 429 and "уже есть" in r.json()["detail"]
    for i in range(ugc.NOTE_DAY - 1):
        assert c.post("/api/notes", json={**body, "text": f"заметка {i}"}, headers=h).status_code == 200
    r = c.post("/api/notes", json={**body, "text": "ещё одна"}, headers=h)
    assert r.status_code == 429 and "вся группа" in r.json()["detail"]


def test_rules_say_forbidden_and_dispute(db):
    import legal_texts
    d = legal_texts.doc("rules")
    assert d["sections"][0]["title"] == "Запрещено" and "Нельзя" not in str(d)
    assert "Оспорить" in str(d)
