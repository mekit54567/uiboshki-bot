"""Кнопки постов канала (chan:pub/next/other) доходят до handlers/channel.py
через все роутеры, а не до кнопки подписки на канал при входе (start.py).
Живой случай 05.11: «↔ Канал» удалял превью и присылал приветствие."""
import pytest

from kapibara.core import config
from kapibara.features.content import channel_posts
from tests.conftest import STAROSTA_ID
from tests.test_channel_posts import _post
from tests.test_review_bot import bot, dp, press  # noqa: F401 — фикстуры


@pytest.mark.asyncio
async def test_post_buttons_reach_channel_router(db, bot, dp, tmp_path, monkeypatch):  # noqa: F811
    _post(tmp_path, "25-news-hello-pinned", "<b>Привет</b>")
    _post(tmp_path, "30-stores", "<b>Дорога в магазины</b>")
    _post(tmp_path, "31-kassa", "<b>Касса</b>")
    monkeypatch.setattr(channel_posts, "POSTS_DIR", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", "-1001234")
    monkeypatch.setattr(config, "LOGIN_CHANNEL", "@kapibara_mirea")
    await press(dp, bot, "chan:other:25-news-hello-pinned", uid=STAROSTA_ID)
    assert "<b>Дорога в магазины</b>" in bot.session.texts()
    assert not bot.session.named("DeleteMessage")
    await press(dp, bot, "chan:next:30-stores", uid=STAROSTA_ID)
    assert bot.session.texts()[-2] == "<b>Касса</b>"
    await press(dp, bot, "chan:pub:30-stores", uid=STAROSTA_ID)
    assert "30-stores" in await channel_posts.published()
