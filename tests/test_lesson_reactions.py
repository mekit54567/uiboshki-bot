"""Реакции на пару (5.100, Никита 18.10): четыре позы, одна на человека,
счёт видит своя группа, кто как отметил — нет."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
from utils import TZ

ME, MATE, STRANGER = 501, 502, 503
OTHER = 5002


@pytest.fixture
async def client(db, monkeypatch):
    import ratelimit
    import webapp.server as server
    from database.groups import upsert_group
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    ratelimit._hits.clear()
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((ME, config.HOME_GROUP_ID), (MATE, config.HOME_GROUP_ID), (STRANGER, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    c = TestClient(server.app)

    def h(uid):
        return {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "A"})}
    return c, h


def _start(hours_ago=1.0) -> str:
    return (datetime.now(TZ) - timedelta(hours=hours_ago)).replace(second=0, microsecond=0).isoformat()


def _q(start, title="Анализ данных"):
    from urllib.parse import urlencode
    return "/api/lesson/reactions?" + urlencode({"start": start, "title": title})


@pytest.mark.asyncio
async def test_group_sees_counts_not_who(client):
    c, h = client
    s = _start()
    body = {"start": s, "title": "Анализ данных", "kind": "joy"}
    r = c.post("/api/lesson/reactions", json=body, headers=h(ME)).json()
    assert r["counts"] == {"joy": 1, "calm": 0, "hard": 0, "sleep": 0, "angry": 0} and r["mine"] == "joy"
    c.post("/api/lesson/reactions", json={**body, "kind": "hard"}, headers=h(MATE))
    # одна пара у всех: время в UTC и название другим регистром — та же
    utc = datetime.fromisoformat(s).astimezone(timezone.utc)
    mate = c.get(_q(utc.isoformat().replace("+00:00", "Z"), "анализ  ДАННЫХ"), headers=h(MATE)).json()
    assert mate["counts"]["joy"] == 1 and mate["counts"]["hard"] == 1 and mate["mine"] == "hard"
    assert mate["open"] is True and "users" not in mate
    other = c.get(_q(s), headers=h(STRANGER)).json()            # другая группа — свой счёт
    assert sum(other["counts"].values()) == 0 and other["mine"] is None


@pytest.mark.asyncio
async def test_change_and_remove_own(client):
    c, h = client
    s = _start()
    # пятая — «Злой препод» (5.100.6)
    r = c.post("/api/lesson/reactions", json={"start": s, "title": "Матан", "kind": "angry"}, headers=h(ME)).json()
    assert r["counts"]["angry"] == 1 and r["mine"] == "angry"
    for kind in ("joy", "sleep"):
        r = c.post("/api/lesson/reactions", json={"start": s, "title": "Матан", "kind": kind}, headers=h(ME)).json()
    assert r["counts"]["joy"] == 0 and r["counts"]["sleep"] == 1 and r["mine"] == "sleep"
    r = c.post("/api/lesson/reactions", json={"start": s, "title": "Матан"}, headers=h(ME)).json()
    assert sum(r["counts"].values()) == 0 and r["mine"] is None


@pytest.mark.asyncio
async def test_only_after_start_and_two_weeks(client):
    c, h = client
    later = _start(-2)                                          # пара через 2 часа
    assert c.get(_q(later), headers=h(ME)).json()["open"] is False
    assert c.post("/api/lesson/reactions", json={"start": later, "title": "Матан", "kind": "joy"},
                  headers=h(ME)).status_code == 400
    old = _start(24 * 15)
    assert c.post("/api/lesson/reactions", json={"start": old, "title": "Матан", "kind": "joy"},
                  headers=h(ME)).status_code == 400


@pytest.mark.asyncio
async def test_validation(client):
    c, h = client
    s = _start()
    assert c.get(_q(s)).status_code == 401
    assert c.post("/api/lesson/reactions", json={"start": s, "title": "Матан", "kind": "fire"},
                  headers=h(ME)).status_code == 400
    assert c.post("/api/lesson/reactions", json={"start": "вчера", "title": "Матан", "kind": "joy"},
                  headers=h(ME)).status_code == 400
    assert c.post("/api/lesson/reactions", json={"start": s, "title": " ", "kind": "joy"},
                  headers=h(ME)).status_code == 400
    assert c.get("/api/v1/lesson/reactions?start=" + s.replace("+", "%2B") + "&title=x",
                 headers=h(ME)).status_code == 200


@pytest.mark.asyncio
async def test_not_member_has_no_group_counts(client, monkeypatch):
    import members
    c, h = client

    async def known(uid):
        return False
    monkeypatch.setattr(members, "known", known)
    assert c.get(_q(_start()), headers=h(ME)).status_code == 403


@pytest.mark.asyncio
async def test_ratelimit(client, monkeypatch):
    import ratelimit
    monkeypatch.setitem(ratelimit.LIMITS, "reaction", (2, 600))
    c, h = client
    s = _start()
    codes = [c.post("/api/lesson/reactions", json={"start": s, "title": "Матан", "kind": k},
                    headers=h(ME)).status_code for k in ("joy", "calm", "hard")]
    assert codes == [200, 200, 429]


@pytest.mark.asyncio
async def test_erased_with_user(client, db):
    import lesson_reactions as lr
    from database.privacy import erase_user
    c, h = client
    s = _start()
    c.post("/api/lesson/reactions", json={"start": s, "title": "Матан", "kind": "joy"}, headers=h(ME))
    await erase_user(ME)
    key = lr.lesson_key(datetime.fromisoformat(s), "Матан")
    assert (await lr.get(config.HOME_GROUP_ID, key, ME))["counts"]["joy"] == 0
