"""Статистика для старосты (/stats): события без содержимого, картинка."""
import time

import aiosqlite
import pytest

from kapibara.ops import stats


def test_kind_for_paths():
    assert stats.kind_for("GET", "/api/me") == "open"
    assert stats.kind_for("GET", "/api/deadlines") == "deadlines"
    assert stats.kind_for("POST", "/api/files/12/link") == "download"
    assert stats.kind_for("POST", "/api/files/delete") is None        # удаление — не «скачал»
    assert stats.kind_for("POST", "/api/sdo/submit") == "submit"
    assert stats.kind_for("GET", "/api/sdo/grades/18672") == "sdo"
    assert stats.kind_for("GET", "/health") is None


@pytest.mark.asyncio
async def test_views_throttled_actions_not(db, monkeypatch):
    monkeypatch.setattr(stats, "_last", {})
    for _ in range(3):
        await stats.track(222, "open")       # просмотр — раз в 30 минут
        await stats.track(222, "ai")         # действие — каждое
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        rows = await (await con.execute("SELECT kind, COUNT(*) FROM events GROUP BY kind")).fetchall()
    assert dict(rows) == {"open": 1, "ai": 3}


@pytest.mark.asyncio
async def test_collect_and_render(db, monkeypatch):
    monkeypatch.setattr(stats, "_last", {})
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "")
        await stats.track(uid, "open")
    await stats.track(1, "deadlines")
    await stats.track(2, "submit")
    s = await stats.collect(7)
    assert s["total"] == 3 and s["day"] == 3 and s["week"] == 3
    assert s["new_day"] == 3 and s["new_week"] == 3 and "Новые: сегодня <b>3</b>" in stats.summary(s)
    assert "ИИ сегодня" not in stats.summary(s)                      # вопросов не было — строки нет
    from kapibara.features.ai import quota as ai_quota                                                     # вопросы ИИ — из дневного счёта
    for _ in range(3):
        await ai_quota.take(2)
    await ai_quota.take(3)
    s2 = await stats.collect(7)
    assert (s2["ai_today"], s2["ai_top"]) == (4, 3) and "ИИ сегодня: <b>4</b>" in stats.summary(s2)
    p = await stats.people(7)
    assert all(a["new"] for a in p["active"]) and "🆕" in stats.people_text(p)   # пришли сегодня
    assert dict((label, n) for label, _, n in s["screens"])["Приложение"] == 3
    assert dict(s["actions"])["сдано работ"] == 1
    assert sum(map(sum, s["heat"])) == 5
    png = stats.render(s)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000


@pytest.mark.asyncio
async def test_webapp_request_is_tracked(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(stats, "_last", {})
    c = TestClient(server.app)
    assert c.get("/api/me", headers={"X-Telegram-Init-Data": _make_init_data()}).status_code == 200
    async with aiosqlite.connect(db.DATABASE_PATH) as con:
        rows = await (await con.execute("SELECT user_id, kind FROM events")).fetchall()
    assert rows == [(222, "open"), (222, "via_tg")]


@pytest.mark.asyncio
async def test_stats_command_only_for_starosta(db, monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    from handlers import announce, deadlines
    from tests.conftest import STAROSTA_ID
    from tests.test_solver_render import RecordingSession

    class Session(RecordingSession):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.photos = []

        async def make_request(self, bot, method, timeout=None):
            if type(method).__name__ == "SendPhoto":
                self.photos.append((method.chat_id, method.caption))
                return Message(message_id=5, date=0, chat=Chat(id=method.chat_id, type="private")).as_(bot)
            return await super().make_request(bot, method, timeout)

    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=Session())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(deadlines.router)   # как в handlers/__init__.py: раньше announce
    dp.include_router(announce.router)
    try:
        for i, uid in enumerate((222, STAROSTA_ID)):
            u = User(id=uid, is_bot=False, first_name="X")
            msg = Message(message_id=i + 1, date=0, chat=Chat(id=uid, type="private"), from_user=u, text="/stats")
            await dp.feed_update(bot, Update(update_id=int(time.time()) + i, message=msg))
    finally:
        announce.router._parent_router = None
        deadlines.router._parent_router = None
    assert [chat for chat, _ in bot.session.photos] == [STAROSTA_ID]
    # остальным /stats по-прежнему показывает их дедлайны
    assert any("Статистика дедлайнов" in text for text, _ in bot.session.sent)
    assert "Статистика за 30 дн." in bot.session.photos[0][1]


@pytest.mark.asyncio
async def test_people_list_names_when_and_what(db, monkeypatch):
    # Владелец: видеть, кто конкретно пользуется (имя и ник), — без содержимого.
    monkeypatch.setattr(stats, "_last", {})
    await db.upsert_user(1, "anya", "Аня <Б>")
    await db.upsert_user(2, "", "Борис")
    await db.upsert_user(3, "vova", "")          # в боте, но за период не заходил
    for kind in ("ai", "ai", "files", "open"):
        await stats.track(1, kind)
    await stats.track(2, "sdo")
    p = await stats.people(30)
    assert [a["id"] for a in p["active"]] == [2, 1]           # свежие сверху
    assert p["active"][1]["uses"][0] == "ИИ" and p["active"][1]["days"] == 1
    assert [u["id"] for u in p["idle"]] == [3]
    text = stats.people_text(p)
    assert "Кто пользуется · 30 дн.</b> — 2 чел." in text
    assert '<a href="tg://user?id=1">Аня &lt;Б&gt;</a> @anya — сегодня' in text
    assert "ИИ, файлы, приложение" in text
    assert "не заходили (1)" in text and "@vova" in text


@pytest.mark.asyncio
async def test_people_button_only_for_starosta(db, monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import CallbackQuery, Chat, Message, Update, User
    from handlers import announce
    from tests.conftest import STAROSTA_ID
    from tests.test_solver_render import RecordingSession

    await db.upsert_user(222, "anya", "Аня")
    await db.add_event(222, "open")
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(announce.router)
    try:
        for i, uid in enumerate((222, STAROSTA_ID)):
            u = User(id=uid, is_bot=False, first_name="X")
            msg = Message(message_id=1, date=0, chat=Chat(id=uid, type="private"), from_user=u, text="")
            cb = CallbackQuery(id=str(i), from_user=u, chat_instance="c", data="stats:people:30", message=msg)
            await dp.feed_update(bot, Update(update_id=int(time.time()) + i, callback_query=cb))
    finally:
        announce.router._parent_router = None
    lists = [t for t, _ in bot.session.sent if "Кто пользуется" in t]
    assert len(lists) == 1 and "Аня" in lists[0]


@pytest.mark.asyncio
async def test_evening_summary_only_with_new_people(db, monkeypatch):
    """Вечером старосте «+N новых (M с сайта)» за сутки — только если пришли
    новые; «с сайта» — только среди новых; склонения."""
    import aiosqlite
    from kapibara.core import config
    from datetime import datetime, timedelta
    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    monkeypatch.setattr(stats, "_last", {})
    monkeypatch.setattr(config, "STAROSTA_ID", 999)
    await stats.send_evening(Bot())
    assert sent == []                                                  # никого — тишина
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "")
    async with aiosqlite.connect(db.DATABASE_PATH) as con:             # 3 — старый, пришёл неделю назад
        await con.execute("UPDATE users SET joined_at = datetime('now', '-7 days') WHERE user_id = 3")
        await con.commit()
    await stats.track(2, "from_site")
    await stats.track(3, "from_site")                                  # старый жмёт /start site — не «новый с сайта»
    await stats.send_evening(Bot())
    (chat, text), = sent
    assert chat == 999 and text.startswith("📈 <b>За сутки</b>: +2 новых (1 с сайта) · всего в боте 3")
    assert stats.evening_text(1, 0, 5, 1, 1, 0).startswith("📈 <b>За сутки</b>: +1 новый · всего в боте 5")
    assert "ИИ: 1 вопрос" in stats.evening_text(1, 0, 5, 1, 1, 0)
    assert stats.evening_text(0, 0, 5, 1, 9, 0) is None
    sent.clear()                                                       # через сутки тех же не считаем
    await stats.send_evening(Bot(), now=datetime.now(stats.TZ) + timedelta(days=1, minutes=5))
    assert sent == []


@pytest.mark.asyncio
async def test_platforms_line(db, monkeypatch):
    """Где открывают (09.10): Telegram, PWA/браузер (токен сессии) и своё приложение (X-App)."""
    from fastapi.testclient import TestClient
    import webapp.server as server
    from database.sessions import create_session
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(stats, "_last", {})
    await db.upsert_user(333, "", "Боря")
    await db.upsert_user(444, "", "Вера")
    c = TestClient(server.app)
    assert c.get("/api/me", headers={"X-Telegram-Init-Data": _make_init_data()}).status_code == 200
    pwa = await create_session(333, "Chrome · Android")
    assert c.get("/api/me", headers={"Authorization": f"Bearer {pwa}"}).status_code == 200
    app = await create_session(444, "Капибара · iPhone")
    assert c.get("/api/me", headers={"Authorization": f"Bearer {app}", "X-App": "ios"}).status_code == 200
    s = await stats.collect(7)
    assert dict(s["platforms"]) == {"Telegram": 1, "PWA и браузер": 1, "приложение": 1}
    assert "Где открывают: Telegram — <b>1</b> · PWA и браузер — <b>1</b> · приложение — <b>1</b>" in stats.summary(s)
    p = await stats.people(7)
    assert "приложение" in {a["id"]: a["uses"] for a in p["active"]}[444]
    assert stats.platforms_line([("Telegram", 0)]) == ""
