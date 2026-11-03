"""Бот в чате своей группы (Никита 03.11): утренняя карточка дня «Мел»,
/say — староста пишет в чат от имени бота, чат — и запомненный при
добавлении бота, не только GROUP_CHAT_ID."""
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from kapibara.core import config

CHAT = -100555
L = {"num": 1, "pairs": 2, "start": "09:00", "end": "12:10", "title": "Моделирование бизнес-процессов",
     "kind": "лекция", "room": "А-17 (В-78)", "teacher": "Иванов И."}


class Bot:
    def __init__(self):
        self.photos, self.copies, self.pins = [], [], []

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        self.photos.append((chat_id, photo, caption, reply_markup))

    async def copy_message(self, chat_id, from_chat_id, message_id):
        self.copies.append((chat_id, from_chat_id, message_id))
        return SimpleNamespace(message_id=99)

    async def pin_chat_message(self, chat_id, message_id, disable_notification=False):
        self.pins.append((chat_id, message_id))


@pytest.fixture
def remembered_chat(db, monkeypatch):
    """GROUP_CHAT_ID не задан, чат запомнен, когда бота добавили в группу."""
    from kapibara.features.groups import members
    from kapibara.jobs import scheduler
    monkeypatch.setattr(config, "GROUP_CHAT_ID", 0)
    monkeypatch.setattr(scheduler, "GROUP_CHAT_ID", 0)
    members.forget_chat()
    yield db
    members.forget_chat()


@pytest.fixture
def lessons(monkeypatch):
    from kapibara.features.schedule import parser
    from kapibara.jobs import scheduler
    day = {"list": [L]}

    async def raw(force=False):
        return b""

    monkeypatch.setattr(scheduler, "fetch_schedule_raw", raw)
    monkeypatch.setattr(parser, "lessons_for_date", lambda raw, d, now=None: list(day["list"]))
    return day


@pytest.mark.asyncio
async def test_morning_card_goes_to_remembered_chat(remembered_chat, lessons):
    from kapibara.jobs import scheduler
    bot = Bot()
    assert await scheduler.send_group_morning(bot) == "no_chat"              # чат ещё не знаем
    await remembered_chat.set_setting("group_chat_id", str(CHAT))
    from kapibara.features.groups import members
    members.forget_chat()
    assert await scheduler.send_group_morning(bot) == "sent"
    chat_id, photo, caption, kb = bot.photos[0]
    assert chat_id == CHAT and photo.data[:2] == b"\xff\xd8"                  # JPEG-карточка
    assert "2 пары" in caption and "А-17" in caption and "startapp" in kb.inline_keyboard[0][0].url
    await remembered_chat.set_setting("group_morning", "off")
    assert await scheduler.send_group_morning(bot) == "off" and len(bot.photos) == 1
    lessons["list"] = []
    assert await scheduler.send_group_morning(bot, 1) == "no_lessons"         # пар нет — молчим


def test_morning_caption_drops_long_notes():
    from kapibara.jobs.scheduler import morning_caption
    assert "Заметки" in morning_caption([L], "\n\n📌 Заметки: взять ноутбук")
    assert "Заметки" not in morning_caption([L], "\n\n📌 Заметки: " + "x" * 1200)   # лимит подписи 1024


async def _state(uid=1):
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=uid, user_id=uid))


class Msg:
    def __init__(self):
        self.chat, self.edits, self.markup = SimpleNamespace(id=1), [], "kb"

    async def edit_reply_markup(self, reply_markup=None):
        self.markup = reply_markup

    async def edit_text(self, text):
        self.edits.append(text)


@pytest.mark.asyncio
async def test_say_copies_to_group_and_pins(remembered_chat, monkeypatch):
    from handlers import members_chat
    monkeypatch.setattr(config, "GROUP_CHAT_ID", CHAT)
    monkeypatch.setattr(config, "is_starosta", lambda uid: uid == 1)
    bot, state, msg = Bot(), await _state(), Msg()
    await state.update_data(say_msg=42)

    async def answer(*a, **kw):
        pass

    cb = SimpleNamespace(from_user=SimpleNamespace(id=1), data="say:pin", message=msg, answer=answer)
    await members_chat.say_confirm(cb, state, bot)
    assert bot.copies == [(CHAT, 1, 42)] and bot.pins == [(CHAT, 99)] and "закрепил" in msg.edits[-1]
    await members_chat.say_confirm(cb, state, bot)                            # второе нажатие — не дублирует
    assert len(bot.copies) == 1


@pytest.mark.asyncio
async def test_say_only_for_starosta(remembered_chat, monkeypatch):
    from handlers import members_chat
    monkeypatch.setattr(config, "is_starosta", lambda uid: False)
    shown = []

    async def answer(text, show_alert=False):
        shown.append(text)

    bot, state = Bot(), await _state(7)
    await state.update_data(say_msg=42)
    cb = SimpleNamespace(from_user=SimpleNamespace(id=7), data="say:send", message=Msg(), answer=answer)
    await members_chat.say_confirm(cb, state, bot)
    assert bot.copies == [] and shown
