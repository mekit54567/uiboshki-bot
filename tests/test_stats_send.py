"""/stats, когда Telegram не принимает фото (17.11): цифры текстом сразу,
повторный /stats не плодит пачку картинок."""

import asyncio

import pytest
from aiogram.exceptions import TelegramServerError
from aiogram.methods import SendPhoto

from handlers import group_tools


class FakeBot:
    def __init__(self, photo_error=None, photo_wait=None):
        self.photos, self.texts = [], []
        self.photo_error, self.photo_wait = photo_error, photo_wait

    async def send_photo(self, chat_id, photo, **kw):
        if self.photo_wait:
            await self.photo_wait.wait()
        if self.photo_error:
            raise self.photo_error
        self.photos.append(chat_id)

    async def send_message(self, chat_id, text, **kw):
        self.texts.append((chat_id, text))


@pytest.fixture(autouse=True)
def fake_report(monkeypatch):
    from kapibara.ops import stats

    async def report(days):
        return b"png", "📊 Статистика за 30 дн."
    monkeypatch.setattr(stats, "report", report)


@pytest.mark.asyncio
async def test_photo_ok():
    bot = FakeBot()
    await group_tools._send_stats(bot, 1, 30)
    assert bot.photos == [1] and bot.texts == []


@pytest.mark.asyncio
async def test_photo_fails_text_instead():
    bot = FakeBot(photo_error=TelegramServerError(SendPhoto(chat_id=1, photo="x"), "Internal Server Error"))
    await group_tools._send_stats(bot, 1, 30)
    assert bot.photos == [] and len(bot.texts) == 1 and "Статистика" in bot.texts[0][1]
    assert 1 not in group_tools._STATS_SENDING


@pytest.mark.asyncio
async def test_repeat_while_sending_no_duplicate():
    gate = asyncio.Event()
    bot = FakeBot(photo_wait=gate)
    first = asyncio.create_task(group_tools._send_stats(bot, 1, 30))
    await asyncio.sleep(0)
    await group_tools._send_stats(bot, 1, 30)            # Никита жмёт /stats ещё раз
    assert len(bot.texts) == 1 and "уже в пути" in bot.texts[0][1]
    gate.set()
    await first
    assert bot.photos == [1]
