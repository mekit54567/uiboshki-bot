"""«Срок скоро, а ты не сдал» (Никита 25.10): за N часов до срока (по
умолчанию 3), только не сданное, один раз, время — в настройках везде."""
from datetime import datetime, timedelta

import pytest

import deadline_soon as ds
import notify_prefs
from utils import TZ

DUE = datetime(2099, 3, 10, 23, 59, tzinfo=TZ)
QUIZ = "https://online-edu.mirea.ru/mod/quiz/view.php?id=501"


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text, **kw):
        self.sent.append((uid, text))


def test_prefs():
    p = notify_prefs.merge(None)
    assert p["deadline_soon"] is True and p["deadline_soon_hours"] == 3
    assert notify_prefs.merge({"deadline_soon_hours": 6})["deadline_soon_hours"] == 6
    assert notify_prefs.merge({"deadline_soon_hours": 5})["deadline_soon_hours"] == 3     # такого выбора нет


def test_text():
    d = {"subject": "Практика 2 · Анализ данных", "due_date": "2099-03-10", "due_time": None}
    title, body, html = ds.text(d, 3, DUE - timedelta(hours=3))
    assert title == "Через 3 ч срок: Практика 2"
    assert body == "Анализ данных · сегодня до 23:59 · ещё не сдано"
    assert "не отмечена сданной" in html


@pytest.mark.asyncio
async def test_send_once_not_done_and_own_hours(db):
    for uid in (1, 2, 3, 4):
        await db.upsert_user(uid, "", "")
    await db.set_notify(2, {"deadline_soon": False})
    await db.set_notify(4, {"deadline_soon_hours": 24})
    did = await db.add_deadline("Практика 2 · Анализ данных", "", "2099-03-10", None, 0)
    await db.set_deadline_done(did, 3, True)                     # 3 — уже сдал
    bot = FakeBot()
    assert await ds.send_due(bot, DUE - timedelta(hours=3, minutes=5)) == 0     # ещё рано
    assert await ds.send_due(bot, DUE - timedelta(hours=3)) == 1
    assert await ds.send_due(bot, DUE - timedelta(hours=2, minutes=55)) == 0   # второй раз — нет
    assert [u for u, _ in bot.sent] == [1]
    assert await ds.send_due(bot, DUE - timedelta(hours=2)) == 0                # окно прошло
    assert await ds.send_due(bot, DUE - timedelta(hours=24)) == 1               # у 4 — за сутки
    assert bot.sent[-1][0] == 4 and "Через 1 день срок" not in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_quiz_skipped_when_quiz_reminders_on(db):
    for uid in (1, 2):
        await db.upsert_user(uid, "", "")
    await db.set_notify(1, {"quiz_remind": [60]})
    await db.add_deadline("Тест 3 · ООП", QUIZ, "2099-03-10", "12:00", 0, external_id="sdo:7")
    bot = FakeBot()
    await ds.send_due(bot, datetime(2099, 3, 10, 9, 0, tzinfo=TZ))
    assert [u for u, _ in bot.sent] == [2]


def test_settings_everywhere():
    """Время «Срок скоро» — и в Mini App, и в PWA, и в приложении."""
    assert "setSoonHours(" in open("webapp/static/js/more.js", encoding="utf-8").read()
    assert "deadline_soon_hours" in open("webapp/static/app-html/js/screens/settings.js", encoding="utf-8").read()
    assert "deadline_soon_hours" in open("app/lib/screens/notify.dart", encoding="utf-8").read()


@pytest.mark.asyncio
async def test_api_gives_choices(db):
    from webapp.routes.account import _notify_view
    await db.upsert_user(1, "", "")
    view = await _notify_view(1)
    assert view["deadline_soon_choices"] == [1, 3, 6, 12, 24] and view["prefs"]["deadline_soon_hours"] == 3


@pytest.mark.asyncio
async def test_telegram_settings_buttons(db):
    import time

    from aiogram import Bot
    from aiogram.types import CallbackQuery, Chat, Message, Update

    from handlers.start import router
    from tests.test_cosmetics import USER, _dp
    from tests.test_solver_render import RecordingSession

    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = _dp(router)
    await db.upsert_user(USER.id, "", "Alice")

    async def click(data):
        msg = Message(message_id=77, date=0, chat=Chat(id=USER.id, type="private"), text="⚙️")
        cb = CallbackQuery(id="1", from_user=USER, chat_instance="c", data=data, message=msg)
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, callback_query=cb))

    try:
        await click("set:soon:6")
        assert notify_prefs.merge((await db.get_user(USER.id))["notify"])["deadline_soon_hours"] == 6
        await click("set:soon:5")                                     # чужое значение — игнор
        assert notify_prefs.merge((await db.get_user(USER.id))["notify"])["deadline_soon_hours"] == 6
        await click("set:soon:0")
        assert notify_prefs.merge((await db.get_user(USER.id))["notify"])["deadline_soon"] is False
    finally:
        router._parent_router = None
    assert "не напоминать" in [t for _, t in bot.session.sent_texts if "Настройки" in t][-1]
