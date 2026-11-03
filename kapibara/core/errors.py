"""Ошибки на границе (HTTP-запрос, хендлер, задание) — docs/adr/0004-errors.md.

Чужой сервис не ответил (сеть, таймаут, СДО/ИИ лежат) — это не наш баг:
человеку «недоступно», в лог одна строка. Всё остальное — баг у нас: в лог
с traceback, чтобы его было видно в /status и было что чинить. Раньше оба
случая выглядели одинаково («СДО сейчас не отвечает»), и баг прятался.
"""
import asyncio
import contextlib
import logging

import httpx
from aiogram.exceptions import TelegramAPIError

# Сбои сети и чужих серверов: ожидаемы, traceback не нужен
NETWORK = (httpx.HTTPError, asyncio.TimeoutError, ConnectionError, TimeoutError)
# Telegram ответил отказом (бот заблокирован, чат пропал, сообщение не
# изменилось, лимит) — тоже чужой сервис, не наш баг
EXTERNAL = (*NETWORK, TelegramAPIError)


def log_failure(logger: logging.Logger, what: str, e: BaseException, expected: tuple = (),
                level: int = logging.WARNING) -> None:
    """Записать сбой на границе: сеть, отказ Telegram и `expected` — строкой (с уровнем
    `level`: частое и не страшное — INFO), остальное — warning с traceback."""
    if isinstance(e, EXTERNAL + tuple(expected)):
        logger.log(level, f"{what}: {type(e).__name__}: {e}")
    else:
        logger.warning(f"{what}: {type(e).__name__}: {e}", exc_info=e)


@contextlib.contextmanager
def aside(logger: logging.Logger, what: str, expected: tuple = (), level: int = logging.WARNING):
    """Граница вспомогательного шага (ADR 0004): не вышло — в лог (сеть и
    `expected` — строкой, баг — с traceback, log_failure), работа идёт дальше.
    Одна рассылка не должна вставать из-за одного человека, синк — из-за
    сообщения старосте. Отмена задачи (CancelledError) проходит насквозь.

        for uid in users:
            with aside(logger, f"утро: {uid}"):
                await deliver(...)
    """
    try:
        yield
    except Exception as e:  # noqa: BLE001 — та самая граница, одна на весь код
        log_failure(logger, what, e, expected, level)
