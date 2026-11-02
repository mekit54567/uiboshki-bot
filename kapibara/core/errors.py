"""Ошибки на границе (HTTP-запрос, хендлер, задание) — docs/adr/0004-errors.md.

Чужой сервис не ответил (сеть, таймаут, СДО/ИИ лежат) — это не наш баг:
человеку «недоступно», в лог одна строка. Всё остальное — баг у нас: в лог
с traceback, чтобы его было видно в /status и было что чинить. Раньше оба
случая выглядели одинаково («СДО сейчас не отвечает»), и баг прятался.
"""
import asyncio
import logging

import httpx

# Сбои сети и чужих серверов: ожидаемы, traceback не нужен
NETWORK = (httpx.HTTPError, asyncio.TimeoutError, ConnectionError, TimeoutError)


def log_failure(logger: logging.Logger, what: str, e: BaseException, expected: tuple = ()) -> None:
    """Записать сбой на границе: сеть и `expected` — строкой, остальное — с traceback."""
    known = isinstance(e, NETWORK + tuple(expected))
    logger.warning(f"{what}: {type(e).__name__}: {e}", exc_info=None if known else e)
