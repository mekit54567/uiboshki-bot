"""Inline-режим: «@бот» в любом чате → карточки сегодня/завтра/неделя;
фамилия/группа/аудитория → их расписание (не больше трёх, с таймаутом)."""
import asyncio
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineQuery, Update, User

from tests.test_solver_render import RecordingSession


class Session(RecordingSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.answers = []

    async def make_request(self, bot, method, timeout=None):
        if type(method).__name__ == "AnswerInlineQuery":
            self.answers.append(method)
            return True
        return await super().make_request(bot, method, timeout)


async def _ask(text: str):
    from handlers import inline
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=Session())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(inline.router)
    try:
        q = InlineQuery(id="1", from_user=User(id=5, is_bot=False, first_name="A"), query=text, offset="")
        await dp.feed_update(bot, Update(update_id=int(time.time()), inline_query=q))
    finally:
        inline.router._parent_router = None
    return bot.session.answers[0]


@pytest.fixture
def schedule(monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser

    async def today():
        return "📅 <b>Сегодня</b>\nМатан"

    async def tomorrow():
        return "🌙 <b>Завтра</b>\n" + "Длинная строка пары\n" * 400       # больше лимита Telegram

    async def week():
        return "🗓 <b>Неделя</b>"

    monkeypatch.setattr(schedule_parser, "get_today_schedule", today)
    monkeypatch.setattr(schedule_parser, "get_tomorrow_schedule", tomorrow)
    monkeypatch.setattr(schedule_parser, "get_week_schedule", week)


@pytest.mark.asyncio
async def test_empty_query_three_own_cards(schedule):
    ans = await _ask("")
    titles = [r.title for r in ans.results]
    assert len(titles) == 3 and "Сегодня" in titles[0] and "Неделя" in titles[2]
    assert ans.is_personal and all(len(r.input_message_content.message_text) <= 4096 for r in ans.results)
    assert ans.results[1].input_message_content.message_text.endswith("…")
    assert "t.me/" in ans.results[0].reply_markup.inline_keyboard[0][0].url


@pytest.mark.asyncio
async def test_day_word_filters(schedule):
    ans = await _ask("завтра")
    assert [r.title.split()[1] for r in ans.results] == ["Завтра"]


@pytest.mark.asyncio
async def test_teacher_search_skips_slow(monkeypatch):
    from kapibara.features.schedule import index as schedule_index
    from handlers import inline, schedule as sched

    async def search(q, types=(1, 2, 3), limit=20):
        return [{"type": 2, "id": 1, "title": "Морозов А. В."}, {"type": 2, "id": 2, "title": "Морозова Е. А."}]

    async def render(tid, ttype, title):
        if tid == 2:
            await asyncio.sleep(1)                                          # «зависло»
        return f"👤 <b>{title}</b>\nпары"

    monkeypatch.setattr(schedule_index, "search", search)
    monkeypatch.setattr(sched, "render_target_schedule", render)
    monkeypatch.setattr(inline, "TARGET_TIMEOUT", 0.05)
    ans = await _ask("Морозов")
    assert [r.title for r in ans.results] == ["👤 Морозов А. В."]


@pytest.mark.asyncio
async def test_short_query_empty(schedule):
    assert (await _ask("Мо")).results == []
