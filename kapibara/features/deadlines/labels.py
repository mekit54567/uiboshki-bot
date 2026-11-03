"""Подпись срока дедлайна: «🔴 сегодня в 23:59», «🟠 завтра»… Переехала из
handlers/deadlines.py (03.11): ей пользуются напоминания и планировщик, а
импорт из handlers снизу вверх сцеплял модули в клубок."""
from datetime import date

WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def due_label(due: date, today: date, due_time: str | None = None) -> str:
    """«🔴 сегодня в 23:59», «🟠 завтра», «🟡 пт, 2 октября», «💀 просрочен (29.09)»."""
    from kapibara.features.schedule.parser import MONTHS_GEN
    delta = (due - today).days
    tp = f" в {due_time}" if due_time else ""
    if delta < 0:
        return f"💀 просрочен ({due.strftime('%d.%m')})"
    if delta == 0:
        return f"🔴 сегодня{tp}"
    if delta == 1:
        return f"🟠 завтра{tp}"
    human = f"{WEEKDAY_SHORT[due.weekday()]}, {due.day} {MONTHS_GEN[due.month - 1]}{tp}"
    return f"{'🟡' if delta <= 3 else '🟢'} {human} · через {delta} дн."
