"""Несколько аккаунтов старосты: STAROSTA_ID="111,222" (второй аккаунт владельца)."""
import time

import pytest

from kapibara.core import config


def test_parse_ids():
    assert config.parse_ids("111") == (111,)
    assert config.parse_ids("111,222") == (111, 222)
    assert config.parse_ids(" 111 , 222 ;333") == (111, 222, 333)
    assert config.parse_ids("0") == () and config.parse_ids("") == ()


@pytest.mark.asyncio
async def test_second_account_is_starosta_everywhere(db, monkeypatch):
    # раньше int("111,222") ронял бота при запуске
    monkeypatch.setattr(config, "STAROSTA_IDS", (111, 222))
    monkeypatch.setattr(db.deadlines, "STAROSTA_IDS", (111, 222))
    assert config.is_starosta(222) and not config.is_starosta(333)
    # общий дедлайн, добавленный со второго аккаунта, видят все
    await db.add_deadline("Курсовая", "", "2026-10-05", None, 222)
    await db.add_deadline("Личное 333", "", "2026-10-05", None, 333)
    seen = [d["subject"] for d in await db.get_active_deadlines(444)]
    assert seen == ["Курсовая"]
    assert db.is_shared_deadline({"created_by": 222})


@pytest.mark.asyncio
async def test_second_account_runs_starosta_command(monkeypatch):
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    from kapibara.features.pulse import check as pulse_check
    from handlers import announce
    from tests.test_solver_render import RecordingSession

    async def fake():
        return {"ok": True, "status": 200, "why": "пускает", "ms": 5}

    monkeypatch.setattr(config, "STAROSTA_IDS", (111, 222))
    monkeypatch.setattr(pulse_check, "check", fake)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(announce.router)
    try:
        u = User(id=222, is_bot=False, first_name="Второй")
        msg = Message(message_id=1, date=0, chat=Chat(id=222, type="private"), from_user=u, text="/pulsecheck")
        await dp.feed_update(bot, Update(update_id=int(time.time()), message=msg))
    finally:
        announce.router._parent_router = None
    assert any("Пульс МИРЭА" in t for t, _ in bot.session.sent)

