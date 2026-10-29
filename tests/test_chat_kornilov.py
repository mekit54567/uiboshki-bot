"""Обновление чата бота («Корнилов»): короткий /start, кнопка приложения."""
import time

import pytest

import config


@pytest.mark.asyncio
async def test_start_is_one_short_message_with_app_button(db, monkeypatch):
    # «Корнилов»: вместо простыни и большой клавиатуры — одно сообщение,
    # старая клавиатура убирается, к сообщению цепляется кнопка приложения
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    import keyboards
    from handlers import start
    from tests.test_solver_render import RecordingSession

    class Session(RecordingSession):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.markups = []

        async def make_request(self, bot, method, timeout=None):
            name = type(method).__name__
            if name in ("SendMessage", "EditMessageReplyMarkup"):
                self.markups.append((name, type(method.reply_markup).__name__))
            if name == "EditMessageReplyMarkup":
                return True
            return await super().make_request(bot, method, timeout)

    monkeypatch.setattr(config, "WEBAPP_URL", "https://app.example")
    monkeypatch.setattr(config, "OPTIONAL_SUBJECTS", [])
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=Session())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    try:
        u = User(id=222, is_bot=False, first_name="Милюков")
        msg = Message(message_id=1, date=0, chat=Chat(id=222, type="private"), from_user=u, text="/start")
        await dp.feed_update(bot, Update(update_id=int(time.time()), message=msg))
    finally:
        start.router._parent_router = None
    texts = [t for t, _ in bot.session.sent]
    assert len(texts) == 1 and "Привет, <b>Милюков</b>" in texts[0] and "В приложении" in texts[0]
    assert bot.session.markups[0] == ("SendMessage", "ReplyKeyboardRemove")
    assert ("EditMessageReplyMarkup", "InlineKeyboardMarkup") in bot.session.markups
    kb = keyboards.app_button("📋 Открыть дедлайны", "deadlines")
    assert kb.inline_keyboard[0][0].web_app.url == "https://app.example?tab=deadlines"
