"""Баллы БРС из журнала СДО (sdo_grades) и проверка доступа к Пульсу."""
import httpx
import pytest

import sdo_grades


def _item(level, kind, name, grade, rng, href="", cls=""):
    a = f'<a class="gradeitemheader" href="{href}">{name}</a>' if href else f'<span class="gradeitemheader">{name}</span>'
    return (f'<tr><th class="level{level} item column-itemname"><div class="d-flex"><div>'
            f'<span class="d-block text-uppercase small dimmed_text">{kind}</span>{a}</div></div></th>'
            f'<td class="level{level} itemcenter column-grade {cls}">{grade}</td>'
            f'<td class="level{level} column-range">{rng}</td></tr>')


def _cat(level, name):
    return f'<tr><th class="level{level} category column-itemname" colspan="3"><div>{name}</div></th></tr>'


A = "https://online-edu.mirea.ru/mod/assign/view.php?id="
# Журнал «Основы предпринимательской деятельности» — как на скрине владельца 01.10
REPORT = ('<table class="generaltable user-grade"><thead><tr><th>Элемент оценивания</th></tr></thead><tbody>'
          + _cat(1, "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]")
          + _item(2, "Вычисляемая оценка", "Текущий контроль", "-", "0–45")
          + _item(2, "Заполняемый вручную элемент", "Посещаемость", "5,0", "0–20")
          + _item(2, "Вычисляемая оценка", "Семестровый контроль", "-", "0–40")
          + _item(2, "Заполняемый вручную элемент", "Трудовая деятельность", "-", "0–5")
          + _item(2, "Заполняемый вручную элемент", "Достижения", "-", "0–10")
          + _item(2, "Вычисляемая оценка", "Сумма баллов", "5,0", "0–130")
          + _item(2, "Вычисляемая оценка", "Оценка за промежуточную аттестацию", "Не зачтено", "Не зачтено–Зачтено")
          + _cat(2, "Текущий контроль")
          + _item(3, "Задание", "Практическое задание 1", "6,00", "0–8", A + "101", "gradepass")
          + _item(3, "Задание", "Защита проекта", "-", "0–15", A + "102")
          + _item(3, "Задание", "Практическое задание 2", "2,00", "0–12", A + "103", "gradefail")
          + _item(3, "Тест", "Тест по курсу", "-", "0–10", "https://online-edu.mirea.ru/mod/quiz/view.php?id=104")
          + _item(2, "Заполняемый вручную элемент", "Балл за зачет(доп)", "-", "0–10")
          + _cat(2, "Самостоятельная работа")
          + _item(3, "Задание", "Самостоятельная работа (СР-1)", "", "–", A + "105")
          + '</tbody></table>')


def test_parse_report_like_owner_screenshot():
    s = sdo_grades.summarize(sdo_grades.parse_report(REPORT), "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]")
    assert s["kind"] == "credit" and s["score"] == 5 and s["max"] == 130 and s["final"] == "Не зачтено"
    assert [(c["name"], c["max"]) for c in s["categories"]] == [
        ("Текущий контроль", 45), ("Посещаемость", 20), ("Семестровый контроль", 40),
        ("Трудовая деятельность", 5), ("Достижения", 10), ("Балл за зачет(доп)", 10)]
    tk = s["categories"][0]
    assert tk["tk"] and tk["score"] == 8          # «-» в журнале — сумма выставленных работ
    # работы — только текущего контроля, без самостоятельной
    assert [(w["name"], w["max"], w["passed"]) for w in s["works"]] == [
        ("Практическое задание 1", 8, True), ("Защита проекта", 15, None),
        ("Практическое задание 2", 12, False), ("Тест по курсу", 10, None)]
    assert s["works"][3]["module"] == "quiz" and s["works"][0]["cmid"] == 101
    assert (s["works_total"], s["works_passed"], s["works_graded"]) == (4, 1, 2)
    assert s["marks"] == [{"at": 40, "label": "зачёт"}] and not s["closed"] and s["need"] == 35


def test_exam_marks_and_closed():
    rep = sdo_grades.parse_report(REPORT.replace("Сумма баллов", "Сумма баллов").replace(">5,0</td>\n", ""))
    s = sdo_grades.summarize(rep, "Анализ данных_Экзамен (часть 1/1) [I.26-27]")
    assert s["kind"] == "exam" and [m["label"] for m in s["marks"]] == ["3", "4", "5"]
    rep["items"][5]["grade"] = 64.0      # «Сумма баллов»
    s = sdo_grades.summarize(rep, "Анализ данных_Экзамен")
    assert s["closed"] and s["need_label"] == "5" and s["need"] == 16


ASSIGN_OPEN = """<div>Открыто с: вторник, 1 сентября 2026, 00:00</div><table>
<tr><th>Проходной балл</th><td>3,0</td></tr><tr><th>Состояние ответа на задание</th><td>Ответы на задание еще не представлены</td></tr>
<tr><th>Оставшееся время</th><td>14 дн. 3 час.</td></tr><tr><th>Срок сдачи</th><td>четверг, 15 октября 2026, 23:59</td></tr></table>
<form><input type="hidden" name="action" value="editsubmission"><button>Добавить ответ на задание</button></form>"""
ASSIGN_OFFLINE = """<div>Открывается: четверг, 15 октября 2026, 16:29</div><table><tr><th>Проходной балл</th><td>6,0</td></tr>
<tr><th>Состояние ответа на задание</th><td>Ответ на задание должен быть представлен вне сайта</td></tr></table>"""
ASSIGN_SENT = """<table><tr><th>Состояние ответа на задание</th><td>Отправлено для оценивания</td></tr></table>"""


def test_assign_page_and_status():
    p = sdo_grades.parse_assign_page(ASSIGN_OPEN)
    assert p["pass"] == 3 and p["can_submit"] and not p["submitted"] and p["due"] == "четверг, 15 октября 2026, 23:59"
    w = {"grade": None, "passed": None}
    assert sdo_grades.work_status(w, p) == "todo"
    assert sdo_grades.work_status(w, sdo_grades.parse_assign_page(ASSIGN_SENT)) == "wait"
    off = sdo_grades.parse_assign_page(ASSIGN_OFFLINE)
    assert off["offline"] and off["opens"] and sdo_grades.work_status(w, off) == "offline"
    assert sdo_grades.work_status({"grade": 2, "passed": False}, None) == "low"


@pytest.mark.asyncio
async def test_webapp_grades(db, monkeypatch):
    from fastapi.testclient import TestClient
    import sdo_accounts
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    sdo_grades._cache.clear()

    async def courses(client):
        return [{"id": 18672, "name": "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]",
                 "title": "Основы предпринимательской деятельности"}]

    def moodle(request):
        url = str(request.url)
        if "grade/report/user" in url:
            return httpx.Response(200, text=REPORT)
        if "id=103" in url:
            return httpx.Response(200, text=ASSIGN_OPEN)
        if "id=102" in url:
            return httpx.Response(200, text=ASSIGN_OFFLINE)
        return httpx.Response(200, text="<p></p>")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    monkeypatch.setattr(sdo_grades, "this_semester_courses", courses)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}

    assert c.get("/api/sdo/grades", headers=h).status_code == 403            # СДО не подключён
    await db.save_sdo_session(222, sdo_accounts.encrypt("abcdef0123456789abcdef0123"))
    data = c.get("/api/sdo/grades", headers=h).json()
    (course,) = data["courses"]
    assert course["id"] == 18672 and course["score"] == 5 and course["works_total"] == 4

    d = c.get("/api/sdo/grades/18672", headers=h).json()
    by = {w["name"]: w for w in d["works"]}
    assert by["Практическое задание 2"]["status"] == "low" and by["Практическое задание 2"]["pass_mark"] == 3
    assert by["Защита проекта"]["status"] == "offline" and not by["Защита проекта"]["can_submit"]
    assert by["Практическое задание 1"]["status"] == "ok"
    # цель по умолчанию — зачёт: 5 + открытые 15 и 10 = 30 < 40 — «не хватит»;
    # 75 %: зачтено 1 из 4, нужно 3 — оба открытых (защита и тест) надо зачесть
    g = d["goal"]
    assert (g["label"], g["need"], g["open_points"], g["best"], g["status"]) == ("зачёт", 35, 25, 30, "no")
    assert g["tk"] == {"total": 4, "passed": 1, "need": 3, "left": 2, "open": 2, "ok": False, "reachable": True}
    assert g["lost_count"] == 1 and not g["own"]
    assert c.post("/api/sdo/goal/18672", headers=h, json={"label": "5"}).status_code == 400   # у зачёта нет «5»
    r = c.post("/api/sdo/goal/18672", headers=h, json={"label": "зачёт"})
    assert r.status_code == 200 and r.json()["own"]
    assert c.get("/api/sdo/grades", headers=h).json()["goals"] == {"18672": "зачёт"}
    # счёт «автомат / с экзаменом» (14.10): у зачёта экзамена нет — переключателя нет
    assert c.post("/api/sdo/goal/18672", headers=h, json={"mode": "x"}).status_code == 400
    r = c.post("/api/sdo/goal/18672", headers=h, json={"mode": "exam"})
    assert r.status_code == 200 and r.json()["mode"] is None and r.json()["own"]   # цель не сбросилась
    assert c.post("/api/pulsecheck", headers=h).status_code == 403            # не староста


@pytest.mark.asyncio
async def test_list_and_course_count_passed_the_same(db, monkeypatch):
    """Б4: «зачтено X из Y» в списке «Учёба» и на экране предмета — одним
    правилом: оценка 6 при проходном 7 со страницы задания не зачтена и там,
    и там (страница — из кэша, когда экран предмета уже открывали)."""
    from fastapi.testclient import TestClient
    import sdo_accounts
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    sdo_grades._cache.clear()
    sdo_grades._pages.clear()

    async def courses(client):
        return [{"id": 18672, "name": "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]",
                 "title": "Основы предпринимательской деятельности"}]

    def moodle(request):
        url = str(request.url)
        if "grade/report/user" in url:
            return httpx.Response(200, text=REPORT)
        if "id=101" in url:
            return httpx.Response(200, text="<table><tr><th>Проходной балл</th><td>7,0</td></tr></table>")
        return httpx.Response(200, text="<p></p>")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    monkeypatch.setattr(sdo_grades, "this_semester_courses", courses)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    await db.save_sdo_session(222, sdo_accounts.encrypt("abcdef0123456789abcdef0123"))

    def listed():
        (course,) = c.get("/api/sdo/grades", headers=h).json()["courses"]
        return course["works_passed"]

    assert listed() == 1                      # страниц ещё нет — по журналу, как экран без страницы
    d = c.get("/api/sdo/grades/18672", headers=h).json()
    assert d["works_passed"] == 0 and d["works_need"] == 3
    assert listed() == 0                      # тот же кэш списка — уже с порогом
    sdo_grades._cache.clear()                 # прошло 10 минут: журнал заново, порог — из страниц
    assert listed() == 0


@pytest.mark.asyncio
async def test_pulse_check(monkeypatch):
    import pulse_check
    real = httpx.AsyncClient

    def use(handler):
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(handler), **kw))

    use(lambda r: httpx.Response(403, text="<title>DDoS-Guard</title> geoblocked: has restricted access"))
    res = await pulse_check.check()
    assert not res["ok"] and "DDoS-Guard" in res["why"] and pulse_check.text(res).startswith("🔴")
    use(lambda r: httpx.Response(200, text="<html>Пульс</html>"))
    assert (await pulse_check.check())["ok"]


@pytest.mark.asyncio
async def test_pulsecheck_command_only_for_starosta(monkeypatch):
    import time
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    import pulse_check
    from handlers import announce
    from tests.conftest import STAROSTA_ID
    from tests.test_solver_render import RecordingSession

    async def fake():
        return {"ok": False, "status": 403, "why": "блокирует (DDoS-Guard не пускает адрес сервера)", "ms": 120}

    monkeypatch.setattr(pulse_check, "check", fake)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(announce.router)
    try:
        for i, uid in enumerate((222, STAROSTA_ID)):
            u = User(id=uid, is_bot=False, first_name="X")
            msg = Message(message_id=i + 1, date=0, chat=Chat(id=uid, type="private"), from_user=u, text="/pulsecheck")
            await dp.feed_update(bot, Update(update_id=int(time.time()) + i, message=msg))
    finally:
        announce.router._parent_router = None
    assert [t for t, _ in bot.session.sent] == ["🔴 Пульс МИРЭА с сервера бота: блокирует (DDoS-Guard не пускает адрес сервера)\nHTTP 403 · 120 мс"]


def test_closed_quiz_dash_is_not_below_threshold():
    """Закрытый тест в журнале — «—» (иногда с классом gradefail): это не
    «ниже порога» (владелец, 06.10), а «ещё закрыто»."""
    html = ('<table class="user-grade"><tr><th class="column-itemname level2">'
            '<a href="https://x/mod/quiz/view.php?id=7">Тест</a></th>'
            '<td class="column-grade gradefail">—</td><td class="column-range">0–5</td></tr></table>')
    (it,) = sdo_grades.parse_report(html)["items"]
    assert not it["graded"] and it["grade"] is None and it["passed"] is None
    page = {"opens": "суббота, 1 ноября 2026, 00:00"}
    assert sdo_grades.work_status(dict(it), page) == "soon"
    # даже если журнал что-то показал, тест, который ещё не открылся, — «закрыт»
    assert sdo_grades.work_status({"grade": 0, "passed": False, "module": "quiz"}, page) == "soon"
    assert sdo_grades._blank("Не оценено") and not sdo_grades._blank("Не зачтено")


def test_overdue_without_grade_waits_15_days():
    """Срок прошёл, ответа и оценки нет: 15 дней ждём (могли сдать на паре) —
    работа ещё может дать баллы; потом — пропущена. Тест — пропущен сразу."""
    from datetime import datetime
    w, page = {"grade": None, "passed": None, "module": "assign"}, {"due": "среда, 1 октября 2026, 23:59"}
    assert sdo_grades.work_status(w, page, now=datetime(2026, 9, 30)) == "todo"
    assert sdo_grades.work_status(w, page, now=datetime(2026, 10, 10)) == "late"
    assert sdo_grades.work_status(w, page, now=datetime(2026, 10, 17, 12)) == "miss"
    assert sdo_grades.work_status(dict(w, module="quiz"), page, now=datetime(2026, 10, 2)) == "miss"
    off = dict(page, offline=True)
    assert sdo_grades.work_status(w, off, now=datetime(2026, 9, 30)) == "offline"
    assert sdo_grades.work_status(w, off, now=datetime(2026, 10, 20)) == "miss"
    import sdo_goal
    assert "late" in sdo_goal.OPEN


def test_works_order_numbers_and_test_by_due():
    """1, 3, 2 в журнале → 1, 2, 3; тест встаёт между практиками по сроку
    (пример владельца: практики 1-го числа месяца, тест 8 ноября → после 3-й)."""
    def pr(n, month):
        return {"name": f"Практическая работа №{n}", "module": "assign", "due": f"1 {month} 2026, 23:59"}
    works = [pr(1, "сентября"), pr(3, "ноября"), pr(2, "октября"),
             {"name": "Тестирование", "module": "quiz", "due": "8 ноября 2026, 23:59"},
             pr(4, "декабря"), {"name": "Контрольная работа", "module": "assign"}, pr(5, "декабря")]
    names = [w["name"] for w in sdo_grades.order_works(works)]
    assert names == ["Практическая работа №1", "Практическая работа №2", "Практическая работа №3",
                     "Тестирование", "Практическая работа №4", "Контрольная работа", "Практическая работа №5"]


def test_auto_needs_75_percent_of_works():
    """«На автомат» (плитка «Баллы СДО») — баллов на зачёт/«3» мало: нужно ещё
    зачесть ≥ 75 % работ ТК (владелец, 06.10)."""
    def item(name, grade, passed, cmid=None, level=2):
        return {"name": name, "kind": "", "module": "assign" if cmid else "", "cmid": cmid, "grade": grade,
                "graded": grade is not None, "text": "", "max": 10 if cmid else 60, "passed": passed,
                "level": level, "category": "Текущий контроль" if cmid else ""}
    rep = {"categories": [{"name": "Текущий контроль", "level": 1}],
           "items": [item("Текущий контроль", 45, None, level=1)] +
                    [item(f"Работа {i}", 10 if i < 3 else None, True if i < 3 else None, cmid=i) for i in range(1, 5)]}
    s = sdo_grades.summarize(rep, "Экономика")
    assert s["closed"] and not s["auto"] and s["works_need"] == 1      # 45 баллов, но зачтено 2 из 4
    rep["items"][3].update(grade=10, graded=True, passed=True)
    assert sdo_grades.summarize(rep, "Экономика")["auto"]


def test_unknown_grade_text_is_not_credited():
    """Служебная надпись журнала у закрытого теста (не число и не «Зачтено») —
    не оценка: «Зачтено работ 3 из 6» при двух зачтённых (владелец, 06.10)."""
    for text in ("Скрыто", "Не доступно", "Недоступно", "Ограничено"):
        assert sdo_grades._blank(text), text
    for text in ("Зачтено", "Не зачтено", "Отлично", "5,00"):
        assert not sdo_grades._blank(text), text
    html = ('<table class="user-grade"><tr><th class="column-itemname level2">'
            '<a href="https://x/mod/quiz/view.php?id=7">Тест</a></th>'
            '<td class="column-grade">Скрыто</td><td class="column-range">0–5</td></tr></table>')
    (it,) = sdo_grades.parse_report(html)["items"]
    assert not it["graded"] and it["passed"] is None


# Разметка — как на настоящих страницах СДО МИРЭА (разведка 07.10, Moodle 4.5)
QUIZ_CLOSED_OLD = ('<div data-region="activity-dates"><div><strong>Закрыто c:</strong> среда, 25 декабря 2024, 18:00</div></div>'
                   '<div class="quizinfo"><p>Проходная оценка: 10,00 из 30,00</p></div>')
QUIZ_NOT_YET = ('<div data-region="activity-dates"><div><strong>Открывается:</strong> вторник, 1 декабря 2026, 09:11</div>'
                '<div><strong>Закрывается:</strong> воскресенье, 20 декабря 2026, 23:59</div></div>'
                '<div class="quizattempt"><p>В настоящее время этот тест недоступен</p></div>')
ASSIGN_COMMENT = ('<div data-region="activity-dates"><div><strong>Открыто с:</strong> пятница, 4 сентября 2026, 12:30</div>'
                  '<div><strong>Срок сдачи:</strong> четверг, 10 сентября 2026, 14:00</div></div><table>'
                  '<tr><th>Состояние ответа на задание</th><td class="submissionstatussubmitted">Отправлено для оценивания</td></tr>'
                  '<tr><th>Состояние оценивания</th><td class="submissionnotgraded">Не оценено</td></tr>'
                  '<tr><th>Отзыв в виде комментария</th><td><p>%s</p></td></tr></table>')


def test_real_sdo_dates_and_closed_quiz():
    """«Закрыто c:» (латинская c) с датой от копии прошлогоднего курса — тест ещё
    не настроен, а не пропущен; «тест недоступен» — ещё не открыт."""
    from datetime import datetime
    now = datetime(2026, 10, 7, 12)
    q = {"grade": None, "passed": None, "module": "quiz"}
    old = sdo_grades.parse_assign_page(QUIZ_CLOSED_OLD)
    assert old["closed"] == "среда, 25 декабря 2024, 18:00" and old["pass"] == 10
    assert sdo_grades.work_status(q, old, now) == "soon"
    recent = sdo_grades.parse_assign_page(QUIZ_CLOSED_OLD.replace("2024", "2026").replace("декабря", "сентября"))
    assert sdo_grades.work_status(q, recent, now) == "miss"          # закрылся недавно, попыток нет
    nyet = sdo_grades.parse_assign_page(QUIZ_NOT_YET)
    assert nyet["unavailable"] and nyet["opens"].startswith("вторник, 1 декабря")
    assert nyet["due"] == "воскресенье, 20 декабря 2026, 23:59"
    assert sdo_grades.work_status(q, nyet, now) == "soon"


def test_comment_is_the_verdict_when_no_grade():
    """Оценка у задания не предусмотрена, «Не оценено» навсегда — вердикт в
    комментарии: «зачет» — зачтено, «не принято» — нет (а не вечное «ждёт оценки»)."""
    w = {"grade": None, "passed": None, "module": "assign"}
    for text, want in (("зачет", "ok"), ("не принято", "low"), ("доработать выводы", "low"), ("Смотрите файл", "wait")):
        assert sdo_grades.work_status(w, sdo_grades.parse_assign_page(ASSIGN_COMMENT % text)) == want, text


def test_who_graded_and_when():
    html = ('<div class="feedback"><table><tr><th>Оценка</th><td>5,0 / 5,0</td></tr>'
            '<tr><th>Оценено в</th><td>пятница, 25 сентября 2026, 12:07</td></tr>'
            '<tr><th>Оценено</th><td><img alt="Иванов И. И."/>Иванов Иван Иванович</td></tr></table></div>')
    p = sdo_grades.parse_assign_page(html)
    assert p["graded_by"] == "Иванов Иван Иванович" and p["graded_at"] == "пятница, 25 сентября 2026, 12:07"


def test_final_mark_without_words_when_digit():
    """Итог «2 (неудовлетворительно)» — просто «2» (Никита 12.10); без цифры —
    как в журнале."""
    sf = sdo_grades.short_final
    assert sf("2 (неудовлетворительно)") == "2"
    assert sf("3 (Удовлетворительно)") == "3"
    assert sf("4,00 (хорошо)") == "4,00"
    assert sf("отлично (5)") == "5"
    assert sf("Не зачтено") == "Не зачтено" and sf("отлично") == "отлично" and sf("") == ""
    assert sf("Зачтено (5)") == "Зачтено (5)"      # не оценка экзамена — не трогаем
    rep = sdo_grades.parse_report(REPORT.replace(">Не зачтено<", ">2 (неудовлетворительно)<", 1))
    assert sdo_grades.summarize(rep, "Анализ данных_Экзамен")["final"] == "2"


@pytest.mark.asyncio
async def test_overview_retry_partial_and_dedup(monkeypatch):
    """16.10 (Amvera): не открывшийся журнал пробуем ещё раз; неполный список
    не кладём в кэш; одновременные запросы одного человека — один обход."""
    import asyncio
    import contextlib
    import sdo_files
    sdo_grades._cache.clear()
    courses = [{"id": i, "name": f"Курс {i} [I.26-27]", "title": f"Курс {i}"} for i in (1, 2, 3)]
    calls, broken = [], {2: 1, 3: 99}          # курс 2 падает один раз, курс 3 — всегда

    @contextlib.asynccontextmanager
    async def client(cookie):
        yield None

    async def listing(c):
        calls.append("list")
        await asyncio.sleep(0.01)
        return courses

    async def report(c, cid):
        if broken.get(cid, 0) > 0:
            broken[cid] -= 1
            raise httpx.ConnectTimeout("нет")
        return sdo_grades.parse_report(REPORT)

    monkeypatch.setattr(sdo_files, "make_client", client)
    monkeypatch.setattr(sdo_grades, "this_semester_courses", listing)
    monkeypatch.setattr(sdo_grades, "_report", report)

    a, b = await asyncio.gather(sdo_grades.overview(7, "k"), sdo_grades.overview(7, "k"))
    assert calls == ["list"] and a is b                         # один обход на двоих
    assert [x["id"] for x in a["courses"]] == [1, 2]            # 2 — со второй попытки
    assert ("all", 7) not in sdo_grades._cache                  # 3 не открылся — не запоминаем

    broken[3] = 0
    full = await sdo_grades.overview(7, "k")
    assert len(full["courses"]) == 3 and ("all", 7) in sdo_grades._cache

    sdo_grades._cache.clear()
    broken.update({1: 99, 2: 99, 3: 99})
    with pytest.raises(httpx.HTTPError):                        # ничего — «СДО не отвечает»
        await sdo_grades.overview(7, "k")


async def test_course_detail_does_not_wait_slow_pages(monkeypatch):
    """19.10: СДО отвечал медленно — экран предмета и цель грузились 76–100 с.
    Страницы работ ждём не дольше PAGES_BUDGET; не успели — ответ без них и
    не в кэш, следующий заход доберёт."""
    import asyncio
    import time
    sdo_grades._cache.clear()
    sdo_grades._pages.clear()
    monkeypatch.setattr(sdo_grades, "PAGES_BUDGET", 0.3)
    slow = {"on": True}

    async def courses(client):
        return [{"id": 18672, "name": "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]",
                 "title": "Основы предпринимательской деятельности"}]

    async def moodle(request):
        url = str(request.url)
        if "grade/report/user" in url:
            return httpx.Response(200, text=REPORT)
        if "id=101" in url and slow["on"]:
            await asyncio.sleep(30)
        return httpx.Response(200, text="<table><tr><th>Проходной балл</th><td>7,0</td></tr></table>")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    monkeypatch.setattr(sdo_grades, "this_semester_courses", courses)
    started = time.monotonic()
    d = await sdo_grades.course_detail(1, "c", 18672)
    assert time.monotonic() - started < 5 and d["works"]
    assert sdo_grades._cached(("detail", 1, 18672)) is None         # неполный — не в кэш
    slow["on"] = False
    d = await sdo_grades.course_detail(1, "c", 18672)
    assert sdo_grades._cached(("detail", 1, 18672)) is d
