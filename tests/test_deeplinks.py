"""Диплинк t.me/<бот>?start=hw_<id> — кнопка «Открыть файл» у ДЗ в WebApp."""
import time

import aiosqlite
import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User

from tests.test_solver_render import RecordingSession

USER = User(id=222, is_bot=False, first_name="Alice")


class DocSession(RecordingSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.docs = []
        self.deleted = []

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name in ("SendDocument", "SendPhoto"):
            self.docs.append((name, getattr(method, "document", None) or getattr(method, "photo", None), method.caption))
            return Message(message_id=1, date=0, chat=Chat(id=USER.id, type="private")).as_(bot)
        if name == "DeleteMessage":
            self.deleted.append(method.message_id)
        return await super().make_request(bot, method, timeout)


@pytest.mark.asyncio
async def test_hw_deeplink_sends_file(db):
    from handlers.start import router
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        await con.execute("CREATE TABLE homework (id INTEGER PRIMARY KEY, subject TEXT, content TEXT, file_id TEXT, "
                          "file_type TEXT, created_by INTEGER, created_at TEXT DEFAULT (datetime('now')), lesson_date TEXT)")
        await con.execute("INSERT INTO homework (subject, content, file_id, file_type) VALUES ('Анализ', 'задачи <1–5>', 'TGDOC', 'document')")
        await con.commit()
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=DocSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        for i, payload in enumerate(("hw_1", "hw_999")):
            msg = Message(message_id=10 + i, date=0, chat=Chat(id=USER.id, type="private"), from_user=USER,
                          text=f"/start {payload}")
            await dp.feed_update(bot, Update(update_id=int(time.time()) + i, message=msg))
    finally:
        router._parent_router = None
    assert bot.session.docs == [("SendDocument", "TGDOC", "📝 <b>Анализ</b>\nзадачи &lt;1–5&gt;")]
    assert any("Файл ДЗ не найден" in t for t, _ in bot.session.sent)


@pytest.mark.asyncio
async def test_file_deeplink_sends_file_and_wipes_start(db):
    # живой тест: после каждого «Открыть» в чате оставалось «/start file_N»
    from database import add_file
    from handlers.start import router
    fid = await add_file("ЛК1", "Основы предпринимательской деятельности", "TGF", "lk1.pdf", 0)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=DocSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        msg = Message(message_id=77, date=0, chat=Chat(id=USER.id, type="private"), from_user=USER,
                      text=f"/start file_{fid}")
        await dp.feed_update(bot, Update(update_id=int(time.time()), message=msg))
    finally:
        router._parent_router = None
    assert bot.session.docs == [("SendDocument", "TGF", "📄 <b>ЛК1</b> (Основы предпринимательской деятельности)")]
    assert bot.session.deleted == [77]


@pytest.mark.asyncio
async def test_webapp_send_file_goes_to_chat_without_start(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from database import add_file
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    fid = await add_file("ЛК2", "ОПД", "TGF2", "lk2.pdf", 0)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=DocSession())
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(server.deps, "tg_bot", lambda: bot)
    c, headers = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.post(f"/api/files/{fid}/send", headers=headers).json() == {"ok": True}
    assert bot.session.docs == [("SendDocument", "TGF2", "📄 <b>ЛК2</b> (ОПД)")]
    assert c.post("/api/files/999/send", headers=headers).status_code == 404


@pytest.mark.asyncio
async def test_site_deeplink_counts_in_stats(db, monkeypatch):
    # кнопки сайта /about ведут на ?start=site — в /stats видно, сколько пришло с сайта
    from kapibara.ops import stats
    from handlers.start import router
    monkeypatch.setattr(stats, "_last", {})
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=DocSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        msg = Message(message_id=30, date=0, chat=Chat(id=USER.id, type="private"), from_user=USER, text="/start site")
        await dp.feed_update(bot, Update(update_id=int(time.time()) + 50, message=msg))
    finally:
        router._parent_router = None
    assert bot.session.sent                                                     # обычное приветствие
    s = await stats.collect(7)
    assert s["from_site"] == 1 and "с сайта за 7 дн.: <b>1</b>" in stats.summary(s)
