"""
Обычная решалка (/solve) сама опирается на загруженные лекции предмета:
раньше лекции подключались только отдельной /solve_lectures и только к
первому сообщению, а кнопки предметов («Математика», «Экономика»…) не
совпадали ни с одним предметом, по которому реально есть лекции.
"""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User

import ai_solver
from tests.test_solver_render import RecordingSession

USER = User(id=222, is_bot=False, first_name="Alice")
CHAT = Chat(id=222, type="private")


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())


@pytest.fixture
def dp():
    from handlers.solver import router
    d = Dispatcher(storage=MemoryStorage())
    d.include_router(router)
    yield d
    router._parent_router = None


_mid = [5000]


async def _feed(dp, bot, text):
    _mid[0] += 1
    msg = Message(message_id=_mid[0], date=0, chat=CHAT, from_user=USER, text=text)
    await dp.feed_update(bot, Update(update_id=_mid[0], message=msg))


def test_lecture_prompt_contains_lectures_and_rules():
    prompt = ai_solver.lecture_system_prompt("Анализ данных", "=== Лекция 1 ===\nМетод наименьших квадратов")
    assert "Метод наименьших квадратов" in prompt
    assert "(не из лекций)" in prompt
    assert "Не здоровайся" in prompt  # общий стиль ответа сохранён


@pytest.mark.asyncio
async def test_solve_uses_lectures_in_first_answer_and_follow_ups(db, dp, bot, monkeypatch):
    import handlers.solver as solver
    import schedule_parser

    fid = await db.add_file("Лекция 1", "Анализ данных", "tg1", "l1.pdf", 1)
    await db.save_file_text(fid, "Метод наименьших квадратов: минимизируем сумму квадратов отклонений")

    async def subjects():
        return ["Анализ данных", "Архитектура предприятия"]

    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    seen = []

    async def fake_solve_text(task, subject="", backend="gemini", lectures=""):
        seen.append(("first", subject, lectures))
        return "**Ответ:** МНК"

    async def fake_history(history, subject="", backend="gemini", lectures="", **kw):
        seen.append(("follow", subject, lectures))
        return "**Ответ:** уточнение"

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)
    monkeypatch.setattr(solver, "solve_with_history", fake_history)

    await _feed(dp, bot, "/solve")
    kb = bot.session.sent[-1]
    await _feed(dp, bot, "📖 Анализ данных")
    await _feed(dp, bot, "Как найти коэффициенты регрессии?")
    await _feed(dp, bot, "А если точек три?")

    assert [s[:2] for s in seen] == [("first", "Анализ данных"), ("follow", "Анализ данных")]
    assert all("наименьших квадратов" in s[2] for s in seen)
    assert any("Буду опираться на загруженные лекции" in t for t, _ in bot.session.sent)


@pytest.mark.asyncio
async def test_subject_keyboard_marks_lecture_subjects(db, monkeypatch):
    import handlers.solver as solver
    import schedule_parser

    fid = await db.add_file("Лекция", "Анализ данных", "tg1", "l1.pdf", 1)
    await db.save_file_text(fid, "текст")

    async def subjects():
        return ["Анализ данных", "Архитектура предприятия"]

    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    kb = await solver.solve_subject_kb()
    labels = [row[0].text for row in kb.keyboard]
    assert labels == ["📖 Анализ данных", "Архитектура предприятия", "Другое"]


@pytest.mark.asyncio
async def test_subject_without_lectures_solves_plainly(db, dp, bot, monkeypatch):
    import handlers.solver as solver
    seen = []

    async def fake_solve_text(task, subject="", backend="gemini", lectures=""):
        seen.append(lectures)
        return "**Ответ:** 4"

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)
    await _feed(dp, bot, "/solve")
    await _feed(dp, bot, "Математика")
    await _feed(dp, bot, "2 + 2")
    assert seen == [""]


def test_style_prompt_keeps_sections_only_for_tasks():
    # Живой тест чата WebApp: на «Какие у нас пары завтра?» ИИ отвечал
    # по шаблону задачи — «Ответ: …  Решение: 1. Согласно расписанию…».
    prompt = ai_solver.build_system_prompt("")
    assert "Если это задача" in prompt
    assert "без разделов" in prompt
