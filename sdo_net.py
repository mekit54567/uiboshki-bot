"""Клиент к СДО (online-edu.mirea.ru) с «предохранителем».

16.10: СДО перестал пускать сервер бота (соединение висит до таймаута), и
каждый запрос приложения к СДО ждал по 30 с — вкладка СДО крутила загрузку
без конца, приложение писало «Сервер не отвечает», хотя сервер отвечал.
Теперь: не соединились с СДО — следующие DOWN_SECONDS запросы к нему сразу
падают той же ошибкой httpx.ConnectError (её уже ловят и пишут «СДО сейчас
не отвечает»), потом снова пробуем. Соединение ждём не дольше CONNECT_TIMEOUT.

16.10 (Amvera): одна неудача на залпе запросов выключала СДО всем на 3 минуты,
хотя СДО отвечал. Теперь предохранитель срабатывает после TRIP_AFTER неудач
подряд (любой ответ СДО сбрасывает счёт), а одновременно к СДО с сервера идёт
не больше MAX_PARALLEL запросов — все студенты ходят с одного адреса.
"""
import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

DOWN_SECONDS = 180
CONNECT_TIMEOUT = 6
TRIP_AFTER = 3
MAX_PARALLEL = 6

_down_until = 0.0
_fails = 0
_gate: tuple[object, asyncio.Semaphore] | None = None


def _sem() -> asyncio.Semaphore:
    global _gate                     # свой на цикл событий: в тестах у каждого теста новый
    loop = asyncio.get_running_loop()
    if _gate is None or _gate[0] is not loop:
        _gate = (loop, asyncio.Semaphore(MAX_PARALLEL))
    return _gate[1]


def is_down() -> bool:
    return time.monotonic() < _down_until


def mark_down() -> None:
    global _down_until
    _down_until = time.monotonic() + DOWN_SECONDS


def reset() -> None:
    global _down_until, _fails, _gate
    _down_until = 0.0
    _fails = 0
    _gate = None


def client(cookie: str, timeout: float = 30) -> httpx.AsyncClient:
    c = httpx.AsyncClient(cookies={"MoodleSession": cookie}, follow_redirects=True,
                          timeout=httpx.Timeout(timeout, connect=min(timeout, CONNECT_TIMEOUT)))
    send = c.send

    async def guarded(request, **kw):
        global _fails
        if is_down():
            raise httpx.ConnectError("СДО недоступен с сервера (недавно не ответил)", request=request)
        try:
            async with _sem():
                resp = await send(request, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            _fails += 1
            if _fails >= TRIP_AFTER:
                logger.warning(f"СДО: нет соединения с сервера ({type(e).__name__}, {_fails} раз подряд) — "
                               f"{DOWN_SECONDS} с не пробуем")
                mark_down()
            else:
                logger.info(f"СДО: не соединились ({type(e).__name__}), неудача {_fails} из {TRIP_AFTER}")
            raise
        _fails = 0
        return resp

    c.send = guarded
    return c
