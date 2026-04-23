import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from groq_solver import solve_text, solve_image, SUBJECTS
from database import upsert_user, add_solver_history, get_solver_history

logger = logging.getLogger(__name__)
router = Router()

BUTTON_TEXTS = {
    "📅 Сегодня","📆 Неделя","🌅 Завтра","⏭ Следующая",
    "📋 Дедлайны","➕ Дедлайн","🤖 Решить","📁 Файлы",
    "🗳 Голосование","❓ Вопрос анон","🔔 Подписка","⚙️ Настройки","❌ Отмена",
}

SUBJECT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SUBJECTS],
    resize_keyboard=True, one_time_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)


class SolverState(StatesGroup):
    choose_subject = State()
    waiting_task   = State()


@router.message(Command("solve"))
@router.message(F.text == "🤖 Решить")
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await state.set_state(SolverState.choose_subject)
    await message.answer("📚 Выбери предмет:", reply_markup=SUBJECT_KB)


@router.message(SolverState.choose_subject, F.text)
async def choose_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(SolverState.waiting_task)
    await message.answer(
        f"✅ Предмет: <b>{message.text}</b>\n\n"
        "Пришли задачу — текстом или фото 📸",
        parse_mode="HTML", reply_markup=CANCEL_KB
    )


@router.message(Command("cancel"), SolverState.waiting_task)
@router.message(Command("cancel"), SolverState.choose_subject)
async def cancel_solve(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(SolverState.waiting_task, F.text)
async def handle_task_text(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    await state.clear()
    wait = await message.answer("🧠 Решаю, секунду...")
    try:
        answer = await solve_text(message.text, subject)
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer, subject)
        for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(SolverState.waiting_task, F.photo)
async def handle_task_photo(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    subject = data.get("subject", "")
    await state.clear()
    wait = await message.answer("🧠 Анализирую фото...")
    try:
        photo      = message.photo[-1]
        file       = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        answer     = await solve_image(file_bytes.read(), subject=subject)
        await wait.delete()
        await add_solver_history(message.from_user.id, "[фото]", answer, subject)
        for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(Command("history"))
async def cmd_history(message: Message):
    history = await get_solver_history(message.from_user.id, limit=5)
    if not history:
        await message.answer("📭 История пустая — ещё не решал задачи.")
        return
    lines = ["📜 <b>Последние 5 задач:</b>\n"]
    for i, h in enumerate(history, 1):
        subj = f" [{h['subject']}]" if h.get("subject") else ""
        task = h["task_text"][:80] + ("..." if len(h["task_text"]) > 80 else "")
        lines.append(f"{i}.{subj} {task}\n   <i>{h['created_at'][:10]}</i>")
    await message.answer("\n\n".join(lines), parse_mode="HTML")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext):
    if message.text in BUTTON_TEXTS:
        return
    if await state.get_state() is not None:
        return
    if len(message.text) < 20:
        return
    wait = await message.answer("🤖 Похоже задание — решаю...")
    try:
        answer = await solve_text(message.text)
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer)
        for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await wait.delete()
