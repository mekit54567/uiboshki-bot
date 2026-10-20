"""Файл по запросу в чате и «📥 Скачать» в WebApp."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update

import file_request
from tests.test_deeplinks import USER, DocSession

OPD = "Основы предпринимательской деятельности"
UCH = "Учетная деятельность на предприятии"
AD = "Анализ данных"
ANFHD = "Анализ и диагностика финансово-хозяйственной деятельности предприятия"
FILES = [{"id": i, "subject": s, "title": t, "category": c} for i, (s, t, c) in enumerate([
    (OPD, "Практическая работа 3", "practice"), (OPD, "Практическая работа 1", "practice"),
    (OPD, "ЛК1", "lecture"), (OPD, "ЛК3", "lecture"), (UCH, "Лекция 1-2", "lecture"),
    (AD, "Практика 13", "practice"), (AD, "Практика 3", "practice"), (ANFHD, "Лекция 5", "lecture"),
])]


@pytest.mark.parametrize("text,subjects,titles", [
    ("скинь практику 3 по основам предпр деят", [OPD], ["Практическая работа 3"]),
    ("нужна лекция 3 по основам предпр деят", [OPD], ["ЛК3"]),
    ("скинь лк1 по основам предпринимательской", [OPD], ["ЛК1"]),
    ("дай файлы по учетной деят", [UCH], ["Лекция 1-2"]),
    ("нужна практика 3 по анализу данных", [AD], ["Практика 3"]),      # не «Практика 13»
    ("скинь лекцию по предпр", [ANFHD, OPD, UCH], []),                         # ничья — переспросить
    # живой тест: «уч» решает между тремя «деят … предпр…»
    ("Скинь 1 лк по уч деят на предпрят", [UCH], ["Лекция 1-2"]),
])
def test_find(text, subjects, titles):
    assert file_request.is_request(text)
    found, items = file_request.find(text, FILES)
    assert found == subjects
    assert [f["title"] for f in items] == titles


@pytest.mark.parametrize("text", ["как решить задачу про анализ данных", "когда следующая пара", "дай совет"])
def test_not_a_request(text):
    assert not file_request.is_request(text)


async def _feed(db, text):
    from database import add_file
    from handlers.files import router as files_router
    from handlers.solver import router as solver_router
    for f in FILES:
        await add_file(f["title"], f["subject"], f"TG{f['id']}", f["title"] + ".pdf", 0, category=f["category"])
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=DocSession())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(files_router)
    dp.include_router(solver_router)
    try:
        msg = Message(message_id=5, date=0, chat=Chat(id=USER.id, type="private"), from_user=USER, text=text)
        await dp.feed_update(bot, Update(update_id=int(time.time()), message=msg))
    finally:
        files_router._parent_router = solver_router._parent_router = None
    return bot.session


@pytest.mark.asyncio
async def test_chat_request_sends_single_file(db, monkeypatch):
    import handlers.solver as solver

    async def no_ai(*a, **kw):
        raise AssertionError("просьба о файле не должна уходить к ИИ")

    monkeypatch.setattr(solver, "classify_intent", no_ai)
    session = await _feed(db, "скинь практику 3 по основам предпр деят")
    assert session.docs == [("SendDocument", "TG0", f"📄 <b>Практическая работа 3</b> ({OPD})")]


@pytest.mark.asyncio
async def test_chat_request_ambiguous_asks_subject(db, monkeypatch):
    import handlers.solver as solver
    monkeypatch.setattr(solver, "classify_intent", lambda *a: (_ for _ in ()).throw(AssertionError()))
    session = await _feed(db, "скинь лекцию по предпр")
    assert not session.docs
    assert any("По какому предмету" in t for t, _ in session.sent)


@pytest.mark.asyncio
async def test_download_link_is_signed_and_expires(db, monkeypatch):
    from types import SimpleNamespace
    from io import BytesIO
    from fastapi.testclient import TestClient
    import webapp.server as server
    from database import add_file
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    fid = await add_file("ЛК1", OPD, "TGF", "Основы ЛК1.pdf", 0)

    class FakeBot:
        async def get_file(self, file_id):
            assert file_id == "TGF"
            return SimpleNamespace(file_path="documents/file_1.pdf")

        async def download_file(self, path):
            return BytesIO(b"%PDF-1.4 test")

    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(server.deps, "WEBAPP_URL", "https://app.example")
    monkeypatch.setattr(server.deps, "tg_bot", lambda: FakeBot())
    c, headers = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    link = c.post(f"/api/files/{fid}/link", headers=headers).json()
    assert link["file_name"] == "Основы ЛК1.pdf"
    assert link["url"].startswith("https://app.example/dl/")
    path = link["url"].removeprefix("https://app.example")
    resp = c.get(path)                                   # без initData — по подписи
    assert resp.status_code == 200 and resp.content == b"%PDF-1.4 test"
    assert "attachment" in resp.headers["content-disposition"]
    # «Просмотр» в приложении: PDF — открыть в браузере, а не качать
    assert c.get(path + "&view=1").headers["content-disposition"].startswith("inline")
    assert c.get(path.replace("sig=", "sig=0")).status_code == 403
    monkeypatch.setattr(time, "time", lambda: 4102444800.0)  # 2100 год — ссылка протухла
    assert c.get(path).status_code == 403


@pytest.mark.asyncio
async def test_view_never_inlines_html(db, monkeypatch):
    # файл .html, открытый «Просмотром» на нашем адресе, исполнился бы как страница сайта
    from types import SimpleNamespace
    from io import BytesIO
    from fastapi.testclient import TestClient
    import webapp.server as server
    from database import add_file
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    fid = await add_file("страница", OPD, "TGH", "x.html", 0)

    class FakeBot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path="documents/x.html")

        async def download_file(self, path):
            return BytesIO(b"<script>alert(1)</script>")

    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(server.deps, "WEBAPP_URL", "https://app.example")
    monkeypatch.setattr(server.deps, "tg_bot", lambda: FakeBot())
    c = TestClient(server.app)
    url = c.post(f"/api/files/{fid}/link", headers={"X-Telegram-Init-Data": _make_init_data()}).json()["url"]
    resp = c.get(url.removeprefix("https://app.example") + "&view=1")
    assert resp.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_webapp_chat_answers_file_request_without_ai(db, monkeypatch):
    # живой тест: в чате WebApp «скинь 5 лк по уч деят» ИИ пересказал чужую лекцию
    from fastapi.testclient import TestClient
    import ai_solver
    import webapp.server as server
    from database import add_file
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    for f in FILES:
        await add_file(f["title"], f["subject"], f"TG{f['id']}", f["title"] + ".pdf", 0, category=f["category"])

    async def no_ai(*a, **kw):
        raise AssertionError("просьба о файле не должна уходить к ИИ")

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", no_ai)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, headers = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    data = c.post("/api/chat", headers=headers, json={"history": [
        {"role": "user", "content": "Скинь 1 лк по уч деят на предпрят"}], "subject": ""}).json()
    assert [f["title"] for f in data["files"]] == ["Лекция 1-2"]
    assert UCH in data["content"]


@pytest.mark.asyncio
async def test_webapp_chat_returns_lecture_sources(db, monkeypatch):
    # «📖 по: …» под ответом — какие лекции ушли ИИ, с id для перехода к файлу
    from fastapi.testclient import TestClient
    import ai_solver
    import webapp.server as server
    from database import add_file, save_file_text
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    lk = await add_file("ЛК1", UCH, "TGL", "lk1.pdf", 0, category="lecture")
    await save_file_text(lk, "Бухгалтерский учет: дебет и кредит, баланс предприятия.")
    seen = {}

    async def fake_chat(history, subject="", extra_system="", lectures=""):
        seen["lectures"] = lectures
        return {"content": seen.get("answer", "Дебет — левая сторона счёта [1]."), "reasoning": ""}

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", fake_chat)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, headers = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    data = c.post("/api/chat", headers=headers, json={"history": [
        {"role": "user", "content": "Что такое дебет?"}], "subject": UCH}).json()
    assert "=== [1] ЛК1 ===" in seen["lectures"]                           # целые лекции — тоже с номерами
    assert data["sources"] == [{"id": lk, "title": "ЛК1"}]
    # ИИ на лекцию не сослался (вопрос не по учёбе) — плашек нет (Никита 20.10)
    seen["answer"] = "Посмотреть погоду я не могу."
    data = c.post("/api/chat", headers=headers, json={"history": [
        {"role": "user", "content": "Что такое дебет?"}], "subject": UCH}).json()
    assert "sources" not in data
