"""
Реальный роутинг через aiogram Dispatcher.feed_update (не прямые вызовы
хендлеров) — так однажды был пойман баг с порядком регистрации хендлеров
в одном состоянии (catch-all перехватывал раньше специфичного). Telegram-
сессия — фейковая (без сети), но Dispatcher/Router/FSM — настоящие aiogram.
"""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import Message, Chat, User, File, PhotoSize, Update

from tests.conftest import STAROSTA_ID

USER = User(id=222, is_bot=False, first_name="Alice")
CHAT = Chat(id=222, type="private")


class FakeSession(BaseSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent_texts = []  # (chat_id, text)

    async def close(self):
        pass

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        name = type(method).__name__
        if name in ("SendMessage", "EditMessageText"):
            text = getattr(method, "text", "")
            chat_id = getattr(method, "chat_id", 0)
            self.sent_texts.append((chat_id, text))
            msg = Message(message_id=int(time.time() * 1000) % 1000000, date=0,
                          chat=Chat(id=chat_id or 1, type="private"), text=text)
            return msg.as_(bot)
        if name == "GetFile":
            return File(file_id=method.file_id, file_unique_id="uniq", file_path="fake/path.jpg")
        if name in ("AnswerCallbackQuery", "SetMyCommands"):
            return True
        raise NotImplementedError(f"FakeSession: не умею отвечать на {name}")

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b"fake-image-bytes"


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())


@pytest.fixture
def dp():
    from handlers.deadlines import router as deadlines_router
    from middleware import MenuInterruptMiddleware

    # Роутер в handlers/deadlines.py — модульный синглтон (как и в проде,
    # он один на всё приложение). aiogram не даёt прикрепить один Router-
    # объект сразу к двум Dispatcher — поэтому после каждого теста отвязываем
    # его от Dispatcher, иначе следующий тест с этой же фикстурой упадёт.
    d = Dispatcher(storage=MemoryStorage())
    d.message.middleware(MenuInterruptMiddleware())
    d.include_router(deadlines_router)
    yield d
    deadlines_router._parent_router = None  # приватный атрибут: у property-сеттера нет detach


def _make_message(text=None, photo=None):
    kwargs = dict(message_id=int(time.time() * 1000) % 1000000, date=0, chat=CHAT, from_user=USER)
    if text is not None:
        kwargs["text"] = text
    if photo is not None:
        kwargs["photo"] = photo
    return Message(**kwargs)


async def _feed(dp, bot, msg):
    update = Update(update_id=int(time.time() * 1000000) % 10**9, message=msg)
    await dp.feed_update(bot, update)


@pytest.mark.asyncio
async def test_add_flow_with_photo_description_and_strict_time(db, dp, bot, monkeypatch):
    import ai_solver

    async def fake_ocr(image_bytes, mime="image/jpeg"):
        return "Распознанный текст с фото задания"

    monkeypatch.setattr(ai_solver, "extract_text_from_image", fake_ocr)

    sess = bot.session
    await _feed(dp, bot, _make_message(text="/add"))
    await _feed(dp, bot, _make_message(text="Алгоритмы"))

    photo = [PhotoSize(file_id="ph1", file_unique_id="phu1", width=100, height=100)]
    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(photo=photo))
    assert any("Распознал с фото" in t for _, t in sess.sent_texts)
    assert any("Дата?" in t for _, t in sess.sent_texts)

    await _feed(dp, bot, _make_message(text="01.01.2099"))

    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text="22.61"))  # неверное время
    assert any("Неверное время" in t for _, t in sess.sent_texts)

    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text="22.59"))  # валидное, точка-разделитель
    assert any("Дедлайн добавлен" in t for _, t in sess.sent_texts)

    rows = await db.get_active_deadlines(USER.id)
    added = [r for r in rows if r["subject"] == "Алгоритмы"]
    assert len(added) == 1
    assert added[0]["due_time"] == "22:59"
    assert "Распознанный текст" in added[0]["description"]


@pytest.mark.asyncio
async def test_add_flow_plain_text_still_works_after_photo_handler(db, dp, bot):
    """Фото-хендлер зарегистрирован ПЕРЕД текстовым в том же состоянии —
    убеждаемся, что обычный текстовый путь этим не сломан (порядок
    хендлеров в aiogram — источник реальных багов, см. Фазу 9)."""
    sess = bot.session
    await _feed(dp, bot, _make_message(text="/add"))
    await _feed(dp, bot, _make_message(text="Экономика"))
    await _feed(dp, bot, _make_message(text="-"))
    await _feed(dp, bot, _make_message(text="02.02.2099"))
    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text="-"))
    assert any("Дедлайн добавлен" in t for _, t in sess.sent_texts)

    rows = await db.get_active_deadlines(USER.id)
    added = [r for r in rows if r["subject"] == "Экономика"]
    assert len(added) == 1 and added[0]["due_time"] is None


@pytest.mark.asyncio
async def test_done_is_personal_via_bot_command(db, dp, bot):
    sess = bot.session
    shared_id = await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)

    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text=f"/done {shared_id}"))
    assert any("отмечен как выполненный" in t for _, t in sess.sent_texts)
    assert await db.is_deadline_done(shared_id, USER.id)
    assert not await db.is_deadline_done(shared_id, 999)


@pytest.mark.asyncio
async def test_del_shared_deadline_requires_starosta(db, dp, bot):
    sess = bot.session
    shared_id = await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)

    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text=f"/del {shared_id}"))
    assert any("может только староста" in t for _, t in sess.sent_texts)
    assert await db.get_deadline(shared_id) is not None


@pytest.mark.asyncio
async def test_del_own_private_deadline_allowed(db, dp, bot):
    sess = bot.session
    own_id = await db.add_deadline("Личный", "-", "2099-01-01", None, USER.id)

    sess.sent_texts.clear()
    await _feed(dp, bot, _make_message(text=f"/del {own_id}"))
    assert any("удалён" in t for _, t in sess.sent_texts)
    assert await db.get_deadline(own_id) is None
