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
