"""Свой вход в СДО (sdo_accounts) и сдача файла в задание (sdo_submit)."""
import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

import sdo_accounts
import sdo_submit

COOKIE = "abcdef0123456789abcdef0123"
ASSIGN = "https://online-edu.mirea.ru/mod/assign/view.php?id=4242"

EDIT_PAGE = """<html><body>
<form autocomplete="off" action="https://online-edu.mirea.ru/mod/assign/view.php" method="post" id="mform1">
<input name="lastmodified" type="hidden" value="1700000000">
<input name="id" type="hidden" value="4242">
<input name="userid" type="hidden" value="77">
<input name="action" type="hidden" value="savesubmission">
<input name="sesskey" type="hidden" value="SK123">
<input name="_qf__mod_assign_submission_form" type="hidden" value="1">
<input name="files_filemanager" type="hidden" value="555">
<input type="submit" name="submitbutton" value="Сохранить">
<input type="submit" name="cancel" value="Отмена">
</form>
<script>M.form_filemanager.init(Y, {"maxbytes":10485760,"areamaxbytes":-1,"itemid":555,
"client_id":"6511ab3c9d1e2","context":{"id":9001,"contextlevel":70},
"repositories":{"3":{"id":"3","name":"Файлы","type":"recent"},
"5":{"id":"5","name":"Загрузить файл","type":"upload","icon":"x.svg"}}});</script>
</body></html>"""

VIEW_SUBMITTED = ('<table><tr><th>Состояние ответа</th>'
                  '<td class="submissionstatussubmitted cell c1">Отправлено для оценивания</td></tr></table>')
DRAFT_SAVED = '<div><form><input type="hidden" name="action" value="submit"><button>Отправить задание</button></form></div>'
CONFIRM_PAGE = """<form method="post" action="https://online-edu.mirea.ru/mod/assign/view.php">
<input type="hidden" name="id" value="4242"><input type="hidden" name="action" value="confirmsubmit">
<input type="hidden" name="sesskey" value="SK123">
<input type="checkbox" name="submissionstatement" value="1">
<input type="submit" name="submitbutton" value="Продолжить"></form>"""


class FakeMoodle:
    def __init__(self, edit=EDIT_PAGE, drafts=False, logged_in=True, exists=False):
        self.edit, self.drafts, self.logged_in, self.exists = edit, drafts, logged_in, exists
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append((request.method, url, request.content))
        if not self.logged_in:
            if "/login/index.php" in url:
                return httpx.Response(200, text="login")
            return httpx.Response(303, headers={"Location": "https://online-edu.mirea.ru/login/index.php"})
        if request.method == "GET" and url.endswith("/my/"):
            return httpx.Response(200, text="dashboard")
        if "action=editsubmission" in url:
            return httpx.Response(200, text=self.edit)
        if "repository_ajax.php?action=upload" in url:
            assert b'name="repo_upload_file"; filename="' in request.content
            assert b"%PDF-work" in request.content
            if self.exists:
                return httpx.Response(200, json={"event": "fileexists",
                    "existingfile": {"filename": "work.pdf", "filepath": "/"},
                    "newfile": {"filename": "work (1).pdf", "filepath": "/"}})
            return httpx.Response(200, json={"url": "x", "id": 555, "file": "work.pdf"})
        if "repository_ajax.php?action=overwrite" in url:
            return httpx.Response(200, json={"filepath": "/"})
        if "action=submit" in url:
            return httpx.Response(200, text=CONFIRM_PAGE)
        if request.method == "POST" and "mod/assign/view.php" in url:
            return httpx.Response(200, text=DRAFT_SAVED if self.drafts else VIEW_SUBMITTED)
        if request.method == "GET" and "mod/assign/view.php" in url:
            return httpx.Response(200, text=VIEW_SUBMITTED)
        return httpx.Response(404)

    def posts(self):
        return [(u, parse_qs(c.decode())) for m, u, c in self.calls
                if m == "POST" and "mod/assign/view.php" in u]


@pytest.fixture
def moodle(monkeypatch):
    fake = FakeMoodle()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, transport=httpx.MockTransport(fake), **kw))
    return fake


def test_cookie_encrypted_and_cleaned():
    token = sdo_accounts.encrypt(COOKIE)
    assert COOKIE not in token and sdo_accounts.decrypt(token) == COOKIE
    assert sdo_accounts.decrypt("мусор") is None
    assert sdo_accounts.clean_cookie(f" MoodleSession={COOKIE}; ") == COOKIE
    assert sdo_accounts.clean_cookie("привет") is None


def test_cmid_and_can_submit():
    assert sdo_submit.cmid_of(ASSIGN) == 4242
    assert sdo_submit.cmid_of("https://online-edu.mirea.ru/mod/quiz/view.php?id=1") is None
    assert sdo_submit.can_submit({"description": ASSIGN, "external_id": "sdo:1"})
    assert not sdo_submit.can_submit({"description": ASSIGN, "external_id": None})   # личный


def test_parse_edit_page():
    page = sdo_submit.parse_edit_page(EDIT_PAGE)
    assert (page["repo_id"], page["ctx_id"], page["itemid"], page["client_id"]) == ("5", "9001", "555", "6511ab3c9d1e2")
    assert page["fields"]["action"] == "savesubmission" and "cancel" not in page["fields"]
    with pytest.raises(sdo_submit.SubmitError, match="Срок сдачи истёк"):
        sdo_submit.parse_edit_page('<div class="alert alert-danger">Срок сдачи истёк</div>')


@pytest.mark.asyncio
async def test_submit_file(moodle):
    res = await sdo_submit.submit_file(COOKIE, 4242, "work.pdf", b"%PDF-work")
    assert res["status"] == "Отправлено для оценивания"
    (url, form), = moodle.posts()
    assert form["files_filemanager"] == ["555"] and form["sesskey"] == ["SK123"]
    assert form["submitbutton"] == ["Сохранить"]


@pytest.mark.asyncio
async def test_submit_overwrites_and_confirms_draft(moodle):
    moodle.exists, moodle.drafts = True, True
    await sdo_submit.submit_file(COOKIE, 4242, "work.pdf", b"%PDF-work")
    assert any("action=overwrite" in u for _, u, _ in moodle.calls)
    confirm = moodle.posts()[-1][1]
    assert confirm["action"] == ["confirmsubmit"] and confirm["submissionstatement"] == ["1"]


@pytest.mark.asyncio
async def test_submit_too_big_for_assignment(moodle):
    with pytest.raises(sdo_submit.SubmitError, match="10 МБ"):
        await sdo_submit.submit_file(COOKIE, 4242, "big.pdf", b"%PDF-work" + b"0" * 11 * 1024 * 1024)


@pytest.mark.asyncio
async def test_webapp_connect_and_submit(db, moodle, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    did = await db.add_deadline("Практическая работа №3", ASSIGN, "2026-10-05", None, 0, external_id="sdo:1")
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}

    assert c.get("/api/sdo/status", headers=h).json()["state"] == "off"
    item = next(d for d in c.get("/api/deadlines", headers=h).json()["items"] if d["id"] == did)
    assert item["can_submit"]
    body = {"deadline_id": did, "name": "work.pdf", "data": base64.b64encode(b"%PDF-work").decode()}
    assert c.post("/api/sdo/submit", json=body, headers=h).status_code == 403     # не подключён

    assert c.post("/api/sdo/connect", json={"cookie": "x", "agree": True}, headers=h).status_code == 400
    # без галочки согласия (152-ФЗ) куку не берём
    res = c.post("/api/sdo/connect", json={"cookie": "MoodleSession=" + COOKIE}, headers=h)
    assert res.status_code == 400 and "согласия" in res.json()["detail"]
    res = c.post("/api/sdo/connect", json={"cookie": "MoodleSession=" + COOKIE, "agree": True}, headers=h)
    assert res.json()["state"] == "ok"
    row = await db.get_sdo_session(222)
    assert COOKIE not in json.dumps(row)                                          # в базе только шифр

    res = c.post("/api/sdo/submit", json=body, headers=h)
    assert res.status_code == 200 and res.json()["status"] == "Отправлено для оценивания"
    assert res.json()["state"] == "submitted"
    assert await db.is_deadline_done(did, 222)              # сдал через бота — дедлайн у себя отмечен сам

    moodle.logged_in = False                                                     # СДО разлогинил
    assert c.post("/api/sdo/submit", json=body, headers=h).status_code == 403
    assert c.get("/api/sdo/status", headers=h).json()["state"] == "expired"
    assert c.post("/api/sdo/disconnect", headers=h).json()["state"] == "off"


@pytest.mark.asyncio
async def test_keepalive_marks_expired_and_tells_once(db, moodle):
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append(chat_id)

    await sdo_accounts.keepalive_all(Bot())
    assert (await db.get_sdo_session(222))["status"] == "ok" and not sent
    moodle.logged_in = False
    await sdo_accounts.keepalive_all(Bot())
    await sdo_accounts.keepalive_all(Bot())
    assert (await db.get_sdo_session(222))["status"] == "expired" and sent == [222]


NO_FORM = """<html><body><noscript><div class="alert alert-danger">JavaScript отключен в вашем браузере.</div></noscript>
<div role="main"><h2>Практическая работа №1</h2></div></body></html>"""
VIEW_CLOSED = """<noscript><div class="alert alert-danger">JavaScript отключен в вашем браузере.</div></noscript>
<table><tr><th>Состояние ответа</th><td>Ни одной попытки</td></tr>
<tr><th>Состояние оценивания</th><td>Не оценено</td></tr>
<tr><th>Оставшееся время</th><td>Задание просрочено на: 5 дн.</td></tr></table>"""


@pytest.mark.asyncio
async def test_no_form_explains_from_assignment_page(moodle, monkeypatch):
    # живой тест 01.10: формы не было, а бот показал плашку «JavaScript отключен» из <noscript>
    moodle.edit = NO_FORM
    real_call = moodle.__call__

    def call(request):
        url = str(request.url)
        if request.method == "GET" and url.endswith("view.php?id=4242"):
            return httpx.Response(200, text=VIEW_CLOSED)
        return real_call(request)

    monkeypatch.setattr(FakeMoodle, "__call__", lambda self, r: call(r))
    with pytest.raises(sdo_submit.SubmitError) as e:
        await sdo_submit.submit_file(COOKIE, 4242, "work.pdf", b"%PDF-work")
    msg = str(e.value)
    assert "JavaScript" not in msg
    assert "Ни одной попытки" in msg and "просрочено на: 5 дн." in msg
    assert not any(m == "POST" for m, _, _ in moodle.calls)                     # ничего не грузили


@pytest.mark.asyncio
async def test_keepalive_spread_over_hour(db, moodle):
    """Проверки входов вразнобой: подключённые до версии получают случайное
    место в ближайшем часе (не все разом), дальше — 50–59 мин, потом 55."""
    from datetime import datetime, timedelta
    t0 = datetime(2026, 10, 2, 12, 0, 0)
    for uid in range(1, 31):
        await db.save_sdo_session(uid, sdo_accounts.encrypt(COOKIE))      # как до версии: без времени
    await sdo_accounts.keepalive_due(None, t0)
    rows = await db.get_sdo_sessions("ok")
    due = sorted(r["next_check_at"] for r in rows)
    assert all("2026-10-02 12:01:00" <= d <= "2026-10-02 12:55:00" for d in due)
    assert len(set(due)) > 10                                              # разошлись по часу

    def mins(r):
        return (datetime.fromisoformat(r["next_check_at"]) - when).total_seconds() / 60

    when = t0 + timedelta(minutes=60)                                      # у всех очередь подошла
    for step in range(4):
        await sdo_accounts.keepalive_due(None, when)
        rows = await db.get_sdo_sessions("ok")
        gaps = {round(mins(r)) for r in rows}
        if step < 3:
            assert gaps <= set(range(50, 60))                              # первые три — вразнобой
        else:
            assert gaps == {55}                                            # дальше ровно 55
        when = max(datetime.fromisoformat(r["next_check_at"]) for r in rows)


@pytest.mark.asyncio
async def test_keepalive_not_due_not_checked(db, moodle):
    from datetime import datetime
    t0 = datetime(2026, 10, 2, 12, 0, 0)
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE), sdo_accounts.first_check_at(t0))
    nxt = (await db.get_sdo_session(222))["next_check_at"]
    assert "2026-10-02 12:50:00" <= nxt <= "2026-10-02 12:59:00"
    moodle.logged_in = False
    await sdo_accounts.keepalive_due(None, t0)                             # ещё не очередь — не трогаем
    assert (await db.get_sdo_session(222))["status"] == "ok"
    await sdo_accounts.keepalive_due(None, datetime.fromisoformat(nxt))
    assert (await db.get_sdo_session(222))["status"] == "expired"


# ── Какие файлы принимает задание (живой случай 02.10: только ZIP) ───────────
# Так Moodle 4 пишет под полем файлов: настройки менеджера (accepted_types) и
# подпись «Допустимые типы файлов».
ZIP_EDIT_PAGE = EDIT_PAGE.replace('"maxbytes":10485760,', '"maxbytes":10485760,"maxfiles":"1","accepted_types":[".zip"],').replace(
    "</form>", '<div class="form-filetypes-descriptions w-100"><ul class="list-unstyled unstyled">'
               '<li>Архив (ZIP) <small class="text-muted muted">.zip</small></li></ul></div></form>')


def test_parse_accepted_types():
    page = sdo_submit.parse_edit_page(ZIP_EDIT_PAGE)
    assert page["accepted"] == [".zip"] and page["labels"] == ["Архив (ZIP)"] and page["maxfiles"] == 1
    assert sdo_submit.parse_edit_page(EDIT_PAGE)["accepted"] == []                  # ограничений нет — любые
    star = EDIT_PAGE.replace('"maxbytes":10485760,', '"maxbytes":10485760,"accepted_types":"*",')
    assert sdo_submit.parse_edit_page(star)["accepted"] == []
    # нет настроек менеджера — расширения из подписи
    only_desc = ZIP_EDIT_PAGE.replace('"accepted_types":[".zip"],', "")
    assert sdo_submit.parse_edit_page(only_desc)["accepted"] == [".zip"]
    assert sdo_submit.ext_ok("Работа.ZIP", [".zip"]) and not sdo_submit.ext_ok("work.pdf", [".zip"])


# Живой случай 04.10: в задании ответ и текстом, и файлом. У редактора текста
# свои настройки (картинки .gif … .svgz, maxfiles 20) — и они на странице
# раньше файлового менеджера. Бот брал их и не пускал .docx.
EDITOR_OPTS = ('<script>Y.use("editor_atto", function() { YUI.M.editor_atto.Editor.init({"elementid":'
               '"id_onlinetext_editor","filepickeroptions":{"image":{"accepted_types":[".gif",".jpe",".jpeg",'
               '".jpg",".png",".svg",".svgz"],"maxfiles":20,"maxbytes":0,"itemid":777,'
               '"client_id":"edit0r1d","context":{"id":9001}}}}); });</script>')
TEXT_AND_FILE_PAGE = EDIT_PAGE.replace("<form ", '<textarea name="onlinetext_editor[text]"></textarea>' + EDITOR_OPTS + "<form ", 1)


def test_editor_image_types_dont_block_files():
    page = sdo_submit.parse_edit_page(TEXT_AND_FILE_PAGE)
    assert page["accepted"] == [] and page["client_id"] == "6511ab3c9d1e2" and page["maxfiles"] == 0
    zip_page = sdo_submit.parse_edit_page(TEXT_AND_FILE_PAGE.replace(
        '"maxbytes":10485760,"areamaxbytes"', '"maxbytes":10485760,"accepted_types":[".zip"],"areamaxbytes"'))
    assert zip_page["accepted"] == [".zip"]


@pytest.mark.asyncio
async def test_docx_goes_to_text_and_file_task(moodle):
    moodle.edit = TEXT_AND_FILE_PAGE
    res = await sdo_submit.submit_file(COOKIE, 4242, "ПР1.docx", b"%PDF-work")   # содержимое — как ждёт заглушка СДО
    assert res["status"] == "Отправлено для оценивания"
    assert any("repository_ajax" in u for _, u, _ in moodle.calls)


@pytest.mark.asyncio
async def test_wrong_type_refused_before_upload(moodle):
    moodle.edit = ZIP_EDIT_PAGE
    with pytest.raises(sdo_submit.SubmitError, match=r"«work\.pdf» не подойдёт: СДО примет здесь только \.zip — упакуй"):
        await sdo_submit.submit_file(COOKIE, 4242, "work.pdf", b"%PDF-work")
    assert not any("repository_ajax" in u for _, u, _ in moodle.calls)              # в СДО ничего не грузили


@pytest.mark.asyncio
async def test_submission_rules_and_route(db, moodle, monkeypatch):
    moodle.edit = ZIP_EDIT_PAGE
    rules = await sdo_submit.submission_rules(COOKIE, 4242)
    assert rules == {"accepted": [".zip"], "labels": ["Архив (ZIP)"], "maxfiles": 1, "maxbytes": 10485760}

    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    did = await db.add_deadline("Практическая работа №3", ASSIGN, "2026-10-05", None, 0, external_id="sdo:1")
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/sdo/submit-rules", params={"deadline_id": did}, headers=h).status_code == 403   # не подключён
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    assert c.get("/api/sdo/submit-rules", params={"deadline_id": did}, headers=h).json()["accepted"] == [".zip"]
    assert c.get("/api/sdo/submit-rules", params={"cmid": 4242}, headers=h).json()["labels"] == ["Архив (ZIP)"]
    assert c.get("/api/sdo/submit-rules", params={"deadline_id": 99999}, headers=h).status_code == 404

    moodle.edit = '<div class="alert alert-danger">Срок сдачи истёк</div>'          # сдача закрыта — говорим сразу
    assert "Срок сдачи истёк" in c.get("/api/sdo/submit-rules", params={"cmid": 4242}, headers=h).json()["closed"]


@pytest.mark.asyncio
async def test_submit_timeout_is_502_not_500(db, moodle, monkeypatch):
    """3.3: СДО не дождалось PDF (таймаут загрузки) или упало что-то ещё —
    понятный 502 «файл, возможно, не дошёл», а не 500 и не «нет связи»."""
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))
    real_call = FakeMoodle.__call__

    def slow(self, request):
        if "repository_ajax.php?action=upload" in str(request.url):
            raise httpx.ReadTimeout("СДО молчит", request=request)
        return real_call(self, request)

    monkeypatch.setattr(FakeMoodle, "__call__", slow)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    body = {"cmid": 4242, "name": "work.pdf", "data": base64.b64encode(b"%PDF-work").decode()}
    res = c.post("/api/sdo/submit", json=body, headers=h)
    assert res.status_code == 502 and "не ответило вовремя" in res.json()["detail"]

    async def boom(*a, **kw):
        raise RuntimeError("что-то странное")

    monkeypatch.setattr(sdo_submit, "submit_file", boom)
    res = c.post("/api/sdo/submit", json=body, headers=h)
    assert res.status_code == 502 and "проверь в СДО" in res.json()["detail"]


@pytest.mark.parametrize("status, state, done", [
    ("Отправлено для оценивания", "submitted", True),
    ("Черновик (не отправлено)", "draft", False),
    ("", "unknown", False),                              # 200 со странной страницей — не «Сдано»
    ("Нет попытки", "unknown", False),
])
@pytest.mark.asyncio
async def test_submit_state_for_app(db, monkeypatch, status, state, done):
    """«Сдано» в приложении — только когда СДО подтвердил отправку; черновик и
    непонятный ответ — свой state, дедлайн не отмечается (аудит 21.10, R5)."""
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    did = await db.add_deadline("Практическая работа №3", ASSIGN, "2026-10-05", None, 0, external_id="sdo:1")
    await db.save_sdo_session(222, sdo_accounts.encrypt(COOKIE))

    async def fake_submit(cookie, cmid, **kw):
        return {"status": status, "url": "u"}
    monkeypatch.setattr(sdo_submit, "submit_file", fake_submit)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    body = {"deadline_id": did, "name": "work.pdf", "data": base64.b64encode(b"%PDF-work").decode()}
    res = c.post("/api/v1/sdo/submit", json=body, headers=h)
    assert res.status_code == 200 and res.json()["state"] == state
    assert await db.is_deadline_done(did, 222) is done
