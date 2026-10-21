"""
Круг правок Kapi ИИ и экрана пары (Никита 21.10, скрины с iPhone):
«МБП» — предмет по сокращению; ночью «завтра» — наступивший день; «что будет
на первой лекции» — какая она по счёту и её файл; понятные чипы источников по
порядку; ошибка без названия провайдера; тёзка-преподаватель, который ведёт
пару, — сразу он.
"""
from datetime import date, datetime

import pytest

import lecture_day
import lecture_picker as lp
from utils import TZ

SUBJECTS = [
    "Анализ данных",
    "Анализ и диагностика финансово-хозяйственной деятельности предприятия",
    "Архитектура предприятия",
    "Моделирование бизнес-процессов",
    "Объектно-ориентированный анализ и программирование",
    "Основы бизнес-анализа в ИТ-сфере",
    "Основы предпринимательской деятельности",
    "Производственная практика",
]


@pytest.mark.parametrize("text,subject", [
    ("завтра МБП ,что на лекции будет кратко", "Моделирование бизнес-процессов"),
    ("когда ООАП?", "Объектно-ориентированный анализ и программирование"),
    ("мбп что задали", "Моделирование бизнес-процессов"),
    ("что по АД", "Анализ данных"),
    ("ОПД объясни", "Основы предпринимательской деятельности"),
    ("привет, как дела", None),
    ("что было на паре пр", None),
])
def test_subject_by_abbreviation(text, subject):
    assert lp.subject_by_abbrev(text, SUBJECTS) == subject


def test_night_tomorrow_is_the_day_that_already_came():
    thu_1am = datetime(2026, 10, 22, 1, 0, tzinfo=TZ)          # четверг, час ночи
    assert lecture_day.target_day("что завтра будет на лекции?", thu_1am) == date(2026, 10, 22)
    assert lecture_day.target_day("а послезавтра?", thu_1am) == date(2026, 10, 23)
    assert lecture_day.target_day("сегодня первая лекция", thu_1am) == date(2026, 10, 22)
    thu_noon = datetime(2026, 10, 22, 12, 0, tzinfo=TZ)
    assert lecture_day.target_day("что завтра на лекции", thu_noon) == date(2026, 10, 23)
    assert lecture_day.target_day("объясни регрессию", thu_noon) is None


def test_lecture_number_by_schedule():
    dates = [date(2026, 9, 3), date(2026, 9, 17), date(2026, 10, 1), date(2026, 10, 22)]
    thu_1am = datetime(2026, 10, 22, 1, 0, tzinfo=TZ)
    assert lecture_day.lecture_on(dates, "ну да, сегодня первая лекция, что там будет", thu_1am) == (date(2026, 10, 22), 4)
    assert lecture_day.lecture_on(dates, "что завтра на лекции?", thu_1am) == (date(2026, 10, 22), 4)
    # без дня, но «что будет на лекции» — ближайшая
    sep = datetime(2026, 9, 10, 12, 0, tzinfo=TZ)
    assert lecture_day.lecture_on(dates, "что будет на лекции?", sep) == (date(2026, 9, 17), 2)
    assert lecture_day.lecture_on(dates, "что такое IDEF0?", thu_1am) is None
    assert lecture_day.lecture_on(dates, "что завтра на лекции", datetime(2026, 10, 22, 12, tzinfo=TZ)) is None


def test_numbered_blocks_pick_the_lecture_file():
    ctx = "\n\n".join([
        "=== Лекция 1 ===\nвведение",
        "=== Лекция 4 ===\nIDEF0",
        "=== Лекция 4 (презентация) ===\nслайды IDEF0",
        "=== Лекция 14 ===\nчужая",
        "=== 4 лекция. Повтор ===\nещё",
    ])
    out = lecture_day.numbered_blocks(ctx, 4)
    assert "IDEF0" in out and "слайды" in out and "ещё" in out
    assert "введение" not in out and "чужая" not in out
    assert lecture_day.numbered_blocks(ctx, 7) == ""


def test_chip_labels_are_human():
    import semantic_search as ss
    subj = "Моделирование бизнес-процессов"
    assert ss.chip_label("!План и комплект оценочных материалов", subj, "часть 18", "часть") == "План и комплект оценочных…"
    assert ss.chip_label(subj, subj, "стр. 2", "стр.") == "Материалы курса · стр. 2"
    assert ss.chip_label("Лекция 3", subj, "стр. 37", "стр.") == "Лекция 3 · стр. 37"


def test_sources_go_in_natural_order():
    from webapp.routes.chat import _natural
    titles = ["Лекция 10", "Лекция 2", "Практика 1", "Лекция 3"]
    assert sorted(titles, key=_natural) == ["Лекция 2", "Лекция 3", "Лекция 10", "Практика 1"]


_TEACHER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:mbp
DTSTART;TZID=Europe/Moscow:20260105T090000
DTEND;TZID=Europe/Moscow:20260105T103000
RRULE:FREQ=WEEKLY
SUMMARY:ЛК {subject}
END:VEVENT
END:VCALENDAR
"""


@pytest.mark.asyncio
async def test_namesake_who_teaches_the_subject_is_marked(monkeypatch):
    # «Сиганьков А. А.» ×2: с экрана пары МБП сразу тот, кто ведёт МБП
    import mirea_schedule_api as api
    icals = {1: _TEACHER_ICS.format(subject="Обеспечение безопасности").encode(),
             2: _TEACHER_ICS.format(subject="Моделирование бизнес-процессов").encode()}

    async def fake_ical(target_id, target_type):
        return icals.get(target_id)

    monkeypatch.setattr(api, "fetch_ical", fake_ical)
    res = await api.add_hints_for_namesakes([
        {"id": 1, "fullTitle": "Сиганьков А. А.", "scheduleTarget": 2},
        {"id": 2, "fullTitle": "Сиганьков А. А.", "scheduleTarget": 2},
    ], subject="Моделирование бизнес-процессов")
    assert {r["id"]: r.get("match") for r in res} == {1: False, 2: True}
    plain = await api.add_hints_for_namesakes([
        {"id": 1, "fullTitle": "Сиганьков А. А.", "scheduleTarget": 2},
        {"id": 2, "fullTitle": "Сиганьков А. А.", "scheduleTarget": 2},
    ])
    assert all("match" not in r for r in plain)


@pytest.mark.asyncio
async def test_chat_abbrev_picks_subject_and_lecture_of_day(db, monkeypatch):
    from fastapi.testclient import TestClient

    import attendance
    import webapp.server as server
    from tests.test_webapp_auth import _make_init_data

    subj = "Моделирование бизнес-процессов"
    for title, text in [("Лекция 1", "Введение в процессы."), ("Лекция 2", "Нотация IDEF0, блоки и стрелки ICOM."),
                        ("Лекция 3", "Нотация BPMN.")]:
        fid = await db.add_file(title, subj, f"f-{title}", f"{title}.pdf", 1)
        await db.save_file_text(fid, text)
    seen = {}

    async def fake_chat(history, subject="", extra_system="", lectures=""):
        seen.update(subject=subject, lectures=lectures, context=extra_system)
        return {"content": "На лекции — IDEF0 [1].", "reasoning": ""}

    async def no_context(user_id):
        return ""

    today = datetime.now(TZ).date()
    monkeypatch.setattr("ai_solver.chat_with_reasoning", fake_chat)
    monkeypatch.setattr("group_context.build_group_context", no_context)
    monkeypatch.setattr(attendance, "lecture_dates", lambda raw, s, d=None: [date(2026, 9, 1), today] if s == subj else [])
    client = TestClient(server.app)
    headers = {"X-Telegram-Init-Data": _make_init_data()}
    data = client.post("/api/chat", json={"history": [
        {"role": "user", "content": "МБП, сегодня на лекции что будет?"}]}, headers=headers).json()
    assert data["subject"] == subj and "choose" not in data
    assert seen["subject"] == subj
    assert "ICOM" in seen["lectures"] and "BPMN" not in seen["lectures"] and "Введение" not in seen["lectures"]
    assert "лекцию №2" in seen["context"]
    assert [s["title"] for s in data["sources"]] == ["Лекция 2"]
