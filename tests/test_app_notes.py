"""Заметки к парам из приложения (владелец 09.10, 2.9): POST /api/notes —
как /note в боте, DELETE — своя или староста группы."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kapibara.core import config
from tests.conftest import STAROSTA_ID
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

AUTHOR, MATE, OTHER_GROUP_USER = 401, 402, 403
OTHER = 5001


@pytest.fixture
async def client(db, monkeypatch):
    from kapibara.core import ratelimit
    import webapp.server as server
    from database.groups import upsert_group
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    ratelimit._hits.clear()
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((AUTHOR, config.HOME_GROUP_ID), (MATE, config.HOME_GROUP_ID), (OTHER_GROUP_USER, OTHER)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    c = TestClient(server.app)

    def h(uid):
        return {"X-Telegram-Init-Data": _make_init_data(user={"id": uid, "first_name": "A"})}
    return c, h


def _day(n=1):
    from kapibara.core.utils import today_msk
    return (today_msk() + timedelta(days=n)).isoformat()


@pytest.mark.asyncio
async def test_add_note_shows_for_group(client):
    c, h = client
    r = c.post("/api/notes", json={"date": _day(), "subject": "Матан", "text": "  контрольная в 401 "},
               headers=h(AUTHOR))
    assert r.status_code == 200 and r.json()["ok"] is True
    mine = c.get(f"/api/notes?date={_day()}", headers=h(AUTHOR)).json()["items"]
    assert [(n["subject"], n["text"], n["mine"]) for n in mine] == [("Матан", "контрольная в 401", True)]
    mate = c.get(f"/api/notes?date={_day()}", headers=h(MATE)).json()["items"]
    assert [n["mine"] for n in mate] == [False]                     # одногруппник видит, но не своё
    assert c.get(f"/api/notes?date={_day()}", headers=h(OTHER_GROUP_USER)).json()["items"] == []
    assert c.post("/api/v1/notes", json={"date": _day(), "text": "x"}, headers=h(AUTHOR)).status_code == 200


@pytest.mark.asyncio
async def test_add_note_validation(client):
    c, h = client
    assert c.post("/api/notes", json={"date": _day(), "text": "x"}).status_code == 401
    assert c.post("/api/notes", json={"date": "завтра", "text": "x"}, headers=h(AUTHOR)).status_code == 400
    assert c.post("/api/notes", json={"date": _day(), "text": "   "}, headers=h(AUTHOR)).status_code == 400
    assert c.post("/api/notes", json={"date": _day(), "text": "я" * 501}, headers=h(AUTHOR)).status_code == 400
    assert c.post("/api/notes", json={"date": _day(-10), "text": "x"}, headers=h(AUTHOR)).status_code == 400
    assert c.post("/api/notes", json={"date": _day(400), "text": "x"}, headers=h(AUTHOR)).status_code == 400


@pytest.mark.asyncio
async def test_add_note_ratelimit(client, monkeypatch):
    from kapibara.core import ratelimit
    monkeypatch.setitem(ratelimit.LIMITS, "note", (2, 600))
    c, h = client
    codes = [c.post("/api/notes", json={"date": _day(), "text": f"{i}"}, headers=h(AUTHOR)).status_code
             for i in range(3)]
    assert codes == [200, 200, 429]


@pytest.mark.asyncio
async def test_delete_note_own_or_starosta(client, db):
    c, h = client
    nid = c.post("/api/notes", json={"date": _day(), "text": "моё"}, headers=h(AUTHOR)).json()["id"]
    assert c.delete(f"/api/notes/{nid}", headers=h(MATE)).status_code == 403           # чужую — нельзя
    assert c.delete(f"/api/notes/{nid}", headers=h(OTHER_GROUP_USER)).status_code == 404
    assert c.delete(f"/api/notes/{nid}", headers=h(AUTHOR)).status_code == 200
    assert await db.get_lesson_note(nid) is None
    nid = c.post("/api/notes", json={"date": _day(), "text": "ещё"}, headers=h(MATE)).json()["id"]
    await db.upsert_user(STAROSTA_ID, "", "староста")
    assert c.delete(f"/api/notes/{nid}", headers=h(STAROSTA_ID)).status_code == 200     # староста — любую
    assert c.delete("/api/notes/999999", headers=h(AUTHOR)).status_code == 404
