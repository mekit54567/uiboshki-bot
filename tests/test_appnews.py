"""Рассылка «у Капибары своё приложение» (/appnews, Никита 05.11): превью
старосте, рассылка только по кнопке и один раз."""
import pytest

from tests.conftest import STAROSTA_ID
from tests.test_review_bot import bot, dp, press, send  # noqa: F401 — фикстуры

ME = 555001


@pytest.mark.asyncio
async def test_appnews_preview_then_once(db, bot, dp, monkeypatch):  # noqa: F811
    from database import get_setting
    from kapibara.core import config
    from kapibara.features.notifications import broadcast
    monkeypatch.setattr(broadcast, "PACE_SECONDS", 0)
    monkeypatch.setattr(config, "APPSTORE_URL", "")
    await db.upsert_user(ME, "", "u")

    await send(dp, bot, "/appnews", uid=ME)                                  # не староста — ничего
    assert not any("своё приложение" in t for t in bot.session.texts())
    await send(dp, bot, "/appnews", uid=STAROSTA_ID)                          # превью, ничего не разослано
    assert "своё приложение" in bot.session.texts()[-2]
    assert await get_setting("appnews:sent") is None

    before = len(bot.session.texts())
    await press(dp, bot, "appnews:go", uid=STAROSTA_ID)
    sent = bot.session.texts()[before:]
    assert sum("своё приложение" in t for t in sent) >= 1 and await get_setting("appnews:sent")
    n = len(bot.session.texts())
    await press(dp, bot, "appnews:go", uid=STAROSTA_ID)                       # второй раз — тишина
    assert not any("своё приложение" in t for t in bot.session.texts()[n:])


def test_appnews_links():
    from handlers import appnews
    from kapibara.core import config
    urls = [b.url for row in appnews.news_kb().inline_keyboard for b in row]
    assert config.RUSTORE_URL in urls and any("apps.apple.com" in u for u in urls)
