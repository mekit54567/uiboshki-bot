"""Подключение к базе. Путь читается в момент вызова (database.DATABASE_PATH),
а не копируется при импорте: тесты и /restore подменяют его в одном месте."""

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
    return aiosqlite.connect(database.DATABASE_PATH, timeout=BUSY_SECONDS, factory=_Tuned)
