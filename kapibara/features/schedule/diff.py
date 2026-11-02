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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import GROUP_CHAT_ID, TIMEZONE
from database import get_schedule_snapshot, save_schedule_snapshot
from schedule_parser import fetch_schedule_raw, parse_events_for_date
from utils import esc

logger = logging.getLogger(__name__)


def _event_key(e: dict) -> str:
    return e["summary"].strip().lower()


def _change_line(oe: dict, ne: dict) -> str:
    parts = []
    if oe.get("time") != ne.get("time"):
        parts.append(f"время {oe.get('time') or '—'} → {ne.get('time') or '—'}")
    if oe.get("location") != ne.get("location"):
        parts.append(f"аудитория {esc(oe.get('location')) or '—'} → {esc(ne.get('location')) or '—'}")
    return f"🔄 <b>{esc(ne['summary'])}</b>: {', '.join(parts)}"


def pair_events(old: list[dict], new: list[dict]) -> list[tuple[str, dict | None, dict | None]]:
    """Те же пары, что и в diff_events, структурой: ("change", старая, новая),
    ("add", None, новая), ("cancel", старая, None). Для текста уведомления и
    для отметок в приложении (кабинет изменён, пары не будет)."""
    out: list[tuple[str, dict | None, dict | None]] = []
    old_groups: dict[str, list[dict]] = {}
    new_groups: dict[str, list[dict]] = {}
    for e in old:
        old_groups.setdefault(_event_key(e), []).append(e)
    for e in new:
        new_groups.setdefault(_event_key(e), []).append(e)

    for key, news in new_groups.items():
        olds = list(old_groups.get(key, []))
        news = list(news)
        for ne in list(news):
            for oe in olds:
                if oe.get("time") == ne.get("time") and oe.get("location") == ne.get("location"):
                    olds.remove(oe)
                    news.remove(ne)
                    break
        out += [("change", oe, ne) for oe, ne in zip(olds, news)]
        out += [("add", None, ne) for ne in news[len(olds):]]
        out += [("cancel", oe, None) for oe in olds[len(news):]]
    for key, olds in old_groups.items():
        if key not in new_groups:
            out += [("cancel", oe, None) for oe in olds]
    return out


def diff_events(old: list[dict], new: list[dict]) -> list[str]:
    """Сравнивает два списка событий одного дня, возвращает человекочитаемые
    строки об изменениях (пусто, если ничего значимого не поменялось).

    Один и тот же предмет может стоять в дне несколько раз (сдвоенная пара) —
    поэтому группируем по названию СПИСКАМИ, а не словарём "название → пара"
    (он молча оставлял только последнюю пару с таким названием: отмена одной
    из двух одинаковых пар выдавалась за "перенос времени", а добавление
    второй — вообще не замечалось). Внутри группы сначала снимаем полностью
    совпавшие пары, остаток сопоставляем по порядку (изменение), лишнее —
    добавлено/отменено."""
    changes = []
    for kind, oe, ne in pair_events(old, new):
        if kind == "change":
            changes.append(_change_line(oe, ne))
        elif kind == "add":
            changes.append(
                f"➕ Добавлена пара: <b>{esc(ne['summary'])}</b> в {ne['time']} "
                f"({esc(ne['location']) or '—'})"
            )
        else:
            changes.append(f"❌ Отменена пара: <b>{esc(oe['summary'])}</b> (была в {oe.get('time') or '—'})")
    return changes


# ── Отметки для приложения (дизайн 5.79, «Изменения в расписании», Никита
# 12.10: старый кабинет зачёркнут и рамка, отменённая пара — серой и
# зачёркнутой). Что заметила проверка — копится по дню в settings
# «schedmarks:<дата>»: кабинет — самый первый (до всех переносов), отмена
# снимается, если пара вернулась. Только своя группа: чужие не проверяются.

MARKS_PREFIX = "schedmarks:"


def _same(a: dict, b: dict) -> bool:
    return _event_key(a) == _event_key(b) and a.get("time") == b.get("time")


def merge_marks(marks: list[dict], old: list[dict], new: list[dict], at: str) -> list[dict]:
    """Добавить к отметкам дня то, что поменялось между снимками old → new."""
    marks = [dict(m) for m in marks]
    for kind, oe, ne in pair_events(old, new):
        if kind == "change" and (oe.get("location") or "") != (ne.get("location") or ""):
            prev = next((m for m in marks if m.get("room_was") is not None and _same(m, oe)), None)
            first = prev["room_was"] if prev else oe.get("location") or ""
            if prev:
                marks.remove(prev)
            if first != (ne.get("location") or ""):     # вернули прежний кабинет — отметки нет
                marks.append({"summary": ne["summary"], "time": ne.get("time"), "room_was": first, "at": at})
        elif kind == "cancel":
            marks = [m for m in marks if not _same(m, oe)]
            marks.append({"summary": oe["summary"], "time": oe.get("time"), "location": oe.get("location") or "",
                          "cancelled": True, "at": at})
        elif kind == "add":
            marks = [m for m in marks if not (m.get("cancelled") and _same(m, ne))]
    return marks


async def record_marks(d_str: str, old: list[dict], new: list[dict]):
    import json
    from database import get_setting, set_setting
    raw = await get_setting(MARKS_PREFIX + d_str)
    marks = json.loads(raw) if raw else []
    at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M")
    fresh = merge_marks(marks, old, new, at)
    if fresh != marks:
        await set_setting(MARKS_PREFIX + d_str, json.dumps(fresh, ensure_ascii=False))


async def marks_for(d_str: str) -> list[dict]:
    import json
    from database import get_setting
    try:
        raw = await get_setting(MARKS_PREFIX + d_str)
        return json.loads(raw) if raw else []
    except Exception:
        return []


def annotate(lessons: list[dict], marks: list[dict], hide: frozenset = frozenset()) -> list[dict]:
    """Отметки — в пары дня (lessons_for_date): у пары с другим кабинетом
    room_was и room_changed_at; возвращает отменённые пары (их в lessons нет)
    в том же виде, что пары, без предметов по выбору, на которые не ходит."""
    from schedule_format import _split_kind
    if not marks:
        return []

    def start(m):
        return (m.get("time") or "").split("–")[0]

    for l in lessons:
        for m in marks:
            if m.get("room_was") is None:
                continue
            title = _split_kind(m["summary"])[0]
            # у сдвоенной пары в lessons одна строка: подходит любая её пара
            if title == l["title"] and l["start"] <= start(m) < (l["end"] or "99:99"):
                l["room_was"], l["room_changed_at"] = m["room_was"], m.get("at") or ""
                break
    cancelled = []
    for m in marks:
        if not m.get("cancelled"):
            continue
        title, kind, _ = _split_kind(m["summary"])
        if title in hide or any(l["title"] == title and l["start"] == start(m) for l in lessons):
            continue
        end = (m.get("time") or "").partition("–")[2]
        cancelled.append({"start": start(m), "end": end, "title": title, "kind": kind,
                          "room": m.get("location") or "", "cancelled_at": m.get("at") or ""})
    return sorted(cancelled, key=lambda c: c["start"])


async def day_changes(user_id: int, d, lessons: list[dict]) -> list[dict]:
    """Для /api/today и /api/day: отметить пары дня d и вернуть отменённые.
    Только своя группа (её расписание проверяет check_schedule_changes)."""
    import groups
    from database import get_user_group
    from optional_subjects import HIDE
    gid = await get_user_group(user_id)
    if gid and gid != groups.home_id():
        return []
    return annotate(lessons, await marks_for(d.isoformat()), HIDE.get())


def _to_serializable(events: list[dict]) -> list[dict]:
    # events из parse_events_for_date содержат datetime в time_start —
    # не сериализуется в JSON напрямую, оставляем только то, что нужно для диффа.
    return [
        {"summary": e["summary"], "time": e["time"], "location": e["location"]}
        for e in events
    ]


# Дни, где новое расписание вдруг пустое, а в старом были пары. С первого
# раза не верим (обрывок календаря, сбой зеркала): ждём повторной проверки,
# иначе всем летели ложные «❌ Отменена пара» по всему дню.
_empty_once: set[str] = set()


def _visible(events: list[dict], hide: frozenset) -> list[dict]:
    """Без предметов по выбору, на которые человек не ходит."""
    from schedule_format import _split_kind
    return [e for e in events if _split_kind(e["summary"])[0] not in hide] if hide else events


async def check_schedule_changes(bot):
    import notify_prefs
    from config import OPTIONAL_SUBJECTS
    from database import get_all_optional_answers, get_reminder_users
    from optional_subjects import no_filter
    try:
        raw = await fetch_schedule_raw()
    except Exception as e:
        logger.error(f"check_schedule_changes: не удалось получить расписание: {e}")
        return

    # Дата по Москве, как и в schedule_parser (get_today_schedule и др.), а не
    # по локальному времени сервера: на UTC-хостинге с 00:00 до 03:00 МСК
    # date.today() — ещё вчерашний день, и "сегодня/завтра" в уведомлении
    # в общий чат относились бы не к тем дням.
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    changed_days = []   # (день, сдвиг, старые пары, новые пары)

    for offset in (0, 1):  # сегодня и завтра — самое чувствительное к изменениям
        d = today + timedelta(days=offset)
        d_str = d.isoformat()

        # снимок — всё расписание группы, без фильтра текущего контекста:
        # что скрыть, решается ниже по каждому человеку
        with no_filter():
            new_events = _to_serializable(parse_events_for_date(raw, d))
        old_events = await get_schedule_snapshot(d_str)

        if old_events and not new_events and d_str not in _empty_once:
            _empty_once.add(d_str)
            logger.warning(f"check_schedule_changes: {d_str} вдруг без пар — проверю ещё раз")
            continue
        _empty_once.discard(d_str)
        await save_schedule_snapshot(d_str, new_events)

        if old_events is None:
            continue  # первый раз видим этот день — не с чем сравнивать
        try:
            await record_marks(d_str, old_events, new_events)
        except Exception as e:
            logger.warning(f"check_schedule_changes: отметки для приложения не записались: {e}")
        if diff_events(old_events, new_events):
            changed_days.append((d, offset, old_events, new_events))

    if not changed_days:
        return

    # Каждому — только про то, что он видит: без предметов по выбору, на
    # которые не ходит, и если уведомления о парах в этот день включены.
    answers = await get_all_optional_answers()
    users = await get_reminder_users()
    for d, offset, old_events, new_events in changed_days:
        weekday_label = "сегодня" if offset == 0 else "завтра"
        head = f"📢 <b>Изменения в расписании на {weekday_label} ({d.strftime('%d.%m')}):</b>\n\n"
        texts: dict[frozenset, str] = {}

        def text_for(hide: frozenset) -> str:
            if hide not in texts:
                changes = diff_events(_visible(old_events, hide), _visible(new_events, hide))
                texts[hide] = head + "\n".join(changes) if changes else ""
            return texts[hide]

        for user in users:
            uid = user["user_id"]
            if not notify_prefs.allowed(notify_prefs.merge(user.get("notify")), "lessons", d.weekday()):
                continue
            mine = answers.get(uid, {})
            text = text_for(frozenset(s for s in OPTIONAL_SUBJECTS if not mine.get(s)))
            if not text:
                continue
            try:
                from delivery import deliver
                await deliver(bot, uid, text, kind="lessons", tab="today",
                              title=f"Изменилось расписание на {weekday_label}",
                              body="\n".join(text.split("\n")[2:]))
            except Exception as e:
                logger.warning(f"Не смог отправить diff расписания {uid}: {e}")

        # Смена/отмена пары — это то, что реально должно долетать до общего
        # чата, не только до лично подписавшихся: как правило, шлём это
        # надёжнее, чем личка (не у всех она включена). В общем чате — без
        # предметов по выбору, как и утренний дайджест.
        text = text_for(frozenset(OPTIONAL_SUBJECTS))
        if GROUP_CHAT_ID and text:
            try:
                await bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Не смог отправить diff расписания в группу: {e}")
