"""kapibara/bot/tg.py: узкие геттеры событий Telegram и ответ на кнопку под
устаревшим сообщением (InaccessibleMessage) — через настоящий dp.error, как в bot.py."""
import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, Message, Update, User

import bot as bot_module
from kapibara.bot import tg
from kapibara.core.errors import StaleMessage
from kapibara.core.telegram import cosmetic

TOKEN = "123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA"
USER = User(id=222, is_bot=False, first_name="Alice")
CHAT = Chat(id=222, type="private")


class FakeSession(BaseSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        self.calls.append(method)
        if type(method).__name__ == "SendMessage":
            return Message(message_id=1, date=0, chat=CHAT, text=method.text).as_(bot)
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


def _msg(**kw):
    return Message(message_id=5, date=0, chat=CHAT, **kw)


def _cb(message, data="x"):
    return CallbackQuery(id="1", from_user=USER, chat_instance="c", message=message, data=data)


def test_sender_text_data():
    m = _msg(from_user=USER, text="/nicks")
    assert tg.sender(m) is USER and tg.text_of(m) == "/nicks"
    assert tg.text_of(_msg(from_user=USER, caption="подпись")) == ""     # подпись не подменяет текст
    with pytest.raises(RuntimeError):
        tg.sender(_msg(text="пост канала"))
    assert tg.data_of(_cb(None, data="nick:reset:5")) == "nick:reset:5"
    assert tg.data_of(CallbackQuery(id="1", from_user=USER, chat_instance="c")) == ""


def test_msg_and_bot():
    m = _msg(from_user=USER, text="hi")
    assert tg.msg(_cb(m)) is m
    with pytest.raises(StaleMessage):
        tg.msg(_cb(InaccessibleMessage(chat=CHAT, message_id=5)))
    with pytest.raises(StaleMessage):
        tg.msg(_cb(None))
    with pytest.raises(RuntimeError):
        tg.bot_of(m)                            # вне диспетчера бота нет
    b = Bot(token=TOKEN, session=FakeSession())
    assert tg.bot_of(m.as_(b)) is b


def test_cosmetic_swallows_stale():
    with cosmetic("тест"):
        tg.msg(_cb(None))                       # не долетает наружу


@pytest.mark.asyncio
async def test_stale_button_answers_without_alert(monkeypatch):
    alerts = []

    async def no_alert(event, bot):
        alerts.append(event.exception)

    monkeypatch.setattr(bot_module, "notify_starosta_on_error", no_alert)
    fake_bot = Bot(token=TOKEN, session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.error.register(tg.stale_message, ExceptionTypeFilter(StaleMessage))
    dp.error.register(bot_module.notify_starosta_on_error)

    router = Router()

    @router.callback_query()
    async def edit(callback: CallbackQuery):
        await tg.msg(callback).edit_text("новое")

    dp.include_router(router)
    cb = _cb(InaccessibleMessage(chat=CHAT, message_id=5), data="nick:reset:5")
    await dp.feed_update(fake_bot, Update(update_id=1, callback_query=cb))

    assert alerts == []
    answers = [c for c in fake_bot.session.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert answers and answers[0].text == tg.STALE_TEXT


def test_document_of():
    from aiogram.types import Document
    doc = Document(file_id="f1", file_unique_id="u1", file_name="files.json")
    assert tg.document_of(_msg(from_user=USER, document=doc)) is doc
    with pytest.raises(RuntimeError):
        tg.document_of(_msg(from_user=USER, text="без файла"))


@pytest.mark.asyncio
async def test_download_bytes():
    import io

    class FakeBot:
        def __init__(self, out):
            self.out, self.asked = out, []

        async def download(self, file):
            self.asked.append(file)
            return self.out

    b = FakeBot(io.BytesIO(b'{"a": 1}'))
    assert await tg.download_bytes(b, "f1") == b'{"a": 1}' and b.asked == ["f1"]
    with pytest.raises(RuntimeError):
        await tg.download_bytes(FakeBot(None), "f1")
