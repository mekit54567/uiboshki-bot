"""Загрузка файлов старостой и участниками: /upload, пачкой, предмет один раз."""

import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
)

from database import add_file, get_files
from kapibara.bot.keyboards import MAIN_KB, CANCEL_KB
from kapibara.core.utils import esc
from kapibara.features.lectures.names import title_from_filename

router = Router()


class UploadFile(StatesGroup):
    waiting_subject  = State()
    waiting_category = State()
    waiting_file     = State()


# ── Загрузка файлов: пачкой, предмет выбирается один раз ─────────────────────
# Раньше /upload принимал ровно один файл и спрашивал его название и предмет
# текстом — залить лекции за семестр было мучением. Теперь: выбрал предмет
# (кнопки — настоящие названия из расписания группы и уже известные по
# файлам), дальше пересылаешь сколько угодно файлов подряд (хоть альбомом
# из чата группы). Название — из имени файла, текст PDF/DOCX/PPTX/TXT сразу
# уходит в контекст ИИ (решалка по лекциям). Прогресс — одним сообщением,
# которое обновляется, а не ответом на каждый файл.

UPLOAD_DONE = "✅ Готово"
UPLOAD_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=UPLOAD_DONE), KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)
_upload_locks: dict[int, asyncio.Lock] = {}


async def _upload_subjects() -> list[str]:
    from kapibara.features.schedule.parser import get_group_subjects
    known = {f["subject"] for f in await get_files() if f.get("subject")}
    return sorted(known | set(await get_group_subjects()))


def _upload_subjects_kb(subjects: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=s[:60], callback_data=f"upsj:{i}")] for i, s in enumerate(subjects[:40])]
    rows.append([InlineKeyboardButton(text="📂 Без предмета", callback_data="upsj:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    subjects = await _upload_subjects()
    await state.set_state(UploadFile.waiting_subject)
    await state.update_data(upload_subjects=subjects)
    await message.answer(
        "📤 <b>Загрузка файлов</b>\n\n"
        "Для какого предмета? Выбери кнопкой или напиши название сам.\n"
        "Дальше можно прислать сразу много файлов — хоть переслать пачкой из чата группы.",
        parse_mode="HTML", reply_markup=_upload_subjects_kb(subjects),
    )
    await message.answer("Отменить — «❌ Отмена».", reply_markup=CANCEL_KB)


async def _ask_category(target: Message, state: FSMContext, subject: str):
    """Второй шаг: тип файлов (лекции/практики/КР/…) — или «определить по
    названию» для смешанной пачки."""
    from kapibara.core.categories import CATEGORIES
    await state.update_data(subject=subject)
    await state.set_state(UploadFile.waiting_category)
    rows = [[InlineKeyboardButton(text=label, callback_data=f"upct:{key}")] for key, label in CATEGORIES]
    rows.insert(0, [InlineKeyboardButton(text="✨ Определить по названию каждого файла", callback_data="upct:auto")])
    where = f"«{esc(subject)}»" if subject else "без предмета"
    await target.answer(f"📚 {where}\n\nЧто загружаешь?", parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(UploadFile.waiting_category, F.data.startswith("upct:"))
async def upload_pick_category(callback: CallbackQuery, state: FSMContext):
    from kapibara.core.categories import LABELS
    key = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_collecting(callback.message, state, (await state.get_data()).get("subject", ""),
                            key if key in LABELS else None)


async def _start_collecting(target: Message, state: FSMContext, subject: str, category: str | None = None):
    from kapibara.core.categories import LABELS
    await state.set_state(UploadFile.waiting_file)
    await state.update_data(subject=subject, category=category, added=0, with_text=0, dupes=0, status_id=None)
    where = f"в «{esc(subject)}»" if subject else "без предмета"
    if category:
        where += f" → {LABELS[category]}"
    await target.answer(
        f"📥 Кидай файлы {where} — сколько угодно, можно пачкой.\n"
        f"PDF, DOCX, PPTX и TXT я ещё и прочитаю, чтобы ИИ отвечал по лекциям.\n\n"
        f"Закончил — жми «{UPLOAD_DONE}».",
        parse_mode="HTML", reply_markup=UPLOAD_KB,
    )


@router.callback_query(UploadFile.waiting_subject, F.data.startswith("upsj:"))
async def upload_pick_subject(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    subjects = (await state.get_data()).get("upload_subjects", [])
    subject = "" if key == "none" or not key.isdigit() or int(key) >= len(subjects) else subjects[int(key)]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_category(callback.message, state, subject)


@router.message(UploadFile.waiting_subject, F.text)
async def upload_type_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await _ask_category(message, state, message.text.strip()[:80])


@router.message(UploadFile.waiting_category, F.text)
async def upload_category_text(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await message.answer("Выбери тип кнопкой выше — или сразу кидай файлы, тип определю по названию.")


# Файлы, присланные сразу после предмета (не нажав тип), тоже принимаем —
# с типом по названию: пересылать пачку и потом обнаружить, что ничего не
# сохранилось, обиднее, чем лишний раз не выбрать кнопку.
@router.message(StateFilter(UploadFile.waiting_file, UploadFile.waiting_category), F.document | F.photo)
async def receive_file(message: Message, state: FSMContext):
    # Альбом из 10 файлов — это 10 апдейтов почти одновременно: без замка
    # счётчики в FSM и одно сообщение-прогресс перетирали бы друг друга.
    lock = _upload_locks.setdefault(message.from_user.id, asyncio.Lock())
    async with lock:
        if await state.get_state() == UploadFile.waiting_category.state:
            await state.set_state(UploadFile.waiting_file)
            await state.update_data(category=None, added=0, with_text=0, dupes=0, status_id=None)
            await message.answer(f"✨ Тип определю по названию каждого файла. Закончишь — жми «{UPLOAD_DONE}».",
                                 reply_markup=UPLOAD_KB)
        data = await state.get_data()
        subject = data.get("subject", "")
        if message.document:
            tg_file_id = message.document.file_id
            file_name = message.document.file_name or "файл"
        else:
            tg_file_id = message.photo[-1].file_id
            # По этому имени фото и отдаётся как фото (handlers.start.send_stored_file)
            file_name = f"фото_{message.message_id}.jpg"

        existing = {(f.get("file_name"), f.get("subject") or "") for f in await get_files(subject or None)}
        if message.document and (file_name, subject) in existing:
            data["dupes"] = data.get("dupes", 0) + 1
        else:
            fid = await add_file(title_from_filename(file_name), subject, tg_file_id, file_name,
                                 message.from_user.id, category=data.get("category"))
            from kapibara.features.lectures.text import extract_and_save
            if await extract_and_save(message.bot, fid, tg_file_id, file_name):
                data["with_text"] = data.get("with_text", 0) + 1
            data["added"] = data.get("added", 0) + 1

        text = (f"📥 Загружено: <b>{data['added']}</b>"
                f" · 📖 прочитано для ИИ: <b>{data.get('with_text', 0)}</b>"
                + (f" · ♻️ уже были: {data['dupes']}" if data.get("dupes") else ""))
        status_id = data.get("status_id")
        try:
            if status_id:
                await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=status_id, parse_mode="HTML")
            else:
                status_id = (await message.answer(text, parse_mode="HTML")).message_id
        except Exception:
            status_id = (await message.answer(text, parse_mode="HTML")).message_id
        await state.update_data(added=data["added"], with_text=data.get("with_text", 0),
                                dupes=data.get("dupes", 0), status_id=status_id)


@router.message(UploadFile.waiting_file, F.text)
async def upload_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if message.text != UPLOAD_DONE:
        await message.answer("Загрузка закончена.", reply_markup=MAIN_KB)
        return
    added, with_text = data.get("added", 0), data.get("with_text", 0)
    if not added:
        await message.answer("Файлов не было — ничего не сохранил.", reply_markup=MAIN_KB)
        return
    subject = data.get("subject", "")
    lecture = (f"\n📖 {with_text} из них — в контексте ИИ: /solve_lectures"
               + (f" → «{esc(subject)}»" if subject else "")) if with_text else ""
    await message.answer(
        f"✅ Сохранено файлов: <b>{added}</b>" + (f" в «{esc(subject)}»" if subject else "") + lecture +
        "\n\nНайти: /files",
        parse_mode="HTML", reply_markup=MAIN_KB,
    )
