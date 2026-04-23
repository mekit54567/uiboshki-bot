from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import add_file, get_files, delete_file

router = Router()

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)


class UploadFile(StatesGroup):
    waiting_file    = State()
    waiting_title   = State()
    waiting_subject = State()


@router.message(Command("files"))
@router.message(F.text == "📁 Файлы")
async def cmd_files(message: Message):
    files = await get_files()
    if not files:
        await message.answer("📁 Файлов пока нет.\n\nЗагрузить: /upload")
        return

    lines = ["📁 <b>Файлы группы</b>\n━━━━━━━━━━━━━━━━━━━\n"]
    for f in files:
        subj = f" [{f['subject']}]" if f.get("subject") else ""
        lines.append(f"[{f['id']}] 📄 <b>{f['title']}</b>{subj}")

    lines.append("\nОтправить файл: /getfile ID\nУдалить: /delfile ID\nЗагрузить: /upload")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    await state.set_state(UploadFile.waiting_file)
    await message.answer("📎 Прикрепи файл (документ, PDF, фото):", reply_markup=CANCEL_KB)


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
    await message.answer("📝 Название файла? (например: <i>Методичка по алгоритмам</i>)", parse_mode="HTML")


@router.message(UploadFile.waiting_title, F.text)
async def receive_title(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(UploadFile.waiting_subject)
    await message.answer("📚 Предмет? (или <i>–</i> пропустить)", parse_mode="HTML")


@router.message(UploadFile.waiting_subject, F.text)
async def receive_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.")
        return
    data    = await state.get_data()
    subject = "" if message.text.strip() == "–" else message.text.strip()
    await state.clear()

    fid = await add_file(data["title"], subject, data["file_id"], data["file_name"], message.from_user.id)
    await message.answer(
        f"✅ Файл сохранён! (ID: {fid})\n\n"
        f"📄 <b>{data['title']}</b>\n"
        f"Получить: /getfile {fid}",
        parse_mode="HTML"
    )


@router.message(Command("getfile"))
async def cmd_getfile(message: Message, bot: Bot):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /getfile ID")
        return
    fid   = int(parts[1])
    files = await get_files()
    f     = next((x for x in files if x["id"] == fid), None)
    if not f:
        await message.answer("❌ Файл не найден.")
        return
    try:
        await bot.send_document(message.chat.id, f["file_id"], caption=f"📄 {f['title']}")
    except Exception:
        await bot.send_photo(message.chat.id, f["file_id"], caption=f"📄 {f['title']}")


@router.message(Command("delfile"))
async def cmd_delfile(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delfile ID")
        return
    await delete_file(int(parts[1]))
    await message.answer(f"🗑 Файл #{parts[1]} удалён.")
