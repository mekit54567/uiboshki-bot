"""Фильтр пар на время запроса: какие предметы скрыть этому человеку.

Что скрывать — решают предметы по выбору (groups/optional_subjects:
hidden_for, apply_for), а читает фильтр разбор календаря (schedule/events).
Сам ContextVar живёт здесь, у расписания, чтобы расписание не импортировало
группы, а группы — расписание по кругу (03.11)."""
import functools
from contextlib import contextmanager
from contextvars import ContextVar

HIDE: ContextVar[frozenset] = ContextVar("hide_subjects", default=frozenset())


@contextmanager
def no_filter():
    token = HIDE.set(frozenset())
    try:
        yield
    finally:
        HIDE.reset(token)


def unfiltered(fn):
    """Для расписания чужой группы/преподавателя/аудитории (поиск): без
    фильтра текущего человека."""

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with no_filter():
            return fn(*a, **kw)
    return wrapper
