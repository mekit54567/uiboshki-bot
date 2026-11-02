"""Дизайн 5.79, «Пусто и ошибка»: /api/deadlines отдаёт, чем кончилась
последняя проверка СДО группы (sdo_check.py) — приложение пишет «СДО
проверено в 12:40» или «СДО не ответил, показываю сроки от 09:41»."""
import json

import pytest
from fastapi.testclient import TestClient

from kapibara.core import config
from kapibara.features.sdo import check as sdo_check
from kapibara.features.sdo import parser as sdo_parser
from tests.test_webapp_home import _make_init_data

HOME = config.HOME_GROUP_ID
OTHER = 5001
MINE, DONOR, MATE = 501, 502, 503


@pytest.fixture
async def client(db, monkeypatch):
    import webapp.server as server
    from database.groups import upsert_group
    from tests.test_webapp_home import BOT_TOKEN
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((MINE, HOME), (DONOR, OTHER), (MATE, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)

    def sdo(uid):
        h = {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "A"})}
        return TestClient(server.app).get("/api/deadlines?include_done=true", headers=h).json()["sdo"]
    return sdo


@pytest.mark.asyncio
async def test_unknown_until_checked(client):
    assert client(MINE) is None and client(MATE) is None


@pytest.mark.asyncio
async def test_home_group_ok_then_failed_keeps_last_ok(client, monkeypatch):
    from kapibara.jobs import scheduler
    await scheduler._note_sync({"added": 1, "updated": 0})
    s = client(MINE)
    assert s["ok"] is True and s["checked_at"] == s["last_ok"]
    ok_at = s["last_ok"]

    await scheduler._note_sync({"error": "ConnectError"})              # СДО не ответил
    s = client(MINE)
    assert s["ok"] is False and s["last_ok"] == ok_at
    await scheduler._note_sync({"expired": True})                       # кука протухла — тоже сбой
    assert client(MINE)["ok"] is False and client(MINE)["last_ok"] == ok_at
    await scheduler._note_sync({"expired": True, "missing": True})      # куки нет — не проверяли
    assert client(MINE)["last_ok"] == ok_at
    assert client(MATE) is None                                         # другая группа — своё


@pytest.mark.asyncio
async def test_home_group_falls_back_to_health(client):
    from kapibara.ops import health
    await health.note("sdo_sync", False, "СДО не ответил")             # итог до 5.80 — только в /status
    s = client(MINE)
    assert s["ok"] is False and s["last_ok"] is None and s["checked_at"]


@pytest.mark.asyncio
async def test_other_group_by_donor(client, db, monkeypatch):
    from kapibara.features.groups import sync as group_sync
    from kapibara.features.sdo import accounts as sdo_accounts
    await db.save_sdo_session(DONOR, sdo_accounts.encrypt("A" * 26))
    await group_sync.sync_group(OTHER)                                  # не делится — не проверяли
    assert client(MATE) is None
    assert await db.set_sdo_share(DONOR, True)

    async def calendar(client):
        return []
    monkeypatch.setattr(sdo_parser, "fetch_calendar_events", calendar)
    await group_sync.sync_group(OTHER)
    s = client(MATE)
    assert s["ok"] is True and s["last_ok"] == s["checked_at"]

    async def down(client):
        raise RuntimeError("502")
    monkeypatch.setattr(sdo_parser, "fetch_calendar_events", down)
    assert (await group_sync.sync_group(OTHER))["error"]
    s2 = client(MATE)
    assert s2["ok"] is False and s2["last_ok"] == s["last_ok"]
    assert client(MINE) is None                                         # своя группа — не о ней


@pytest.mark.asyncio
async def test_broken_setting_is_unknown(db):
    await db.set_setting(f"sdo_check:{OTHER}", "{битый")
    assert await sdo_check.state(OTHER) is None
    await db.set_setting(f"sdo_check:{OTHER}", json.dumps([1]))
    assert await sdo_check.state(OTHER) is None
    assert await sdo_check.state(0) is None                             # не в чате своей группы
