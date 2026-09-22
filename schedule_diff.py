"""
Диффы расписания.

Идея: показывать расписание умеет любое приложение. А вот заметить, что
пару перенесли в другую аудиторию, сдвинули по времени или вовсе отменили,
и тут же пушнуть об этом всем подписчикам — то, чего не делает ни
стандартное приложение расписания, ни сама МИРЭА. Для группы это часто
единственная причина открыть бота, а не гуглить, куда идти.

Механика: на каждой проверке берём расписание на сегодня/завтра (самое
чувствительное к последним изменениям), сравниваем с последним сохранённым
снепшотом (database.get_schedule_snapshot/save_schedule_snapshot),
находим добавленные/изменённые/отменённые пары по совпадению названия
предмета, и если есть реальные изменения — рассылаем короткое уведомление
именно о том, что поменялось, а не всё расписание целиком.
"""

import logging
from datetime import date, timedelta

from database import get_schedule_snapshot, save_schedule_snapshot, get_all_subscribed_users
from schedule_parser import fetch_schedule_raw, parse_events_for_date

logger = logging.getLogger(__name__)


def _event_key(e: dict) -> str:
    return e["summary"].strip().lower()


def diff_events(old: list[dict], new: list[dict]) -> list[str]:
    """Сравнивает два списка событий одного дня, возвращает человекочитаемые
    строки об изменениях (пусто, если ничего значимого не поменялось)."""
    changes = []
    old_by_key = {_event_key(e): e for e in old}
    new_by_key = {_event_key(e): e for e in new}

    for key, ne in new_by_key.items():
        if key not in old_by_key:
            changes.append(
                f"➕ Добавлена пара: <b>{ne['summary']}</b> в {ne['time']} "
                f"({ne['location'] or '—'})"
            )
            continue
        oe = old_by_key[key]
        if oe.get("location") != ne.get("location") or oe.get("time") != ne.get("time"):
            parts = []
            if oe.get("time") != ne.get("time"):
                parts.append(f"время {oe.get('time') or '—'} → {ne.get('time') or '—'}")
            if oe.get("location") != ne.get("location"):
                parts.append(f"аудитория {oe.get('location') or '—'} → {ne.get('location') or '—'}")
            changes.append(f"🔄 <b>{ne['summary']}</b>: {', '.join(parts)}")

    for key, oe in old_by_key.items():
        if key not in new_by_key:
            changes.append(f"❌ Отменена пара: <b>{oe['summary']}</b> (была в {oe.get('time') or '—'})")

    return changes


def _to_serializable(events: list[dict]) -> list[dict]:
    # events из parse_events_for_date содержат datetime в time_start —
    # не сериализуется в JSON напрямую, оставляем только то, что нужно для диффа.
    return [
        {"summary": e["summary"], "time": e["time"], "location": e["location"]}
        for e in events
    ]


async def check_schedule_changes(bot):
    try:
        raw = await fetch_schedule_raw()
    except Exception as e:
        logger.error(f"check_schedule_changes: не удалось получить расписание: {e}")
        return

    today = date.today()
    all_changes_by_day = {}

    for offset in (0, 1):  # сегодня и завтра — самое чувствительное к изменениям
        d = today + timedelta(days=offset)
        d_str = d.isoformat()

        new_events = _to_serializable(parse_events_for_date(raw, d))
        old_events = await get_schedule_snapshot(d_str)
        await save_schedule_snapshot(d_str, new_events)

        if old_events is None:
            continue  # первый раз видим этот день — не с чем сравнивать

        changes = diff_events(old_events, new_events)
        if changes:
            all_changes_by_day[(d, offset)] = changes

    if not all_changes_by_day:
        return

    users = await get_all_subscribed_users()
    for (d, offset), changes in all_changes_by_day.items():
        weekday_label = "сегодня" if offset == 0 else "завтра"
        text = (
            f"📢 <b>Изменения в расписании на {weekday_label} ({d.strftime('%d.%m')}):</b>\n\n"
            + "\n".join(changes)
        )
        for uid in users:
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Не смог отправить diff расписания {uid}: {e}")
