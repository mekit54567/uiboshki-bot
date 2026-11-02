"""Ревью бота: состояния FSM и команды, «Подслушано» (реакции, анонимность),
доска ДЗ, фото из /upload, /vote, публикация дедлайнов в группу.
Всё через настоящий Dispatcher.feed_update, Telegram — фейковый."""
import asyncio
import inspect
import time

import aiosqlite
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, MessageId, Update, User

from tests.conftest import STAROSTA_ID

TOKEN = "123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA"
GROUP = -100500
UID = 222


class Session(BaseSession):
    """Записывает все вызовы; fail[имя метода] — исключение (или функция,
    которая его вернёт) вместо ответа; delay — пауза в отправке (гонки)."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = []
        self.fail = {}
        self.delay = 0.0

    async def close(self):
        pass

    def named(self, name):
        return [m for n, m in self.calls if n == name]

    def texts(self):
        return [m.text for m in self.named("SendMessage")]

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls.append((name, method))
        err = self.fail.get(name)
        if callable(err):
            err = err(method)
        if err:
            raise err
        if self.delay and name == "SendMessage":
            await asyncio.sleep(self.delay)
        if name == "CopyMessage":
            return MessageId(message_id=1)
        if name in ("SendMessage", "SendPhoto", "SendDocument", "EditMessageText", "EditMessageReplyMarkup"):
            chat_id = getattr(method, "chat_id", None) or UID
            return Message(message_id=int(time.time() * 1000) % 10**6, date=0,
                           chat=Chat(id=chat_id, type="private"),
                           text=getattr(method, "text", None) or "x").as_(bot)
        return True

    async def stream_content(self, *a, **kw):
        yield b""


def _bad(text):
    return TelegramBadRequest(method=None, message=text)


@pytest.fixture
def bot():
    return Bot(token=TOKEN, session=Session())


@pytest.fixture
def dp(monkeypatch):
    """Как в bot.py: middleware + все роутеры (register_handlers)."""
    import handlers.solver
    from handlers import register_handlers
    from kapibara.bot.middleware import MenuInterruptMiddleware, StatsMiddleware

    async def no_intent(text):
        return "none"
    monkeypatch.setattr(handlers.solver, "classify_intent", no_intent)   # без ИИ
    d = Dispatcher(storage=MemoryStorage())
    d.message.outer_middleware(MenuInterruptMiddleware())
    d.message.outer_middleware(StatsMiddleware())
    register_handlers(d)
    yield d
    for r in list(d.sub_routers):
        r._parent_router = None


_n = [0]


def _uid():
    _n[0] += 1
    return int(time.time() * 1000) % 10**8 + _n[0]


async def send(dp, bot, text=None, uid=UID, **kw):
    msg = Message(message_id=_uid() % 10**6, date=0, chat=Chat(id=uid, type="private"),
                  from_user=User(id=uid, is_bot=False, first_name="X"), text=text, **kw)
    await dp.feed_update(bot, Update(update_id=_uid(), message=msg))


async def press(dp, bot, data, uid=UID, text="старое сообщение", message_id=7):
    msg = Message(message_id=message_id, date=0, chat=Chat(id=uid, type="private"), text=text)
    cb = CallbackQuery(id=str(_uid()), from_user=User(id=uid, is_bot=False, first_name="X"),
                       chat_instance="c", data=data, message=msg)
    await dp.feed_update(bot, Update(update_id=_uid(), callback_query=cb))


def ctx(dp, bot, uid=UID) -> FSMContext:
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))


def _all_states():
    import handlers.announce, handlers.deadlines, handlers.feed, handlers.files_admin  # noqa: E401
    import handlers.files_upload, handlers.homework, handlers.schedule, handlers.social, handlers.solver  # noqa: E401
    mods = [handlers.announce, handlers.deadlines, handlers.feed, handlers.files_admin, handlers.files_upload,
            handlers.homework, handlers.schedule, handlers.social, handlers.solver]
    groups = {obj for m in mods for obj in vars(m).values()
              if inspect.isclass(obj) and issubclass(obj, StatesGroup) and obj is not StatesGroup}
    return sorted((s.state for g in groups for s in g.__all_states__))


ALL_STATES = _all_states()


# ── 1. Команды сбрасывают состояние ─────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("state", ALL_STATES)
async def test_cancel_works_in_every_state(db, dp, bot, state):
    await ctx(dp, bot).set_state(state)
    await send(dp, bot, "/cancel")
    assert await ctx(dp, bot).get_state() is None
    assert bot.session.texts() == ["Отменил."]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ALL_STATES)
async def test_other_command_interrupts_state(db, dp, bot, state):
    await ctx(dp, bot).set_state(state)
    await send(dp, bot, "/help")
    assert await ctx(dp, bot).get_state() is None
    assert any("/feed — «Подслушано»" in t for t in bot.session.texts())   # сама команда выполнилась


@pytest.mark.asyncio
async def test_cancel_without_state(db, dp, bot):
    await send(dp, bot, "/cancel")
    assert bot.session.texts() == ["Отменять нечего."]


@pytest.mark.asyncio
async def test_add_then_cancel_is_not_subject(db, dp, bot):
    await send(dp, bot, "/add")
    await send(dp, bot, "/cancel")        # раньше становился предметом дедлайна
    assert await ctx(dp, bot).get_state() is None
    assert "Отменил." in bot.session.texts()


@pytest.mark.asyncio
async def test_feed_help_text_does_not_post(db, dp, bot, monkeypatch):
    import handlers.feed
    monkeypatch.setattr(handlers.feed, "GROUP_CHAT_ID", GROUP)
    await send(dp, bot, "/feed")
    await send(dp, bot, "/help")
    await send(dp, bot, "секрет")
    sent_to_group = [m for n, m in bot.session.calls if getattr(m, "chat_id", None) == GROUP]
    assert sent_to_group == []


@pytest.mark.asyncio
async def test_announce_then_stats_is_not_broadcast(db, dp, bot):
    for uid in (301, 302):
        await db.upsert_user(uid, "", "")
    await send(dp, bot, "/announce", uid=STAROSTA_ID)
    await send(dp, bot, "/stats", uid=STAROSTA_ID)
    assert not [m for m in bot.session.named("SendMessage") if m.chat_id in (301, 302)]
    assert [m.chat_id for m in bot.session.named("SendPhoto")] == [STAROSTA_ID]   # /stats сработал
    assert await ctx(dp, bot, STAROSTA_ID).get_state() is None


@pytest.mark.asyncio
async def test_clearsem_needs_button_not_word(db, dp, bot):
    await db.add_deadline("Общий", "-", "2099-01-01", None, STAROSTA_ID)
    await send(dp, bot, "/clearsem", uid=STAROSTA_ID)
    assert bot.session.named("SendMessage")[-1].reply_markup is not None
    await send(dp, bot, "да", uid=STAROSTA_ID)
    assert len(await db.get_active_deadlines(STAROSTA_ID)) == 1
    await press(dp, bot, "clearsem:yes", uid=UID)                # не староста
    assert len(await db.get_active_deadlines(STAROSTA_ID)) == 1
    await press(dp, bot, "clearsem:yes", uid=STAROSTA_ID)
    assert await db.get_active_deadlines(STAROSTA_ID) == []


# ── 2–3. «Подслушано»: реакции и анонимность ────────────────────────────────

@pytest.mark.asyncio
async def test_feed_post_goes_out_with_reactions(db, dp, bot, monkeypatch):
    import handlers.feed
    monkeypatch.setattr(handlers.feed, "GROUP_CHAT_ID", GROUP)
    await send(dp, bot, "/feed")
    await send(dp, bot, "кто украл маркер")
    posted = [m for m in bot.session.named("SendMessage") if m.chat_id == GROUP]
    assert len(posted) == 1 and "кто украл маркер" in posted[0].text
    data = [b.callback_data for b in posted[0].reply_markup.inline_keyboard[0]]
    assert data and all(d.startswith("freact:") for d in data)
    assert bot.session.named("EditMessageReplyMarkup") == []


@pytest.mark.asyncio
async def test_feed_author_is_not_stored(db, monkeypatch):
    from database import social
    pid = await social.add_feed_post("текст", None, UID)
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        (author,) = await (await con.execute("SELECT author_id FROM feed_posts WHERE id=?", (pid,))).fetchone()
    assert author != UID and author == social.feed_author_hash(UID)
    # антиспам по-прежнему работает — по хэшу
    assert await social.get_last_feed_post_time(UID) is not None
    assert await social.get_last_feed_post_time(333) is None
    # другой токен — другой хэш (по копии базы без токена автора не подобрать)
    monkeypatch.setattr("kapibara.core.config.BOT_TOKEN", "999:OTHER")
    assert social.feed_author_hash(UID) != author


@pytest.mark.asyncio
async def test_old_feed_rows_are_anonymized(db):
    from database import social
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        await con.execute("INSERT INTO feed_posts (text, author_id) VALUES ('свежий', ?)", (UID,))
        await con.execute("INSERT INTO feed_posts (text, author_id, created_at) "
                          "VALUES ('старый', ?, datetime('now', '-3 days'))", (UID,))
        await con.commit()
    await social.anonymize_feed_authors()
    await social.anonymize_feed_authors()       # повторно — хэш не хэшируется ещё раз
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        rows = dict(await (await con.execute("SELECT text, author_id FROM feed_posts")).fetchall())
    assert rows == {"свежий": social.feed_author_hash(UID), "старый": 0}


@pytest.mark.asyncio
async def test_anonymous_flows_are_not_in_stats(db, dp, bot, monkeypatch):
    import handlers.feed
    import handlers.social
    from kapibara.ops import stats
    monkeypatch.setattr(stats, "_last", {})
    monkeypatch.setattr(handlers.feed, "GROUP_CHAT_ID", GROUP)
    await send(dp, bot, "/feed")
    await send(dp, bot, "анонимно")
    await send(dp, bot, "/anon")
    await send(dp, bot, "вопрос старосте")
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        assert await (await con.execute("SELECT COUNT(*) FROM events")).fetchone() == (0,)
    await send(dp, bot, "/help")
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        assert await (await con.execute("SELECT user_id, kind FROM events")).fetchall() == [(UID, "bot")]


# ── 4. ДЗ: «Удалить последнее» ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hw_delete_by_id_and_redraw(db, dp, bot):
    a, b = "Математический анализ", "Математический анализ II"     # общие первые 20 символов
    await db.add_hw(a, "старое A", None, None, STAROSTA_ID)
    a2 = await db.add_hw(a, "новое A", None, None, STAROSTA_ID)
    b1 = await db.add_hw(b, "ДЗ B", None, None, STAROSTA_ID)
    subjects = await db.get_hw_subjects()

    await press(dp, bot, f"hw:{subjects.index(b)}", uid=STAROSTA_ID)
    button = bot.session.named("EditMessageText")[-1].reply_markup.inline_keyboard[0][-1]
    assert button.callback_data == f"hwdel:{b1}"

    await press(dp, bot, f"hw:{subjects.index(a)}", uid=STAROSTA_ID)
    button = bot.session.named("EditMessageText")[-1].reply_markup.inline_keyboard[0][-1]
    assert button.callback_data == f"hwdel:{a2}"
    await press(dp, bot, button.callback_data, uid=STAROSTA_ID)
    assert [h["content"] for h in await db.get_hw_by_subject(b)] == ["ДЗ B"]          # чужой предмет цел
    assert [h["content"] for h in await db.get_hw_by_subject(a)] == ["старое A"]
    redraw = bot.session.named("EditMessageText")[-1]
    assert "новое A" not in redraw.text and redraw.reply_markup.inline_keyboard[0][-1].callback_data != button.callback_data

    await press(dp, bot, button.callback_data, uid=STAROSTA_ID)     # то же нажатие ещё раз
    assert [h["content"] for h in await db.get_hw_by_subject(a)] == ["старое A"]
    assert bot.session.named("AnswerCallbackQuery")[-1].text == "Уже удалено"


# ── 5. Фото из /upload ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_uploaded_photo_is_sent_as_photo(db, dp, bot):
    fid = await db.add_file("Фото доски", "Матан", "PHOTO_ID", "фото_55.jpg", UID)
    await press(dp, bot, f"fget:{fid}")
    assert [m.photo for m in bot.session.named("SendPhoto")] == ["PHOTO_ID"]
    assert bot.session.named("SendDocument") == []

    from handlers.start import send_file_to
    assert await send_file_to(bot, UID, fid)
    assert len(bot.session.named("SendPhoto")) == 2 and bot.session.named("SendDocument") == []


@pytest.mark.asyncio
async def test_photo_with_other_name_falls_back(db, bot):
    from handlers.start import send_file_to
    fid = await db.add_file("Скан", "Матан", "PHOTO_ID", "скан.pdf", UID)
    bot.session.fail["SendDocument"] = _bad("Bad Request: can't use file of type Photo as Document")
    assert await send_file_to(bot, UID, fid)
    assert [m.photo for m in bot.session.named("SendPhoto")] == ["PHOTO_ID"]


# ── 6. /vote: тот же голос ещё раз ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_same_vote_twice_is_quiet(db, dp, bot):
    vote_id = await db.create_vote("Идём в пятницу?", STAROSTA_ID)
    await press(dp, bot, f"vote:{vote_id}:да")
    bot.session.fail["EditMessageText"] = _bad("Bad Request: message is not modified")
    await press(dp, bot, f"vote:{vote_id}:да")                   # раньше — исключение и алерт старосте
    answers = bot.session.named("AnswerCallbackQuery")
    assert len(answers) == 2 and all("Твой голос: да" in a.text for a in answers)


# ── 7. «Опубликовать в группу» дважды ───────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_post_double_click_posts_once(db, dp, bot, monkeypatch):
    import handlers.deadlines
    monkeypatch.setattr(handlers.deadlines, "GROUP_CHAT_ID", GROUP)
    bot.session.delay = 0.05
    await asyncio.gather(*(press(dp, bot, "dlpost:yes", uid=STAROSTA_ID, text="⏰ Завтра: лаба 3",
                                 message_id=4242) for _ in range(3)))
    posted = [m for m in bot.session.named("SendMessage") if m.chat_id == GROUP]
    assert len(posted) == 1
    assert sorted(a.text for a in bot.session.named("AnswerCallbackQuery")) == \
        ["Опубликовано!", "Уже опубликовано", "Уже опубликовано"]
