"""Изменения расписания в приложении (дизайн 5.79, Никита 12.10): проверка
расписания копит отметки дня — старый кабинет (зачёркнут, рамка) и
отменённые пары (серые, «пары не будет»)."""
import json
from datetime import date

import pytest

from kapibara.features.schedule.diff import annotate, merge_marks


def ev(summary, time, location):
    return {"summary": summary, "time": time, "location": location}


A = ev("ЛК Анализ данных", "09:00–10:30", "А-332 (МП-1)")
B = ev("ПР Архитектура предприятия", "10:40–12:10", "Г-226 (МП-1)")


def test_room_change_keeps_first_room_and_revert_clears():
    m = merge_marks([], [A, B], [A, ev(B["summary"], B["time"], "Г-310 (МП-1)")], "09:12")
    assert m == [{"summary": B["summary"], "time": B["time"], "room_was": "Г-226 (МП-1)", "at": "09:12"}]
    # перенесли ещё раз — зачёркнут всё равно самый первый кабинет
    m = merge_marks(m, [A, ev(B["summary"], B["time"], "Г-310 (МП-1)")],
                    [A, ev(B["summary"], B["time"], "А-17 (В-78)")], "10:00")
    assert [x["room_was"] for x in m] == ["Г-226 (МП-1)"]
    # вернули прежний — отметки нет
    m = merge_marks(m, [A, ev(B["summary"], B["time"], "А-17 (В-78)")], [A, B], "10:30")
    assert m == []


def test_cancel_and_return():
    m = merge_marks([], [A, B], [A], "08:00")
    assert m[0]["cancelled"] and m[0]["summary"] == B["summary"]
    assert merge_marks(m, [A], [A, B], "08:30") == []


def test_annotate_marks_lessons_and_lists_cancelled():
    lessons = [
        {"start": "09:00", "end": "12:10", "title": "Анализ данных", "kind": "лекция", "room": "А-17"},  # сдвоенная
    ]
    marks = [
        {"summary": "ЛК Анализ данных", "time": "10:40–12:10", "room_was": "А-332", "at": "09:12"},
        {"summary": "ПР Архитектура предприятия", "time": "12:40–14:10", "location": "Г-226",
         "cancelled": True, "at": "08:00"},
        {"summary": "ПР Военная кафедра", "time": "14:20–15:50", "location": "",
         "cancelled": True, "at": "08:00"},
    ]
    cancelled = annotate(lessons, marks, frozenset({"Военная кафедра"}))
    assert lessons[0]["room_was"] == "А-332" and lessons[0]["room_changed_at"] == "09:12"
    assert cancelled == [{"start": "12:40", "end": "14:10", "title": "Архитектура предприятия",
                          "kind": "практика", "room": "Г-226", "cancelled_at": "08:00"}]


@pytest.mark.asyncio
async def test_day_changes_only_home_group(db):
    from database import set_setting
    from kapibara.features.schedule.diff import MARKS_PREFIX, day_changes
    d = date(2026, 9, 26)
    await set_setting(MARKS_PREFIX + d.isoformat(), json.dumps([
        {"summary": "ЛК Анализ данных", "time": "09:00–10:30", "location": "А-1", "cancelled": True, "at": "08:00"},
    ], ensure_ascii=False))
    assert [c["title"] for c in await day_changes(1, d, [])] == ["Анализ данных"]


@pytest.mark.asyncio
async def test_check_records_marks(db, monkeypatch):
    """Проверка расписания записывает отметки: снимок был — пару убрали."""
    from kapibara.features.schedule import diff as schedule_diff
    from database import save_schedule_snapshot
    from kapibara.features.schedule.diff import MARKS_PREFIX, marks_for
    monkeypatch.setattr(schedule_diff, "parse_events_for_date",
                        lambda raw, d: [{"summary": A["summary"], "time": A["time"], "location": A["location"],
                                         "time_start": None}])

    async def raw():
        return b""
    monkeypatch.setattr(schedule_diff, "fetch_schedule_raw", raw)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    await save_schedule_snapshot(today, [A, B])

    class Bot:
        async def send_message(self, *a, **k):
            pass
    await schedule_diff.check_schedule_changes(Bot())
    marks = await marks_for(today)
    assert [m["summary"] for m in marks if m.get("cancelled")] == [B["summary"]]
    assert MARKS_PREFIX
