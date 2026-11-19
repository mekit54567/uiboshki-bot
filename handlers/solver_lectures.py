"""Решалка по лекциям: /solve_lectures — выбор предмета с загруженными лекциями и решение по ним."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from database import add_solver_history, get_subjects_with_lecture_text, get_subject_lecture_context
from kapibara.bot.keyboards import MAIN_KB, CANCEL_KB, MENU_BUTTON_TEXTS
from kapibara.bot.tg import sender, text_of
from kapibara.core.utils import esc
from kapibara.features.ai.gemini import solve_with_lecture_context
from kapibara.features.privacy.privacy import upsert_user  # до согласия — без имени (152-ФЗ)
from handlers import solver_reply

router = Router()


# ── Решалка по лекциям (Gemini, Фаза 9) ─────────────────────────────────────


@router.message(Command("solve_lectures"), solver_reply.PRIVATE)
async def cmd_solve_lectures(message: Message, state: FSMContext):
    await upsert_user(sender(message).id, sender(message).username or "", sender(message).full_name or "")
    subjects = await get_subjects_with_lecture_text()
    if not subjects:
        await message.answer(
            "📖 Пока ни по одному предмету нет загруженных лекций с текстом "
            "(PDF/DOCX/PPTX не-сканы). Сначала загрузи через /upload — если формат "
            "поддерживается, бот сам заберёт текст в контекст."
        )
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=s)] for s in subjects],
        resize_keyboard=True, one_time_keyboard=True
    )
    await state.set_state(solver_reply.LectureSolverState.choose_subject)
    await message.answer("📖 По какому предмету решаем — на основе загруженных лекций?", reply_markup=kb)


@router.message(solver_reply.LectureSolverState.choose_subject, F.text)
async def lecture_choose_subject(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    subject = text_of(message).strip()
    subjects = await get_subjects_with_lecture_text()
    if subject not in subjects:
        await message.answer("Не нашёл такой предмет среди тех, где есть лекции — выбери кнопкой из списка выше.")
        return
    await state.update_data(subject=subject)
    await state.set_state(solver_reply.LectureSolverState.waiting_task)
    await message.answer(
        f"✅ Предмет: <b>{esc(subject)}</b>\n\nПришли текст задания (практики) — решу, опираясь на лекции этого предмета.",
        parse_mode="HTML", reply_markup=CANCEL_KB
    )


@router.message(solver_reply.LectureSolverState.waiting_task, F.text, solver_reply.PRIVATE)
async def lecture_handle_task(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    if (why := await solver_reply.ai_block(message)):
        await message.answer(why)       # состояние не сбрасываем — можно прислать ещё раз
        return

    data    = await state.get_data()
    subject = data.get("subject", "")
    wait = await message.answer("📖 Читаю лекции и решаю — с большим контекстом это может занять чуть больше времени...")
    try:
        async with solver_reply.ai_reply(wait, "решалка по лекциям"):
            from kapibara.features.lectures import picker as lecture_picker
            context_text = lecture_picker.pick(await get_subject_lecture_context(subject), text_of(message))
            answer = await solve_with_lecture_context(text_of(message), subject, context_text)
            await wait.delete()
            await add_solver_history(sender(message).id, text_of(message), answer, subject)
            await solver_reply.answer_model_text(message, answer)
            await message.answer("Готово ✅ (/solve_lectures — ещё раз по этому или другому предмету)", reply_markup=MAIN_KB)
    finally:
        await state.clear()
