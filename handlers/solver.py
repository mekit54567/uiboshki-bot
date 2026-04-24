import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from groq_solver import solve_text, solve_image, solve_with_history, SUBJECTS
from database import upsert_user, add_solver_history, get_solver_history

logger = logging.getLogger(__name__)
router = Router()

BUTTON_TEXTS = {
    "📅 Сегодня","📆 Неделя","🌅 Завтра","⏭ Следующая",
    "📋 Дедлайны","➕ Дедлайн","🤖 Решить","📁 Файлы",
    "🗳 Голосование","❓ Вопрос анон","🔔 Подписка","⚙️ Настройки",
    "❌ Отмена","🌤 Погода",
}

SUBJECT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SUBJECTS],
    resize_keyboard=True, one_time_keyboard=True
)

STOP_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🛑 Завершить диалог")]],
    resize_keyboard=True
)

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),      KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),    KeyboardButton(text="➕ Дедлайн")],
    [KeyboardButton(text="🤖 Решить"),      KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="🗳 Голосование")],
    [KeyboardButton(text="❓ Вопрос анон"), KeyboardButton(text="🔔 Подписка"),    KeyboardButton(text="⚙️ Настройки")],
], resize_keyboard=True)


class SolverState(StatesGroup):
    choose_subject = State()
    waiting_task   = State()
    in_dialog      = State()


@router.message(Command("solve"))
@router.message(F.text == "🤖 Решить")
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await state.set_state(SolverState.choose_subject)
    await message.answer("📚 Выбери предмет:", reply_markup=SUBJECT_KB)


@router.message(SolverState.choose_subject, F.text)
async def choose_subject(message: Message, state: FSMContext):
    if message.text in BUTTON_TEXTS:
        await state.clear()
        return
    await state.update_data(subject=message.text.strip(), history=[], msg_ids=[])
    await state.set_state(SolverState.waiting_task)
    msg = await message.answer(
        f"✅ Предмет: <b>{message.text}</b>\n\nПришли задачу — текстом или фото 📸",
        parse_mode="HTML", reply_markup=STOP_KB
    )
    await state.update_data(msg_ids=[msg.message_id])


@router.message(F.text == "🛑 Завершить диалог")
async def stop_dialog(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    # Удаляем сообщения диалога из чата
    msg_ids = data.get("msg_ids", [])
    for mid in msg_ids:
        try:
            await bot.delete_message(message.chat.id, mid)
        except:
            pass

    await message.answer("✅ Диалог завершён.", reply_markup=MAIN_KB)


@router.message(Command("cancel"), SolverState.waiting_task)
@router.message(Command("cancel"), SolverState.choose_subject)
@router.message(Command("cancel"), SolverState.in_dialog)
async def cancel_solve(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


async def send_answer(message: Message, state: FSMContext, answer: str):
    """Отправляем ответ и сохраняем msg_id."""
    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])

    chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
    for chunk in chunks:
        try:
            msg = await message.answer(chunk, parse_mode="Markdown")
        except:
            msg = await message.answer(chunk)
        msg_ids.append(msg.message_id)

    # Подсказка
    hint = await message.answer(
        "💬 Можешь уточнить или задать следующий вопрос.\n"
        "Нажми <b>🛑 Завершить диалог</b> чтобы выйти.",
        parse_mode="HTML"
    )
    msg_ids.append(hint.message_id)
    await state.update_data(msg_ids=msg_ids)


@router.message(SolverState.waiting_task, F.text)
async def handle_first_task(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    wait    = await message.answer("🧠 Решаю, секунду...")
    try:
        answer = await solve_text(message.text, subject)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог обработать. Попробуй переформулировать.")
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer, subject)

        history = [
            {"role": "user",      "content": f"Задание:\n{message.text}"},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(SolverState.in_dialog)
        await send_answer(message, state, answer)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(SolverState.waiting_task, F.photo)
async def handle_first_photo(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    subject = data.get("subject", "")
    wait    = await message.answer("🧠 Анализирую фото...")
    try:
        photo      = message.photo[-1]
        file       = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        answer     = await solve_image(file_bytes.read(), subject=subject)

        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(
                "📝 Не смог распознать фото.\n\n"
                "Попробуй:\n• Переслать текстом\n• Сделать чёткое фото\n• Прислать скриншот"
            )
            return

        await wait.delete()
        await add_solver_history(message.from_user.id, "[фото]", answer, subject)

        history = [
            {"role": "user",      "content": "Задание на фото"},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(SolverState.in_dialog)
        await send_answer(message, state, answer)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(SolverState.in_dialog, F.text)
async def handle_dialog(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])

    # Сохраняем ID входящего сообщения
    msg_ids.append(message.message_id)
    history.append({"role": "user", "content": message.text})

    wait = await message.answer("🧠 Думаю...")
    try:
        answer = await solve_with_history(history, subject)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог ответить. Попробуй иначе.")
            return

        await wait.delete()
        history.append({"role": "assistant", "content": answer})
        if len(history) > 10:
            history = history[-10:]
        await state.update_data(history=history, msg_ids=msg_ids)
        await send_answer(message, state, answer)

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
    await message.answer("\n".join(lines), parse_mode="HTML")


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
        if not answer or len(answer.strip()) < 10:
            await wait.delete()
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer)
        for chunk in [answer[i:i+4000] for i in range(0, len(answer), 4000)]:
            try:
                await message.answer(chunk, parse_mode="Markdown")
            except:
                await message.answer(chunk)
    except Exception as e:
        logger.error(e)
        await wait.delete()
