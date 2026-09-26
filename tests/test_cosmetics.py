"""
Оформление по итогам живого теста в Telegram (26.09.2026): расписание без
съезжающих рамок ┌│└, подряд идущие одинаковые пары одним блоком, текущая
пара отмечена, неделя компактно, /help без команд старосты для остальных,
утренняя рассылка без «⚠️ Не удалось получить погоду», подсказка решалки —
один раз за диалог.
"""
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, Chat, User, Update

from schedule_parser import format_day, format_lesson
from tests.conftest import STAROSTA_ID
from tests.test_solver_render import RecordingSession

TZ = ZoneInfo("Europe/Moscow")


def _ev(start, end, summary, location="А-18", teacher=""):
    hs, ms = map(int, start.split(":"))
    he, me = map(int, end.split(":"))
    return {
        "summary": summary, "time": f"{start}–{end}", "location": location, "teacher": teacher,
        "time_start": datetime(2026, 9, 26, hs, ms, tzinfo=TZ),
        "time_end": datetime(2026, 9, 26, he, me, tzinfo=TZ),
    }


DAY = [
    _ev("09:00", "10:30", "ЛК Основы бизнес-анализа", "А-18", "Иванов Иван Иванович"),
    _ev("10:40", "12:10", "ПР Предпринимательство", "А-215"),
    _ev("12:40", "14:10", "ДОП Военная кафедра", "ВУЦ"),
    _ev("14:20", "15:50", "ДОП Военная кафедра", "ВУЦ"),
]


def test_day_has_no_box_drawing_and_readable_kind_and_teacher():
    text = format_day(DAY, date(2026, 9, 26))
    assert "┌" not in text and "│" not in text and "└" not in text
    assert text.startswith("📅 <b>Суббота, 26 сентября</b>\n4 пары · 09:00–15:50")
    assert "1️⃣ <b>09:00–10:30</b>  📍 А-18\nОсновы бизнес-анализа\n<i>лекция · Иванов И. И.</i>" in text


def test_consecutive_identical_pairs_are_merged():
    text = format_day(DAY, date(2026, 9, 26))
    assert text.count("Военная кафедра") == 1
    assert "3️⃣–4️⃣ <b>12:40–15:50</b>" in text
    assert "2 пары подряд" in text


def test_pairs_with_different_groups_are_not_merged():
    a = {**_ev("12:40", "14:10", "ЛАБ Физика", "В-328"), "groups": "КСБО-11-26"}
    b = {**_ev("14:20", "15:50", "ЛАБ Физика", "В-328"), "groups": "ЭКБО-01-26"}
    text = format_day([a, b], date(2026, 9, 26), compact=True, extra="groups")
    assert "КСБО-11-26" in text and "ЭКБО-01-26" in text
    assert "3️⃣ 12:40–14:10" in text and "4️⃣ 14:20–15:50" in text


def test_today_marks_current_and_past_pairs():
    text = format_day(DAY, date(2026, 9, 26), now=datetime(2026, 9, 26, 11, 0, tzinfo=TZ))
    assert "1️⃣ <s>09:00–10:30</s>" in text
    assert "2️⃣ <b>10:40–12:10</b>  📍 А-215 · 🟢 <b>сейчас</b>" in text
    assert "3️⃣–4️⃣ <b>12:40–15:50</b>" in text


def test_week_day_is_compact():
    text = format_day(DAY, date(2026, 9, 26), compact=True)
    assert text.splitlines() == [
        "<b>Суббота, 26 сентября</b>",
        "1️⃣ 09:00–10:30 · Основы бизнес-анализа (лк) · А-18",
        "2️⃣ 10:40–12:10 · Предпринимательство (пр) · А-215",
        "3️⃣–4️⃣ 12:40–15:50 · Военная кафедра (доп) · ВУЦ",
    ]
    assert format_day([], date(2026, 9, 27), compact=True) == "<b>Воскресенье, 27 сентября</b> — пар нет 🎉"


def test_lesson_escapes_html():
    text = format_lesson(_ev("09:00", "10:30", "ЛК R&D <тест>", "A<1>"))
    assert "R&amp;D &lt;тест&gt;" in text and "A&lt;1&gt;" in text


@pytest.mark.asyncio
async def test_morning_weather_line_is_empty_on_failure(monkeypatch):
    import handlers.weather as weather

    async def no_weather():
        return None

    monkeypatch.setattr(weather, "fetch_weather", no_weather)
    assert await weather.get_weather_for_morning() == ""

    async def some_weather():
        return {"current": {"temperature_2m": 12.2, "apparent_temperature": 9.6, "weathercode": 3,
                            "windspeed_10m": 7, "precipitation": 0}}

    monkeypatch.setattr(weather, "fetch_weather", some_weather)
    assert await weather.get_weather_for_morning() == "☁️ +12°, пасмурно, ощущается +10° · 👕 лёгкая куртка"


# ── /help и подсказка решалки через настоящий Dispatcher ────────────────────

USER = User(id=222, is_bot=False, first_name="Alice")
STAROSTA = User(id=STAROSTA_ID, is_bot=False, first_name="Starosta")


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())


def _dp(router):
    d = Dispatcher(storage=MemoryStorage())
    d.include_router(router)
    return d


async def _feed(dp, bot, text, user=USER):
    msg = Message(message_id=int(time.time() * 1000) % 1000000, date=0,
                  chat=Chat(id=user.id, type="private"), from_user=user, text=text)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9, message=msg))


@pytest.mark.asyncio
async def test_help_hides_starosta_commands_from_students(db, bot):
    from handlers.start import router
    dp = _dp(router)
    try:
        await _feed(dp, bot, "/help", USER)
        student = bot.session.sent[-1][0]
        await _feed(dp, bot, "/help", STAROSTA)
        starosta = bot.session.sent[-1][0]
    finally:
        router._parent_router = None
    assert "/announce" not in student and "Для старосты" not in student
    assert "/announce" in starosta and "Для старосты" in starosta


@pytest.mark.asyncio
async def test_solver_hint_only_after_first_answer(db, bot, monkeypatch):
    import handlers.solver as solver

    async def fake_solve_text(task, subject="", backend="gemini", **kw):
        return "**Ответ:** 4"

    async def fake_history(history, subject="", backend="gemini", **kw):
        return "**Ответ:** 5"

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)
    monkeypatch.setattr(solver, "solve_with_history", fake_history)
    dp = _dp(solver.router)
    try:
        await _feed(dp, bot, "/solve")
        await _feed(dp, bot, "Математика")
        await _feed(dp, bot, "2 + 2 = ?")
        await _feed(dp, bot, "а 2 + 3?")
    finally:
        solver.router._parent_router = None
    texts = [t for t, _ in bot.session.sent]
    assert sum("уточняющий вопрос" in t for t in texts) == 1
    assert any("<b>Ответ:</b> 5" in t for t in texts)


@pytest.mark.parametrize("n,word", [(1, "задача"), (3, "задачи"), (5, "задач"), (11, "задач"), (21, "задача"), (22, "задачи"), (112, "задач")])
def test_plural(n, word):
    from utils import plural
    assert plural(n, "задача", "задачи", "задач") == word


@pytest.mark.asyncio
async def test_settings_buttons_toggle_and_reminder(db, bot):
    from aiogram.types import CallbackQuery
    from handlers.start import router
    dp = _dp(router)
    await db.upsert_user(USER.id, "", "Alice")

    async def click(data):
        msg = Message(message_id=77, date=0, chat=Chat(id=USER.id, type="private"), text="⚙️")
        cb = CallbackQuery(id="1", from_user=USER, chat_instance="c", data=data, message=msg)
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, callback_query=cb))

    try:
        await _feed(dp, bot, "/settings")
        assert "Напоминать о паре за <b>15 мин</b>" in bot.session.sent[-1][0]
        await click("set:rem:30")
        await click("set:sub")
        await click("set:rem:999")  # чужое значение — игнор
    finally:
        router._parent_router = None
    user = await db.get_user(USER.id)
    assert user["reminder_minutes"] == 30 and not user["subscribed"]
    edits = [t for _, t in bot.session.sent_texts if "Настройки" in t]
    assert "Напоминать о паре за <b>30 мин</b>" in edits[-1] and "выключены" in edits[-1]


@pytest.mark.asyncio
async def test_actions_send_clickable_hints(db, bot):
    from aiogram.types import CallbackQuery
    from handlers.start import router
    dp = _dp(router)
    msg = Message(message_id=78, date=0, chat=Chat(id=USER.id, type="private"), text="Выбери действие:")
    cb = CallbackQuery(id="2", from_user=USER, chat_instance="c", data="act:upload", message=msg)
    try:
        await dp.feed_update(bot, Update(update_id=424242, callback_query=cb))
    finally:
        router._parent_router = None
    assert "/upload" in bot.session.sent[-1][0] and "пачкой" in bot.session.sent[-1][0]


def test_deadlines_grouped_by_urgency_with_safe_links():
    from datetime import timedelta
    from handlers.deadlines import format_deadlines
    from utils import today_msk
    t = today_msk()
    mk = lambda i, s, d, by=0, desc="": {"id": i, "subject": s, "due_date": (t + timedelta(days=d)).isoformat(),
                                         "due_time": None, "created_by": by, "description": desc}
    text = format_deadlines([mk(1, "Эссе", -1), mk(2, "СР-2", 0, desc='https://sdo/x?a=1&b="2"'),
                             mk(3, "Практика", 5), mk(4, "Своё", 12, by=222)])
    order = [text.index(g) for g in ("💀 Просрочено", "🔥 Горит", "📅 На неделе", "🗓 Позже")]
    assert order == sorted(order)
    assert '<a href="https://sdo/x?a=1&amp;b=&quot;2&quot;">' in text   # кавычка в URL не рвёт атрибут
    assert "━" not in text and "%" not in text                    # никаких загадочных «80%»
    assert "<b>Своё</b> 👤" in text
