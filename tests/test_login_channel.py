"""Канал при первом входе через Telegram (login_channel.py, 5.97.0): новый
человек подписывается на канал, жмёт «Я в канале, дальше», бот проверяет и
только потом спрашивает «это вы?» или здоровается. Из приложения из стора —
с «Позже». Кто был до канала, — как раньше. /start ios — без строк об оплате."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, ChatMemberLeft, ChatMemberMember, Message, Update, User

from tests.test_deadlines_routing import FakeSession

UID = 778


class ChannelSession(FakeSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.members, self.alerts, self.keyboards = set(), [], []

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "GetChatMember":
            user = User(id=method.user_id, is_bot=False, first_name="Аня")
            return ChatMemberMember(user=user) if method.user_id in self.members else ChatMemberLeft(user=user)
        if name == "AnswerCallbackQuery":
            self.alerts.append(method.text or "")
            return True
        if name in ("DeleteMessage", "EditMessageReplyMarkup"):
            return True
        if name in ("SendMessage", "EditMessageText"):
            kb = getattr(method, "reply_markup", None)
            self.keyboards.append([b.text for row in getattr(kb, "inline_keyboard", []) or [] for b in row])
        return await super().make_request(bot, method, timeout)


async def _say(dp, bot, text=None, data=None):
    user = User(id=UID, is_bot=False, first_name="Аня")
    msg = Message(message_id=1, date=0, chat=Chat(id=UID, type="private"), from_user=user, text=text or "x")
    if data:
        upd = Update(update_id=int(time.time() * 1000) % 10**9,
                     callback_query=CallbackQuery(id="1", from_user=user, chat_instance="c", data=data, message=msg))
    else:
        upd = Update(update_id=int(time.time() * 1000) % 10**9, message=msg)
    await dp.feed_update(bot, upd)


@pytest.fixture
def env(db, monkeypatch):
    import config
    import handlers.start as start
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "https://t.me/kapibara_news")
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=ChannelSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    yield bot, dp
    start.router._parent_router = None


async def _since_before_user(db):
    """Канал включили раньше, чем человек пришёл."""
    from database import set_setting
    await set_setting("login_channel:since:@kapibara_news", "2000-01-01 00:00:00")


def test_channel_name_forms(monkeypatch):
    import config
    import login_channel
    for v, want in (("https://t.me/kapibara_news", "@kapibara_news"), ("@kapibara_news", "@kapibara_news"),
                    ("kapibara_news", "@kapibara_news"), ("-1001234", "-1001234"), ("", "")):
        monkeypatch.setattr(config, "LOGIN_CHANNEL", v)
        assert login_channel.channel() == want
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "@kapibara_news")
    assert login_channel.link() == "https://t.me/kapibara_news"
    assert login_channel.store_app("Капибара · iPhone") and not login_channel.store_app("Chrome · Android")


@pytest.mark.asyncio
async def test_new_user_login_waits_for_channel(env, db):
    from database.sessions import create_login, get_login
    bot, dp = env
    await _since_before_user(db)
    code = await create_login("Chrome · Android")
    await _say(dp, bot, text=f"/start login_{code}")
    text = bot.session.sent_texts[-1][1]
    assert "подпишись на канал" in text and "Да, это я" not in str(bot.session.keyboards[-1])
    assert bot.session.keyboards[-1] == ["Открыть канал", "Я в канале, дальше"]       # без «Позже»

    await _say(dp, bot, data=f"chan:ok:login:{code}")                              # ещё не подписан
    assert "не вижу подписки" in bot.session.alerts[-1]
    assert bot.session.sent_texts[-1][1] == text

    bot.session.members.add(UID)
    await _say(dp, bot, data=f"chan:ok:login:{code}")
    assert "Войти в приложение" in bot.session.sent_texts[-1][1]
    assert bot.session.keyboards[-1] == ["✅ Да, это я", "Нет"]
    assert (await get_login(code))["status"] == "wait"                              # дальше — как раньше

    code2 = await create_login("Chrome · Android")                                  # прошёл — больше не спрашиваем
    bot.session.members.clear()
    await _say(dp, bot, text=f"/start login_{code2}")
    assert "Войти в приложение" in bot.session.sent_texts[-1][1]


@pytest.mark.asyncio
async def test_store_app_login_can_skip(env, db):
    from database.sessions import create_login
    bot, dp = env
    await _since_before_user(db)
    code = await create_login("Капибара · iPhone")
    await _say(dp, bot, text=f"/start login_{code}")
    assert "Позже" in bot.session.keyboards[-1] and "вход от этого не зависит" in bot.session.sent_texts[-1][1]
    await _say(dp, bot, data=f"chan:later:login:{code}")
    assert "Войти в приложение" in bot.session.sent_texts[-1][1]


@pytest.mark.asyncio
async def test_old_users_and_no_channel_as_before(env, db, monkeypatch):
    import config
    import login_channel
    from database.sessions import create_login
    bot, dp = env
    await db.upsert_user(UID, "anya", "Аня")
    await login_channel.start()                    # канал включили после того, как человек пришёл
    code = await create_login("Chrome · Android")
    await _say(dp, bot, text=f"/start login_{code}")
    assert "Войти в приложение" in bot.session.sent_texts[-1][1]

    monkeypatch.setattr(config, "LOGIN_CHANNEL", "")
    assert await login_channel.needed(bot, UID + 1) is False


@pytest.mark.asyncio
async def test_telegram_silent_does_not_block(env, db):
    import login_channel

    class Broken:
        async def get_chat_member(self, *a):
            raise RuntimeError("bot is not a member of the channel chat")
    await _since_before_user(db)
    assert await login_channel.needed(Broken(), UID) is False


@pytest.mark.asyncio
async def test_new_user_start_then_welcome(env, db):
    bot, dp = env
    await _since_before_user(db)
    await _say(dp, bot, text="/start")
    assert "подпишись на канал" in bot.session.sent_texts[-1][1]
    bot.session.members.add(UID)
    await _say(dp, bot, data="chan:ok:start")
    assert any("Привет" in t for _, t in bot.session.sent_texts[-3:])


def test_ios_welcome_has_no_pay_lines():
    from handlers.start import start_text, without_pay
    text = start_text("Аня") + "\n\n✨ Всё это бесплатно. Хочешь больше — /plus: подписка «Капибара+», оплата на сайте."
    clean = without_pay(text)
    assert "/plus" not in clean and "оплат" not in clean and "Привет" in clean
    assert "uiboshki.ru/app" in clean                         # про другие места — остаётся


@pytest.mark.asyncio
async def test_start_ios_welcome(env, db, monkeypatch):
    import config
    bot, dp = env
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "")
    await _say(dp, bot, text="/start ios")
    sent = " ".join(t for _, t in bot.session.sent_texts)
    assert "Привет" in sent and "/plus" not in sent


@pytest.mark.asyncio
async def test_erase_forgets_channel_mark(db):
    import privacy
    from database import get_setting, set_setting
    await db.upsert_user(UID, "anya", "Аня")
    await set_setting(f"login_channel:{UID}", "1")
    await privacy.erase(UID)
    assert await get_setting(f"login_channel:{UID}") is None
