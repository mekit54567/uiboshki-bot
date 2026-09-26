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

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name in ("SendDocument", "SendPhoto"):
            self.docs.append((name, getattr(method, "document", None) or getattr(method, "photo", None), method.caption))
            return Message(message_id=1, date=0, chat=Chat(id=USER.id, type="private")).as_(bot)
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
