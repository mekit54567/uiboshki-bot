"""Экран задания СДО: описание, файлы преподавателя (📥), сдача до трёх файлов."""
import base64

import httpx
import pytest

from kapibara.features.sdo import grades as sdo_grades
from kapibara.features.sdo import submit as sdo_submit

PF = "https://online-edu.mirea.ru/pluginfile.php/9001/mod_assign/introattachment/0/"
TASK = f"""<html><body><div role="main"><h2>Практическая работа №5</h2>
<div class="activity-dates">Открыто с: вторник, 1 сентября 2026, 00:00</div>
<div class="activity-description" id="intro"><div class="no-overflow"><p>Построить регрессионную модель.</p>
<p>Прикрепить отчёт и расчёты.</p></div>
<ul><li><a href="{PF}%D0%9C%D0%B5%D1%82%D0%BE%D0%B4%D0%B8%D1%87%D0%BA%D0%B0.pdf?forcedownload=1">Методичка.pdf</a></li>
<li><a href="{PF}dataset_v5.xlsx?forcedownload=1">dataset_v5.xlsx</a></li></ul></div>
<table><tr><th>Проходной балл</th><td>3,0</td></tr>
<tr><th>Состояние ответа на задание</th><td>Ответы на задание еще не представлены</td></tr>
<tr><th>Срок сдачи</th><td>четверг, 15 октября 2026, 23:59</td></tr>
<tr><th>Оставшееся время</th><td>14 дн. 3 час.</td></tr>
<tr><th>Ответ в виде файла</th><td><a href="https://online-edu.mirea.ru/pluginfile.php/9001/assignsubmission_file/submission_files/7/old.docx?forcedownload=1">old.docx</a></td></tr></table>
<form><input type="hidden" name="action" value="editsubmission"><button>Изменить ответ</button></form></div></body></html>"""


def test_parse_task_page():
    t = sdo_grades.parse_task_page(TASK)
    assert t["title"] == "Практическая работа №5"
    assert t["description"] == "Построить регрессионную модель.\nПрикрепить отчёт и расчёты."
    assert [f["name"] for f in t["files"]] == ["Методичка.pdf", "dataset_v5.xlsx"]
    assert [f["name"] for f in t["mine"]] == ["old.docx"]
    assert t["pass"] == 3 and t["can_submit"] and t["due"] == "четверг, 15 октября 2026, 23:59"


# Moodle 4: заголовок — h1 в шапке страницы, описание и файлы — в activity-header
# внутри #region-main, но ДО <div role="main"> (там только таблица состояния).
TASK_M4 = f"""<html><body><header id="page-header"><h1>Практическое задание 1</h1></header>
<section id="region-main"><div class="activity-header" data-for="page-activity-header">
<div class="activity-information"><div class="activity-dates">Срок сдачи: 30 сентября 2026, 16:26</div></div>
<div class="activity-description" id="intro"><div class="box generalbox"><div class="no-overflow"><p>Решить задачи из файла.</p></div></div>
<div id="assign_files_tree1"><ul><li><a href="{PF}%D0%9F%D0%97-1.docx?forcedownload=1">ПЗ-1.docx</a></li></ul></div></div></div>
<div role="main"><span id="maincontent"></span>
<table><tr><th>Состояние ответа на задание</th><td>Ответ на задание должен быть представлен вне сайта</td></tr>
<tr><th>Состояние оценивания</th><td>Не оценено</td></tr></table></div></section></body></html>"""


def test_parse_task_page_moodle4_header():
    t = sdo_grades.parse_task_page(TASK_M4)
    assert t["title"] == "Практическое задание 1"
    assert t["description"] == "Решить задачи из файла."
    assert [f["name"] for f in t["files"]] == ["ПЗ-1.docx"]
    assert t["mine"] == []


@pytest.mark.asyncio
async def test_submit_three_files_in_one_answer(monkeypatch):
    from tests.test_sdo_submit import COOKIE, FakeMoodle
    fake = FakeMoodle()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    files = [("work.pdf", b"%PDF-work"), ("calc.pdf", b"%PDF-work 2"), ("scan.pdf", b"%PDF-work 3")]
    res = await sdo_submit.submit_file(COOKIE, 4242, files=files)
    assert res["status"] == "Отправлено для оценивания"
    uploads = [c for c in fake.calls if "action=upload" in c[1]]
    assert len(uploads) == 3                                             # все в один черновик…
    assert len(fake.posts()) == 1                                        # …и одно сохранение ответа
    with pytest.raises(sdo_submit.SubmitError, match="не больше 3"):
        await sdo_submit.submit_file(COOKIE, 4242, files=files + [("x.pdf", b"%PDF-work")])


@pytest.mark.asyncio
async def test_submit_respects_assignment_maxfiles(monkeypatch):
    from tests.test_sdo_submit import COOKIE, EDIT_PAGE, FakeMoodle
    fake = FakeMoodle(edit=EDIT_PAGE.replace('"maxbytes":10485760', '"maxbytes":10485760,"maxfiles":1'))
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    with pytest.raises(sdo_submit.SubmitError, match="не больше 1"):
        await sdo_submit.submit_file(COOKIE, 4242, files=[("a.pdf", b"%PDF-work"), ("b.pdf", b"%PDF-work")])
    assert not any("action=upload" in c[1] for c in fake.calls)          # ничего не загружено


@pytest.mark.asyncio
async def test_webapp_task_and_signed_download(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.sdo import accounts as sdo_accounts
    import webapp.server as server
    from tests.test_sdo_submit import COOKIE, EDIT_PAGE
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(server.deps, "WEBAPP_URL", "https://app.example")
    seen = []

    def moodle(request):
        url = str(request.url)
        seen.append((url, request.headers.get("cookie", "")))
        if "action=editsubmission" in url:
            return httpx.Response(200, text=EDIT_PAGE.replace('"maxbytes":10485760', '"maxbytes":10485760,"maxfiles":20'))
        if "pluginfile.php" in url:
            return httpx.Response(200, content=b"%PDF-teacher", headers={"content-type": "application/pdf"})
        return httpx.Response(200, text=TASK)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}

    t = c.get("/api/sdo/task/4242", headers=h).json()
    assert t["can_submit"] and t["limit"] == 3 and t["title"] == "Практическая работа №5"
    link = t["files"][0]["dl"]
    assert link.startswith("https://app.example/sdl/") and "pluginfile" not in link   # путь только внутри подписи
    resp = c.get(link.removeprefix("https://app.example"))                            # без initData — по подписи
    assert resp.status_code == 200 and resp.content == b"%PDF-teacher"
    assert "attachment" in resp.headers["content-disposition"]
    assert any("pluginfile.php" in u and COOKIE in ck for u, ck in seen)            # скачано входом студента
    token = link.split("/sdl/")[1].split("/")[0]
    # подпись испорчена (раньше брали token[:-1] + "0" — если подпись и так
    # кончалась на «0», она не менялась, и тест краснел ~1 раз из 16)
    bad = token[:-1] + ("1" if token[-1] == "0" else "0")
    assert c.get(f"/sdl/{bad}/x.pdf").status_code == 403
    forged = server.sdo._sdl_token(222, "/login/index.php", 4102444800)
    assert c.get(f"/sdl/{forged}/x").status_code == 403                               # только pluginfile.php


@pytest.mark.asyncio
async def test_webapp_submit_several_files(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.sdo import accounts as sdo_accounts
    import webapp.server as server
    from tests.test_sdo_submit import COOKIE, FakeMoodle
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    fake = FakeMoodle()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    b64 = base64.b64encode(b"%PDF-work").decode()
    res = c.post("/api/sdo/submit", headers=h, json={"cmid": 4242, "files": [
        {"name": "отчёт.pdf", "data": b64}, {"name": "расчёты.pdf", "data": b64}]})
    assert res.status_code == 200
    assert sum("action=upload" in u for _, u, _ in fake.calls) == 2


def test_teacher_feedback_comment():
    """Комментарий преподавателя к оценке («Отзыв в виде комментария») — в экран
    задания (владелец, 06.10)."""
    html = ('<div role="main"><h2>Аналитическая работа 1</h2><table>'
            '<tr><th>Состояние ответа на задание</th><td>Отправлено для оценивания</td></tr>'
            '<tr><th>Оценка</th><td>5,00 / 8,00</td></tr>'
            '<tr><th>Отзыв в виде комментария</th><td><p>Хорошо, но SWOT</p><p>без выводов.</p></td></tr>'
            '</table></div>')
    p = sdo_grades.parse_task_page(html)
    assert p["feedback"] == "Хорошо, но SWOT\nбез выводов."
    assert sdo_grades.parse_assign_page("<table><tr><th>Оценка</th><td>-</td></tr></table>")["feedback"] == ""


QUIZ_DONE = ('<div id="region-main"><h2>Тест</h2><div class="quizinfo"><p>Разрешено попыток: 1</p>'
             '<p>Ограничение по времени: 30 мин.</p><p>Проходная оценка: 10,00 из 30,00</p></div>'
             '<h3>Ваши попытки</h3><div class="card"><h4 class="card-title">Попытка 1</h4><table class="quizreviewsummary">'
             '<tr><th>Состояние</th><td>Завершены</td></tr><tr><th>Завершен</th><td>суббота, 3 октября 2026, 16:57</td></tr>'
             '<tr><th>Оценка</th><td>30,00 из 30,00 ( 100 %)</td></tr></table></div>'
             '<div id="feedback"><h3>Ваша итоговая оценка за этот тест: 30,00/30,00</h3></div>'
             '<div class="quizattempt"><p>У Вас больше нет попыток</p></div></div>')
QUIZ_OPEN = ('<div id="region-main"><div class="quizinfo"><p>Разрешено попыток: 3</p><p>Проходная оценка: 1,00 из 3,00</p></div>'
             '<div class="quizstartbuttondiv"><button>Попытка теста</button></div></div>')


def test_quiz_page_attempts_best_and_open():
    """Экран теста (разведка СДО 07.10): попытки, лучший результат, проходная, открыт ли."""
    done = sdo_grades.parse_quiz_page(QUIZ_DONE)
    assert done["attempts_allowed"] == 1 and len(done["attempts"]) == 1 and done["no_more"]
    assert done["best"] == "30,00/30,00" and done["pass_text"] == "10,00 из 30,00" and not done["open_now"]
    assert done["attempts"][0]["grade"].startswith("30,00 из 30,00")
    opened = sdo_grades.parse_quiz_page(QUIZ_OPEN)
    assert opened["open_now"] and opened["attempts"] == [] and opened["attempts_allowed"] == 3


@pytest.mark.asyncio
async def test_webapp_quiz_screen(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.sdo import accounts as sdo_accounts
    import webapp.server as server
    from tests.test_sdo_submit import COOKIE
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    seen = []

    def moodle(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=QUIZ_DONE)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(moodle), **kw))
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    t = c.get("/api/sdo/task/77?module=quiz", headers=h).json()
    assert t["quiz"] and t["best"] == "30,00/30,00" and not t["can_submit"] and t["time_limit"] == 30
    assert any("/mod/quiz/view.php?id=77" in u for u in seen)
    assert c.get("/api/sdo/task/77?module=forum", headers=h).status_code == 400
