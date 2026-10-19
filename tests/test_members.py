"""Своя группа = участники чата группы в Telegram (members.py, владелец 09.10)."""
import pytest
from fastapi.testclient import TestClient

import config

HOME = config.HOME_GROUP_ID
CHAT = -100777


class FakeBot:
    def __init__(self, members):
        self.members, self.asked = members, []

    async def get_chat_member(self, chat_id, user_id):
        self.asked.append((chat_id, user_id))
        return type("M", (), {"status": "member" if user_id in self.members else "left"})()


@pytest.fixture
def chat(db, monkeypatch):
    monkeypatch.setattr(config, "GROUP_CHAT_ID", CHAT)
    return db


@pytest.mark.asyncio
async def test_without_chat_nothing_changes(db):
    import groups
    import members
    assert await members.is_member(501, FakeBot(set())) is None        # чат не задан — не знаем
    await db.upsert_user(501, "", "Вася")
    assert (await groups.choose(501, HOME, FakeBot(set())))["id"] == HOME


@pytest.mark.asyncio
async def test_only_chat_members_choose_home_group(chat):
    import groups
    import plans
    from database.groups import viewer_group
    db = chat
    bot = FakeBot({601})
    await db.set_setting("plus:gift", "off")                            # тариф без подарка «Капибары+»
    for uid in (601, 602):
        await db.upsert_user(uid, "", f"u{uid}")
    assert (await groups.choose(601, HOME, bot))["id"] == HOME
    denied = await groups.choose(602, HOME, bot)
    assert denied.get("denied") and "чат" in denied["denied"]
    assert await db.get_user_group(602) is None
    assert await viewer_group(602) == 0                                 # не в чате — данных своей группы нет
    assert await plans.plan_of(601) == plans.OWN and await plans.plan_of(602) == plans.BASE
    # в чате, но выбрал другую группу — тариф своей группы остаётся
    await db.set_user_group(601, 5001)
    assert await plans.plan_of(601) == plans.OWN
    # ответ Telegram помнится — второй раз не спрашиваем
    n = len(bot.asked)
    await groups.choose(601, HOME, bot)
    assert len(bot.asked) == n


@pytest.mark.asyncio
async def test_api_refuses_home_group_to_outsider(chat, monkeypatch):
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(server.deps, "tg_bot", lambda: FakeBot(set()))
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data(user={"id": 603, "first_name": "Чужой"})}
    r = c.post("/api/me/group", headers=h, json={"id": HOME})
    assert r.status_code == 403 and "чат" in r.json()["detail"]


@pytest.mark.asyncio
async def test_bot_added_to_chat_by_starosta_remembers_it(db, monkeypatch):
    import members
    from handlers.members_chat import bot_added_to_group
    from tests.conftest import STAROSTA_ID
    monkeypatch.setattr(config, "GROUP_CHAT_ID", 0)
    sent = []

    class Bot:
        async def send_message(self, *a, **k):
            sent.append(a)

    def event(uid):
        return type("E", (), {
            "new_chat_member": type("N", (), {"status": "administrator"})(),
            "from_user": type("U", (), {"id": uid})(),
            "chat": type("C", (), {"id": CHAT, "title": "уибошки", "type": "supergroup"})(),
            "bot": Bot()})()

    await bot_added_to_group(event(999))                    # не староста — не запоминаем
    assert await members.chat_id() == 0
    await bot_added_to_group(event(STAROSTA_ID))
    assert await members.chat_id() == CHAT and sent and "уибошки" in sent[0][1]


@pytest.mark.asyncio
async def test_chat_id_and_settings_without_extra_db_opens(db, monkeypatch):
    """19.10, медленный диск: chat_id открывал базу по 5 раз на запрос, а каждое
    чтение настройки — ещё раз ради проверки таблиц (init_hw_table)."""
    import database.homework as hw
    import members
    monkeypatch.setattr(config, "GROUP_CHAT_ID", 0)
    await db.set_setting("group_chat_id", str(CHAT))
    members.forget_chat()
    opened = []
    real = hw.connect
    monkeypatch.setattr(hw, "connect", lambda: opened.append(1) or real())
    assert await members.chat_id() == CHAT
    opened.clear()
    assert await members.chat_id() == CHAT
    assert opened == []                                     # второй раз — из памяти
    await hw.get_setting("x")
    assert len(opened) == 1                                 # таблицы уже проверены — одно открытие
