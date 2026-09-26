"""
/upload пачкой: предмет один раз, дальше сколько угодно файлов подряд
(в т.ч. альбомом), название — из имени файла, текст — в контекст ИИ,
прогресс — одним сообщением, дубли пропускаются.
"""
import time

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Document, Message, Update, User

from handlers.files import title_from_filename
from tests.test_solver_render import RecordingSession

USER = User(id=222, is_bot=False, first_name="Alice")
CHAT = Chat(id=222, type="private")


@pytest.mark.parametrize("name,title", [
    ("Лекция_3_Бизнес-анализ.pdf", "Лекция 3 Бизнес-анализ"),
    ("  Методичка  по  ОБА.docx", "Методичка по ОБА"),
    ("notes.txt", "notes"),
    ("", "Файл"),
])
def test_title_from_filename(name, title):
    assert title_from_filename(name) == title


@pytest.fixture
def bot():
    return Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=RecordingSession())


@pytest.fixture
def dp():
    from handlers.files import router
    d = Dispatcher(storage=MemoryStorage())
    d.include_router(router)
    yield d
    router._parent_router = None


_mid = [1000]


async def _feed(dp, bot, **kw):
    _mid[0] += 1
    msg = Message(message_id=_mid[0], date=0, chat=CHAT, from_user=USER, **kw)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9 + _mid[0], message=msg))


def _doc(name, fid):
    return Document(file_id=fid, file_unique_id=fid + "u", file_name=name)


@pytest.mark.asyncio
async def test_batch_upload_saves_files_reads_text_and_skips_dupes(db, dp, bot, monkeypatch):
    import schedule_parser

    async def no_schedule():
        return []

    monkeypatch.setattr(schedule_parser, "get_group_subjects", no_schedule)

    await _feed(dp, bot, text="/upload")
    await _feed(dp, bot, text="Анализ данных")                   # предмет текстом
    await _feed(dp, bot, document=_doc("Лекция_1.txt", "f1"))
    await _feed(dp, bot, document=_doc("Практика 2.pdf", "f2"))  # fake-байты — не PDF, текста не будет
    await _feed(dp, bot, document=_doc("Лекция_1.txt", "f3"))    # тот же файл второй раз
    await _feed(dp, bot, text="✅ Готово")

    files = await db.get_files("Анализ данных")
    assert sorted(f["title"] for f in files) == ["Лекция 1", "Практика 2"]
    assert await db.get_subjects_with_lecture_text() == ["Анализ данных"]
    assert "fake-image-bytes" in await db.get_subject_lecture_context("Анализ данных")

    texts = [t for t, _ in bot.session.sent]
    progress = [t for t in bot.session.sent_texts if "Загружено" in t[1]]
    assert progress[-1][1] == "📥 Загружено: <b>2</b> · 📖 прочитано для ИИ: <b>1</b> · ♻️ уже были: 1"
    assert sum("Загружено" in t for t in texts) == 1  # одно сообщение, дальше — правки
    assert "Сохранено файлов: <b>2</b>" in texts[-1]
    # тип не выбран кнопкой — определён по названию каждого файла
    assert {f["title"]: f["category"] for f in files} == {"Лекция 1": "lecture", "Практика 2": "practice"}


# ── типы файлов внутри предмета ──────────────────────────────────────────────

@pytest.mark.parametrize("names,category", [
    (("Лекция 3. Бизнес-анализ", "lec3.pdf"), "lecture"),
    (("Презентация к теме 2",), "lecture"),
    (("ПР_5 Сети",), "practice"),
    (("Лабораторная работа №2",), "practice"),
    (("КР 1 вариант 3",), "control"),
    (("Тест по главе 4",), "control"),
    (("Методические указания к практике",), "method"),   # методичка, а не практика
    (("Вопросы к экзамену по лекциям",), "exam"),         # экзамен, а не лекция
    (("Зачёт 2025",), "exam"),
    (("scan_0001", "IMG_22.jpg"), "other"),
    (("Криптография",), "other"),                          # «кр» внутри слова — не КР
    (("Проект",), "other"),                                # «пр» без номера — не практика
])
def test_detect_category(names, category):
    from file_categories import detect_category
    assert detect_category(*names) == category


class _Session(RecordingSession):
    async def make_request(self, bot, method, timeout=None):
        if type(method).__name__ == "EditMessageReplyMarkup":
            return True
        return await super().make_request(bot, method, timeout)


async def _click(dp, bot, data):
    from aiogram.types import CallbackQuery
    _mid[0] += 1
    msg = Message(message_id=_mid[0], date=0, chat=CHAT, text="…")
    cb = CallbackQuery(id=str(_mid[0]), from_user=USER, chat_instance="c", data=data, message=msg)
    await dp.feed_update(bot, Update(update_id=int(time.time() * 1000000) % 10**9 + _mid[0], callback_query=cb))


@pytest.mark.asyncio
async def test_upload_with_picked_category(db, dp, monkeypatch):
    import schedule_parser

    async def subjects():
        return ["Анализ данных"]

    monkeypatch.setattr(schedule_parser, "get_group_subjects", subjects)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=_Session())

    await _feed(dp, bot, text="/upload")
    await _click(dp, bot, "upsj:0")
    assert "Что загружаешь?" in bot.session.sent[-1][0]
    await _click(dp, bot, "upct:control")
    assert "📝 КР и тесты" in bot.session.sent[-1][0]
    await _feed(dp, bot, document=_doc("вариант_7.pdf", "k1"))      # по названию был бы «другое»
    await _feed(dp, bot, text="✅ Готово")

    [f] = await db.get_files("Анализ данных")
    assert f["category"] == "control"


@pytest.mark.asyncio
async def test_files_browse_subject_then_category(db, dp, bot):
    await db.add_file("Лекция 1", "ОБА", "a", "l1.pdf", 1)
    await db.add_file("Лекция 2", "ОБА", "b", "l2.pdf", 1)
    await db.add_file("ПР 1", "ОБА", "c", "p1.pdf", 1)
    await db.add_file("Лекция 1", "Сети", "d", "s1.pdf", 1)

    await _click(dp, bot, "fsj:0")                                  # ОБА: два типа — сначала выбор типа
    menu = bot.session.sent_texts[-1][1]
    assert "Что нужно?" in menu
    await _click(dp, bot, "fct:0:lecture")
    assert bot.session.sent_texts[-1][1] == "📁 <b>ОБА</b> → 📓 Лекции (2):"

    await _click(dp, bot, "fsj:1")                                  # Сети: один тип — сразу файлы
    assert bot.session.sent_texts[-1][1] == "📁 <b>Сети</b> (1):"


@pytest.mark.asyncio
async def test_files_list_pages_instead_of_dropping(db, dp, bot):
    # после выгрузки из СДО лекций у предмета бывает больше, чем влезало (30)
    for i in range(30):
        await db.add_file(f"Лекция {i + 1}", "ОБА", f"x{i}", f"l{i}.pdf", 1)
    await _click(dp, bot, "fsj:0")                                  # один тип — сразу файлы, стр. 1
    assert bot.session.sent_texts[-1][1] == "📁 <b>ОБА</b> (30) · стр. 1/2:"
    await _click(dp, bot, "fct:0:*:1")
    assert bot.session.sent_texts[-1][1] == "📁 <b>ОБА</b> → 📋 Все файлы (30) · стр. 2/2:"
    await _click(dp, bot, "fct:0:lecture:9")                        # страница за краем — последняя
    assert bot.session.sent_texts[-1][1] == "📁 <b>ОБА</b> → 📓 Лекции (30) · стр. 2/2:"


def test_files_keyboard_pages():
    from handlers.files import files_keyboard
    files = [{"id": i, "title": f"Файл {i}"} for i in range(30)]
    first = files_keyboard(files, back="fsj:0", page=0, page_cb="fct:0:*").inline_keyboard
    assert len(first) == 25 + 2 and [b.callback_data for b in first[-2]] == ["fct:0:*:1"]
    second = files_keyboard(files, back="fsj:0", page=1, page_cb="fct:0:*").inline_keyboard
    assert len(second) == 5 + 2 and [b.callback_data for b in second[-2]] == ["fct:0:*:0"]
    assert second[-1][0].callback_data == "fsj:0"
    assert len(files_keyboard(files[:3]).inline_keyboard) == 4           # одна страница — без стрелок
