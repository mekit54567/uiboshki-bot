"""
Предметы по выбору (config.OPTIONAL_SUBJECTS, сейчас «Военная кафедра»):
на них ходят не все, и остальным эти пары в расписании только мешают.

Пары такого предмета скрыты, пока человек не ответил «хожу». Спрашиваем сами
(карточка на главной WebApp, кнопки после /start в боте), чтобы тем, кто
ходит, не пришлось искать настройку.

Фильтр — через ContextVar HIDE: schedule_parser.parse_events_for_date
выкидывает пары из HIDE, а HIDE выставляют на время запроса конкретного
человека (middleware бота, зависимость WebApp, рассылки по пользователям).
Расписание чужой группы/преподавателя (поиск) — без фильтра.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from config import OPTIONAL_SUBJECTS

HIDE: ContextVar[frozenset] = ContextVar("hide_subjects", default=frozenset())


async def hidden_for(user_id: int) -> frozenset:
    """Что скрыть этому человеку: предметы по выбору без ответа «хожу».
    База недоступна — скрываем все (так у большинства и должно быть)."""
    from database import get_optional_answers
    try:
        answers = await get_optional_answers(user_id)
    except Exception as e:
        logging.getLogger(__name__).warning(f"предметы по выбору: ответы {user_id} не прочитались: {e!r}")
        answers = {}
    return frozenset(s for s in OPTIONAL_SUBJECTS if not answers.get(s))


async def pending_for(user_id: int) -> list[str]:
    """Предметы по выбору, которые есть в расписании группы и на которые
    человек ещё не ответил."""
    from database import get_optional_answers
    from schedule_parser import get_group_subjects
    from sdo_parser import SEMESTER_WINDOW
    answers = await get_optional_answers(user_id)
    subjects = set(await get_group_subjects(**SEMESTER_WINDOW))
    return [s for s in OPTIONAL_SUBJECTS if s not in answers and s in subjects]


async def apply_for(user_id: int):
    """Выставить фильтр на остаток текущего запроса/задачи."""
    HIDE.set(await hidden_for(user_id))


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
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with no_filter():
            return fn(*a, **kw)
    return wrapper
