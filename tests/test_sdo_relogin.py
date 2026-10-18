"""Тихое обновление входа в СДО (5.102.0): приложение на телефоне само
переподключает протухший вход скрытой страницей СДО (via=silent), «делиться
с группой» при этом не сбрасывается, а бот пишет вошедшим страницей, что
вход обновится сам."""
import pytest

import sdo_accounts
from tests.test_sdo_submit import COOKIE, moodle  # noqa: F401  (фикстура)


@pytest.fixture
def client(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_silent_reconnect_keeps_share(db, moodle, client):  # noqa: F811
    c, h = client
    r = c.post("/api/sdo/connect", json={"cookie": COOKIE, "agree": True, "via": "page"}, headers=h)
    assert r.json()["state"] == "ok"
    await db.set_sdo_share(222, True)
    await db.set_sdo_status(222, "expired")
    # согласие уже дано — галочка не нужна; via=silent запоминается
    r = c.post("/api/sdo/connect", json={"cookie": "b" + COOKIE[1:], "via": "silent"}, headers=h)
    assert r.json()["state"] == "ok"
    row = await db.get_sdo_session(222)
    assert row["share"] == 1 and row["via"] == "silent" and row["status"] == "ok"
    c.post("/api/sdo/connect", json={"cookie": COOKIE, "via": "чужое"}, headers=h)
    assert (await db.get_sdo_session(222))["via"] == "paste"


@pytest.mark.asyncio
async def test_expired_message_depends_on_how_logged_in(db, moodle):  # noqa: F811
    sent = {}

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent[chat_id] = text

    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE), via="page")
    await db.save_sdo_session(333, sdo_accounts.encrypt(COOKIE))
    moodle.logged_in = False
    await sdo_accounts.keepalive_all(Bot())
    assert "обновится сам" in sent[222] and "обновится сам" not in sent[333]
    assert "Подключи заново" in sent[333]
