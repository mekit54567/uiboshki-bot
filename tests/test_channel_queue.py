"""Посты каналов сами по очереди (/channel auto, Никита 05.11): первый пост
каждого канала сразу, дальше «Капибара» раз в 20–30 мин, «Разработка» раз
в 4–6 ч, ночью (23–9 МСК) — пауза; очередь в базе, её можно отменить."""
import random
from datetime import datetime, timedelta

import pytest

from kapibara.core import config
from kapibara.core.utils import TZ
from kapibara.features.content import channel_posts, channel_queue
from tests.conftest import STAROSTA_ID
from tests.test_channel_posts import _post
from tests.test_review_bot import bot, dp, press, send  # noqa: F401 — фикстуры


def _posts(tmp_path, monkeypatch):
    for slug in ("25-news-hello-pinned", "26-news-stores", "27-news-sdo", "30-stores", "31-kassa", "32-cleanup"):
        _post(tmp_path, slug, f"<b>{slug}</b>")
    monkeypatch.setattr(channel_posts, "POSTS_DIR", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", "-1001")
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "-1002")
    monkeypatch.setattr(config, "STAROSTA_ID", STAROSTA_ID)


def test_plan_gaps_and_night(tmp_path, monkeypatch):
    _posts(tmp_path, monkeypatch)
    now = datetime(2026, 11, 6, 12, 0, tzinfo=TZ)
    items = channel_queue.plan(channel_posts.load_posts(), {"25-news-hello-pinned": {}}, now, random.Random(1))
    news = [datetime.fromisoformat(i["at"]) for i in items if "news" in i["slug"]]
    dev = [datetime.fromisoformat(i["at"]) for i in items if "news" not in i["slug"]]
    assert [i["slug"] for i in items if "news" in i["slug"]] == ["26-news-stores", "27-news-sdo"]   # вышедший — нет
    assert news[0] == now and dev[0] == now                                   # первые — сразу
    assert timedelta(minutes=20) <= news[1] - news[0] <= timedelta(minutes=30)
    assert timedelta(hours=4) <= dev[1] - dev[0] <= timedelta(hours=6)
    late = datetime(2026, 11, 6, 22, 50, tzinfo=TZ)                           # ночью — ждём 9:00
    items = channel_queue.plan(channel_posts.load_posts(), {}, late, random.Random(1))
    dev = [datetime.fromisoformat(i["at"]) for i in items if "news" not in i["slug"]]
    assert dev[0] == late and dev[1] == datetime(2026, 11, 7, 9, 0, tzinfo=TZ)
    assert all(not channel_queue.is_night(t) for t in dev[1:])


@pytest.mark.asyncio
async def test_auto_go_tick_and_stop(db, bot, dp, tmp_path, monkeypatch):  # noqa: F811
    _posts(tmp_path, monkeypatch)
    await send(dp, bot, "/channel auto", uid=STAROSTA_ID)
    assert "Выпустить всё по очереди" in bot.session.texts()[-1]
    assert await channel_queue.load() == []                                    # без кнопки — ничего
    await press(dp, bot, "chan:auto:go", uid=STAROSTA_ID)
    done = await channel_posts.published()
    assert set(done) == {"25-news-hello-pinned", "30-stores"}                  # первые обоих каналов — сразу
    left = await channel_queue.load()
    assert [i["slug"] for i in left if "news" in i["slug"]] == ["26-news-stores", "27-news-sdo"]

    # подошло время — по одному на канал за раз; ночью — ничего
    late = max(datetime.fromisoformat(i["at"]) for i in left) + timedelta(hours=1)
    night = late.replace(hour=2)
    assert await channel_queue.tick(bot, night) == []
    day = late.replace(hour=12) + timedelta(days=1)
    assert await channel_queue.tick(bot, day) == ["26-news-stores", "31-kassa"]
    assert any("Вышел по очереди" in t for t in bot.session.texts())

    await send(dp, bot, "/channel auto", uid=STAROSTA_ID)                      # идёт — видно очередь и «Отменить»
    assert "Очередь постов" in bot.session.texts()[-1]
    await press(dp, bot, "chan:auto:stop", uid=STAROSTA_ID)
    assert await channel_queue.load() == [] and "отменена, не вышло 2" in bot.session.texts()[-1]
    assert await channel_queue.tick(bot, day + timedelta(days=1)) == []


@pytest.mark.asyncio
async def test_not_starosta_cannot_start(db, bot, dp, tmp_path, monkeypatch):  # noqa: F811
    _posts(tmp_path, monkeypatch)
    await press(dp, bot, "chan:auto:go", uid=555002)
    assert await channel_queue.load() == [] and await channel_posts.published() == {}
