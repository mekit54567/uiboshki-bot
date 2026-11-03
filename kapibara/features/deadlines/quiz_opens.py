"""Когда открываются тесты СДО — что узнал синк (03.11, из notifications/quiz_alerts).

Синк дедлайнов (sdo/parser.apply_items) после каждого прохода записывает
сюда открытия тестов из календаря и что он видел о тестах (для peek), а
рассылки «Тест открылся» и напоминания (notifications/quiz_alerts) это
читают. Отдельно — чтобы синк не импортировал уведомления, а уведомления —
синк по кругу.
"""
import json
from datetime import datetime

from kapibara.core.utils import TZ

FMT = "%Y-%m-%d %H:%M"
PEEK_KEY = "sdo:quiz_sig"                # что о тестах видел последний полный синк (peek)


def _parse(at: str | None) -> datetime | None:
    try:
        return datetime.strptime((at or "")[:16], FMT).replace(tzinfo=TZ)
    except ValueError:
        return None


def next_open(prev: str | None, new: str | None, now: datetime) -> str:
    """Что запомнить об открытии теста после синка. prev — что знали (None —
    тест видим впервые), new — событие «открывается» из календаря (None —
    нет: открыт без ограничения или открылся до окна календаря)."""
    n = now.strftime(FMT)
    if new and new > n:
        return new                           # откроется потом — по расписанию
    if prev and prev > n:
        return n                             # ждали позже, а он уже открыт: открыли сейчас
    if prev is not None:
        return prev                          # уже открыт и мы это знаем
    return new or ""                         # впервые: открыт с new или «когда — не знаем»


async def note_opens(items: list[dict], now: datetime | None = None):
    """После синка (sdo_parser.apply_items): открытия тестов из календаря."""
    from kapibara.features.deadlines import quiz_time
    from database.sdo import get_quiz_opens, save_quiz_opens
    now = now or datetime.now(TZ)
    new = {c: i.get("opens") for i in items if i.get("calendar") and (c := quiz_time.quiz_cmid(i.get("description")))}
    if not new:
        return
    known = await get_quiz_opens(new)
    fresh = {c: next_open(known.get(c), o, now) for c, o in new.items()}
    await save_quiz_opens({c: v for c, v in fresh.items() if known.get(c) != v})


def signature(items: list[dict]) -> list[str]:
    """Тесты из календаря: «id события|когда открывается»."""
    return sorted({f"{i['external_id']}|{i.get('opens') or ''}" for i in items
                   if i.get("calendar") and "/mod/quiz/" in (i.get("description") or "")})


async def remember(items: list[dict]):
    """Полный синк своей группы: что он видел о тестах — для peek."""
    from database import set_setting
    await set_setting(PEEK_KEY, json.dumps(signature(items)))
