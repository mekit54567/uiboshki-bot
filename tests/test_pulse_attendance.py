"""Посещения лекций из Пульса: разбор ответов, синк с памятью, Пульс поверх СДО."""
from datetime import date, datetime, timedelta

import httpx

import attendance
import pulse_accounts
import pulse_attendance as pa
import pulse_probe
from pulse_attendance import _field as F

NOW = datetime(2026, 11, 1, 10, 0, tzinfo=pa.MSK)
OK = b"\x80" + len(b"grpc-status:0\r\n").to_bytes(4, "big") + b"grpc-status:0\r\n"


def _lesson(lid, y, m, d, kind):
    return F(1, F(2, F(1, y) + F(2, m) + F(3, d)) + F(4, F(1, lid) + F(2, F(1, "t") + F(2, kind)) + F(3, F(1, 1))))


def _daily(*lessons):
    return b"".join(lessons)


def _in_lesson(lid, word, subject, kind, start):
    me = F(1, F(1, F(1, F(1, "h") + F(2, "Имя"))) + F(2, F(1, f"x|1|{word}")))
    les = F(1, lid) + F(3, F(1, "s") + F(2, subject)) + F(4, F(1, "t") + F(2, kind)) + F(5, F(1, int(start.timestamp())))
    return me + F(4, les)


def test_parse_daily_and_status():
    msg = pulse_probe.decode(_daily(_lesson("a1", 2026, 10, 12, "ЛК"), _lesson("a2", 2026, 10, 12, "ПР")))
    assert pa.parse_daily([msg]) == [{"id": "a1", "day": "2026-10-12", "kind": "ЛК"},
                                     {"id": "a2", "day": "2026-10-12", "kind": "ПР"}]
    assert pa.parse_status("u|1|Present") == "ok" and pa.parse_status("u|1|Absent") == "miss"
    assert pa.parse_status("u|1|Excused") == "excused" and pa.parse_status("u|1|Wat") is None
    start = datetime(2026, 10, 12, 9, 0, tzinfo=pa.MSK)
    info = pa.parse_in_lesson([pulse_probe.decode(_in_lesson("a1", "Present", "Анализ данных", "ЛК", start))])
    assert info == {"status": "ok", "raw": "Present", "subject": "Анализ данных", "kind": "ЛК", "day": "2026-10-12"}


def _pulse(lectures: dict, calls: list):
    """Пульс: пары и свои отметки; calls — какие пары спрашивали."""
    def handler(request):
        assert request.headers["cookie"] == "sid=abc"
        body = request.content[5:]
        if request.url.path.endswith("GetDailyLessonsCountForSemesterOfAvailableVisitingLogs"):
            msg = _daily(*(_lesson(lid, d.year, d.month, d.day, k) for lid, (d, k, _w) in lectures.items()))
        else:
            lid = pulse_probe.decode(body)[0][1]
            calls.append(lid)
            d, k, w = lectures[lid]
            msg = _in_lesson(lid, w, "Анализ данных", k, datetime.combine(d, datetime.min.time(), pa.MSK) + timedelta(hours=9))
        return httpx.Response(200, content=pulse_probe.frame(msg) + OK)
    return httpx.MockTransport(handler)


async def test_sync_only_lectures_and_remembers(db, monkeypatch):
    monkeypatch.setattr(pa, "PAUSE", 0)
    lect = {"old": (date(2026, 9, 14), "ЛК", "Present"), "new": (date(2026, 10, 26), "ЛК", "Absent"),
            "pr": (date(2026, 10, 26), "ПР", "Present"), "next": (date(2026, 11, 9), "ЛК", "Absent")}
    calls = []
    r = await pa.sync(1, cookie="sid=abc", now=NOW, transport=_pulse(lect, calls))
    assert r == {"state": "ok", "asked": 2, "saved": 2} and sorted(calls) == ["new", "old"]
    rows = {x["lesson_id"]: x["status"] for x in await pa.stored(1)}
    assert rows == {"old": "ok", "new": "miss"}
    calls.clear()                              # старая лекция окончательна — не переспрашиваем
    await pa.sync(1, cookie="sid=abc", now=NOW, transport=_pulse(lect, calls))
    assert calls == ["new"]


async def test_sync_expired(db, monkeypatch):
    t = httpx.MockTransport(lambda r: httpx.Response(401))
    assert (await pa.sync(1, cookie="sid=abc", now=NOW, transport=t))["state"] == "expired"


def _sdo_result():
    today = date(2026, 10, 30)
    lectures = [date(2026, 9, 7), date(2026, 9, 14), date(2026, 10, 19), date(2026, 11, 9)]
    # до начала истории — 1 лекция из 2 засчитана, какие — не видно («?»)
    return attendance.build(5.0, 20.0, lectures, [("2026-10-10", 5.0)], today), today


def test_with_pulse_overrides_and_locks():
    res, today = _sdo_result()
    assert res["before"] and any(x["status"] == "before" for x in res["lectures"])
    assert attendance.with_pulse(res, {}, "off", today)["source"] == "sdo"
    live = attendance.with_pulse(res, {"2026-09-07": "miss", "2026-09-14": "ok"}, "ok", today)
    st = {x["date"]: x["status"] for x in live["lectures"]}
    assert live["source"] == "pulse" and "before" not in live
    assert st["2026-09-07"] == "miss" and st["2026-09-14"] == "ok" and st["2026-11-09"] == "future"
    assert live["attended"] == 1
    # Пульс отвалился: сказанное им остаётся, остальное — по СДО
    lost = attendance.with_pulse(res, {"2026-09-07": "miss"}, "expired", today)
    st = {x["date"]: x["status"] for x in lost["lectures"]}
    assert lost["source"] == "pulse_lost" and st["2026-09-07"] == "miss" and st["2026-09-14"] == "before"


def test_lecture_marks_match_subject():
    rows = [{"kind": "ЛК", "status": "ok", "subject": "Анализ данных", "day": "2026-10-12"},
            {"kind": "ПР", "status": "ok", "subject": "Анализ данных", "day": "2026-10-13"},
            {"kind": "ЛК", "status": "miss", "subject": "Физика", "day": "2026-10-14"}]
    assert pa.lecture_marks(rows, "Анализ данных", lambda n: n) == {"2026-10-12": "ok"}


async def test_keepalive_syncs(db, monkeypatch):
    called = []

    async def fake_check(cookie):
        return "ok"

    async def fake_sync(uid, now=None):
        called.append(uid)
    monkeypatch.setattr(pulse_accounts, "check", fake_check)
    monkeypatch.setattr(pa, "sync_due", fake_sync)
    assert (await pulse_accounts.connect_from_app(5, "sid=abc"))["state"] == "ok"
    await pulse_accounts.keepalive_due(datetime.now(pa.MSK) + timedelta(hours=2))
    assert 5 in called
