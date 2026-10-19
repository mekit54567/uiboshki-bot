"""Посещения лекций из баллов СДО (attendance.py): баллы за посещаемость
делятся поровну на лекции семестра, ушка выбывает из деления; какие лекции
засчитаны — по приросту в истории; до начала истории человек отмечает сам,
но не больше, чем видно по баллам."""
from datetime import date, timedelta

import pytest

import attendance

LECTURES = [date(2026, 9, 7) + timedelta(weeks=i) for i in range(8)]     # по понедельникам


def test_solve_plain_and_excused():
    # пример владельца: 5 из 20, 8 лекций, прошло 2 — по 2,5, был на обеих
    assert attendance.solve(5, 20, 8, 2) == [(2, 0)]
    # одна ушка: 20 делятся на 7 — по 2,857; три лекции = 8,57 (СДО округляет)
    assert attendance.solve(8.57, 20, 8, 4)[0] == (3, 1)
    assert attendance.solve(3.1, 20, 8, 4) == []                            # так не делится
    assert attendance.solve(0, 20, 8, 3)[0] == (0, 0)


def statuses(res):
    return {x["date"]: x["status"] for x in res["lectures"]}


def test_history_attributes_lectures():
    hist = [("2026-09-15", 2.5),     # прошло 2 (7 и 14 сен), засчитана 1 — какая, не видно
            ("2026-09-23", 5.0),     # после лекции 21 сен +2,5 — она
            ("2026-10-02", 5.0),     # 28 сен — ничего
            ("2026-10-06", 7.5)]     # 5 окт — засчитана
    res = attendance.build(7.5, 20, LECTURES, hist, date(2026, 10, 10))
    st = statuses(res)
    assert res["ok"] and res["attended"] == 3 and res["excused"] == 0 and res["unit"] == 2.5
    assert st["2026-09-07"] == st["2026-09-14"] == "before"
    assert st["2026-09-21"] == "ok" and st["2026-09-28"] == "miss" and st["2026-10-05"] == "ok"
    assert st["2026-10-12"] == "future" and res["left"] == 3
    assert res["before"]["attended"] == 1 and res["before"]["left_ok"] == 1
    assert res["can_get"] == 7.5

    # своя отметка: был 14 сен → 7 сен становится «Н», плюсиков больше не осталось
    res = attendance.build(7.5, 20, LECTURES, hist, date(2026, 10, 10), {"2026-09-14": "ok"})
    st = statuses(res)
    assert st["2026-09-14"] == "ok" and st["2026-09-07"] == "miss" and res["before"]["left_ok"] == 0
    assert [x["manual"] for x in res["lectures"][:2]] == [False, True]


def test_recent_lecture_waits_and_late_mark_goes_back():
    # отметку за 5 окт ещё не поставили — «ждём», а не «Н»
    res = attendance.build(10.0, 20, LECTURES, [("2026-09-30", 10.0)], date(2026, 10, 7))
    assert statuses(res)["2026-10-05"] == "wait" and res["waiting"] == 1
    # всё засчитано на первом же замере — без «отметь сам»
    assert "before" not in res and set(statuses(res).values()) >= {"ok"}
    # прирост, а новых лекций после прошлого замера нет — значит, отметили
    # лекцию ещё до начала истории (с опозданием): самую свежую из них
    hist = [("2026-09-22", 2.5), ("2026-09-27", 5.0)]
    st = statuses(attendance.build(5.0, 20, LECTURES, hist, date(2026, 9, 27)))
    assert st["2026-09-21"] == "ok" and st["2026-09-07"] == st["2026-09-14"] == "before"


def test_excused_shrinks_division():
    # 4 лекции прошло, ушка за одну: дальше каждая лекция — по 20/7
    hist = [("2026-09-29", 5.0), ("2026-10-01", 5.71)]
    res = attendance.build(5.71, 20, LECTURES, hist, date(2026, 10, 1))
    assert res["ok"] and (res["attended"], res["excused"]) == (2, 1) and res["unit"] == round(20 / 7, 3)
    assert "excused" in statuses(res).values()


def test_not_even_division():
    res = attendance.build(3.1, 20, LECTURES, [], date(2026, 10, 1))
    assert not res["ok"] and "свой подсчёт" in res["why"]
    assert not attendance.build(5, 20, [], [], date(2026, 10, 1))["ok"]


def test_check_mark_limits():
    blank = attendance.build(2.5, 20, LECTURES, [("2026-09-15", 2.5)], date(2026, 9, 16))
    assert attendance.check_mark(blank, {}, "2026-09-07", "ok") == ""
    assert "только 1" in attendance.check_mark(blank, {"2026-09-14": "ok"}, "2026-09-07", "ok")
    assert attendance.check_mark(blank, {"2026-09-14": "ok"}, "2026-09-14", None) == ""      # снять — можно
    assert "сам" in attendance.check_mark(blank, {}, "2026-09-21", "ok")                     # не до истории
    assert "уважительных" in attendance.check_mark(blank, {}, "2026-09-07", "excused")


def test_lecture_dates_only_lectures():
    ics = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Moscow:20260907T090000
DTEND;TZID=Europe/Moscow:20260907T103000
RRULE:FREQ=WEEKLY;COUNT=3
SUMMARY:\xd0\x9b\xd0\x9a \xd0\x90\xd0\xbd\xd0\xb0\xd0\xbb\xd0\xb8\xd0\xb7 \xd0\xb4\xd0\xb0\xd0\xbd\xd0\xbd\xd1\x8b\xd1\x85
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;TZID=Europe/Moscow:20260908T090000
DTEND;TZID=Europe/Moscow:20260908T103000
RRULE:FREQ=WEEKLY;COUNT=3
SUMMARY:\xd0\x9f\xd0\xa0 \xd0\x90\xd0\xbd\xd0\xb0\xd0\xbb\xd0\xb8\xd0\xb7 \xd0\xb4\xd0\xb0\xd0\xbd\xd0\xbd\xd1\x8b\xd1\x85
END:VEVENT
END:VCALENDAR
"""
    days = attendance.lecture_dates(ics, "Анализ данных", date(2026, 9, 20))
    assert days == [date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21)]            # практики не в счёт


@pytest.mark.asyncio
async def test_history_records_attendance(db):
    import sdo_history
    await sdo_history.record(5, [{"id": 7, "score": 30, "categories": [
        {"name": "Текущий контроль", "score": 25, "max": 45}, {"name": "Посещаемость", "score": 5, "max": 20}]}])
    pts = await db.get_attendance_points(5, 7, "2000-01-01")
    assert len(pts) == 1 and pts[0][1] == 5


@pytest.mark.asyncio
async def test_webapp_attendance_and_marks(db, monkeypatch):
    from fastapi.testclient import TestClient
    import schedule_parser
    import sdo_accounts
    import sdo_grades
    import webapp.server as server
    from schedule_events import TZ
    from datetime import datetime
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    today = datetime.now(TZ).date()
    lect = [today - timedelta(days=d) for d in (30, 23, 16, 9, 2)] + [today + timedelta(days=5 + 7 * i) for i in range(3)]

    async def detail(uid, cookie, cid, stale_ok=False):
        return {"id": cid, "name": "Анализ данных (Экз) [I.26-27]", "title": "Анализ данных", "score": 40,
                "categories": [{"name": "Посещаемость", "score": 5.0, "max": 20.0, "tk": False}], "works": []}

    async def subjects(**kw):
        return ["Анализ данных", "Архитектура предприятия"]

    async def raw(*a, **kw):
        return b""

    monkeypatch.setattr(sdo_grades, "course_detail", detail)
    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(attendance, "lecture_dates", lambda r, s, t=None: lect if s == "Анализ данных" else [])
    await db.save_sdo_session(222, sdo_accounts.encrypt("abcdef0123456789abcdef0123"))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}

    a = c.get("/api/sdo/grades/18672", headers=h).json()["attendance"]
    assert a["ok"] and a["attended"] == 2 and a["total"] == 8 and a["past"] == 5
    assert a["before"]["left_ok"] == 2                                     # 5 прошло, по баллам — 2
    d = [x["date"] for x in a["lectures"]]
    r = c.post("/api/sdo/attendance/18672", headers=h, json={"day": d[0], "mark": "ok"})
    assert r.status_code == 200 and r.json()["before"]["left_ok"] == 1
    c.post("/api/sdo/attendance/18672", headers=h, json={"day": d[1], "mark": "ok"})
    r = c.post("/api/sdo/attendance/18672", headers=h, json={"day": d[2], "mark": "ok"})
    assert r.status_code == 400 and "только 2" in r.json()["detail"]        # больше, чем по баллам, — нельзя
    st = [x["status"] for x in c.get("/api/sdo/grades/18672", headers=h).json()["attendance"]["lectures"]]
    assert st[:5] == ["ok", "ok", "miss", "miss", "miss"] and st[5:] == ["future"] * 3
    assert c.post("/api/sdo/attendance/18672", headers=h, json={"day": "2020-01-01", "mark": "ok"}).status_code == 400
