"""Общая кука СДО протухла (СДО лежал 10 часов, 15–16.11) — бот за свою
группу ходит живым входом из приложения: аккаунт старосты, потом тот, кто
делится дедлайнами. Раньше синк и другие аккаунты старосты стояли, пока не
поменяешь куку на сервере."""

import pytest

from kapibara.core import config
from kapibara.features.sdo import accounts as sdo_accounts
from kapibara.features.sdo import parser as sdo_parser

SHARED = "shared-cookie-0123456789"
APP = "app-login-cookie-0123456789"


@pytest.fixture
def starosta(monkeypatch):
    """Три аккаунта старосты, как у Никиты: 111 — основной, 222 и 333 — другие."""
    monkeypatch.setattr(config, "STAROSTA_IDS", [222, 111, 333])
    monkeypatch.setattr(sdo_accounts, "is_starosta", lambda uid: uid in (111, 222, 333))
    monkeypatch.setattr(sdo_accounts, "SDO_SESSION_COOKIE", SHARED)
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", SHARED)


@pytest.mark.asyncio
async def test_home_cookie_shared_while_alive(db, starosta):
    await db.save_sdo_session(111, sdo_accounts.encrypt(APP))
    assert await sdo_parser.home_cookie() == (SHARED, None)


@pytest.mark.asyncio
async def test_dead_shared_falls_back_to_starosta_app_login(db, starosta):
    await sdo_accounts.note_shared(False)
    assert await sdo_parser.home_cookie() == (SHARED, None)      # запасного входа нет — пробуем как есть
    await db.save_sdo_session(111, sdo_accounts.encrypt(APP))
    assert await sdo_parser.home_cookie() == (APP, 111)
    # второй и третий аккаунты старосты без своего входа — этим же входом
    assert await sdo_accounts.cookie_for(222) == APP
    assert await sdo_accounts.cookie_for(333) == APP
    assert (await sdo_accounts.status_for(222))["state"] == "ok"
    # Никита поменял куку на сервере — снова общая
    sdo_parser.SDO_SESSION_COOKIE = sdo_accounts.SDO_SESSION_COOKIE = SHARED + "x"
    assert await sdo_parser.home_cookie() == (SHARED + "x", None)


@pytest.mark.asyncio
async def test_expired_app_login_not_used(db, starosta):
    await sdo_accounts.note_shared(False)
    await db.save_sdo_session(111, sdo_accounts.encrypt(APP))
    await db.set_sdo_status(111, "expired")
    assert await sdo_accounts.backup_login() is None
    assert (await sdo_accounts.status_for(222))["state"] == "expired"


@pytest.mark.asyncio
async def test_sync_uses_app_login_and_keeps_shared_mark(db, starosta, monkeypatch):
    """Синк запасным входом: дедлайны приходят, а погасший запасной вход не
    помечает общую куку (её состояние — дело keepalive)."""
    from kapibara.jobs import scheduler
    await sdo_accounts.note_shared(False)
    await db.save_sdo_session(111, sdo_accounts.encrypt(APP))
    used = []

    async def items(cookie=None):
        used.append(cookie)
        return []
    monkeypatch.setattr(sdo_parser, "fetch_deadline_items", items)
    res = await sdo_parser.sync_deadlines()
    assert used == [APP] and res["via"] == 111 and not res.get("expired")

    async def expired(cookie=None):
        raise sdo_parser.SdoSessionExpired("login")
    monkeypatch.setattr(sdo_parser, "fetch_deadline_items", expired)
    await sdo_accounts.note_shared(True)
    await db.set_sdo_status(111, "ok")
    res = await sdo_parser.sync_deadlines()
    assert res["expired"] and res["via"] is None             # общая жива — ходили ею
    await scheduler._note_sync(res)
    assert not await sdo_accounts.shared_alive()
