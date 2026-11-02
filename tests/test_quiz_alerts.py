"""Тесты СДО в уведомлениях (quiz_alerts.py, Никита 12.10): напоминания до
закрытия (несколько сразу), «Открыли тест» — по времени открытия из
календаря, внезапное открытие и новый открытый тест после синка; каждое —
один раз, только тем, кто видит тест и не сдал."""
from datetime import datetime, timedelta

import pytest

import notify_prefs
import quiz_alerts as qa
from utils import TZ

QUIZ = "https://online-edu.mirea.ru/mod/quiz/view.php?id=501"
CLOSE = datetime(2099, 3, 10, 12, 0, tzinfo=TZ)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def test_prefs_validation():
    p = notify_prefs.merge(None)
    assert p["quiz_remind"] == [] and p["quiz_open"] is True                 # по умолчанию: «открыли» — да
    p = notify_prefs.merge({"quiz_remind": [10, 60, 10, 7, True, "30", 1440], "quiz_open": False})
    assert p["quiz_remind"] == [1440, 60, 10] and p["quiz_open"] is False   # мусор — мимо, без повторов
    assert notify_prefs.merge({"quiz_remind": "60"})["quiz_remind"] == []
    assert notify_prefs.merge({"quiz_remind": [30]})["quiz_remind"] is not notify_prefs.DEFAULTS["quiz_remind"]


def test_next_open():
    now = datetime(2099, 3, 9, 10, 0, tzinfo=TZ)
    assert qa.next_open(None, "2099-03-09 12:00", now) == "2099-03-09 12:00"    # откроется потом
    assert qa.next_open("2099-03-09 12:00", None, now) == "2099-03-09 10:00"    # открыли раньше — сейчас
    assert qa.next_open("2099-03-09 12:00", "2099-03-09 09:00", now) == "2099-03-09 10:00"
    assert qa.next_open("2099-03-08 09:00", None, now) == "2099-03-08 09:00"    # уже знали, что открыт
    assert qa.next_open(None, None, now) == ""                                  # открыт, когда — неизвестно
    assert qa.next_open(None, "2099-03-08 09:00", now) == "2099-03-08 09:00"


def test_calendar_attaches_open_time():
    import sdo_parser
    ts = lambda d: int(d.timestamp())       # noqa: E731
    ev = [{"id": 1, "name": "Тест 3 открывается", "component": "mod_quiz", "eventtype": "open",
           "timestart": ts(CLOSE - timedelta(hours=2)), "url": QUIZ},
          {"id": 2, "name": "Тест 3 закрывается", "component": "mod_quiz", "eventtype": "close",
           "timestart": ts(CLOSE), "url": QUIZ, "course": {"fullname": "Анализ данных"}},
          {"id": 3, "name": "ПР 1", "component": "mod_assign", "eventtype": "due",
           "timestart": ts(CLOSE), "url": "https://x/mod/assign/view.php?id=9"}]
    items = sdo_parser.parse_calendar_events(ev)
    assert [i["external_id"] for i in items] == ["sdo:2", "sdo:3"]          # открытие — не дедлайн
    assert items[0]["opens"] == "2099-03-10 10:00" and "opens" not in items[1]


async def _setup(db):
    """1 — напоминания за час и 10 мин; 2 — ничего; 3 — сдал; 4 — другая группа."""
    for uid in (1, 2, 3, 4):
        await db.upsert_user(uid, "", "")
    await db.set_notify(1, {"quiz_remind": [60, 10]})
    await db.set_notify(2, {"quiz_open": False})
    await db.set_notify(3, {"quiz_remind": [60, 10]})
    await db.set_notify(4, {"quiz_remind": [60, 10]})
    await db.set_user_group(4, 9999)
    did = await db.add_deadline("Тест 3 · Анализ данных", QUIZ, "2099-03-10", "12:00", 0, external_id="sdo:2")
    await db.set_deadline_done(did, 3, True)
    await db.save_quiz_limits({501: 30})
    return did


@pytest.mark.asyncio
async def test_reminders_before_close_once(db):
    await _setup(db)
    bot = FakeBot()
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=61)) == 0              # ещё рано
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=60)) == 1
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=59)) == 0              # второй раз — нет
    (uid, text), = bot.sent
    assert uid == 1 and text == "⏰ <b>Через 1 ч закрывается тест</b> · Тест 3 · Анализ данных (30 мин на попытку)"
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=10)) == 1
    assert bot.sent[-1] == (1, "⏰ <b>Через 10 мин закрывается тест</b> · Тест 3 · Анализ данных (30 мин на попытку)")
    assert await qa.send_due(bot, CLOSE) == 0                                       # закрылся — тишина


@pytest.mark.asyncio
async def test_late_reminder_window_and_day_text(db):
    """После перезапуска опоздавшее ещё приходит (с честным «через …»), сильно
    опоздавшее — нет; «за день» — «Завтра в 12:00»."""
    await _setup(db)
    await db.set_notify(1, {"quiz_remind": [1440, 30]})
    bot = FakeBot()
    await qa.send_due(bot, CLOSE - timedelta(minutes=30) + timedelta(minutes=16))   # окно 15 мин прошло
    assert bot.sent == []
    await qa.send_due(bot, CLOSE - timedelta(minutes=30) + timedelta(minutes=6))
    assert bot.sent[-1][1].startswith("⏰ <b>Через 24 мин закрывается тест</b>")
    await qa.send_due(bot, CLOSE - timedelta(days=1))
    assert bot.sent[-1][1].startswith("⏰ <b>Завтра в 12:00 закрывается тест</b>")


@pytest.mark.asyncio
async def test_open_at_scheduled_time(db):
    await _setup(db)
    opens = CLOSE - timedelta(hours=2)
    await qa.note_opens([{"calendar": True, "description": QUIZ, "opens": opens.strftime(qa.FMT)}],
                        now=opens - timedelta(days=1))
    bot = FakeBot()
    assert await qa.send_due(bot, opens - timedelta(minutes=1)) == 0
    assert await qa.send_due(bot, opens) == 1 and await qa.send_due(bot, opens + timedelta(minutes=1)) == 0
    got = dict(bot.sent)
    assert set(got) == {1}                       # 2 выключил, 3 сдал, 4 — не его группа; 1 — да
    assert got[1].startswith("🔓 <b>Открыли тест</b>\n• <b>Тест 3 · Анализ данных</b> (30 мин на попытку) — сдать")


@pytest.mark.asyncio
async def test_sudden_open_found_by_sync(db):
    """Ждали открытия завтра, а синк не видит события «открывается» — открыли
    сейчас: «Открыли тест» на ближайшей минутной проверке."""
    await _setup(db)
    now = CLOSE - timedelta(days=2)
    await qa.note_opens([{"calendar": True, "description": QUIZ, "opens": "2099-03-09 09:00"}], now=now)
    await qa.note_opens([{"calendar": True, "description": QUIZ, "opens": None}], now=now + timedelta(hours=3))
    bot = FakeBot()
    assert await qa.send_due(bot, now + timedelta(hours=3, minutes=1)) == 1
    assert bot.sent[0][0] == 1 and "Открыли тест" in bot.sent[0][1]


@pytest.mark.asyncio
async def test_new_open_quiz_announced_once(db):
    """Новый тест, уже открытый: у кого «Тест открылся» — строкой «Открыли
    тест» вместо нового задания, и минутная проверка его не повторит."""
    from database.sdo import get_quiz_opens
    import new_tasks
    await _setup(db)
    await db.upsert_user(5, "", "")
    await db.set_notify(5, {"quiz_open": False})              # только «новые задания»
    await db.upsert_user(6, "", "")
    await db.set_notify(6, {"new_tasks": False})             # только «открыли тест»
    d = await db.add_deadline("Тест 4 · Анализ данных", QUIZ.replace("501", "502"), "2099-03-11", "12:00", 0,
                              external_id="sdo:4")
    a = await db.add_deadline("Практика 5 · Анализ данных", "", "2099-03-11", "12:00", 0, external_id="sdo:5")
    now = datetime.now(TZ)
    await qa.note_opens([{"calendar": True, "description": QUIZ.replace("501", "502"), "opens": None}], now=now)
    assert (await get_quiz_opens([502])) == {502: ""}
    bot = FakeBot()
    await new_tasks.announce(bot, [d, a])
    got = dict(bot.sent)
    assert got[1].startswith("🔓 <b>Открыли тест</b>\n• <b>Тест 4") and "🆕 В СДО новое задание:\n• <b>Практика 5" in got[1]
    assert got[1].count("Тест 4") == 1
    assert "Открыли" not in got[5] and "Тест 4" in got[5] and "Практика 5" in got[5]
    assert "Открыли тест" in got[6] and "Практика 5" not in got[6]
    assert "Открыли тест" in got[3]                           # 3 сдал Тест 3, а Тест 4 — новый
    bot = FakeBot()
    await new_tasks.announce(bot, [d])                        # повтор синка — «открыли» уже ушло
    assert not any("Открыли" in t for _, t in bot.sent)
    from database.sdo import save_quiz_opens
    await save_quiz_opens({502: now.strftime(qa.FMT)})        # и минутная проверка не повторит
    bot = FakeBot()
    await qa.send_due(bot, now + timedelta(minutes=1))
    assert not any("Тест 4" in t for _, t in bot.sent)


@pytest.mark.asyncio
async def test_hidden_and_optional_not_sent(db, monkeypatch):
    import config
    did = await _setup(db)
    from database.deadlines import hide_deadline_for
    await hide_deadline_for(1, did)
    bot = FakeBot()
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=60)) == 0
    monkeypatch.setattr(config, "OPTIONAL_SUBJECTS", ["Анализ данных"])
    await db.set_notify(2, {"quiz_remind": [10]})
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=10)) == 0           # предмет по выбору без «хожу»
    await db.set_optional_answer(2, "Анализ данных", True)
    assert await qa.send_due(bot, CLOSE - timedelta(minutes=9)) == 1


@pytest.mark.asyncio
async def test_peek_triggers_sync_only_on_change(db, monkeypatch):
    import sdo_parser
    items = [{"external_id": "sdo:2", "description": QUIZ, "calendar": True, "opens": "2099-03-10 10:00"}]
    await qa.remember(items)
    state = {"events": items}

    async def months(client, sesskey, n):
        assert sesskey == "sk"
        return state["events"]

    monkeypatch.setattr(sdo_parser, "calendar_months", months)
    monkeypatch.setattr(sdo_parser, "parse_calendar_events", lambda ev: ev)
    html = '{"sesskey":"sk"}'
    assert await qa.peek(None, html) is False
    state["events"] = [dict(items[0], opens=None)]                                  # время открытия пропало
    assert await qa.peek(None, html) is True
    state["events"] = items + [{"external_id": "sdo:9", "description": QUIZ, "calendar": True}]   # новый тест
    assert await qa.peek(None, html) is True
    assert await qa.peek(None, "без сессии") is False


@pytest.mark.asyncio
async def test_keepalive_peek_runs_sync(monkeypatch):
    import health
    import quiz_alerts
    import scheduler
    import sdo_parser
    calls = []

    async def keepalive(peek=None):
        await peek("client", "html")
        return True

    async def peek(client, html):
        return True

    async def sync(bot):
        calls.append(bot)

    async def note(*a, **kw):
        pass

    monkeypatch.setattr(sdo_parser, "keepalive", keepalive)
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")
    monkeypatch.setattr("config.SDO_SESSION_COOKIE", "x")
    monkeypatch.setattr(quiz_alerts, "peek", peek)
    monkeypatch.setattr(scheduler, "sync_sdo_deadlines", sync)
    monkeypatch.setattr(health, "note", note)
    bot = FakeBot()
    await scheduler.sdo_keepalive(bot)
    assert calls == [bot]


def test_jobs_registered():
    """Минутная проверка тестов и keepalive с ботом (для внеочередного синка)."""
    import deadline_reminders
    import quiz_alerts
    import scheduler
    jobs = {(j.func.__module__, j.func.__name__): j for j in scheduler.start_scheduler(object()).get_jobs()}
    # переехали в kapibara/ (ADR 0003) — имя модуля берём у самого модуля
    reminders, quizzes = deadline_reminders.__name__, quiz_alerts.__name__
    assert str(jobs[(quizzes, "send_due")].trigger) == str(jobs[(reminders, "send_due")].trigger)
    assert jobs[(scheduler.__name__, "sdo_keepalive")].args
    assert ("database.sdo", "purge_quiz_alerts") in jobs


@pytest.mark.asyncio
async def test_api_notify_quiz(db, monkeypatch):
    from fastapi.testclient import TestClient
    import schedule_parser
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data

    async def fake_raw(*a, **kw):
        return b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", fake_raw)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    r = c.get("/api/notify", headers=h).json()
    assert r["quiz_choices"] == [1440, 180, 60, 30, 10]
    assert r["prefs"]["quiz_remind"] == [] and r["prefs"]["quiz_open"] is True
    r = c.post("/api/notify", headers=h, json={"prefs": {"quiz_remind": [10, 1440, 5], "quiz_open": False}}).json()
    assert r["prefs"]["quiz_remind"] == [1440, 10] and r["prefs"]["quiz_open"] is False
    r = c.post("/api/notify", headers=h, json={"prefs": {"weather": False}}).json()
    assert r["prefs"]["quiz_remind"] == [1440, 10]                                  # другое не стирает


@pytest.mark.asyncio
async def test_sync_records_opens_and_peek_signature(db):
    """Синк своей группы: время открытия теста — в quiz_opens, что видел о
    тестах — для peek; синк чужой группы peek не трогает."""
    import json
    import sdo_parser
    from database.sdo import get_quiz_opens
    item = {"title": "Тест 3", "course": "", "external_id": "sdo:2", "subject": "Тест 3", "description": QUIZ,
            "due_date": "2099-03-10", "due_time": "12:00", "calendar": True, "opens": "2099-03-10 10:00"}
    await sdo_parser.apply_items([dict(item)])
    assert await get_quiz_opens([501]) == {501: "2099-03-10 10:00"}
    assert json.loads(await db.get_setting(qa.PEEK_KEY)) == ["sdo:2|2099-03-10 10:00"]
    await sdo_parser.apply_items([dict(item, opens=None)], group_id=77)
    assert json.loads(await db.get_setting(qa.PEEK_KEY)) == ["sdo:2|2099-03-10 10:00"]
