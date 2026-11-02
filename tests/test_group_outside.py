"""Этап 1 (д): снаружи — inline-карточки группы того, кто пишет; /stats по
группам; описание бота и сайт — для любой группы."""
import pytest

from kapibara.core import config

OTHER = 5001


@pytest.mark.asyncio
async def test_inline_cards_of_users_group(db, monkeypatch):
    import handlers.inline as inline
    from database.groups import upsert_group
    await upsert_group(OTHER, "УИБО-01-24")
    await db.upsert_user(601, "", "x")
    await db.set_user_group(601, OTHER)
    monkeypatch.setattr(inline, "_card_base", lambda: "https://app.example")
    other = await inline._own_results(None, 601)
    assert other[0].title == "📅 Сегодня — УИБО-01-24" and f"-1-{OTHER}-" in other[0].photo_url
    own = await inline._own_results("week", None)
    assert own[0].title == f"🗓 Неделя — {config.GROUP_NAME}" and "week-0-0-" in own[0].photo_url


def test_stats_groups_line():
    from kapibara.ops import stats
    assert stats.groups_line([{"id": 4928, "name": "УИБО-03-24", "users": 25}]) == ""     # одна группа — молчим
    line = stats.groups_line([{"id": 4928, "name": "УИБО-03-24", "users": 25},
                              {"id": OTHER, "name": "УИБО-01-24", "users": 3}, {"id": None, "name": "", "users": 2}])
    assert line == "\nГруппы: УИБО-03-24 — 25 · УИБО-01-24 — 3 · без группы — 2"


def test_description_is_for_any_group():
    import bot
    assert "любой группы" in bot.BOT_DESCRIPTION and len(bot.BOT_SHORT_DESCRIPTION) <= 120
    assert len(bot.BOT_DESCRIPTION.format(group=config.GROUP_NAME)) <= 512           # лимит Telegram
