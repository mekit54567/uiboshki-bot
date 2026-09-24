"""
Личный ICS-календарь (Фаза 12): токен-ссылки, привязка ДЗ к конкретной паре
по дате, и сборка самого .ics-фида (icalendar VEVENT per occurrence, не
RRULE — см. webapp/calendar_feed.py, почему).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar as ICalCalendar, Event as ICalEvent

import handlers.announce as announce
from handlers.announce import parse_lesson_date
from webapp.calendar_feed import _matches_subject, build_ics_for_user

TZ = ZoneInfo("Europe/Moscow")


# ── parse_lesson_date (чистая функция) ────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_ok,expected_date", [
    ("-", True, None),
    ("–", True, None),
    ("30.05", True, None),  # год подставляется текущий — сверяем отдельно ниже
    ("30.05.2026", True, "2026-05-30"),
    ("31.02.2026", False, None),  # несуществующая дата
    ("abc", False, None),
    ("", False, None),
    ("30/05/2026", False, None),
])
def test_parse_lesson_date(raw, expected_ok, expected_date):
    ok, value = parse_lesson_date(raw)
    assert ok == expected_ok
    if expected_date is not None:
        assert value == expected_date
    elif not expected_ok:
        assert value is None


def test_parse_lesson_date_default_year_is_current():
    ok, value = parse_lesson_date("30.05")
    assert ok is True
    assert value == f"{datetime.now(TZ).year}-05-30"


# ── _matches_subject (чистая функция) ────────────────────────────────────────

@pytest.mark.parametrize("item_subject,lesson_summary,expected", [
    (None, "Математический анализ (ЛК)", True),
    ("", "Физкультура", True),
    ("анализ", "Математический анализ (ЛК)", True),  # подстрока — реалистичный ввод
    ("математический анализ", "Математический анализ (ЛК)", True),
    ("Матан", "Математический анализ (ЛК)", False),  # НЕ подстрока ("матан" != "математи…") — известное ограничение, см. docstring
    ("Физика", "Математический анализ (ЛК)", False),
])
def test_matches_subject(item_subject, lesson_summary, expected):
    assert _matches_subject(item_subject, lesson_summary) == expected


# ── database.calendar_token ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_token_is_created_once_and_stable(db):
    token1 = await db.get_or_create_calendar_token(777)
    token2 = await db.get_or_create_calendar_token(777)
    assert token1 == token2
    assert len(token1) > 20  # secrets.token_urlsafe(24) — не короткий предсказуемый id


@pytest.mark.asyncio
async def test_calendar_token_is_unique_per_user(db):
    token_a = await db.get_or_create_calendar_token(1)
    token_b = await db.get_or_create_calendar_token(2)
    assert token_a != token_b


@pytest.mark.asyncio
async def test_calendar_token_works_before_any_upsert_user(db):
    # get_or_create_calendar_token может быть вызвана для юзера, который ещё
    # ни разу не делал /start (upsert_user) — не должно тихо "теряться".
    token = await db.get_or_create_calendar_token(999)
    owner = await db.get_user_by_calendar_token(token)
    assert owner is not None
    assert owner["user_id"] == 999


@pytest.mark.asyncio
async def test_unknown_token_resolves_to_none(db):
    assert await db.get_user_by_calendar_token("does-not-exist") is None
    assert await db.get_user_by_calendar_token("") is None


# ── ДЗ, привязанное к конкретной дате/паре ───────────────────────────────────

@pytest.mark.asyncio
async def test_add_hw_with_and_without_lesson_date(db, monkeypatch):
    monkeypatch.setattr(announce, "DATABASE_PATH", db.DATABASE_PATH)
    await announce.init_hw_table()

    await announce.add_hw("Матан", "Решить №5-10", None, None, 111, lesson_date="2026-05-30")
    await announce.add_hw("Физика", "Прочитать главу 2", None, None, 111)  # без даты — как раньше

    dated = await announce.get_hw_for_date("2026-05-30")
    assert len(dated) == 1
    assert dated[0]["subject"] == "Матан"
    assert dated[0]["content"] == "Решить №5-10"

    assert await announce.get_hw_for_date("2026-06-01") == []


# ── Сборка ICS-фида ──────────────────────────────────────────────────────────

def _fake_ical_bytes(event_date, subject="Математический анализ (ЛК)"):
    cal = ICalCalendar()
    cal.add("prodid", "-//test//")
    cal.add("version", "2.0")
    start = datetime.combine(event_date, datetime.min.time()).replace(hour=9, tzinfo=TZ)
    end = start + timedelta(hours=1, minutes=30)
    ev = ICalEvent()
    ev.add("uid", "test-1@example.com")
    ev.add("summary", subject)
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("location", "ауд. 123")
    ev.add("description", "Преподаватель: Иванов Иван Иванович\\nещё текст")
    cal.add_component(ev)
    return cal.to_ical()


@pytest.mark.asyncio
async def test_build_ics_includes_matched_homework_and_notes(db, monkeypatch):
    import webapp.calendar_feed as calendar_feed

    monkeypatch.setattr(announce, "DATABASE_PATH", db.DATABASE_PATH)
    await announce.init_hw_table()

    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    await announce.add_hw("Математический анализ", "Решить №5-10", None, None, 111, lesson_date=date_str)
    await db.add_lesson_note(date_str, "Математический анализ", "Принести калькулятор", 111)

    raw = _fake_ical_bytes(tomorrow)
    monkeypatch.setattr(calendar_feed, "fetch_schedule_raw", lambda force=False: _AwaitableBytes(raw))

    body = await calendar_feed.build_ics_for_user("some-token")
    # RFC 5545 фолдит длинные строки на 75 октетах ("\r\n " перед
    # продолжением) — разворачиваем перед проверками содержимого, иначе слово
    # может оказаться буквально разорвано переводом строки посередине.
    text = body.decode("utf-8").replace("\r\n ", "")

    assert "Математический анализ" in text
    assert "Решить №5-10" in text
    assert "Принести калькулятор" in text
    assert "Иванов Иван Иванович" in text
    assert "ауд. 123" in text


@pytest.mark.asyncio
async def test_build_ics_skips_unrelated_homework(db, monkeypatch):
    import webapp.calendar_feed as calendar_feed

    monkeypatch.setattr(announce, "DATABASE_PATH", db.DATABASE_PATH)
    await announce.init_hw_table()

    tomorrow = (datetime.now(TZ) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    await announce.add_hw("Физика", "Не должно попасть в это событие", None, None, 111, lesson_date=date_str)

    raw = _fake_ical_bytes(tomorrow, subject="Математический анализ (ЛК)")
    monkeypatch.setattr(calendar_feed, "fetch_schedule_raw", lambda force=False: _AwaitableBytes(raw))

    body = await calendar_feed.build_ics_for_user("some-token")
    text = body.decode("utf-8")
    assert "Не должно попасть" not in text


class _AwaitableBytes:
    """Мини-заглушка для fetch_schedule_raw (async-функция) — monkeypatch
    подменяет её на синхронную lambda, а awaited-результат должен сам
    поддерживать await. __await__ делает объект awaitable без реальной
    корутины/сети."""
    def __init__(self, data: bytes):
        self._data = data

    def __await__(self):
        async def _coro():
            return self._data
        return _coro().__await__()
