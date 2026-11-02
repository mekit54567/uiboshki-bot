"""«Что будет на лекции завтра?» — какая это лекция по счёту и её файл.

Никита 21.10: в час ночи «завтра» помощник понял как пятницу, а на «первая
лекция сегодня, что там будет?» выдал обзор всего курса и случайные «Лекция 2,
Лекция 4». Здесь — день из слов вопроса (ночью «завтра» — это наступивший
день: человек ещё не спал), номер лекции предмета в семестре по календарю
группы и блок «Лекция N» из текстов лекций предмета.
"""

import re
from datetime import date, datetime, timedelta

# до этого часа «завтра» — день, который уже наступил (после сна)
NIGHT_UNTIL = 5

_DAY_WORDS = (
    (re.compile(r"послезавтра", re.I), 2),
    (re.compile(r"(?<![а-яё])завтра", re.I), 1),
    (re.compile(r"сегодня|(?<![а-яё])сейчас(?![а-яё])", re.I), 0),
    (re.compile(r"(?<![а-яё])вчера", re.I), -1),
)
_NEXT = re.compile(r"следующ\w* лекци|ближайш\w* лекци|на лекции будет|будет на лекции", re.I)
_ABOUT_LECTURE = re.compile(r"лекци|(?<![а-яё])лк(?![а-яё])|на пар[еау]", re.I)


def is_night(now: datetime) -> bool:
    return now.hour < NIGHT_UNTIL


def target_day(text: str, now: datetime) -> date | None:
    """День, о котором вопрос: «сегодня», «завтра», «послезавтра», «вчера».
    Ночью (до 5 утра) «завтра» — уже наступивший день."""
    today = now.date()
    for rx, shift in _DAY_WORDS:
        if rx.search(text or ""):
            if is_night(now) and shift > 0:
                shift -= 1
            return today + timedelta(days=shift)
    return None


def asks_about_lecture(text: str) -> bool:
    return bool(_ABOUT_LECTURE.search(text or ""))


def lecture_on(dates: list[date], text: str, now: datetime) -> tuple[date, int] | None:
    """(дата, номер лекции в семестре) для вопроса; dates — даты лекций
    предмета по порядку (attendance.lecture_dates). Нет слова про день, но
    «что будет на лекции» — ближайшая лекция с сегодняшнего дня."""
    if not dates or not asks_about_lecture(text):
        return None
    day = target_day(text, now)
    if day is None:
        if not _NEXT.search(text or ""):
            return None
        today = now.date()
        upcoming = [d for d in dates if d >= today]
        if not upcoming:
            return None
        day = upcoming[0]
    if day not in dates:
        return None
    return day, dates.index(day) + 1


def numbered_blocks(context: str, n: int) -> str:
    """Блоки «=== Лекция N … ===» из текстов лекций предмета
    (database.get_subject_lecture_context) — PDF и презентация одной лекции
    идут вместе. Нет такого файла — пусто."""
    rx = re.compile(rf"(?:лекци\w*|(?<![а-яё])лк)\.?\s*№?\s*0?{n}(?!\d)|(?<!\d){n}\s*-?\s*(?:я\s*)?лекци", re.I)
    blocks = []
    for i, part in enumerate(context.split("\n\n=== ")):
        block = part if i == 0 else "=== " + part
        title = block.split("\n", 1)[0].strip("= ").strip()
        if rx.search(title):
            blocks.append(block)
    return "\n\n".join(blocks)
