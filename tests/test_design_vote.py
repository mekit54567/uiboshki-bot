"""Переход на новый дизайн (шаг 9, Никита 18.11): «Новое» — основной вид, у
кого была тёмная — сравнить «Ночную тетрадь» с прежней и один раз ответить,
какая лучше. Голос — один на человека, в /stats только счёт."""
import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_one_vote_per_person_and_counts(db):
    from database import design_votes
    assert await design_votes.counts() == {"new": 0, "old": 0}
    await design_votes.vote(1, "old", "2026-11-18T10:00:00+03:00")
    await design_votes.vote(2, "new", "2026-11-18T10:01:00+03:00")
    await design_votes.vote(1, "new", "2026-11-21T10:00:00+03:00")   # передумал — голос заменился
    assert await design_votes.counts() == {"new": 2, "old": 0}
    with pytest.raises(ValueError):
        await design_votes.vote(3, "всё", "2026-11-18T10:00:00+03:00")


def test_stats_line_only_counts():
    from kapibara.ops.stats import dark_vote_line
    assert dark_vote_line({"new": 0, "old": 0}) == ""
    assert dark_vote_line({}) == ""
    assert dark_vote_line({"new": 12, "old": 4}) == "\nКакая тёмная лучше: новая — <b>12</b> · прежняя — <b>4</b>"


@pytest.mark.asyncio
async def test_vote_goes_with_erased_data(db):
    from database import design_votes, upsert_user
    from database.privacy import erase_user
    await upsert_user(1, "", "Аня")
    await design_votes.vote(1, "new", "2026-11-18T10:00:00+03:00")
    await erase_user(1)
    assert await design_votes.counts() == {"new": 0, "old": 0}


def test_vote_api(db, monkeypatch):
    import webapp.server as server
    from database import design_votes
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    assert c.post("/api/design/vote", headers=h, json={"choice": "old"}).json() == {"ok": True}
    assert c.post("/api/v1/design/vote", headers=h, json={"choice": "new"}).json() == {"ok": True}
    assert c.post("/api/design/vote", headers=h, json={"choice": "<b>"}).status_code == 400
    assert c.post("/api/design/vote", json={"choice": "new"}).status_code == 401
    assert asyncio.run(design_votes.counts()) == {"new": 1, "old": 0}
