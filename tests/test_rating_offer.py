"""Предложение показаться в рейтинге (rating_offer.py): варианты А и В, без тёмных паттернов."""
from datetime import UTC, datetime, timedelta

import pytest

from kapibara.features.social import rating_offer as offer
from kapibara.features.social import xp

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh():
    xp.forget()
    yield
    xp.forget()


async def _person(db, uid=1, joined=T0):
    await db.upsert_user(uid, f"u{uid}", f"Имя{uid} Фамилия")
    from database._conn import connect
    async with connect() as c:
        await c.execute("UPDATE users SET joined_at = ? WHERE user_id = ?",
                        (joined.strftime("%Y-%m-%d %H:%M:%S"), uid))
        await c.commit()


@pytest.mark.asyncio
async def test_sheet_not_before_two_hours_card_at_once(db):
    await _person(db)
    assert await offer.state(1, T0 + timedelta(hours=1)) == {"card": True, "sheet": False}
    assert await offer.state(1, T0 + timedelta(hours=2)) == {"card": True, "sheet": True}


@pytest.mark.asyncio
async def test_sheet_every_14_days_three_times_max(db):
    await _person(db)
    now = T0 + timedelta(hours=3)
    for _ in range(3):
        assert (await offer.state(1, now))["sheet"] is True
        await offer.act(1, "shown", now=now)
        assert (await offer.state(1, now))["sheet"] is False            # не на каждом входе
        assert (await offer.state(1, now + timedelta(days=13)))["sheet"] is False
        now += timedelta(days=14)
    assert (await offer.state(1, now + timedelta(days=100)))["sheet"] is False   # максимум 3


@pytest.mark.asyncio
async def test_stop_is_forever(db):
    await _person(db)
    await offer.act(1, "stop", now=T0)
    assert await offer.state(1, T0 + timedelta(days=400)) == {"card": False, "sheet": False}


@pytest.mark.asyncio
async def test_not_now_hides_card_for_two_weeks(db):
    await _person(db)
    await offer.act(1, "later", now=T0)
    assert (await offer.state(1, T0 + timedelta(days=13)))["card"] is False
    assert (await offer.state(1, T0 + timedelta(days=14)))["card"] is True


@pytest.mark.asyncio
async def test_nothing_to_offer_when_already_visible(db):
    await _person(db)
    await xp.save(1, show=True)
    assert await offer.state(1, T0 + timedelta(days=30)) == {"card": False, "sheet": False}


@pytest.mark.asyncio
async def test_offer_never_turns_anything_on(db):
    await _person(db)
    for a in ("shown", "later", "accepted"):
        await offer.act(1, a, "card", now=T0)
    p = await xp.profile(1)
    assert not p["show"] and not p["show_all"]


@pytest.mark.asyncio
async def test_bad_action_and_source(db):
    await _person(db)
    with pytest.raises(ValueError):
        await offer.act(1, "enable")
    with pytest.raises(ValueError):
        await offer.act(1, "accepted", "magic")


@pytest.mark.asyncio
async def test_counts_by_source(db):
    for uid in (1, 2, 3):
        await _person(db, uid)
    await offer.act(1, "shown", now=T0)
    await offer.act(1, "accepted", "sheet", now=T0)
    await offer.act(2, "accepted", "card", now=T0)
    await offer.act(2, "accepted", "event", now=T0)        # засчитан первый
    await offer.act(3, "stop", now=T0)
    assert await offer.counts() == {"card": 1, "sheet": 1, "event": 0, "shown": 1, "stopped": 1}


def _board(week_xp=0, places=(5, 3)):
    hist = [{"week": "a", "xp": 1, "place": places[0], "place_inst": 1},
            {"week": "b", "xp": 2, "place": places[1], "place_inst": 1}]
    return {"people": {1: {"group": 7}}, "history": {7: hist}, "groups": {7: {"name": "УИБО-03-24"}},
            "xp": {1: {"total": week_xp}}, "week_start": {1: {"total": 0}}}


def test_reason_group_up_then_xp_then_none():
    assert offer.reason(_board(), 1) == {"kind": "group", "group": "УИБО-03-24", "place": 3, "up": 2}
    assert offer.reason(_board(week_xp=50, places=(3, 3)), 1) == {"kind": "xp", "week": 50}
    assert offer.reason(_board(week_xp=10, places=(3, 5)), 1) is None
    assert offer.reason(_board(), 99) is None


def test_event_text_does_not_pressure():
    for why in ({"kind": "xp", "week": 40}, {"kind": "group", "group": "Г", "place": 2, "up": 1}):
        _t, body, html = offer.text(why)
        assert "решать тебе" in body
        assert "чтобы видеть" not in body.lower() and html.startswith("<b>")


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text, **kw):
        self.sent.append(uid)


async def _run(db, monkeypatch, *, joined=T0 - timedelta(days=10), now=T0, notify=None, board=None):
    from kapibara.features.notifications import broadcast

    async def nap():
        return None
    monkeypatch.setattr(broadcast, "pace", nap)
    await _person(db, 1, joined)
    if notify is not None:
        from database._conn import connect
        async with connect() as c:
            await c.execute("UPDATE users SET notify = ? WHERE user_id = ?", (notify, 1))
            await c.commit()

    async def fake_board():
        return board or _board(week_xp=60, places=(3, 3))
    monkeypatch.setattr(xp, "board", fake_board)
    delivered = []

    async def fake_deliver(bot, uid, html, **kw):
        delivered.append((uid, kw["kind"], kw.get("tab")))
    from kapibara.features.notifications import delivery
    monkeypatch.setattr(delivery, "deliver", fake_deliver)
    return delivered, await offer.send_events(_Bot(), now)


@pytest.mark.asyncio
async def test_event_sent_once_a_month(db, monkeypatch):
    delivered, n = await _run(db, monkeypatch)
    assert n == 1 and delivered == [(1, "rating", "more")]
    assert await offer.send_events(_Bot(), T0 + timedelta(days=29)) == 0
    assert await offer.send_events(_Bot(), T0 + timedelta(days=30)) == 1


@pytest.mark.asyncio
async def test_event_skips_new_stopped_visible_important_and_quiet(db, monkeypatch):
    _d, n = await _run(db, monkeypatch, joined=T0 - timedelta(days=1))
    assert n == 0                                               # только пришёл
    assert await offer.send_events(_Bot(), T0 + timedelta(days=5)) == 1
    await offer.act(1, "stop")
    assert await offer.send_events(_Bot(), T0 + timedelta(days=90)) == 0   # «больше не предлагать»


@pytest.mark.asyncio
async def test_event_respects_quiet_hours(db, monkeypatch):
    night = datetime(2026, 11, 18, 21, 30, tzinfo=UTC)          # 00:30 по Москве
    _d, n = await _run(db, monkeypatch, notify='{"quiet": true}', now=night)
    assert n == 0


@pytest.mark.asyncio
async def test_event_not_for_only_important_profile(db, monkeypatch):
    from kapibara.features.notifications import prefs
    import json
    _d, n = await _run(db, monkeypatch, notify=json.dumps(prefs.PROFILES["important"]))
    assert n == 0


@pytest.mark.asyncio
async def test_event_not_right_after_sheet(db, monkeypatch):
    await _person(db, 1, T0 - timedelta(days=10))
    await offer.act(1, "shown", now=T0 - timedelta(days=1))
    _d, n = await _run(db, monkeypatch)
    assert n == 0


@pytest.mark.asyncio
async def test_api_offer(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "u", "Alice")
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/rating/offer", headers=h).json()["card"] is True
    assert c.post("/api/rating/offer", headers=h, json={"action": "later"}).json()["card"] is False
    assert c.post("/api/rating/offer", headers=h, json={"action": "bogus"}).status_code == 400
