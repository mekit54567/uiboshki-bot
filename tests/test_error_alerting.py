"""
bot.notify_starosta_on_error: реальная проводка через aiogram (dp.error),
не прямой вызов функции — убеждаемся, что падение хендлера действительно
долетает до алерта, а не просто "функция существует и красиво выглядит".
"""
import time

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import Message, Chat, User, Update

import bot as bot_module
from tests.conftest import STAROSTA_ID


class FakeSession(BaseSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.sent_texts = []

    async def close(self):
        pass

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        if type(method).__name__ == "SendMessage":
            text = getattr(method, "text", "")
            chat_id = getattr(method, "chat_id", 0)
            self.sent_texts.append((chat_id, text))
            return Message(message_id=1, date=0, chat=Chat(id=chat_id, type="private"), text=text).as_(bot)
        raise NotImplementedError(type(method).__name__)

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


@pytest.mark.asyncio
async def test_handler_crash_alerts_starosta(monkeypatch):
    # -inf, не 0.0: на свежем процессе time.monotonic() сам может быть
    # маленьким числом (реальный баг, пойманный CI — см. bot.py) — 0.0 тут
    # маскировал бы регрессию обратно.
    monkeypatch.setattr(bot_module, "_LAST_ERROR_ALERT_AT", float("-inf"))

    fake_bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.error.register(bot_module.notify_starosta_on_error)

    router = Router()

    @router.message()
    async def boom(message):
        raise RuntimeError("тестовый сбой хендлера")

    dp.include_router(router)

    msg = Message(message_id=1, date=0, chat=Chat(id=222, type="private"),
                  from_user=User(id=222, is_bot=False, first_name="Alice"), text="привет")
    update = Update(update_id=1, message=msg)
    await dp.feed_update(fake_bot, update)

    sent = fake_bot.session.sent_texts
    assert any(chat_id == STAROSTA_ID and "тестовый сбой хендлера" in text for chat_id, text in sent), sent


@pytest.mark.asyncio
async def test_error_alert_is_throttled(monkeypatch):
    monkeypatch.setattr(bot_module, "_LAST_ERROR_ALERT_AT", time.monotonic())  # "только что" был алерт

    fake_bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.error.register(bot_module.notify_starosta_on_error)

    router = Router()

    @router.message()
    async def boom(message):
        raise RuntimeError("повторный сбой сразу после предыдущего")

    dp.include_router(router)

    msg = Message(message_id=1, date=0, chat=Chat(id=222, type="private"),
                  from_user=User(id=222, is_bot=False, first_name="Alice"), text="привет")
    await dp.feed_update(fake_bot, Update(update_id=1, message=msg))

    assert fake_bot.session.sent_texts == [], "троттлинг не сработал — алерт ушёл повторно раньше кулдауна"
