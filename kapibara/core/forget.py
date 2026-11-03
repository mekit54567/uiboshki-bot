"""Забыть человека в памяти процесса: кэши, которые держат его данные
(баллы СДО и т. п.), при удалении данных (152-ФЗ, privacy.erase).

Модуль с таким кэшем сам записывает сюда свою очистку при импорте
(forget.register). Так privacy не импортирует каждый такой модуль — раньше
privacy звал sdo/grades, и через него сцеплялся в клубок с оплатой и ИИ
(03.11). Модуль ни разу не импортирован — значит, и кэш его пуст.
"""
from __future__ import annotations

from collections.abc import Callable

_hooks: list[Callable[[int], None]] = []


def register(fn: Callable[[int], None]) -> Callable[[int], None]:
    """Добавить очистку (можно декоратором). Одна и та же — один раз."""
    if fn not in _hooks:
        _hooks.append(fn)
    return fn


def user(user_id: int) -> None:
    """Забыть человека во всех записанных кэшах."""
    for fn in _hooks:
        fn(user_id)
