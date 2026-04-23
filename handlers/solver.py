import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from groq_solver import solve_text, solve_image
from database import upsert_user

logger = logging.getLogger(__name__)
router = Router()


class SolverState(StatesGroup):
    waiting_task = State()


# ── Команда /solve или кнопка ─────────────────────────────────────────────────

@router.message(Command("solve"))
@router.message(F.text == "🤖 Решить задачу")
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await state.set_state(SolverState.waiting_task)
    await message.answer(
        "🤖 Пришли мне задачу:\n"
        "• Просто напиши текст задания\n"
        "• Или прикрепи <b>фото/скриншот</b>\n\n"
        "Отправь /cancel чтобы отменить.",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), SolverState.waiting_task)
async def cmd_cancel_solve(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


# ── Получить текст задачи ─────────────────────────────────────────────────────

@router.message(SolverState.waiting_task, F.text)
async def handle_task_text(message: Message, state: FSMContext):
    await state.clear()
    wait = await message.answer("🧠 Решаю задачу, секунду...")
    try:
        answer = await solve_text(message.text)
        await wait.delete()
        # Telegram ограничивает сообщение 4096 символами
        if len(answer) <= 4096:
            await message.answer(answer, parse_mode="Markdown")
        else:
            # Разбиваем на части
            for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
                await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Groq error: {e}")
        await wait.edit_text(f"❌ Ошибка при обращении к AI: {e}")


# ── Получить фото задачи ─────────────────────────────────────────────────────

@router.message(SolverState.waiting_task, F.photo)
async def handle_task_photo(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    wait = await message.answer("🧠 Анализирую фото, секунду...")
    try:
        # Берём самое большое фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_bytes = file_bytes.read()

        answer = await solve_image(image_bytes)
        await wait.delete()
        if len(answer) <= 4096:
            await message.answer(answer, parse_mode="Markdown")
        else:
            for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
                await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Groq vision error: {e}")
        await wait.edit_text(f"❌ Ошибка при анализе фото: {e}")


# ── Любое сообщение вне FSM — предлагаем решить ──────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext):
    """Если пользователь просто написал текст — предполагаем, что это задача."""
    # Проверяем, что не в другом FSM состоянии
    current = await state.get_state()
    if current is not None:
        return

    # Короткие сообщения игнорируем
    if len(message.text) < 20:
        return

    wait = await message.answer("🤖 Похоже, это задание — решаю...")
    try:
        answer = await solve_text(message.text)
        await wait.delete()
        if len(answer) <= 4096:
            await message.answer(answer, parse_mode="Markdown")
        else:
            for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
                await message.answer(chunk, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Auto-solve error: {e}")
        await wait.delete()
