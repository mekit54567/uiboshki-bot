"""Группа месяца (group_award.py, 5.100.7): опыт за месяц на человека, ≥3 с
опытом, своя группа не участвует; 7 дней «Капибары+» всем в группе — один раз."""
from datetime import date, datetime, timedelta

import pytest

import group_award
import scheduler
import xp
from database.billing import get_sub
from tests.conftest import STAROSTA_ID
from tests.test_review_bot import bot, dp  # noqa: F401 — фикстуры


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    xp.forget()
    monkeypatch.setattr(scheduler, "PACE_SECONDS", 0)
    yield
    xp.forget()


def _month() -> tuple[str, str, str]:
    """Прошлый месяц: «ГГГГ-ММ», день до него и день в нём."""
    month = group_award.prev_month()
    start = date.fromisoformat(month + "-01")
    return month, (start - timedelta(days=1)).isoformat(), (start + timedelta(days=5)).isoformat()


async def _people(db, rows):
    """rows: (uid, группа или None, баллы до месяца, баллы в конце месяца)."""
    from database.groups import set_user_group, upsert_group
    await upsert_group(501, "УИБО-01-24")
    await upsert_group(502, "ИКБО-02-24")
    await upsert_group(503, "БСБО-03-24")
    _, before, inside = _month()
    for uid, gid, was, now in rows:
        await db.upsert_user(uid, f"u{uid}", f"Имя{uid} Ф")
        if gid is not None:
            await set_user_group(uid, gid)
        if was:
            await db.save_score_points(uid, before, {1: was})
        if now:
            await db.save_score_points(uid, inside, {1: now})


ROWS = [
    # своя группа — больше всех, но не участвует
    (1, None, 0, 90), (2, None, 0, 90), (3, None, 0, 90),
    # 501: по 20 за месяц на троих (до месяца было много — не в счёт); четвёртый без опыта
    (11, 501, 100, 120), (12, 501, 100, 120), (13, 501, 100, 120), (14, 501, 0, 0),
    # 502: всего больше, но двое — вне награды
    (21, 502, 0, 200), (22, 502, 0, 200),
    # 503: по 10 на троих
    (31, 503, 0, 10), (32, 503, 0, 10), (33, 503, 0, 10),
]


@pytest.mark.asyncio
async def test_standings_per_person_month_only(db):
    await _people(db, ROWS)
    month = _month()[0]
    table = await group_award.standings(month)
    assert [(g["name"], g["avg"], g["people"]) for g in table] == [("УИБО-01-24", 20, 3), ("БСБО-03-24", 10, 3)]


@pytest.mark.asyncio
async def test_award_once_to_whole_group(db, bot):  # noqa: F811
    await _people(db, ROWS)
    month = _month()[0]
    res = await group_award.award(bot, month)
    assert res["name"] == "УИБО-01-24" and res["granted"] == 4
    for uid in (11, 12, 13, 14):                         # и тот, у кого опыта нет
        assert (await get_sub(uid))["source"] == "group_award"
    for uid in (1, 21, 31):
        assert await get_sub(uid) is None
    texts = {m.chat_id: m.text for m in bot.session.named("SendMessage")}
    assert "самая активная группа МИРЭА" in texts[14] and "7 дней" in texts[14]
    assert "УИБО-01-24" in texts[STAROSTA_ID] and "БСБО-03-24" in texts[STAROSTA_ID]
    first = (await get_sub(11))["until"]
    assert await group_award.award(bot, month) is None   # второй раз — ничего
    assert (await get_sub(11))["until"] == first


@pytest.mark.asyncio
async def test_award_skips_blocked(db, bot, monkeypatch):  # noqa: F811
    """Ждёт удаления или без согласия — ни в счёт, ни в награду."""
    import privacy

    async def blocked(uid):
        return uid in (13, 14)
    monkeypatch.setattr(privacy, "blocked", blocked)
    await _people(db, ROWS)
    month = _month()[0]
    table = await group_award.standings(month)
    assert table[0]["name"] == "БСБО-03-24"                # у 501 осталось двое с опытом
    res = await group_award.award(bot, month)
    assert res["name"] == "БСБО-03-24"
    assert await get_sub(13) is None and await get_sub(14) is None


@pytest.mark.asyncio
async def test_no_winner_marks_month(db, bot):  # noqa: F811
    await _people(db, ROWS[:3])
    month = _month()[0]
    assert await group_award.award(bot, month) is None
    assert not [m for m in bot.session.named("SendMessage")]


def test_prev_month_and_bounds():
    msk = xp.MSK
    assert group_award.prev_month(datetime(2027, 1, 1, 12, 5, tzinfo=msk)) == "2026-12"
    assert group_award.prev_month(datetime(2026, 11, 1, 12, 5, tzinfo=msk)) == "2026-10"
    start, end = group_award._bounds("2026-12")
    assert (start.isoformat(), end.isoformat()) == ("2026-12-01T00:00:00+03:00", "2027-01-01T00:00:00+03:00")
