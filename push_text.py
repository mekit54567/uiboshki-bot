"""
Тексты пушей (Никита 25.10: «смысл от такого пуша? человеку смысла ноль»).
Пуш читают на экране блокировки: в заголовке — суть («Неделя 9: 21 пара,
свободен вт», «Через 15 мин: Анализ данных»), в тексте — одна-две строки,
что делать. Сообщение в Telegram остаётся подробным, а заголовок и текст
пуша каждая рассылка передаёт в delivery.deliver(title=, body=) сама.
Здесь — общие куски: короткое имя дедлайна, «когда», слова по числу.
"""

from datetime import date

DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def word(n: int, one: str, few: str, many: str) -> str:
    """word(3, "пара", "пары", "пар") → «пары»."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many


def split_subject(subject: str) -> tuple[str, str]:
    """«Практика 2 · Анализ данных (Экз)» → («Практика 2», «Анализ данных (Экз)»)."""
    name, _, course = (subject or "").partition(" · ")
    return name.strip() or (subject or "").strip(), course.strip()


def when(due_date: str, due_time: str | None, today: date) -> str:
    """«сегодня до 23:59», «завтра», «в чт до 18:00», «8 октября»."""
    from schedule_parser import MONTHS_GEN
    d = date.fromisoformat(due_date)
    delta = (d - today).days
    tail = f" до {due_time}" if due_time else ""
    if delta == 0:
        return "сегодня" + tail
    if delta == 1:
        return "завтра" + tail
    if 1 < delta < 7:
        return f"в {DAYS[d.weekday()]}" + tail
    return f"{d.day} {MONTHS_GEN[d.month - 1]}" + tail


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def num(x: float) -> str:
    """5.0 → «5», 2.5 → «2,5»."""
    return f"{x:g}".replace(".", ",")
