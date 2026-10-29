"""Обзор недели в воскресенье: пары по дням, другой корпус, свободные дни,
дедлайны недели; пустую неделю не шлём; тумблер в уведомлениях."""
from datetime import date, datetime, timedelta

import pytest

import weekly_digest
from utils import TZ

MON = date(2026, 10, 5)


def _lessons(by_day):
    def fake(raw, d, now=None):
        out = []
        for start, room in by_day.get((d - MON).days, []):
            out.append({"start": start, "pairs": 1, "room": room, "kind": "лекция", "title": "X"})
        return out
    return fake


@pytest.fixture
def week(monkeypatch):
    import schedule_parser

    def set_days(by_day):
        monkeypatch.setattr(schedule_parser, "lessons_for_date", _lessons(by_day))
        monkeypatch.setattr(schedule_parser, "week_number", lambda raw, d: 6)
    return set_days


def test_build(week):
    week({0: [("09:00", "А-1 (В-78)"), ("10:40", "А-2 (В-78)")], 3: [("12:40", "И-201 (МП-1)")]})
    dls = [{"subject": "Курсовая", "due_date": "2026-10-08", "due_time": "18:00"},
           {"subject": "Старое", "due_date": "2026-10-20"}, {"subject": "Сделано", "due_date": "2026-10-06", "done": 1}]
    text = weekly_digest.build(b"", MON, dls, "В-78")
    assert text.startswith("🗓 <b>Следующая неделя: 3 пары</b>\nНеделя 6 · 5–11 октября")
    assert "<b>Пн</b> — 2 пары, с 09:00" in text and "<b>Чт</b> — 1 пара, с 12:40 · 📍 МП-1" in text
    assert "Курсовая — Чт 18:00" in text and "Старое" not in text and "Сделано" not in text
    assert text.index("Сдать на неделе") < text.index("<b>Пн</b>")        # сначала — что делать


def test_headline_for_push(week):
    """Пуш (Никита 25.10): «Следующая неделя: 16 пар» и «Сдать 2 работы» — без
    номера недели, свободных дней, корпусов и названий работ."""
    week({0: [("09:00", "А-1 (В-78)")] * 5, 1: [("09:00", "А-1 (В-78)")] * 2, 2: [("09:00", "А-1 (В-78)")] * 3,
          3: [("09:00", "А-1 (В-78)")] * 3, 4: [("12:40", "И-201 (МП-1)")] * 3})
    dls = [{"subject": "Практика 2 · Анализ данных (Экз)", "due_date": "2026-10-05", "due_time": "23:59"},
           {"subject": "Лаба 3", "due_date": "2026-10-08"}]
    assert weekly_digest.headline(b"", MON, dls, "В-78", [("ООП", 2.5)]) == ("Следующая неделя: 16 пар",
                                                                           "Сдать 2 работы")
    assert weekly_digest.headline(b"", MON, dls[1:], "В-78")[1] == "Сдать 1 работу"
    assert weekly_digest.headline(b"", MON, [], "В-78")[1] == "Сроков на неделе нет"


def test_empty_week_not_sent(week):
    week({})
    assert weekly_digest.build(b"", MON, [], "В-78") is None


def test_next_monday():
    assert weekly_digest.next_monday(date(2026, 10, 4)) == MON          # воскресенье → завтра
    assert weekly_digest.next_monday(MON) == MON + timedelta(days=7)


@pytest.mark.asyncio
async def test_send_respects_toggle(db, week, monkeypatch):
    import schedule_parser
    week({0: [("09:00", "А-1 (В-78)")]})

    async def raw():
        return b""

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    for uid in (1, 2):
        await db.upsert_user(uid, "", "X")
    await db.set_notify(2, {"weekly": False})
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append(uid)

    await weekly_digest.send_all(Bot(), datetime(2026, 10, 4, 19, 0, tzinfo=TZ))
    assert sent == [1]


def test_toggle_in_app():
    src = open("webapp/static/js/more.js", encoding="utf-8").read()
    assert "toggleNotify('weekly')" in src


def test_build_with_week_grades(week):
    """Прирост баллов за неделю — строкой в конце, не больше четырёх предметов."""
    week({0: [("09:00", "А-1 (В-78)")]})
    grades = [("Анализ данных", 5.0), ("Архитектура <ИТ>", 2.5), ("A", 1), ("B", 1), ("C", 1)]
    text = weekly_digest.build(b"", MON, [], "В-78", grades)
    assert "📈 <b>Баллы за неделю</b>: Анализ данных +5 · Архитектура &lt;ИТ&gt; +2,5 · A +1 · B +1" in text
    assert "C +1" not in text
    assert "Баллы за неделю" not in weekly_digest.build(b"", MON, [], "В-78", [])


@pytest.mark.asyncio
async def test_week_grades_from_history(db, monkeypatch):
    """Только у кого свой вход; только рост; по убыванию; СДО упал — пусто."""
    import sdo_accounts
    import sdo_grades
    import utils
    monkeypatch.setattr(utils, "today_msk", lambda: date(2026, 10, 4))
    import sdo_history
    monkeypatch.setattr(sdo_history, "today_msk", lambda: date(2026, 10, 4))
    assert await weekly_digest.week_grades(222) == []                       # входа нет
    await db.save_sdo_session(222, sdo_accounts.encrypt("abcdef0123456789abcdef0123"))
    await db.save_score_points(222, "2026-09-26", {1: 30.0, 2: 40.0, 3: 50.0})

    async def overview(uid, cookie, fresh=False):
        return {"courses": [{"id": 1, "title": "Анализ данных", "score": 35.0},
                            {"id": 2, "title": "Архитектура", "score": 48.0},
                            {"id": 3, "title": "ООП", "score": 50.0}]}

    monkeypatch.setattr(sdo_grades, "overview", overview)
    assert await weekly_digest.week_grades(222) == [("Архитектура", 8.0), ("Анализ данных", 5.0)]

    async def down(uid, cookie, fresh=False):
        raise RuntimeError("СДО лежит")

    monkeypatch.setattr(sdo_grades, "overview", down)
    assert await weekly_digest.week_grades(222) == []



@pytest.mark.asyncio
async def test_send_grades_only_for_real_week_and_without_optional(db, week, monkeypatch):
    """Баллы в обзор — только если обзор уйдёт (пустая неделя — без запросов в
    СДО) и без предметов по выбору, куда человек не ходит."""
    import config
    import schedule_parser
    calls = []

    async def raw():
        return b""

    async def grades(uid):
        calls.append(uid)
        return [("Военная кафедра", 3.0), ("Анализ данных", 5.0)]

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(weekly_digest, "week_grades", grades)
    monkeypatch.setattr(config, "OPTIONAL_SUBJECTS", ["Военная кафедра"])
    await db.upsert_user(1, "", "X")
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append(text)

    week({})                                                           # пустая неделя — ни сообщения, ни СДО
    await weekly_digest.send_all(Bot(), datetime(2026, 10, 4, 19, 0, tzinfo=TZ))
    assert sent == [] and calls == []
    week({0: [("09:00", "А-1 (В-78)")]})
    await weekly_digest.send_all(Bot(), datetime(2026, 10, 4, 19, 0, tzinfo=TZ))
    assert calls == [1] and "Анализ данных +5" in sent[0] and "Военная кафедра" not in sent[0]
