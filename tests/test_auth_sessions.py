"""Этап 2: вход в приложение без Telegram — код входа, подтверждение в
боте, токен сессии устройства, список устройств и выход."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from tests.test_deadlines_routing import FakeSession

UID = 777


async def _bot_says(dp, bot, text=None, data=None):
    user = User(id=UID, is_bot=False, first_name="Аня")
    msg = Message(message_id=1, date=0, chat=Chat(id=UID, type="private"), from_user=user, text=text or "x")
    if data:
        upd = Update(update_id=int(time.time() * 1000) % 10**9,
                     callback_query=CallbackQuery(id="1", from_user=user, chat_instance="c", data=data, message=msg))
    else:
        upd = Update(update_id=int(time.time() * 1000) % 10**9, message=msg)
    await dp.feed_update(bot, upd)


@pytest.fixture
def client(db, monkeypatch):
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/130"})


@pytest.mark.asyncio
async def test_login_via_bot_gives_device_session(db, client):
    import handlers.start as start
    await db.upsert_user(UID, "anya", "Аня Петрова")
    res = client.post("/api/auth/start").json()
    code = res["code"]
    assert res["link"].endswith(f"?start=login_{code}")
    assert res["tg_link"].startswith("tg://resolve?domain=") and res["tg_link"].endswith(f"&start=login_{code}")
    assert client.post("/api/auth/poll", json={"code": code}).json() == {"status": "wait"}

    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    try:
        await _bot_says(dp, bot, text=f"/start login_{code}")
        assert "Chrome · Android" in bot.session.sent_texts[-1][1]           # видно, что за устройство
        await _bot_says(dp, bot, data=f"login:ok:{code}")
        assert client.post("/api/auth/poll", json={"code": code}).json() == {"status": "wait"}   # ещё число
        from database.sessions import get_login
        pick = (await get_login(code))["pick"]
        assert pick == res["pick"]
        await _bot_says(dp, bot, data=f"login:n:{pick}:{code}")
    finally:
        start.router._parent_router = None

    ok = client.post("/api/auth/poll", json={"code": code}).json()
    assert ok["status"] == "ok" and ok["user_id"] == UID
    assert client.post("/api/auth/poll", json={"code": code}).json()["status"] == "expired"   # код — один раз
    h = {"Authorization": f"Bearer {ok['token']}"}
    me = client.get("/api/me", headers=h).json()
    assert me["id"] == UID and me["first_name"] == "Аня"
    devices = client.get("/api/auth/sessions", headers=h).json()["items"]
    assert len(devices) == 1 and devices[0]["current"] and devices[0]["device"] == "Chrome · Android"
    assert client.post("/api/auth/logout", headers=h).json()["revoked"] == 1
    assert client.get("/api/me", headers=h).status_code == 401              # вышел — токен не работает
    assert client.get("/api/me", headers={"Authorization": "Bearer someone-else"}).status_code == 401


@pytest.mark.asyncio
async def test_denied_and_expired(db, client):
    from database.sessions import decide_login
    code = client.post("/api/auth/start").json()["code"]
    assert await decide_login(code, UID, False)
    assert client.post("/api/auth/poll", json={"code": code}).json() == {"status": "denied"}
    assert not await decide_login(code, UID, True)                             # решение не переигрывается
    assert client.post("/api/auth/poll", json={"code": "нет-такого"}).json() == {"status": "expired"}


@pytest.mark.asyncio
async def test_logout_everywhere(db, client):
    from database.sessions import create_session
    await db.upsert_user(UID, "", "Аня")
    t1, t2 = await create_session(UID, "Phone"), await create_session(UID, "Laptop")
    h1 = {"Authorization": f"Bearer {t1}"}
    assert len(client.get("/api/auth/sessions", headers=h1).json()["items"]) == 2
    assert client.post("/api/auth/logout?everywhere=true", headers=h1).json()["revoked"] == 2
    assert client.get("/api/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401


@pytest.mark.asyncio
async def test_app_login_names_device(db, client):
    """Вход из своего приложения: у Dart нет браузера в User-Agent — бот спрашивал
    «на устройстве Браузер»; приложение шлёт X-App, и устройство — «Капибара · iPhone»."""
    from database.sessions import get_login
    res = client.post("/api/auth/start", headers={"User-Agent": "Dart/3.9 (dart:io)", "X-App": "ios"}).json()
    assert (await get_login(res["code"]))["device"] == "Капибара · iPhone"
    res = client.post("/api/auth/start", headers={"User-Agent": "Dart/3.9 (dart:io)", "X-App": "android"}).json()
    assert (await get_login(res["code"]))["device"] == "Капибара · Android"


@pytest.mark.asyncio
async def test_login_wrong_number_denied(db, client):
    """Как у Google: «Да, это я» — и число с экрана устройства из трёх. Не то
    число — вход отклонён (чужую ссылку входа одним «Да» больше не подтвердить)."""
    import handlers.start as start
    from database.sessions import get_login, pick_options
    await db.upsert_user(UID, "anya", "Аня Петрова")
    code = client.post("/api/auth/start").json()["code"]
    pick = (await get_login(code))["pick"]
    opts = pick_options(pick)
    assert len(set(opts)) == 3 and pick in opts and all(10 <= n <= 99 for n in opts)
    wrong = next(n for n in range(10, 100) if n != pick)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=FakeSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    try:
        await _bot_says(dp, bot, data=f"login:ok:{code}")
        await _bot_says(dp, bot, data=f"login:n:{wrong}:{code}")
    finally:
        start.router._parent_router = None
    assert client.post("/api/auth/poll", json={"code": code}).json()["status"] == "denied"


@pytest.mark.asyncio
async def test_devices_grouped_and_revoked_together(db, client):
    """Никита 25.10: девять «Safari · iPhone» — каждый перелогин оставлял запись.
    Одинаковые устройства — одной строкой, «Выйти» закрывает их все, текущий
    вход — своей строкой и соседей не трогает."""
    from database.sessions import create_session, session_user
    await db.upsert_user(UID, "anya", "Аня")
    cur = await create_session(UID, "Safari · iPhone")
    old = [await create_session(UID, d) for d in ("Safari · iPhone", "Safari · iPhone · VK ID", "Safari · iPhone")]
    pc = await create_session(UID, "Chrome · Windows")
    h = {"Authorization": f"Bearer {cur}"}
    items = client.get("/api/auth/sessions", headers=h).json()["items"]
    names = sorted((i["device"], i["current"]) for i in items)
    assert names == [("Chrome · Windows", False), ("Safari · iPhone", True), ("Safari · iPhone · 3 входа", False)]
    group = next(i for i in items if i["count"] == 3)
    assert client.delete(f"/api/auth/sessions/{group['ids'][-1]}", headers=h).json() == {"ok": True}
    assert [await session_user(t) for t in old] == [None, None, None]
    assert await session_user(cur) == UID and await session_user(pc) == UID
    assert len(client.get("/api/auth/sessions", headers=h).json()["items"]) == 2
    assert client.delete("/api/auth/sessions/999999", headers=h).status_code == 404


@pytest.mark.asyncio
async def test_browser_session_idles_out_in_30_days_app_in_90(db):
    from database._conn import connect
    from database.sessions import create_session, session_user
    from database.schema import init_db
    web = await create_session(UID, "Safari · iPhone")
    app = await create_session(UID, "Капибара · iPhone")
    async with connect() as db_:
        rows = dict(await (await db_.execute(
            "SELECT device, julianday(expires_at) - julianday(last_seen) FROM sessions")).fetchall())
    assert round(rows["Safari · iPhone"]) == 30 and round(rows["Капибара · iPhone"]) == 90
    # записи до этой версии жили 90 дней — при запуске урезаются (браузерные)
    async with connect() as db_:
        await db_.execute("UPDATE sessions SET last_seen = datetime('now', '-40 days'), "
                          "expires_at = datetime('now', '+50 days')")
        await db_.commit()
    await init_db()
    assert await session_user(web) is None
    assert await session_user(app) == UID


def test_home_screen_pwa_named_apart(client):
    from webapp.routes.auth import _device
    from starlette.requests import Request
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Version/18.0 Mobile/15E148 Safari/604.1"
    req = lambda extra: Request({"type": "http", "headers": [(b"user-agent", ua.encode())] + extra})  # noqa: E731
    assert _device(req([])) == "Safari · iPhone"
    assert _device(req([(b"x-client", b"home")])) == "Ярлык · iPhone"
