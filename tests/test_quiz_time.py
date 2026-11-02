"""Время теста в «Сдать» (Никита 12.10, «Сколько займёт работа», вариант Б):
только у тестов и только ограничение по времени из СДО, одно на всех."""
import httpx
import pytest

from kapibara.features.deadlines import quiz_time
from kapibara.features.sdo import grades as sdo_grades
from tests.test_webapp_home import _headers_for, client  # noqa: F401 — фикстура

QUIZ = "https://online-edu.mirea.ru/mod/quiz/view.php?id={}"
ASSIGN = "https://online-edu.mirea.ru/mod/assign/view.php?id=5011"


def _quiz_page(limit: str = "") -> str:
    line = f"<p>Ограничение по времени: {limit}</p>" if limit else ""
    return (f'<div id="region-main"><div class="quizinfo"><p>Разрешено попыток: 1</p>{line}'
            '<p>Проходная оценка: 10,00 из 30,00</p></div></div>')


def test_parse_time_limit_hours_and_minutes():
    assert sdo_grades.parse_time_limit("Ограничение по времени: 30 мин. Проходная") == 30
    assert sdo_grades.parse_time_limit("Ограничение по времени: 1 час 30 мин. Проходная оценка: 1") == 90
    assert sdo_grades.parse_time_limit("Ограничение по времени: 2 час.") == 120
    assert sdo_grades.parse_time_limit("Ограничение по времени: 1,5 ч") == 90
    assert sdo_grades.parse_time_limit("Разрешено попыток: 1") is None
    assert sdo_grades.parse_assign_page(_quiz_page("1 час 30 мин."))["time_limit"] == 90


def test_quiz_cmid_and_learned():
    assert quiz_time.quiz_cmid(QUIZ.format(7001)) == 7001
    assert quiz_time.quiz_cmid(ASSIGN) is None and quiz_time.quiz_cmid("") is None
    assert quiz_time.learned(sdo_grades.parse_assign_page(_quiz_page("45 мин."))) == 45
    assert quiz_time.learned(sdo_grades.parse_assign_page(_quiz_page())) == 0      # тест без ограничения
    assert quiz_time.learned(sdo_grades.parse_assign_page("<p>Нет доступа</p>")) is None  # не та страница


@pytest.mark.asyncio
async def test_api_deadlines_time_limit_only_for_quizzes(db, client):  # noqa: F811
    c, _ = client
    quiz = await db.add_deadline("Тест 2 · Учетная деятельность", QUIZ.format(7001), "2099-10-01", "18:00", 0,
                                 external_id="sdo:1")
    free = await db.add_deadline("Тест 3 · Учетная деятельность", QUIZ.format(7002), "2099-10-02", "18:00", 0,
                                 external_id="sdo:2")
    unknown = await db.add_deadline("Тест 4", QUIZ.format(7003), "2099-10-03", "18:00", 0, external_id="sdo:3")
    task = await db.add_deadline("Практика 2", ASSIGN, "2099-10-04", "23:59", 0, external_id="sdo:4")
    await quiz_time.remember({7001: sdo_grades.parse_assign_page(_quiz_page("15 мин.")),
                              7002: sdo_grades.parse_assign_page(_quiz_page()),
                              5011: sdo_grades.parse_assign_page(_quiz_page("20 мин."))})
    items = {i["id"]: i for i in c.get("/api/deadlines", headers=_headers_for(222)).json()["items"]}
    assert items[quiz]["time_limit"] == 15
    assert items[free]["time_limit"] is None          # тест без ограничения — ничего
    assert items[unknown]["time_limit"] is None       # ещё не знаем — ничего
    assert items[task]["time_limit"] is None          # у задания — никогда
    # преподаватель поменял ограничение — запоминается последнее увиденное
    await quiz_time.remember({7001: sdo_grades.parse_assign_page(_quiz_page("1 час 30 мин."))})
    assert (await db.get_quiz_limits([7001])) == {7001: 90}


@pytest.mark.asyncio
async def test_learn_missing_fetches_only_unknown_quizzes(db, monkeypatch):
    await db.add_deadline("Тест 2", QUIZ.format(7001), "2099-10-01", "18:00", 0, external_id="sdo:1")
    await db.add_deadline("Тест 3", QUIZ.format(7002), "2099-10-02", "18:00", 0, external_id="sdo:2")
    await db.add_deadline("Тест прошлый", QUIZ.format(7009), "2020-10-02", "18:00", 0, external_id="sdo:9")
    await db.add_deadline("Тест чужой группы", QUIZ.format(7010), "2099-10-02", "18:00", 0,
                          external_id="sdo:5:10", group_id=5)
    await db.add_deadline("Практика", ASSIGN, "2099-10-02", "18:00", 0, external_id="sdo:3")
    await db.save_quiz_limits({7002: 20})
    seen = []

    def moodle(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=_quiz_page("40 мин."))

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    assert await quiz_time.learn_missing("cookie") == 1
    assert seen == [QUIZ.format(7001)]
    assert await db.get_quiz_limits([7001, 7002, 7009, 7010]) == {7001: 40, 7002: 20}
    assert await quiz_time.learn_missing("cookie") == 0 and len(seen) == 1       # второй раз — не ходит
    from kapibara.core import config
    monkeypatch.setattr(config, "SDO_SESSION_COOKIE", "")
    await db.add_deadline("Тест 5", QUIZ.format(7005), "2099-10-05", "18:00", 0, external_id="sdo:6")
    assert await quiz_time.learn_missing() == 0 and len(seen) == 1                # без куки — никуда


@pytest.mark.asyncio
async def test_quiz_screen_remembers_limit(db, monkeypatch):
    """Открыл тест своим входом — время видно всей группе в «Сдать»."""
    from kapibara.features.sdo import accounts as sdo_accounts
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_sdo_submit import COOKIE
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    real = httpx.AsyncClient
    page = _quiz_page("1 час.")
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(
        *a, transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page)), **kw))
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/sdo/task/77?module=quiz", headers=h).json()["time_limit"] == 60
    assert await db.get_quiz_limits([77]) == {77: 60}
