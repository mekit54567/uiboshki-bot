"""Этап 1 (а): любая группа института — группа человека, тариф, лимиты ИИ
по тарифу, выбор группы в боте и WebApp."""
import time
from datetime import date

import aiosqlite
import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

import config
import ratelimit
from tests.conftest import STAROSTA_ID
from tests.test_deadlines_routing import FakeSession

HOME = config.HOME_GROUP_ID
OTHER = 5001


@pytest.fixture
def index(monkeypatch):
    """Справочник расписания без сети: две группы."""
    import schedule_index
    names = {HOME: config.GROUP_NAME, OTHER: "УИБО-01-24"}

    async def search(q, types=(1, 2, 3), limit=20):
        return [{"type": 1, "id": i, "title": t} for i, t in names.items() if q.lower() in t.lower()][:limit]

    async def get_title(t, i):
        return names.get(i) if t == 1 else None

    monkeypatch.setattr(schedule_index, "search", search)
    monkeypatch.setattr(schedule_index, "get_title", get_title)
    return names


def test_home_group_from_ical_url():
    assert HOME == 4928                                                     # УИБО-03-24 на зеркале


@pytest.mark.asyncio
async def test_old_users_land_in_home_group(tmp_path, monkeypatch):
    """Кто был в боте до этапа 1 — в своей группе, без вопроса."""
    import database
    path = str(tmp_path / "old.db")
    async with aiosqlite.connect(path) as db:
        await db.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, "
                         "subscribed INTEGER DEFAULT 1, reminder_minutes INTEGER DEFAULT 15, joined_at TEXT)")
        await db.execute("INSERT INTO users (user_id, username, full_name) VALUES (7, 'old', 'Old')")
        await db.commit()
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    await database.init_db()
    assert await database.get_user_group(7) == HOME
    await database.init_db()                                                # повторный запуск ничего не ломает
    await database.upsert_user(8, "new", "New")
    assert await database.get_user_group(8) is None                         # новый выбирает сам


@pytest.mark.asyncio
async def test_choose_and_plans(db, index):
    import groups
    import plans
    await db.upsert_user(10, "a", "A")
    assert await plans.plan_of(10) == plans.BASE                            # группы ещё нет
    assert await groups.choose(10, 999999) is None                          # нет в справочнике
    g = await groups.choose(10, OTHER)
    assert g == {"id": OTHER, "name": "УИБО-01-24", "own": False}
    assert await groups.of_user(10) == {"id": OTHER, "name": "УИБО-01-24", "own": False}
    assert await plans.plan_of(10) == plans.BASE
    await groups.choose(10, HOME)
    assert (await groups.of_user(10))["own"] and await plans.plan_of(10) == plans.SUB     # подарок «Капибары+»
    await db.set_setting("plus:gift", "off")
    assert await plans.plan_of(10) == plans.OWN                             # подарок кончился — своя группа
    await groups.choose(10, OTHER)
    await db.set_subscription_until(10, "2999-01-01")
    assert await plans.plan_of(10) == plans.SUB
    await db.set_subscription_until(10, "2000-01-01")                       # кончилась
    assert await plans.plan_of(10) == plans.BASE
    assert await plans.plan_of(STAROSTA_ID) == plans.OWN                    # Никита — всегда
    assert groups.ical_url(OTHER).endswith("/ical/1/5001") and groups.ical_url(HOME) == config.ICAL_URL


@pytest.mark.asyncio
async def test_single_group_copy_has_no_plans(db, monkeypatch):
    """Копия бота на одну группу (ICAL_URL без id) — у всех ИИ как раньше."""
    import plans
    monkeypatch.setattr(config, "HOME_GROUP_ID", 0)
    await db.upsert_user(11, "b", "B")
    assert await plans.plan_of(11) == plans.OWN


@pytest.mark.asyncio
async def test_ai_limits_by_plan(db, index, monkeypatch):
    import ai_quota
    import groups
    day = [date(2026, 10, 8)]
    monkeypatch.setattr("utils.today_msk", lambda: day[0])
    monkeypatch.setattr(ratelimit, "allow", lambda action, uid: True)
    for uid in (20, 21, 22):
        await db.upsert_user(uid, "u", "U")
        await groups.choose(uid, OTHER)
    # база: проба — AI_TRIAL_DAILY вопросов в день
    for _ in range(config.AI_TRIAL_DAILY):
        assert await ai_quota.gate(20) is None
    assert await ai_quota.gate(20) == "trial"
    assert "3 в день" in ai_quota.text("trial") and "подписке" in ai_quota.text("trial")
    # потолок пробы на всех
    monkeypatch.setattr(config, "AI_TRIAL_DAY_TOTAL", 4)
    assert await ai_quota.gate(21) is None
    assert await ai_quota.gate(21) == "trial_all"
    # конспекты — свой недельный счёт, вопросы на него не влияют
    for _ in range(config.SUMMARY_WEEKLY):
        assert await ai_quota.gate(22, kind="summary") is None
    assert await ai_quota.gate(22, kind="summary") == "summary"
    assert "готовые открываются" in ai_quota.text("summary")
    # подписка — свой дневной потолок
    await db.set_subscription_until(20, "2999-01-01")
    monkeypatch.setattr(config, "AI_SUB_DAILY", 5)
    assert await ai_quota.gate(20) is None and await ai_quota.gate(20) is None
    assert await ai_quota.gate(20) == "sub"
    # новый день — проба снова
    day[0] = date(2026, 10, 9)
    assert await ai_quota.gate(21) is None


@pytest.mark.asyncio
async def test_ai_left_for_chat_screen(db, index, monkeypatch):
    """Сколько вопросов осталось сегодня — строка на пустом экране помощника
    в приложении (2.12); старосте лимит не действует — null."""
    import ai_quota
    import groups
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(ratelimit, "allow", lambda action, uid: True)
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 10)
    await db.set_setting("plus:gift", "off")                                # своя группа без подарка
    await db.upsert_user(30, "u", "U")
    await db.set_user_group(30, HOME)
    await db.upsert_user(31, "u", "U")
    await groups.choose(31, OTHER)
    assert await ai_quota.left(30) == {"left": 10, "limit": 10}
    await ai_quota.gate(30)
    assert await ai_quota.left(30) == {"left": 9, "limit": 10}
    assert await ai_quota.left(31) == {"left": config.AI_TRIAL_DAILY, "limit": config.AI_TRIAL_DAILY}
    assert await ai_quota.left(STAROSTA_ID) is None
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 0)
    assert await ai_quota.left(30) is None
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 10)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr("database.get_subjects_with_lecture_text", _no_subjects, raising=False)
    h = {"X-Telegram-Init-Data": _make_init_data(user={"id": 30, "first_name": "U"})}
    r = TestClient(server.app).get("/api/subjects", headers=h).json()
    assert r["quota"] == {"left": 9, "limit": 10}


async def _no_subjects():
    return []


# ── бот: /start новому человеку и /group ─────────────────────────────────────

USER = User(id=4242, is_bot=False, first_name="Новенький")


async def _feed(dp, bot, text):
    msg = Message(message_id=int(time.time() * 1000) % 1000000, date=0,
                  chat=Chat(id=USER.id, type="private"), from_user=USER, text=text)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9, message=msg))


@pytest.mark.asyncio
async def test_bot_asks_group_and_saves_choice(db, index, monkeypatch):
    import groups
    import handlers.group_pick as gp
    import handlers.start as start
    monkeypatch.setattr(start, "app_button", lambda *a, **k: None)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(gp.router)
    try:
        await _feed(dp, bot, "/start")
        assert "Из какой ты группы" in bot.session.sent_texts[-1][1]
        await _feed(dp, bot, "уибо-01")
        assert bot.session.sent_texts[-1][1] == "Выбери свою:"
        msg = Message(message_id=1, date=0, chat=Chat(id=USER.id, type="private"), from_user=USER, text="x")
        cb = CallbackQuery(id="1", from_user=USER, chat_instance="c", data=f"grp:{OTHER}", message=msg)
        await dp.feed_update(bot, Update(update_id=int(time.time()), callback_query=cb))
        assert (await groups.of_user(USER.id))["id"] == OTHER
        assert "УИБО-01-24" in bot.session.sent_texts[-1][1]
        await _feed(dp, bot, "/group")
        assert "Сейчас ты в группе <b>УИБО-01-24</b>" in bot.session.sent_texts[-1][1]
        await _feed(dp, bot, "абракадабра")
        assert "Не нашёл" in bot.session.sent_texts[-1][1]
    finally:
        start.router._parent_router = None
        gp.router._parent_router = None


# ── WebApp: /api/me и выбор группы ───────────────────────────────────────────

def test_webapp_group_api(db, index, monkeypatch):
    import billing
    import webapp.server as server
    monkeypatch.setattr(billing, "GIFT_UNTIL", "2999-12-31")
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    me = c.get("/api/me", headers=h).json()
    assert me["group"] is None and me["plan"] == "base"
    assert c.get("/api/groups/search?q=УИБО-01", headers=h).json()["items"] == [{"id": OTHER, "name": "УИБО-01-24"}]
    assert c.post("/api/me/group", json={"id": 1}, headers=h).status_code == 404
    assert c.post("/api/me/group", json={"id": HOME}, headers=h).json()["group"]["own"] is True
    me = c.get("/api/me", headers=h).json()
    assert me["group"]["name"] == config.GROUP_NAME and me["plan"] == "sub"   # своя — с подарком «Капибары+»
