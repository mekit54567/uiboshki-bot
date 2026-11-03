"""Календарь из нескольких потоков разом (инлайн рисует четыре картинки в
потоках): обход повторов dateutil не потокобезопасен — без замка зацикливался
навсегда (CI 03.11 висел на test_inline_sends_photos_when_server_known)."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from kapibara.features.schedule import events


def _ical(n: int = 30) -> bytes:
    rows = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//t//t//RU"]
    for i in range(n):
        day = 1 + i % 5
        hour = 9 + (i % 4) * 2
        rows += ["BEGIN:VEVENT", f"UID:e{i}@t", f"SUMMARY:ЛК Предмет {i}",
                 f"DTSTART;TZID=Europe/Moscow:202609{day:02d}T{hour:02d}0000",
                 f"DTEND;TZID=Europe/Moscow:202609{day:02d}T{hour + 1:02d}3000",
                 "RRULE:FREQ=WEEKLY;INTERVAL=1;UNTIL=20261231T000000Z", "END:VEVENT"]
    rows.append("END:VCALENDAR")
    return "\r\n".join(rows).encode()


def test_lessons_from_many_threads_same_as_one():
    raw = _ical()
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(40)]
    for _ in range(5):
        events._parsed_cal = None          # каждый раз — свежий объект с пустым кэшем повторов
        pool = ThreadPoolExecutor(8)
        try:                               # зависание — ошибка по тайм-ауту, а не вечный CI
            futs = [pool.submit(events.lessons_for_date, raw, d) for d in days * 2]
            got = [f.result(timeout=30) for f in futs]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        events._parsed_cal = None
        want = [events.lessons_for_date(raw, d) for d in days * 2]
        assert got == want
    assert any(got)
