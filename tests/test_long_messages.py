"""
«message is too long»: живой тест — одногруппник открыл /deadlines, а там
после синка СДО 32 дедлайна с описаниями и ссылками.
"""
from datetime import timedelta

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage

from long_messages import LIMIT, SplitLongMessages, split_text


def test_split_by_lines_and_long_line():
    text = "\n".join(f"<b>строка {i}</b> " + "х" * 90 for i in range(100))
    parts = split_text(text)
    assert len(parts) > 1 and all(len(p) <= LIMIT for p in parts)
    assert "\n".join(parts) == text                       # ничего не потеряли и не переставили
    assert all(p.count("<b>") == p.count("</b>") for p in parts)
    assert [len(p) for p in split_text("я" * (LIMIT * 2 + 5))] == [LIMIT, LIMIT, 5]
    assert split_text("коротко") == ["коротко"]


@pytest.mark.asyncio
async def test_middleware_sends_parts_keyboard_on_last():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    sent = []

    async def make_request(bot, method):
        sent.append((method.text, method.reply_markup))
        return True

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ок", callback_data="x")]])
    long = "\n".join("строка " + "х" * 100 for _ in range(80))
    await SplitLongMessages()(make_request, None, SendMessage(chat_id=1, text=long, reply_markup=kb))
    assert len(sent) > 1 and all(len(t) <= LIMIT for t, _ in sent)
    assert [m for _, m in sent[:-1]] == [None] * (len(sent) - 1) and sent[-1][1] == kb
    assert "\n".join(t for t, _ in sent) == long

    sent.clear()
    await SplitLongMessages()(make_request, None, SendMessage(chat_id=1, text="коротко"))
    assert sent == [("коротко", None)]


@pytest.mark.asyncio
async def test_deadlines_list_of_40_goes_out_in_parts(db):
    import time
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    from handlers.deadlines import router
    from tests.test_solver_render import RecordingSession
    from utils import today_msk

    for i in range(40):
        await db.add_deadline(f"Практическая работа №{i} - срок сдачи (Анализ и диагностика финансово-хозяйственной "
                              f"деятельности предприятия [I.26-27])", "https://online-edu.mirea.ru/mod/assign/view.php?id=1" + "0" * 20,
                              (today_msk() + timedelta(days=i % 20)).isoformat(), "23:59", 0, external_id=f"sdo:{i}")

    class LimitSession(RecordingSession):
        async def make_request(self, bot, method, timeout=None):
            if type(method).__name__ == "SendMessage" and len(method.text) > 4096:
                raise AssertionError("message is too long")
            return await super().make_request(bot, method, timeout)

    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=LimitSession())
    bot.session.middleware(SplitLongMessages())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    user = User(id=555, is_bot=False, first_name="Одногруппник")
    try:
        msg = Message(message_id=1, date=0, chat=Chat(id=555, type="private"), from_user=user, text="/deadlines")
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, message=msg))
    finally:
        router._parent_router = None
    parts = [t for t, _ in bot.session.sent]
    assert len(parts) >= 2 and parts[0].startswith("📋 <b>Дедлайны</b> · 40")
    assert "/done ID" in parts[-1]
