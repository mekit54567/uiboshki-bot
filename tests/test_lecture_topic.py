"""Тема лекции из текста файла (владелец, 09.10: «тема лекции в файлах точно
есть, её бы писать под „Лекция 1“»): lecture_topic, file_names.text_titles,
/tidyfiles с пометкой 📄 и кнопкой «без тем из текста», head/topic в API."""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from kapibara.features.lectures.names import split_title, text_titles, tidy_titles
from kapibara.features.lectures.topic import topic_from_text
from tests.conftest import STAROSTA_ID

HEADER = ("МИНОБРНАУКИ РОССИИ\nФедеральное государственное бюджетное образовательное учреждение\n"
          "высшего образования\n«МИРЭА – Российский технологический университет»\nРТУ МИРЭА\n"
          "Институт технологий управления\nКафедра корпоративной информатики\n")


@pytest.mark.parametrize("text, subject, topic", [
    # титульный: шапка вуза, «Лекция 8», тема в две строки, преподаватель, год
    (HEADER + "Лекция 8\nУправление архитектурой:\nдорожная карта и governance\n"
     "Преподаватель: к.э.н., доцент Иванов И.И.\nМосква 2025", "Архитектура предприятия",
     "Управление архитектурой: дорожная карта и governance"),
    # название предмета перед лекцией — не тема
    ("Архитектура предприятия\nЛекция 8. Roadmap и Governance\nИванов Иван Иванович",
     "Архитектура предприятия", "Roadmap и Governance"),
    ("Основы предпринимательской деятельности\nЛекция 2\nОсновы предпринимательской деятельности\n"
     "Предпринимательство как вид деятельности\n2025", "Основы предпринимательской деятельности",
     "Предпринимательство как вид деятельности"),
    # «Тема 3. …» капсом — обычными буквами, сокращения остаются
    ("ТЕМА 3. УПРАВЛЕНИЕ РИСКАМИ В ИТ-ПРОЕКТАХ\nПлан лекции:\n1. Понятие риска", "Управление ИТ",
     "Управление рисками в ИТ-проектах"),
    ("Дисциплина «Архитектура предприятия»\nТема: Бизнес-архитектура\nВопросы:\n1.", "Архитектура предприятия",
     "Бизнес-архитектура"),
    ("Лекция 1.\nПредмет и задачи курса\nЦели и задачи:", "Матан", "Предмет и задачи курса"),
    ("Лекция 3. Тема: Классы и объекты\n", "ООП", "Классы и объекты"),
    # без «Лекция» — первая строка-заголовок после шапки
    ("РТУ МИРЭА\nПроцессная архитектура\nпредприятия\nДоцент кафедры КИ\nПетров П.П.",
     "Архитектура предприятия", "Процессная архитектура предприятия"),
    ("1\nЛекция\nВведение в тематическое моделирование\n", "ML", "Введение в тематическое моделирование"),
    # первая строка — предложение из текста лекции: не гадаем
    ("Рассмотрим основные понятия курса. Предприятие представляет собой систему, которая "
     "состоит из многих частей.\nДалее", "Архитектура предприятия", ""),
    ("Иванов Иван Иванович\nк.т.н., доцент\nМосква 2025", "Матан", ""),
    ("", "Матан", ""),
])
def test_topic_from_text(text, subject, topic):
    assert topic_from_text(text, subject) == topic


# Начало текста настоящих лекций группы (файлы владельца 09.10, ФИО и почты
# заменены): как его отдаёт file_text — PDF с «бизнес -анализа», капс,
# шапка в таблице, план курса со всеми лекциями на втором слайде.
REAL = [
    ("Институт технологий управления\nВ М Е СТ Е СО З Д А Ё М БУД У Щ Е ЕАНАЛИЗ ДАННЫХ\n"
     "Лекция 5. Регрессионный анализ и\nмодели временных рядов\n"
     "Иванова Ольга Ивановна, кандидат экономических наук,\nдоцент кафедры ИТГУ\ne-mail: ivanova@mirea.ru\n"
     "2Лекция 5. Регрессионный анализ и модели временных рядов\nСодержание лекции\n",
     "Анализ данных", 5, "Регрессионный анализ и модели временных рядов"),
    ("ЛЕКЦИЯ 7\nИсходная и целевая архитектуры\nGap Analysis, Fit-Gap, воздействие, альтернативы и приоритизация\n"
     "Курс «Архитектура предприятия» • 2026/2027\n07\nEA\n7.1 • ЛЕКЦИЯ 7\n",
     "Архитектура предприятия", 7, "Исходная и целевая архитектуры"),
    ("1\nДИСЦИПЛИНА Основы бизнес -анализа в ИТ -сфере\nИНСТИТУТ технологий управления\nКАФЕДРА\n"
     "информационных технологий в государственном\nуправлении\nВИД УЧЕБНОГО Лекция 6\nМАТЕРИАЛА\n"
     "ПРЕПОДАВАТЕЛЬ Петрова Ирина Петровна\n(фамилия, имя, отчество)\nСЕМЕСТР 5, 202 6/2027 учебный год\n2\n"
     "Лекция 6. УПРАВЛЕНИЕ ПРОЦЕССОМ БИЗНЕС -АНАЛИЗА\nПлан лекции\n6.1. Подходы к бизнес -анализу.\n",
     "Основы бизнес-анализа в ИТ-сфере", 6, "Управление процессом бизнес-анализа"),
    ("ИТГУ\n1\nПЛАН КУРСА\nЛекция 1. Основы анализа финансово-хозяйственной деятельности организации\n"
     "Лекция 2. Основные концепции финансового менеджмента. Управление капиталом\nЛекция 3. Финансовый анализ\n"
     "Лекция 4. Система показателей оценки финансового состояния организации (1)\n2\n"
     "Литература, необходимая для освоения дисциплины\n",
     "АФХДП", 1, "Основы анализа финансово-хозяйственной деятельности организации"),
    ("ДИСЦИПЛИНА МОДЕЛИРОВАНИЕ БИЗНЕС -ПРОЦЕССОВ\nИНСТИТУТ ТЕХНОЛОГИЙ УПРАВЛЕНИЯ\n"
     "КАФЕДРАИНФОРМАЦИОННЫХ ТЕХНОЛОГИЙ В\nГОСУДАРСТВЕННОМ УПРАВЛЕНИИ\nВИД УЧЕБНОГО\n"
     "МАТЕРИАЛА ЛЕКЦИОННЫЕ МАТЕРИАЛЫ\nПРЕПОДАВАТЕЛЬ ПЕТРОВ АЛЕКСЕЙ АЛЕКСАНДРОВИЧ\n"
     "СЕМЕСТР 5 СЕМЕСТР ОБУЧЕНИЯ, 2026/202 7УЧЕБНЫЙ ГОД\nOnline -edu.mirea.ruМОДЕЛИРОВАНИЕ\nБИЗНЕС -ПРОЦЕССОВ\n"
     "К.Э.Н, ДОЦ., ДОЦ. ПЕТРОВ АЛЕКСЕЙ АЛЕКСАНДРОВИЧ\nE-MAIL: PETROV@MIREA.RU\nЛЕКЦИЯ 8\nКЛАССИФИКАЦИЯ ПРОЦЕССОВ\n3\n"
     "Основные вопросы лекции:\n",
     "Моделирование бизнес-процессов", 8, "Классификация процессов"),
]


@pytest.mark.parametrize("text, subject, number, topic", REAL)
def test_real_lectures(text, subject, number, topic):
    assert topic_from_text(text, subject, number) == topic


def test_course_plan_gives_own_lecture_or_nothing():
    plan = REAL[3][0]
    assert topic_from_text(plan, "АФХДП", 3) == "Финансовый анализ"
    assert topic_from_text(plan, "АФХДП") == ""                # чей номер — неизвестно: не гадаем
    assert topic_from_text(plan, "АФХДП", 8) == ""


def test_split_title():
    assert split_title("Лекция 8. Управление рисками") == ("Лекция 8", "Управление рисками")
    assert split_title("Практика 5–6") == ("Практика 5–6", "")
    assert split_title("Тема 2, лекция 1. Методы контроля") == ("Тема 2, лекция 1", "Методы контроля")
    assert split_title("Вопросы к экзамену") == ("", "")


def _f(i, title, subject, file_name, category=None):
    return {"id": i, "title": title, "subject": subject, "file_name": file_name, "category": category}


def test_pdf_gets_topic_of_its_presentation_and_text():
    # первый скрин владельца: «Лекция N» (PDF) и «Лекция N. Презентация» (PPTX)
    s = "Основы предпринимательской деятельности"
    files = [_f(1, "Лекция 1", s, "l1.pdf"), _f(2, "Лекция 1. Презентация", s, "p1.pptx"),
             _f(3, "Лекция 2", s, "l2.pdf"), _f(4, "Лекция 3. Формы собственности", s, "l3.pdf")]
    texts = {2: HEADER + s + "\nЛекция 1\nПредпринимательство как вид деятельности\n",
             3: "Лекция 2\nПредпринимательская идея\n", 4: "Лекция 3\nЧто-то другое\n"}
    out = text_titles(files, tidy_titles(files), texts)
    assert out == {1: "Лекция 1. Предпринимательство как вид деятельности",
                   2: "Лекция 1. Предпринимательство как вид деятельности",
                   3: "Лекция 2. Предпринимательская идея"}              # тема из названия не трогается


def test_pdf_borrows_topic_from_presentation_name():
    # второй скрин: «Lektsiya 05 Protsessnaya arhitektura» (PPTX) и «Лекция 5» (PDF)
    s = "Архитектура предприятия"
    files = [_f(1, "Lektsiya 05 Protsessnaya arhitektura", s, "l5.pptx"), _f(2, "Лекция 5", s, "l5.pdf"),
             _f(3, "Лекция 6", s, "l6.pdf")]
    names = tidy_titles(files)
    out = text_titles(files, names, {2: "Лекция 5\nСовсем не то\n"})
    assert names[1] == out[2] == "Лекция 5. Процессная архитектура"     # из названия пары, не из текста
    assert 3 not in out                                                  # ни текста, ни пары — без темы


def test_course_name_on_every_title_slide_is_not_a_topic():
    # предмет в базе назван коротко, а на всех титульных — полное название курса
    files = [_f(i, f"Лекция {i}", "ОПД", f"l{i}.pdf") for i in range(1, 5)]
    texts = {i: f"Основы предпринимательской деятельности\nЛекция {i}\n" for i in range(1, 5)}
    assert text_titles(files, tidy_titles(files), texts) == {}


def test_tidy_titles_is_idempotent_with_topics():
    files = [_f(1, "Лекция 8. Управление рисками", "ИБ", "l8.pdf")]
    assert tidy_titles(files) == {} and text_titles(files, {}, {1: "Лекция 8\nДругое\n"}) == {}


# ── /tidyfiles: 📄 у тем из текста, «Без 📄» переименовывает только по названиям ──

STAROSTA = User(id=STAROSTA_ID, is_bot=False, first_name="Starosta")


@pytest.fixture
def tidy_dp():
    from handlers.files import router                      # /tidyfiles — во вложенном files_admin
    d = Dispatcher(storage=MemoryStorage())
    d.include_router(router)
    yield d
    router._parent_router = None


async def _seed(db):
    s = "Основы предпринимательской деятельности"
    a = await db.add_file("ЛК3_бизнес", "ООП", "f1", "lk3.pdf", STAROSTA_ID)
    b = await db.add_file("Лекция 1", s, "f2", "l1.pdf", STAROSTA_ID)
    await db.save_file_text(b, HEADER + "Лекция 1\nПредпринимательство как вид деятельности\n" + "текст " * 50)
    return a, b


@pytest.mark.asyncio
async def test_tidyfiles_marks_text_topics_and_names_only_button(db, tidy_dp):
    from tests.test_solver_render import RecordingSession

    class Session(RecordingSession):
        async def make_request(self, bot, method, timeout=None):
            if type(method).__name__ in ("EditMessageReplyMarkup", "AnswerCallbackQuery"):
                return True
            return await super().make_request(bot, method, timeout)

    a, b = await _seed(db)
    session = Session()
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=session)
    msg = Message(message_id=1, date=0, chat=Chat(id=STAROSTA_ID, type="private"), from_user=STAROSTA,
                  text="/tidyfiles")
    await tidy_dp.feed_update(bot, Update(update_id=int(time.time()) % 10**9, message=msg))
    text = session.sent[-1][0]
    assert "📄 Лекция 1 → <b>Лекция 1. Предпринимательство как вид деятельности</b>" in text
    assert "• ЛК3_бизнес → <b>Лекция 3. Бизнес</b>" in text

    cb = CallbackQuery(id="1", from_user=STAROSTA, chat_instance="c", data="tidy:names", message=msg)
    await tidy_dp.feed_update(bot, Update(update_id=int(time.time()) % 10**9 + 1, callback_query=cb))
    titles = {f["id"]: f["title"] for f in await db.get_files()}
    assert titles == {a: "Лекция 3. Бизнес", b: "Лекция 1"}             # тема из текста не применилась

    cb = CallbackQuery(id="2", from_user=STAROSTA, chat_instance="c", data="tidy:yes", message=msg)
    await tidy_dp.feed_update(bot, Update(update_id=int(time.time()) % 10**9 + 2, callback_query=cb))
    titles = {f["id"]: f["title"] for f in await db.get_files()}
    assert titles[b] == "Лекция 1. Предпринимательство как вид деятельности"
    assert await db.undo_file_renames() == 2


@pytest.mark.asyncio
async def test_api_files_gives_number_and_topic_separately(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await db.add_file("Лекция 8. Управление рисками", "ИБ", "f1", "l8.pdf", STAROSTA_ID)
    await db.add_file("Лекция 1. Презентация", "ИБ", "f2", "p1.pptx", STAROSTA_ID)
    await db.add_file("Вопросы к экзамену", "ИБ", "f3", "q.docx", STAROSTA_ID)
    h = {"X-Telegram-Init-Data": _make_init_data(user={"id": STAROSTA_ID, "first_name": "S"})}
    items = {f["title"]: f for f in TestClient(server.app).get("/api/files", headers=h).json()["items"]}
    assert (items["Лекция 8. Управление рисками"]["head"], items["Лекция 8. Управление рисками"]["topic"]) == \
        ("Лекция 8", "Управление рисками")
    assert (items["Лекция 1. Презентация"]["head"], items["Лекция 1. Презентация"]["topic"]) == ("Лекция 1", "")
    assert (items["Вопросы к экзамену"]["head"], items["Вопросы к экзамену"]["topic"]) == ("Вопросы к экзамену", "")
