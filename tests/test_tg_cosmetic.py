"""kapibara.core.telegram.cosmetic (02.11): мелкие действия в Telegram не ломают
ответ, но и не глотают баги молча (docs/adr/0004-errors.md)."""
import logging

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup

from kapibara.core.telegram import cosmetic


def test_expected_telegram_error_is_quiet(caplog):
    with caplog.at_level(logging.DEBUG, logger="kapibara.core.telegram"):
        with cosmetic("тест"):
            raise TelegramBadRequest(EditMessageReplyMarkup(), "message is not modified")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_unexpected_error_is_logged_with_traceback(caplog):
    with caplog.at_level(logging.WARNING, logger="kapibara.core.telegram"):
        with cosmetic("тест"):
            raise AttributeError("'NoneType' object has no attribute 'edit_text'")
    [rec] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "тест" in rec.getMessage() and rec.exc_info


def test_cancellation_is_not_swallowed():
    import asyncio
    with pytest.raises(asyncio.CancelledError):
        with cosmetic("тест"):
            raise asyncio.CancelledError
