"""Подключение к базе. Путь читается в момент вызова (database.DATABASE_PATH),
а не копируется при импорте: тесты и /restore подменяют его в одном месте."""

import asyncio
import logging
import sqlite3

import aiosqlite

import database

# Сколько ждать занятую базу, прежде чем «database is locked». У sqlite3 по
# умолчанию 5 с — на Amvera (16.10, диск /data медленнее Railway) напоминания,
# снимок расписания и чтение настроек падали с locked, пока шла чужая запись.
BUSY_SECONDS = 15


class _Tuned(sqlite3.Connection):
    """В WAL — synchronous=NORMAL: запись не ждёт fsync диска на каждом commit
    (только на checkpoint). Для WAL это безопасно: при сбое питания теряются
    последние записи, база не бьётся. Не в WAL — как было (FULL)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            if self.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                self.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            pass


def connect():
    import timing                # время в базе — в «Долгие запросы» /status
    return timing.Timed(aiosqlite.connect(database.DATABASE_PATH, timeout=BUSY_SECONDS, factory=_Tuned), "db")


# Отметки «заходил» на каждом запросе (сессия устройства, users.last_seen) —
# в фоне: чтение в WAL не ждёт ничью запись, а запись ждёт замок до
# BUSY_SECONDS. После перезапуска первая такая запись была почти у каждого
# запроса, и пока база занята (синк СДО, сброс WAL на медленный диск),
# дедлайны, ДЗ и «СДО» отвечали по 30–35 с (Никита 17.10, /status).
# WAIT = True — писать сразу (тесты сверяют базу сразу после запроса).
WAIT = False
_background: set[asyncio.Task] = set()


async def write_later(coro):
    """Выполнить запись, не задерживая запрос; ошибка — только в лог."""
    if WAIT:
        await coro
        return
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_done)


def _done(task: asyncio.Task):
    _background.discard(task)
    if not task.cancelled() and task.exception():
        logging.getLogger(__name__).info(f"фоновая запись: {task.exception()!r}")
