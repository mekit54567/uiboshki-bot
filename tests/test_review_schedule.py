"""Ревью расписания: склейка только соседних пар, номер /next по звонку,
напоминания по блокам, диффы с учётом предметов по выбору и пустого дня,
длинные заметки и /delnote, кэш погоды, fetch_ical, справочник, срок /card."""
import asyncio
import time
from datetime import date, datetime
from types import SimpleNamespace

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fastapi.testclient import TestClient

from schedule_format import TZ
from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

DAY = date(2026, 10, 1)          # четверг


def _ev(day, s, e, summ, loc="", uid=None):
    d = day.strftime("%Y%m%d")
    return (f"BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Moscow:{d}T{s}\r\nDTEND;TZID=Europe/Moscow:{d}T{e}\r\n"
            f"SUMMARY:{summ}\r\nLOCATION:{loc}\r\nUID:{uid or summ + s + loc}\r\nEND:VEVENT\r\n")


def _cal(*events) -> bytes:
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode()


def _fake_now(now):
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    return FakeDatetime


# ── 1. склейка только соседних пар ─────────────────────────────────────────

def test_same_pairs_with_window_are_not_merged():
    from schedule_parser import format_day, lessons_for_date, parse_events_for_date, week_overview
    raw = _cal(_ev(DAY, "090000", "103000", "ПР Матан", "А-1"), _ev(DAY, "142000", "155000", "ПР Матан", "А-1"))
    lessons = lessons_for_date(raw, DAY, now=datetime(2026, 10, 1, 12, 0, tzinfo=TZ))
    assert [(l["num"], l["start"], l["end"], l["status"], l["pairs"]) for l in lessons] == [
        (1, "09:00", "10:30", "past", 1), (4, "14:20", "15:50", "later", 1)]
    assert week_overview(raw, DAY, days=1)["days"][0]["dots"] == ["практика", "практика"]
    text = format_day(parse_events_for_date(raw, DAY), DAY)
    assert "подряд" not in text and "1️⃣ <b>09:00–10:30</b>" in text and "4️⃣ <b>14:20–15:50</b>" in text

    # соседние (в том числе через большую перемену после 2-й пары) — по-прежнему блоком
    raw = _cal(*(_ev(DAY, s, e, "ПР Военная кафедра") for s, e in (
        ("090000", "103000"), ("104000", "121000"), ("124000", "141000"), ("142000", "155000"))))
    lessons = lessons_for_date(raw, DAY)
    assert [(l["num"], l["start"], l["end"], l["pairs"]) for l in lessons] == [("1–4", "09:00", "15:50", 4)]
    # и каждая пара блока отдельно: виджет «530′ до конца пары» (14.10) — до
    # конца текущей пары, а не всей военки
    parts = lessons[0]["parts"]
    assert [(a[11:16], b[11:16]) for a, b in parts] == [
        ("09:00", "10:30"), ("10:40", "12:10"), ("12:40", "14:10"), ("14:20", "15:50")]
    assert "parts" not in lessons_for_date(_cal(_ev(DAY, "090000", "103000", "ЛК Физика")), DAY)[0]


# ── 6. /next — номер пары по звонку ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_next_lesson_number_by_bell(monkeypatch):
    import schedule_parser
    from datetime import timedelta
    raw = _cal(_ev(DAY, "124000", "141000", "ЛК Физика", "А-1"),
               _ev(DAY + timedelta(days=1), "142000", "155000", "ПР Матан", "А-2"))

    async def fake_raw():
        return raw

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(schedule_parser, "datetime", _fake_now(datetime(2026, 10, 1, 8, 0, tzinfo=TZ)))
    text = await schedule_parser.get_next_lesson()
    assert "3️⃣" in text and "1️⃣" not in text
    monkeypatch.setattr(schedule_parser, "datetime", _fake_now(datetime(2026, 10, 1, 20, 0, tzinfo=TZ)))
    text = await schedule_parser.get_next_lesson()
    assert "Завтра первая пара" in text and "4️⃣" in text and "1️⃣" not in text


# ── 5. напоминания: блок — одно напоминание, подгруппы — все аудитории ──────

def test_reminders_once_per_block_and_parallel_rooms():
    import notify_prefs
    from schedule_parser import parse_events_for_date
    raw = _cal(*(_ev(DAY, s, e, "ПР Военная кафедра", "ВК-1") for s, e in (
        ("090000", "103000"), ("104000", "121000"), ("124000", "141000"), ("142000", "155000"))))
    plan = notify_prefs.plan_reminders(parse_events_for_date(raw, DAY), notify_prefs.merge({}))
    assert [(e["time_start"].strftime("%H:%M"), m, k) for e, m, k in plan] == [("09:00", 60, "remind_first")]

    raw = _cal(_ev(DAY, "090000", "103000", "ЛАБ Физика", "А-1"), _ev(DAY, "090000", "103000", "ЛАБ Физика", "Б-2"),
               _ev(DAY, "104000", "121000", "ЛК Матан", "В-3"))
    plan = notify_prefs.plan_reminders(parse_events_for_date(raw, DAY), notify_prefs.merge({}))
    assert [(e["location"], k) for e, _, k in plan] == [("А-1 / Б-2", "remind_first"), ("В-3", "remind_short")]


# ── 3, 7. диффы: предметы по выбору, «уведомления о парах», пустой день ────

class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


@pytest.mark.asyncio
async def test_schedule_diff_per_person_and_empty_day(db, monkeypatch):
    import schedule_diff
    raw = [b""]

    async def fake_raw():
        return raw[0]

    monkeypatch.setattr(schedule_diff, "fetch_schedule_raw", fake_raw)
    monkeypatch.setattr(schedule_diff, "datetime", _fake_now(datetime(2026, 10, 1, 7, 0, tzinfo=TZ)))
    monkeypatch.setattr(schedule_diff, "GROUP_CHAT_ID", -100)
    monkeypatch.setattr(schedule_diff, "_empty_once", set())
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "")
    await db.set_optional_answer(2, "Военная кафедра", True)   # 2 ходит на военку, 1 — нет
    await db.set_notify(3, {"lessons": False})                  # 3 выключил уведомления о парах

    async def run(*events):
        raw[0] = _cal(*events)
        bot = _Bot()
        await schedule_diff.check_schedule_changes(bot)
        return {c for c, _ in bot.sent}

    mat = lambda loc="А-1": _ev(DAY, "090000", "103000", "ЛК Матан", loc)
    voen = lambda loc="ВК-1": _ev(DAY, "104000", "121000", "ПР Военная кафедра", loc)
    assert await run(mat(), voen()) == set()                    # первый снимок
    assert await run(mat(), voen("ВК-2")) == {2}                # военка — только тем, кто ходит
    assert await run(mat("А-5"), voen("ВК-2")) == {1, 2, -100}  # общий предмет — всем (кроме 3)

    # день вдруг пуст (обрывок/сбой) — с первого раза не верим
    assert await run(_ev(DAY, "000000", "000100", "5 неделя")) == set()
    assert len(await db.get_schedule_snapshot(DAY.isoformat())) == 2
    assert await run(_ev(DAY, "000000", "000100", "5 неделя")) == {1, 2, -100}   # подтвердилось


# ── 4. длинные заметки и /delnote ───────────────────────────────────────────

class _Session(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls.append((name, getattr(method, "text", None), getattr(method, "reply_markup", None)))
        if name in ("SendMessage", "EditMessageText"):
            chat_id = getattr(method, "chat_id", None) or 1
            return Message(message_id=len(self.calls), date=0, chat=Chat(id=chat_id, type="private"),
                           text=method.text).as_(bot)
        return True

    async def stream_content(self, *a, **kw):
        yield b""


@pytest.fixture
def feed():
    from handlers.schedule import router
    bot = Bot(token=BOT_TOKEN, session=_Session())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    async def send(user_id, text=None, data=None):
        user = User(id=user_id, is_bot=False, first_name="U")
        msg = Message(message_id=1, date=0, chat=Chat(id=user_id, type="private"), from_user=user, text=text or "?")
        if data:
            upd = Update(update_id=int(time.time() * 1e6) % 10**9,
                         callback_query=CallbackQuery(id="1", from_user=user, chat_instance="x", data=data, message=msg))
        else:
            upd = Update(update_id=int(time.time() * 1e6) % 10**9, message=msg)
        bot.session.calls.clear()
        await dp.feed_update(bot, upd)
        return bot.session.calls

    yield send
    router._parent_router = None


@pytest.mark.asyncio
async def test_long_note_rejected_and_old_long_note_does_not_break_today(db, feed, monkeypatch):
    import handlers.schedule as hs
    from utils import today_msk
    today = today_msk().isoformat()

    calls = await feed(5, "/note сегодня Матан: " + "а" * 600)
    assert "до 500" in calls[-1][1] and await db.get_lesson_notes(today) == []
    await feed(5, "/note сегодня Матан: контрольная")
    assert len(await db.get_lesson_notes(today)) == 1

    # старая простыня в базе (до ограничения) — /today не падает
    await db.add_lesson_note(today, "", "б" * 5000, 5)
    await db.add_lesson_note(today, "", "\n".join(["в" * 400] * 12), 5)

    async def schedule(*a, **k):
        return "📅 <b>Сегодня</b>\n" + "\n".join(["пара"] * 10)

    monkeypatch.setattr(hs, "get_today_schedule", schedule)
    calls = await feed(5, "/schedule")
    texts = [t for n, t, _ in calls if n in ("SendMessage", "EditMessageText") and t != "⏳ Загружаю..."]
    assert texts and all(len(t) <= 4096 for t in texts) and "б" * 600 not in "".join(texts)


@pytest.mark.asyncio
async def test_starosta_deletes_note(db, feed):
    from tests.conftest import STAROSTA_ID
    from utils import today_msk
    today = today_msk().isoformat()
    note_id = await db.add_lesson_note(today, "Матан", "ерунда", 5)

    calls = await feed(5, "/delnote")
    assert "только староста" in calls[-1][1]
    assert await feed(5, data=f"delnote:{note_id}") and len(await db.get_lesson_notes(today)) == 1

    calls = await feed(STAROSTA_ID, "/delnote")
    kb = calls[-1][2]
    assert kb.inline_keyboard[0][0].callback_data == f"delnote:{note_id}"
    await feed(STAROSTA_ID, data=f"delnote:{note_id}")
    assert await db.get_lesson_notes(today) == []


# ── 8. погода: кэш и параллельно с расписанием ──────────────────────────────

@pytest.mark.asyncio
async def test_weather_cached(monkeypatch):
    import handlers.weather as weather
    calls = []

    async def fetch():
        calls.append(1)
        return None if len(calls) == 1 else {"current": {}}

    monkeypatch.setattr(weather, "_fetch_weather", fetch)
    monkeypatch.setattr(weather, "_weather_cache", None)
    assert await weather.fetch_weather() is None and await weather.fetch_weather() is None
    assert len(calls) == 1                                  # сбой запомнен, не ждём снова
    monkeypatch.setattr(weather, "_weather_cache", (time.monotonic() - 1, None))
    assert await weather.fetch_weather() == {"current": {}}
    assert await weather.fetch_weather() == {"current": {}} and len(calls) == 2


@pytest.mark.asyncio
async def test_api_today_weather_in_parallel(db, monkeypatch):
    import handlers.weather as weather
    import schedule_parser
    import webapp.server as server

    async def slow_raw():
        await asyncio.sleep(0.4)
        return _cal(_ev(DAY, "090000", "103000", "ЛК Матан"))

    async def slow_weather():
        await asyncio.sleep(0.4)
        return "☁️ +12°"

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", slow_raw)
    monkeypatch.setattr(weather, "get_weather_for_morning", slow_weather)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    t = time.monotonic()
    data = c.get("/api/today", headers={"X-Telegram-Init-Data": _make_init_data()}).json()
    assert data["weather"] == "☁️ +12°" and time.monotonic() - t < 0.75


# ── 9. fetch_ical: короткий запасной таймаут, не календарь — None ──────────

@pytest.mark.asyncio
async def test_fetch_ical_checks_calendar_and_short_fallback(db, monkeypatch):
    import mirea_schedule_api as api
    import webapp.server as server
    timeouts = []
    real_client = httpx.AsyncClient

    def client(timeout=None, **kw):
        timeouts.append(timeout)

        async def handler(request):
            if "english" in str(request.url):
                return httpx.Response(200, content=b"<html>502 Bad Gateway</html>")
            raise httpx.ConnectTimeout("timeout")
        return real_client(transport=httpx.MockTransport(handler))

    with monkeypatch.context() as m:
        m.setattr(api.httpx, "AsyncClient", client)
        assert await api.fetch_ical(100, 2) is None
    assert timeouts == [20, 5]

    async def cut(target_id, target_type):      # календарь оборван — 502, а не 500
        return b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nDTSTART;TZID=Europe/Mos"

    import schedule_index
    await schedule_index._save([(2, 100, "Блеко В. В.")])     # без похода за baseinfo в сеть
    monkeypatch.setattr(api, "fetch_ical", cut)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    assert c.get("/api/target/2/100", headers={"X-Telegram-Init-Data": _make_init_data()}).status_code == 502


# ── 10. справочник: прогресс обновления не сбрасывается на каждом запуске ──

@pytest.mark.asyncio
async def test_index_refresh_resumes(db, monkeypatch):
    import schedule_index
    await schedule_index._set_state("built_at", str(int(time.time()) - 40 * 86400))
    await schedule_index._set_state("next_id_1", "9000")
    seen = []

    async def interrupted_build():
        seen.append(await schedule_index._get_state("next_id_1"))
        await schedule_index._set_state("next_id_1", "500")
        raise httpx.ConnectError("деплой")

    monkeypatch.setattr(schedule_index, "build_index", interrupted_build)
    await schedule_index.ensure_fresh()
    await schedule_index.ensure_fresh()
    assert seen == ["1", "500"]                 # сброс — только в начале круга

    async def finished_build():
        seen.append(await schedule_index._get_state("next_id_1"))
        await schedule_index._set_state("built_at", str(int(time.time())))
        await schedule_index._set_state("refreshing", "")

    monkeypatch.setattr(schedule_index, "build_index", finished_build)
    await schedule_index.ensure_fresh()
    assert seen[-1] == "500"
    # через месяц — новый круг снова с начала
    await schedule_index._set_state("built_at", str(int(time.time()) - 40 * 86400))
    await schedule_index.ensure_fresh()
    assert seen[-1] == "1"


@pytest.mark.asyncio
async def test_real_build_clears_refreshing_mark(db, monkeypatch):
    import schedule_index
    from tests.test_schedule_search import _mirror
    monkeypatch.setattr(schedule_index, "STOP_AFTER_MISSES", 5)
    await schedule_index._set_state("refreshing", "123")
    client, _ = _mirror()
    async with client:
        await schedule_index.build_index(client)
    assert not await schedule_index._get_state("refreshing")


# ── 11. /card — ссылка не вечная ────────────────────────────────────────────

def test_card_link_expires(monkeypatch):
    import schedule_card
    url = schedule_card.card_url("https://x.app/", "today")
    key, sig = url.split("/card/")[1].split(".jpg?sig=")
    assert schedule_card.parse_key(key, sig) == ("today", 0, 0)
    old = f"today-0-0-{int(time.time()) // 600 - schedule_card.CARD_MAX_AGE - 1}"
    assert schedule_card.parse_key(old, schedule_card.sign(old)) is None
    later = time.time() + 40 * 86400
    monkeypatch.setattr(schedule_card, "time", SimpleNamespace(time=lambda: later))
    assert schedule_card.parse_key(key, sig) is None


@pytest.mark.asyncio
async def test_fetch_ical_cached_single_flight(monkeypatch):
    """Чужое расписание: десять человек открыли одну группу — одна загрузка с
    зеркала; через 10 минут — заново; сбой не запоминается."""
    import asyncio
    import mirea_schedule_api as api
    calls = []

    async def slow(target_id, target_type):
        calls.append((target_type, target_id))
        await asyncio.sleep(0.01)
        return None if target_id == 13 else b"BEGIN:VCALENDAR\r\nEND:VCALENDAR"

    clock = [100.0]
    monkeypatch.setattr(api, "_fetch_ical", slow)
    monkeypatch.setattr(api.time, "monotonic", lambda: clock[0])
    res = await asyncio.gather(*(api.fetch_ical(4928, 1) for _ in range(10)))
    assert all(r.startswith(b"BEGIN:VCALENDAR") for r in res) and calls == [(1, 4928)]
    clock[0] += api.ICAL_TTL + 1
    await api.fetch_ical(4928, 1)
    assert len(calls) == 2
    assert await api.fetch_ical(13, 1) is None and await api.fetch_ical(13, 1) is None
    assert calls.count((1, 13)) == 2
    assert (1, 13) not in api._ical_locks and (1, 4928) in api._ical_locks     # замки сбоев не копятся


@pytest.mark.asyncio
async def test_weather_down_keeps_last_good(monkeypatch, caplog):
    # Open-Meteo отвечал 503 (17.10, 9 «ошибок» в /status): показываем
    # последнюю удачную погоду до 3 часов, в лог — предупреждение, не ошибка
    import logging
    from types import SimpleNamespace

    import httpx

    import handlers.weather as weather
    real_fetch = weather._fetch_weather
    clock = [1000.0]
    monkeypatch.setattr(weather, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    answers = [{"current": {"temperature_2m": 9.9}}, None, None]

    async def fetch():
        return answers.pop(0)

    monkeypatch.setattr(weather, "_fetch_weather", fetch)
    monkeypatch.setattr(weather, "_weather_cache", None)
    monkeypatch.setattr(weather, "_last_good", None)
    good = await weather.fetch_weather()
    clock[0] += weather.WEATHER_TTL + 1
    assert await weather.fetch_weather() == good           # сбой — прежняя
    clock[0] += weather.WEATHER_STALE
    assert await weather.fetch_weather() is None           # старше 3 часов — уже нет

    class Down:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def get(self, url):
            raise httpx.HTTPStatusError("503", request=httpx.Request("GET", url),
                                        response=httpx.Response(503))

    monkeypatch.setattr(weather.net, "client", lambda **kw: Down())
    with caplog.at_level(logging.WARNING, logger=weather.__name__):
        assert await real_fetch() is None
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
