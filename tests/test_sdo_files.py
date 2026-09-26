"""
Файлы из СДО (sdo_files.py, /sdofiles). Сам СДО из облачной сессии
недоступен — здесь он имитируется httpx.MockTransport по разметке
стандартных страниц Moodle: AJAX «Мои курсы», course/resources.php,
страница курса, папка, редирект ресурса на pluginfile.php.
"""
import asyncio
import json
import time
from urllib.parse import quote

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Document, Message, Update, User

import sdo_files
from tests.conftest import STAROSTA_ID
from tests.test_solver_render import RecordingSession

BASE = "https://online-edu.mirea.ru"
SUBJECTS = ["Архитектура вычислительных машин и систем", "Анализ данных", "Сети и телекоммуникации"]

MY = '<html><div class="usermenu"></div><script>M.cfg = {"wwwroot":"x","sesskey":"sk123","sessiontimeout":"28800"};</script></html>'

RESOURCES_11 = f"""
<table class="generaltable mod_index">
<thead><tr><th>Тема</th><th>Название</th><th>Описание</th></tr></thead>
<tbody>
<tr><td class="cell c0">Лекции</td><td class="cell c1"><a href="{BASE}/mod/resource/view.php?id=101"><img src="i.svg" alt=""> Введение в архитектуру<span class="accesshide"> Файл</span></a></td><td></td></tr>
<tr><td class="cell c0"></td><td class="cell c1"><a href="{BASE}/mod/folder/view.php?id=102">Материалы лекций</a></td><td></td></tr>
<tr><td class="cell c0">Практические занятия</td><td class="cell c1"><a href="{BASE}/mod/resource/view.php?id=103">Задание к ПР 1</a></td><td></td></tr>
<tr><td class="cell c0"></td><td class="cell c1"><a href="{BASE}/mod/resource/view.php?id=104">Ссылка-страница</a></td><td></td></tr>
<tr><td class="cell c0"></td><td class="cell c1"><a href="{BASE}/mod/url/view.php?id=105">Ютуб</a></td><td></td></tr>
</tbody></table>"""

FOLDER_102 = f"""
<div class="foldertree"><ul>
<li><span class="fp-filename-icon"><a href="{BASE}/pluginfile.php/77/mod_folder/content/0/1.txt?forcedownload=1"><span class="fp-icon"><img alt=""></span><span class="fp-filename">1.txt</span></a></span></li>
<li><span class="fp-filename-icon"><a href="{BASE}/pluginfile.php/77/mod_folder/content/0/%D0%9A%D0%A0%201.pdf?forcedownload=1"><span class="fp-filename">КР 1.pdf</span></a></span></li>
</ul></div>"""

COURSE_12 = f"""
<ul class="topics">
<li class="section main" data-sectionname="Контрольные мероприятия"><h3 class="sectionname">Контрольные мероприятия</h3>
<ul><li class="activity modtype_resource"><a href="{BASE}/mod/resource/view.php?id=201"><span class="instancename">Вопросы к зачёту<span class="accesshide"> Файл</span></span></a></li></ul>
</li></ul>"""


def _sdo(calls=None, expired=False):
    calls = calls if calls is not None else []

    def handler(request: httpx.Request):
        path, q = request.url.path, dict(request.url.params)
        calls.append((request.method, path, q))
        if path == "/login/index.php":
            return httpx.Response(200, text="<html>login</html>")
        if expired:
            return httpx.Response(303, headers={"location": f"{BASE}/login/index.php"})
        if path == "/my/":
            return httpx.Response(200, text=MY)
        if path == "/lib/ajax/service.php":
            assert q["sesskey"] == "sk123"
            body = json.loads(request.content)
            assert body[0]["methodname"] == "core_course_get_enrolled_courses_by_timeline_classification"
            return httpx.Response(200, json=[{"error": False, "data": {"courses": [
                {"id": 11, "fullname": "Архитектура_Экзамен [I.26-27]", "shortname": "арх"},
                {"id": 12, "fullname": "Анализ данных (УИБО-03-24)", "shortname": "ад"},
                {"id": 13, "fullname": "Физкультура", "shortname": "фк"},
                {"id": 14, "fullname": "Информатика [II.25-26]", "shortname": "инф"},
            ], "nextoffset": 4}}])
        if path == "/course/resources.php":
            return httpx.Response(200, text=RESOURCES_11 if q["id"] == "11" else "<p>Нет ресурсов</p>")
        if path == "/course/view.php":
            return httpx.Response(200, text=COURSE_12 if q["id"] == "12" else "<p>пусто</p>")
        if path == "/mod/folder/view.php":
            return httpx.Response(200, text=FOLDER_102)
        if path == "/mod/resource/view.php":
            target = {"101": "lec.txt", "103": "pr1.txt", "201": "exam.txt"}.get(q["id"])
            if not target:
                return httpx.Response(200, text="<html>страница ресурса</html>", headers={"content-type": "text/html"})
            return httpx.Response(303, headers={"location": f"{BASE}/pluginfile.php/5/mod_resource/content/1/{target}"})
        if path.startswith("/pluginfile.php/"):
            name = path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=f"текст файла {name}".encode(), headers={
                "content-type": "application/octet-stream",
                "content-disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True,
                             cookies={"MoodleSession": "x"}), calls


# ── разбор ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,clean", [
    ("Архитектура_Экзамен [I.26-27]", "Архитектура"),
    ("Анализ данных (УИБО-03-24)", "Анализ данных"),
    ("Сети и телекоммуникации_Зачёт 2025-2026", "Сети и телекоммуникации"),
    ("[I.26-27]", "[I.26-27]"),                      # нечего оставить — как есть
])
def test_clean_course_name(name, clean):
    assert sdo_files.clean_course_name(name) == clean


@pytest.mark.parametrize("course,subject", [
    ("Архитектура_Экзамен [I.26-27]", "Архитектура вычислительных машин и систем"),
    ("Анализ данных (УИБО-03-24)", "Анализ данных"),
    ("Сети и системы телекоммуникаций", "Сети и телекоммуникации"),
    ("Физкультура", "Физкультура"),                  # в расписании нет — имя курса
    ("Анализ рисков", "Анализ рисков"),              # одно общее слово из двух — мало
])
def test_match_subject(course, subject):
    assert sdo_files.match_subject(course, SUBJECTS) == subject


def test_parse_resources_carries_section_and_strips_hidden_text():
    items = sdo_files.parse_course_resources(RESOURCES_11)
    assert [(i["kind"], i["cmid"], i["title"], i["section"]) for i in items] == [
        ("resource", 101, "Введение в архитектуру", "Лекции"),
        ("folder", 102, "Материалы лекций", "Лекции"),
        ("resource", 103, "Задание к ПР 1", "Практические занятия"),
        ("resource", 104, "Ссылка-страница", "Практические занятия"),
    ]
    assert sdo_files.parse_course_resources(COURSE_12) == [
        {"kind": "resource", "cmid": 201, "title": "Вопросы к зачёту", "section": "Контрольные мероприятия"}]


def test_parse_folder_and_course_links():
    assert [f["name"] for f in sdo_files.parse_folder_files(FOLDER_102)] == ["1.txt", "КР 1.pdf"]
    assert sdo_files.parse_sesskey(MY) == "sk123"
    profile = '<a href="/user/view.php?id=5&amp;course=44">ОБА</a><a href="/course/view.php?id=1">Главная</a>'
    assert sdo_files.parse_course_links(profile) == [{"id": 44, "name": "ОБА"}]


# ── пробный прогон и выгрузка ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_maps_subjects_and_categories():
    client, _ = _sdo()
    async with client:
        courses = await sdo_files.scan(client, SUBJECTS)
    arch, data, sport, old = courses
    assert old.old and old.files == []                    # прошлый семестр — даже не открывали
    assert arch.subject == "Архитектура вычислительных машин и систем"
    assert [(f.title, f.category, f.source) for f in arch.files] == [
        ("Введение в архитектуру", "lecture", "sdo:101"),       # тип — по разделу «Лекции»
        ("Материалы лекций 1", "lecture", "sdo:102:1.txt"),     # «1.txt» из папки лекций
        ("КР 1", "control", "sdo:102:КР 1.pdf"),                # имя файла важнее папки
        ("Задание к ПР 1", "practice", "sdo:103"),
        ("Ссылка-страница", "practice", "sdo:104"),
    ]
    assert data.subject == "Анализ данных" and [f.category for f in data.files] == ["exam"]
    assert sport.files == [] and not sport.error


class _BotSession(RecordingSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.documents, self.deleted = [], []

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name == "SendDocument":
            self.documents.append(method.document.filename)
            n = len(self.documents)
            return Message(message_id=5000 + n, date=0, chat=Chat(id=method.chat_id, type="private"),
                           document=Document(file_id=f"tg{n}", file_unique_id=f"u{n}",
                                             file_name=method.document.filename)).as_(bot)
        if name == "DeleteMessage":
            self.deleted.append(method.message_id)
            return True
        if name == "EditMessageReplyMarkup":
            return True
        return await super().make_request(bot, method, timeout)


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=_BotSession())


@pytest.mark.asyncio
async def test_import_saves_files_text_and_skips_known(db, bot, monkeypatch):
    monkeypatch.setattr(sdo_files, "SEND_PAUSE", 0)
    client, _ = _sdo()
    async with client:
        files = [f for c in await sdo_files.scan(client, SUBJECTS) for f in c.files]
        stats = await sdo_files.import_files(bot, STAROSTA_ID, client, files)
        assert stats == {"added": 5, "with_text": 4, "skipped": 0, "failed": 0, "too_big": 0, "not_file": 1}
        again = await sdo_files.import_files(bot, STAROSTA_ID, client, files)
    assert again["added"] == 0 and again["skipped"] == 6 - again["not_file"]

    assert bot.session.documents[:2] == ["lec.txt", "1.txt"]
    assert len(bot.session.deleted) == 5          # у старосты в чате ничего не остаётся
    saved = {f["title"]: f for f in await db.get_files()}
    lec = saved["Введение в архитектуру"]
    assert (lec["subject"], lec["category"], lec["file_name"], lec["uploaded_by"]) == \
           ("Архитектура вычислительных машин и систем", "lecture", "lec.txt", 0)
    assert "текст файла lec.txt" in await db.get_subject_lecture_context("Архитектура вычислительных машин и систем")


@pytest.mark.asyncio
async def test_expired_cookie_is_reported():
    client, _ = _sdo(expired=True)
    async with client:
        with pytest.raises(sdo_files.SdoSessionExpired):
            await sdo_files.scan(client, SUBJECTS)


@pytest.mark.asyncio
async def test_sdofiles_command_dry_run_then_import(db, bot, monkeypatch):
    import sdo_parser
    import schedule_parser
    import handlers.files as hf

    async def subjects():
        return SUBJECTS

    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    monkeypatch.setattr(sdo_parser, "SDO_SESSION_COOKIE", "x")
    monkeypatch.setattr(sdo_files, "SEND_PAUSE", 0)
    calls = []
    monkeypatch.setattr(sdo_files, "make_client", lambda cookie: _sdo(calls)[0])

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(hf.router)
    user = User(id=STAROSTA_ID, is_bot=False, first_name="Староста")
    chat = Chat(id=STAROSTA_ID, type="private")
    try:
        msg = Message(message_id=1, date=0, chat=chat, from_user=user, text="/sdofiles")
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9, message=msg))
        report = bot.session.sent_texts[-1][1]
        assert "СДО: 4 курса, 6 файлов</b> (новых: 6)" in report
        assert "Прошлый семестр — пропустил: Информатика [II.25-26]" in report
        assert "<b>Архитектура_Экзамен [I.26-27]</b>\n→ 📁 Архитектура вычислительных машин и систем · 5: 📓 2 · 🛠 2 · 📝 1" in report
        assert "Без файлов: Физкультура" in report
        assert await db.get_files() == []               # пробный прогон ничего не сохраняет
        assert not [c for c in calls if c[1].startswith("/pluginfile.php/")]  # и ничего не качает
        assert not [c for c in calls if c[2].get("id") == "14"]           # старый курс не открывали

        cb = CallbackQuery(id="1", from_user=user, chat_instance="c", data="sdof:go",
                           message=Message(message_id=2, date=0, chat=chat, text="…"))
        await dp.feed_update(bot, Update(update_id=int(time.time() * 1000) % 10**9 + 1, callback_query=cb))
        await asyncio.gather(*hf._sdo_tasks)
    finally:
        hf.router._parent_router = None
    final = bot.session.sent_texts[-1][1]
    assert "Из СДО добавлено: 5" in final and "ИИ прочитал: 4" in final and "Не файлы (ссылки/страницы): 1" in final
    assert len(await db.get_files()) == 5
