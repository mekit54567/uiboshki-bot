"""kapibara.core.errors: одна граница для вспомогательных шагов (ADR 0004)."""
import asyncio
import logging

import httpx
import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from kapibara.core.errors import aside

log = logging.getLogger("test.aside")


def _records(caplog):
    return [(r.levelno, r.exc_info is not None) for r in caplog.records if r.name == "test.aside"]


def test_external_failures_one_line(caplog):
    """Сеть и отказ Telegram (бот заблокирован) — одна строка без traceback,
    с заданным уровнем: в утренней рассылке их много, и это не наш баг."""
    caplog.set_level(logging.INFO)
    with aside(log, "рассылка 1", level=logging.INFO):
        raise TelegramForbiddenError(SendMessage(chat_id=1, text="x"), "bot was blocked by the user")
    with aside(log, "рассылка 2"):
        raise httpx.ConnectError("нет сети")
    assert _records(caplog) == [(logging.INFO, False), (logging.WARNING, False)]


def test_bug_with_traceback_and_work_goes_on(caplog):
    """Баг у нас — warning с traceback (его видно в /status), а цикл идёт дальше."""
    done = []
    for uid in (1, 2):
        with aside(log, f"рассылка {uid}", level=logging.INFO):
            if uid == 1:
                raise KeyError("subject")
            done.append(uid)
    assert done == [2]
    assert _records(caplog) == [(logging.WARNING, True)]


def test_expected_types_and_cancel():
    """`expected` — тоже без traceback; отмену задачи aside не глотает."""
    with aside(log, "разбор", expected=(ValueError,)):
        int("x")

    async def job():
        with aside(log, "задание"):
            await asyncio.sleep(10)

    async def main():
        t = asyncio.ensure_future(job())
        await asyncio.sleep(0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    asyncio.run(main())
