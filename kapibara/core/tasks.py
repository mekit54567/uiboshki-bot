"""Фоновые задачи без потери (Ruff RUF006, ревью 03.11).

asyncio держит на задачу только слабую ссылку: задача, которую никто не
запомнил, может пропасть посреди работы при сборке мусора. spawn запоминает
её, пока она идёт, и пишет в лог, если она упала (иначе ошибка видна только
как «Task exception was never retrieved» при выходе).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_running: set[asyncio.Task] = set()


def _done(task: asyncio.Task) -> None:
    _running.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("фоновая задача %s упала", task.get_name(), exc_info=exc)


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _running.add(task)
    task.add_done_callback(_done)
    return task
