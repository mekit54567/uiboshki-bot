import json
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import add_file, get_files, delete_file
from config import STAROSTA_ID

router = Router()

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),      KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),    KeyboardButton(text="➕ Дедлайн")],
    [KeyboardButton(text="🤖 Решить"),      KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="🗳 Голосование")],
    [KeyboardButton(text="❓ Вопрос анон"), KeyboardButton(text="🔔 Подписка"),    KeyboardButton(text="⚙️ Настройки")],
], resize_keyboard=True)


class UploadFile(StatesGroup):
    waiting_file    = State()
    waiting_title   = State()
    waiting_subject = State()


def subjects_keyboard(subjects: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура с предметами — используем индекс вместо названия."""
    buttons = []
    for i, s in enumerate(subjects):
        buttons.append([InlineKeyboardButton(text=s, callback_data=f"fsj:{i}")])
    buttons.append([InlineKeyboardButton(text="📋 Все файлы", callback_data="fsj:all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def files_keyboard(files: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for f in files[:30]:
        name = f["title"][:35]
        buttons.append([InlineKeyboardButton(text=f"📄 {name}", callback_data=f"fget:{f['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="fbk")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("files"))
@router.message(F.text == "📁 Файлы")
async def cmd_files(message: Message):
    files = await get_files()
    if not files:
        await message.answer("📁 Файлов пока нет.\n\nЗагрузить: /upload")
        return
    subjects = sorted(set(f["subject"] for f in files if f.get("subject")))
    await message.answer(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )


@router.callback_query(F.data.startswith("fsj:"))
async def files_by_subject(callback: CallbackQuery):
    idx = callback.data.split(":", 1)[1]
    all_files = await get_files()

    if idx == "all":
        files = all_files
        title = "Все файлы"
    else:
        subjects = sorted(set(f["subject"] for f in all_files if f.get("subject")))
        try:
            subject = subjects[int(idx)]
        except (ValueError, IndexError):
            await callback.answer("Ошибка")
            return
        files = [f for f in all_files if f.get("subject") == subject]
        title = subject

    if not files:
        await callback.answer("Файлов нет")
        return

    await callback.message.edit_text(
        f"📁 <b>{title}</b> ({len(files)} файлов):",
        parse_mode="HTML",
        reply_markup=files_keyboard(files)
    )


@router.callback_query(F.data == "fbk")
async def files_back(callback: CallbackQuery):
    files = await get_files()
    subjects = sorted(set(f["subject"] for f in files if f.get("subject")))
    await callback.message.edit_text(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )


@router.callback_query(F.data.startswith("fget:"))
async def send_file(callback: CallbackQuery, bot: Bot):
    fid = int(callback.data.split(":")[1])
    files = await get_files()
    f = next((x for x in files if x["id"] == fid), None)
    if not f:
        await callback.answer("Файл не найден")
        return
    try:
        await bot.send_document(
            callback.message.chat.id,
            f["file_id"],
            caption=f"📄 {f['title']}\n📚 {f['subject']}"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ── Загрузка файла вручную ────────────────────────────────────────────────────

@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    await state.set_state(UploadFile.waiting_file)
    await message.answer("📎 Прикрепи файл:", reply_markup=CANCEL_KB)


@router.message(UploadFile.waiting_file, F.document | F.photo)
async def receive_file(message: Message, state: FSMContext):
    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name or "файл"
    else:
        file_id   = message.photo[-1].file_id
        file_name = "фото"
    await state.update_data(file_id=file_id, file_name=file_name)
    await state.set_state(UploadFile.waiting_title)
    await message.answer("📝 Название файла?")


@router.message(UploadFile.waiting_title, F.text)
async def receive_title(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(UploadFile.waiting_subject)
    await message.answer("📚 Предмет? (или <i>–</i> пропустить)", parse_mode="HTML")


@router.message(UploadFile.waiting_subject, F.text)
async def receive_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    data    = await state.get_data()
    subject = "" if message.text.strip() == "–" else message.text.strip()
    await state.clear()
    fid = await add_file(data["title"], subject, data["file_id"], data["file_name"], message.from_user.id)
    await message.answer(
        f"✅ Файл сохранён! (ID: {fid})\n📄 <b>{data['title']}</b>",
        parse_mode="HTML", reply_markup=MAIN_KB
    )


@router.message(Command("delfile"))
async def cmd_delfile(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delfile ID")
        return
    await delete_file(int(parts[1]))
    await message.answer(f"🗑 Файл #{parts[1]} удалён.")


# ── Синхронизация файлов из локальной базы ────────────────────────────────────

@router.message(Command("syncfiles"))
async def cmd_syncfiles(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await message.answer(
        "📤 Пришли файл <b>files_export.json</b>",
        parse_mode="HTML"
    )


@router.message(F.document)
async def handle_sync_json(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        return
    if not message.document.file_name.endswith('.json'):
        return
    if 'export' not in message.document.file_name.lower() and 'files' not in message.document.file_name.lower():
        return

    wait = await message.answer("⏳ Синхронизирую файлы...")
    try:
        bot  = message.bot
        file = await bot.get_file(message.document.file_id)
        data = await bot.download_file(file.file_path)
        files = json.loads(data.read().decode('utf-8'))

        added = skipped = 0
        for f in files:
            if not f.get('file_id') or f.get('title') == 'Файл':
                skipped += 1
                continue
            existing = await get_files(f.get('subject', ''))
            if any(x['file_id'] == f['file_id'] for x in existing):
                skipped += 1
                continue
            await add_file(
                title=f['title'],
                subject=f.get('subject', ''),
                file_id=f['file_id'],
                file_name=f.get('file_name', ''),
                uploaded_by=0
            )
            added += 1

        await wait.edit_text(
            f"✅ Синхронизация завершена!\n\nДобавлено: {added}\nПропущено: {skipped}"
        )
    except Exception as e:
        await wait.edit_text(f"❌ Ошибка: {e}")
