"""Ачивки на сервере (5.91): приложение присылает открытые у себя, сервер
хранит самое раннее время, отдаёт всё обратно — ачивки и иконки за них не
пропадают при смене телефона."""
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import achievements
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

ROOT = Path(__file__).resolve().parent.parent
UID, OTHER = 601, 602
NOW = int(time.time() * 1000)


def test_catalog_matches_app():
    dart = (ROOT / "app" / "lib" / "achievements" / "catalog.dart").read_text(encoding="utf-8")
    pairs = re.findall(r"Achievement\(\s*'(\w+)',\s*Rank\.(\w+)", dart)
    assert pairs, "в catalog.dart не нашлись ачивки"
    assert {a: r for a, r in pairs} == {a: r for r, ids in achievements.RANKS.items() for a in ids}


@pytest.fixture
async def client(db, monkeypatch):
    import ratelimit
    import webapp.server as server
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    ratelimit._hits.clear()
    for uid in (UID, OTHER):
        await db.upsert_user(uid, "", f"u{uid}")
    c = TestClient(server.app)

    def h(uid):
        return {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "A"})}
    return c, h


@pytest.mark.asyncio
async def test_sync_keeps_earliest_and_drops_unknown(client):
    c, h = client
    first = NOW - 5 * 86400_000
    r = c.post("/api/achievements", json={"items": {"lesson": first, "nope": first}}, headers=h(UID))
    assert r.status_code == 200 and r.json()["items"] == {"lesson": first}
    # второй телефон: та же ачивка позже и новая — время остаётся первым
    r = c.post("/api/achievements", json={"items": {"lesson": NOW, "ai": NOW - 1000}}, headers=h(UID))
    assert r.json()["items"] == {"lesson": first, "ai": NOW - 1000}
    assert c.get("/api/achievements", headers=h(UID)).json()["items"] == {"lesson": first, "ai": NOW - 1000}
    # у другого — своё
    assert c.get("/api/achievements", headers=h(OTHER)).json()["items"] == {}


@pytest.mark.asyncio
async def test_time_from_phone_is_clamped(client):
    c, h = client
    r = c.post("/api/achievements", json={"items": {"wave": NOW + 10 * 86400_000, "fri13": 5}}, headers=h(UID))
    got = r.json()["items"]
    assert got["wave"] <= int(time.time() * 1000) and got["fri13"] == achievements._MIN_MS


@pytest.mark.asyncio
async def test_rank_closed(db):
    await achievements.add(UID, {a: NOW for a in achievements.RANKS["dusk"][:-1]}, NOW)
    assert not await achievements.rank_closed(UID, "dusk")
    await achievements.add(UID, {achievements.RANKS["dusk"][-1]: NOW}, NOW)
    assert await achievements.rank_closed(UID, "dusk")
