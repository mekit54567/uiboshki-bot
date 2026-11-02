"""«Редактировать ответ» и «Удалить ответ» на задание СДО (владелец 09.10,
3.3): кнопки на странице задания, замена файлов ответа и удаление ответа."""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from kapibara.features.sdo import grades as sdo_grades
from kapibara.features.sdo import submit as sdo_submit
from tests.test_sdo_submit import COOKIE, EDIT_PAGE, VIEW_SUBMITTED

MINE = ('<a href="https://online-edu.mirea.ru/pluginfile.php/9001/assignsubmission_file/submission_files/7/'
        'old.docx?forcedownload=1">old.docx</a>')

# страница задания Moodle 4 с отправленным, но не оценённым ответом
VIEW_ANSWERED = f"""<div role="main"><h2>Практическая работа №5</h2><table>
<tr><th>Состояние ответа на задание</th><td class="submissionstatussubmitted">Отправлено для оценивания</td></tr>
<tr><th>Состояние оценивания</th><td>Не оценено</td></tr>
<tr><th>Срок сдачи</th><td>четверг, 15 октября 2026, 23:59</td></tr>
<tr><th>Ответ в виде файла</th><td>{MINE}</td></tr></table>
<div class="singlebutton"><form method="get" action="https://online-edu.mirea.ru/mod/assign/view.php">
<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="editsubmission">
<button type="submit">Редактировать ответ</button></form></div>
<div class="singlebutton"><form method="get" action="https://online-edu.mirea.ru/mod/assign/view.php">
<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="removesubmissionconfirm">
<button type="submit">Удалить ответ</button></form></div></div>"""

VIEW_GRADED = VIEW_ANSWERED.replace("<td>Не оценено</td>", "<td>Оценено</td>").replace(
    '<div class="singlebutton"><form method="get" action="https://online-edu.mirea.ru/mod/assign/view.php">\n'
    '<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="removesubmissionconfirm">',
    "<div><form>")

VIEW_EMPTY = """<div role="main"><h2>Практическая работа №5</h2><table>
<tr><th>Состояние ответа на задание</th><td>Ответы на задание еще не представлены</td></tr></table>
<form><input type="hidden" name="action" value="editsubmission"><button>Добавить ответ на задание</button></form></div>"""

CONFIRM_REMOVE = """<div role="main"><div class="modal-body"><p>Вы уверены, что хотите удалить свой ответ?</p></div>
<div class="singlebutton"><form method="post" action="https://online-edu.mirea.ru/mod/assign/view.php">
<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="removesubmission">
<input type="hidden" name="userid" value="77"><input type="hidden" name="sesskey" value="SK123">
<button type="submit">Продолжить</button></form></div>
<div class="singlebutton"><form method="get" action="https://online-edu.mirea.ru/mod/assign/view.php">
<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="view">
<button type="submit">Отмена</button></form></div></div>"""


def test_task_page_answered_can_edit_and_remove():
    t = sdo_grades.parse_task_page(VIEW_ANSWERED)
    assert t["can_edit"] and t["can_remove"]
    assert [f["name"] for f in t["mine"]] == ["old.docx"]


def test_task_page_graded_or_empty_no_buttons():
    graded = sdo_grades.parse_task_page(VIEW_GRADED)
    assert not graded["can_edit"] and not graded["can_remove"]        # оценено — менять нельзя
    empty = sdo_grades.parse_task_page(VIEW_EMPTY)
    assert empty["can_submit"] and not empty["can_edit"] and not empty["can_remove"]   # ответа ещё нет


class Moodle:
    """СДО с черновиком, где уже лежит прежний файл ответа."""

    def __init__(self, removable=True):
        self.calls, self.draft, self.removed, self.removable = [], ["old.docx"], False, removable

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = request.content
        self.calls.append((request.method, url, body))
        if "action=editsubmission" in url:
            return httpx.Response(200, text=EDIT_PAGE)
        if "draftfiles_ajax.php?action=dir" in url:
            return httpx.Response(200, json={"list": [{"filename": n, "filepath": "/", "type": "file"}
                                                      for n in self.draft]})
        if "draftfiles_ajax.php?action=delete" in url:
            form = parse_qs(body.decode())
            assert form["itemid"] == ["555"] and form["sesskey"] == ["SK123"]
            self.draft.remove(form["filename"][0])
            return httpx.Response(200, json={"filepath": "/"})
        if "repository_ajax.php?action=upload" in url:
            self.draft.append("new.pdf")
            return httpx.Response(200, json={"url": "x", "id": 555, "file": "new.pdf"})
        if "action=removesubmissionconfirm" in url:
            return httpx.Response(200, text=CONFIRM_REMOVE if self.removable else
                                  '<div class="alert alert-danger">Изменения не допускаются</div>')
        if request.method == "POST" and "mod/assign/view.php" in url:
            form = parse_qs(body.decode())
            if form.get("action") == ["removesubmission"]:
                assert form["sesskey"] == ["SK123"] and form["userid"] == ["77"]
                self.removed = True
            return httpx.Response(200, text=VIEW_SUBMITTED)
        if request.method == "GET" and "mod/assign/view.php" in url:
            return httpx.Response(200, text=VIEW_EMPTY if self.removed else VIEW_SUBMITTED)
        return httpx.Response(404)


@pytest.fixture
def moodle(monkeypatch):
    fake = Moodle()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    return fake


@pytest.mark.asyncio
async def test_edit_answer_replaces_old_files(moodle):
    await sdo_submit.submit_file(COOKIE, 4242, files=[("new.pdf", b"%PDF-new")], replace=True)
    assert moodle.draft == ["new.pdf"]                                   # старый убран, новый на месте
    order = [u.split("?")[1] if "?" in u else u for _, u, _ in moodle.calls]
    assert order.index("action=delete") < order.index("action=upload")   # сначала убрать, потом загрузить


@pytest.mark.asyncio
async def test_plain_submit_keeps_old_files(moodle):
    await sdo_submit.submit_file(COOKIE, 4242, files=[("new.pdf", b"%PDF-new")])
    assert moodle.draft == ["old.docx", "new.pdf"]
    assert not any("draftfiles_ajax" in u for _, u, _ in moodle.calls)


@pytest.mark.asyncio
async def test_remove_answer(moodle):
    res = await sdo_submit.remove_submission(COOKIE, 4242)
    assert moodle.removed and res["status"] == "Ответы на задание еще не представлены"


@pytest.mark.asyncio
async def test_remove_answer_refused(moodle):
    moodle.removable = False
    with pytest.raises(sdo_submit.SubmitError, match="Изменения не допускаются"):
        await sdo_submit.remove_submission(COOKIE, 4242)
    assert not moodle.removed


@pytest.mark.asyncio
async def test_webapp_remove_and_replace(db, moodle, monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from kapibara.features.sdo import accounts as sdo_accounts
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.post("/api/sdo/submission/remove", headers=h, json={"cmid": 4242}).status_code == 403   # нет входа
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    b64 = base64.b64encode(b"%PDF-new").decode()
    r = c.post("/api/sdo/submit", headers=h, json={"cmid": 4242, "replace": True,
                                                   "files": [{"name": "new.pdf", "data": b64}]})
    assert r.status_code == 200 and moodle.draft == ["new.pdf"]
    r = c.post("/api/v1/sdo/submission/remove", headers=h, json={"cmid": 4242})
    assert r.status_code == 200 and moodle.removed
    moodle.removable = False
    r = c.post("/api/sdo/submission/remove", headers=h, json={"cmid": 4242})
    assert r.status_code == 400 and "Изменения не допускаются" in json.loads(r.text)["detail"]
