"""
Дедлайны СДО из календаря по месяцам. Владелец: «дедлайнов маловато — или
они только самые близкие?». Да: «Предстоящие события» Moodle — 21 день
вперёд и не больше 10 событий, а закрытия тестов не проходили фильтр.
Теперь — core_calendar_get_calendar_monthly_view на CALENDAR_MONTHS
месяцев. СДО имитируется httpx.MockTransport.
"""
import json
from datetime import datetime, timedelta

import httpx
import pytest

import sdo_parser

BASE = "https://online-edu.mirea.ru"
TZ = sdo_parser.TZ


def _ts(days: int, hour: int = 23, minute: int = 59) -> int:
    d = datetime.now(TZ).replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days)
    return int(d.timestamp())


def _event(eid, name, component, eventtype, days, course="Анализ данных"):
    return {"id": eid, "name": name, "component": component, "modulename": component.removeprefix("mod_"),
            "eventtype": eventtype, "timestart": _ts(days), "url": f"{BASE}/mod/x/view.php?id={eid}",
            "course": {"id": 7, "fullname": course}}


# по месяцу — своё; 11 заданий — больше, чем влезло бы в «Предстоящие»
MONTHS = {
    0: [_event(1, "Практика 1 - срок сдачи", "mod_assign", "due", 2),
        _event(2, "Тест 1 закрывается", "mod_quiz", "close", 3),
        _event(3, "Опрос о курсе закрывается", "mod_feedback", "close", 4),
        _event(4, "Старое задание", "mod_assign", "due", -3),
        _event(5, "Лекция в Zoom", "", "course", 5)],
    1: [_event(10 + i, f"ПР {i} - срок сдачи", "mod_assign", "due", 40 + i,
               course="Архитектура &amp; ЭВМ [I.26-27]") for i in range(11)],
    2: [_event(1, "Практика 1 - срок сдачи", "mod_assign", "due", 2)],  # то же событие ещё раз — один дедлайн
}


def _sdo(calls, error=False):
    def handler(request: httpx.Request):
        path = request.url.path
        if path == "/my/":
            return httpx.Response(200, text='<script>M.cfg = {"sesskey":"sk1"};</script>')
        if path == "/lib/ajax/service.php":
            assert request.url.params["sesskey"] == "sk1"
            body = json.loads(request.content)[0]
            assert body["methodname"] == "core_calendar_get_calendar_monthly_view"
            calls.append((body["args"]["year"], body["args"]["month"]))
            if error:
                return httpx.Response(200, json=[{"error": True, "exception": {"message": "нет доступа"}}])
            events = MONTHS.get(len(calls) - 1, [])
            return httpx.Response(200, json=[{"error": False, "data": {"weeks": [
                {"days": [{"events": events[:2]}, {"events": events[2:]}]}, {"days": [{"events": []}]}]}}])
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.mark.asyncio
async def test_calendar_months_give_all_deadlines_including_quizzes():
    calls = []
    async with _sdo(calls) as client:
        events = await sdo_parser.fetch_calendar_events(client)
    items = sdo_parser.parse_calendar_events(events)

    assert len(calls) == sdo_parser.CALENDAR_MONTHS
    today = datetime.now(TZ).date()
    y, m = calls[0]
    assert (y, m) == (today.year, today.month)
    assert calls[1] == ((y + 1, 1) if m == 12 else (y, m + 1))

    names = [i["subject"] for i in items]
    assert names[:2] == ["Практика 1 - срок сдачи (Анализ данных)", "Тест 1 закрывается (Анализ данных)"]
    assert len(items) == 2 + 11                      # опрос, событие курса и прошедшее — мимо, повтор — один раз
    assert "ПР 0 - срок сдачи (Архитектура & ЭВМ [I.26-27])" in names
    first = items[0]
    assert (first["external_id"], first["due_time"]) == ("sdo:1", "23:59")
    assert first["due_date"] == (today + timedelta(days=2)).isoformat()


@pytest.mark.asyncio
async def test_calendar_error_means_fallback():
    async with _sdo([], error=True) as client:
        assert await sdo_parser.fetch_calendar_events(client) is None


@pytest.mark.asyncio
async def test_sync_uses_calendar_and_keeps_ids(db, monkeypatch):
    calls = []
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")

    async def calendar():
        async with _sdo(calls) as client:
            return sdo_parser.parse_calendar_events(await sdo_parser.fetch_calendar_events(client))

    async def upcoming_must_not_be_used():
        raise AssertionError("календарь ответил — «Предстоящие» не нужны")

    monkeypatch.setattr(sdo_parser, "fetch_calendar_deadlines", calendar)
    monkeypatch.setattr(sdo_parser, "fetch_upcoming_html", upcoming_must_not_be_used)
    res = await sdo_parser.sync_deadlines()
    assert (res["added"], res["updated"]) == (13, 0)
    assert (await db.get_deadline_by_external_id("sdo:2"))["subject"] == "Тест 1 закрывается (Анализ данных)"

    calls.clear()
    again = await sdo_parser.sync_deadlines()
    assert (again["added"], again["skipped"]) == (0, 13)


def test_upcoming_page_also_takes_quizzes():
    html = f"""
    <div data-type="event" data-event-component="mod_quiz" data-event-eventtype="close"
         data-event-id="77" data-event-title="КР 1 закрывается">
      <a href="{BASE}/calendar/view.php?view=day&amp;time=4102444800">Когда</a>
      <a href="{BASE}/course/view.php?id=7">Анализ данных</a>
    </div>
    <div data-type="event" data-event-component="mod_feedback" data-event-eventtype="close"
         data-event-id="78" data-event-title="Опрос"><a href="{BASE}/x?time=4102444800">Когда</a></div>"""
    assert [d["external_id"] for d in sdo_parser.parse_deadlines(html)] == ["sdo:77"]


# ── прошлый семестр ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("day,tag", [
    ("2026-09-26", "I.26-27"), ("2026-12-30", "I.26-27"), ("2027-01-20", "I.26-27"),
    ("2027-02-10", "II.26-27"), ("2027-06-30", "II.26-27"), ("2027-08-25", "I.27-28"),
])
def test_current_semester_tag(day, tag):
    from datetime import date
    assert sdo_parser.current_semester_tag(date.fromisoformat(day)) == tag


def test_is_old_semester():
    from datetime import date
    d = date(2026, 9, 26)
    assert sdo_parser.is_old_semester("ПР 3 (Анализ данных [II.25-26])", d)
    assert not sdo_parser.is_old_semester("ПР 1 (Архитектура_Экзамен [I.26-27])", d)
    assert not sdo_parser.is_old_semester("Тест (Физкультура)", d)          # без метки — не трогаем


@pytest.mark.asyncio
async def test_sync_skips_old_semester_and_sdoclean_removes_them(db, monkeypatch):
    import time
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import CallbackQuery, Chat, Message, Update, User
    from handlers.deadlines import router
    from tests.conftest import STAROSTA_ID
    from tests.test_sdo_files import _BotSession
    from aiogram import Bot

    cur, old = sdo_parser.current_semester_tag(), "II.10-11"
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")

    async def calendar():
        return [
            {"external_id": "sdo:1", "subject": f"ПР 1 (Анализ [{cur}])", "description": "", "due_date": "2099-10-01", "due_time": "23:59"},
            {"external_id": "sdo:2", "subject": f"ПР 9 (Старое [{old}])", "description": "", "due_date": "2099-10-02", "due_time": "23:59"},
        ]

    monkeypatch.setattr(sdo_parser, "fetch_calendar_deadlines", calendar)
    res = await sdo_parser.sync_deadlines()
    assert (res["added"], res["old_semester"]) == (1, 1)
    assert await db.get_deadline_by_external_id("sdo:2") is None

    # а уже заведённые раньше — чистит /sdoclean после подтверждения
    stale = await db.add_deadline(f"Тест 3 (Старое [{old}])", "", "2099-10-05", "23:59", 0, external_id="sdo:3")
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=_BotSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    user = User(id=STAROSTA_ID, is_bot=False, first_name="С")
    chat = Chat(id=STAROSTA_ID, type="private")
    try:
        msg = Message(message_id=1, date=0, chat=chat, from_user=user, text="/sdoclean")
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, message=msg))
        assert "Дедлайны не этого семестра: 1" in bot.session.sent_texts[-1][1]
        assert await db.get_deadline(stale)                                   # до кнопки — на месте
        cb = CallbackQuery(id="1", from_user=user, chat_instance="c", data="sdoclean:go",
                           message=Message(message_id=2, date=0, chat=chat, text="…"))
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9 + 1, callback_query=cb))
    finally:
        router._parent_router = None
    assert await db.get_deadline(stale) is None
    assert await db.get_deadline_by_external_id("sdo:1")                     # нынешний — не тронут


def test_course_of_takes_last_top_level_parentheses():
    assert sdo_parser.course_of("ПР 1 (Анализ данных (УИБО-03-24))") == "Анализ данных (УИБО-03-24)"
    assert sdo_parser.course_of("Тест (1) закрывается (Архитектура_Экзамен [I.26-27])") == "Архитектура_Экзамен [I.26-27]"
    assert sdo_parser.course_of("Без курса") == ""


@pytest.mark.asyncio
async def test_sync_keeps_only_courses_from_schedule(db, monkeypatch):
    # живой тест: «Методы принятия управленческих решений», «Физкультура 3/3»
    # прошлых семестров были без метки «[II.25-26]» — сверяем с расписанием
    import schedule_parser
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")

    async def subjects():
        return ["Анализ данных", "Архитектура предприятия"]

    async def calendar():
        mk = lambda n, course: {"external_id": f"sdo:{n}", "course": course, "subject": f"ПР {n} ({course})",
                                "description": "", "due_date": "2099-10-01", "due_time": "23:59"}
        return [mk(1, "Анализ данных (УИБО-03-24)"), mk(2, "Архитектура_Экзамен [I.26-27]"),
                mk(3, "Методы принятия управленческих решений"), mk(4, "Физическая культура и спорт 3/3")]

    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    monkeypatch.setattr(sdo_parser, "fetch_calendar_deadlines", calendar)
    res = await sdo_parser.sync_deadlines()
    assert (res["added"], res["old_semester"]) == (2, 2)
    assert res["old_courses"] == ["Методы принятия управленческих решений", "Физическая культура и спорт 3/3"]

    async def no_schedule():
        return []

    monkeypatch.setattr(schedule_parser, "get_group_subjects", no_schedule)   # расписание не загрузилось —
    res = await sdo_parser.sync_deadlines()                                    # ничего не выбрасываем
    assert (res["added"], res["old_semester"]) == (2, 0)
