"""Куда ушло время запроса приложения: база, СДО — для «Долгих запросов» в
/status (19.10: цель меняли по 15 с, а по /status было не понять, ждали ли
базу, СДО или сам сервер). Счётчик ставит webapp/server.py на каждый запрос;
вне запроса (рассылки, синк) ничего не считается."""

import time
from contextvars import ContextVar

_spent: ContextVar[dict | None] = ContextVar("spent", default=None)


def start() -> dict:
    d: dict = {}
    _spent.set(d)
    return d


def spend(kind: str, seconds: float) -> None:
    d = _spent.get()
    if d is not None:
        d[kind] = d.get(kind, 0.0) + seconds
        d[kind + "_n"] = d.get(kind + "_n", 0) + 1


class Timed:
    """async with вокруг другого async with: время внутри — в счётчик kind."""

    def __init__(self, cm, kind: str):
        self._cm, self._kind = cm, kind

    async def __aenter__(self):
        self._t = time.monotonic()
        return await self._cm.__aenter__()

    async def __aexit__(self, *exc):
        try:
            return await self._cm.__aexit__(*exc)
        finally:
            spend(self._kind, time.monotonic() - self._t)
