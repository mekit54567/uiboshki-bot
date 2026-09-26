import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from ai_solver import solve_text, solve_image, solve_with_history, SUBJECTS
from gemini_solver import solve_with_lecture_context
from database import (
    upsert_user, add_solver_history, get_solver_history,
    get_subjects_with_lecture_text, get_subject_lecture_context,
)
from keyboards import MAIN_KB, STOP_DIALOG_KB, CANCEL_KB, MENU_BUTTON_TEXTS
from intent_router import classify_intent, dispatch_intent
from utils import esc, md_to_tg_html_chunks, split_by_lines, utc_to_msk_date

logger = logging.getLogger(__name__)
router = Router()

SUBJECT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SUBJECTS],
    resize_keyboard=True, one_time_keyboard=True
)


class SolverState(StatesGroup):
    choose_subject = State()
    waiting_task   = State()
    in_dialog      = State()


class LectureSolverState(StatesGroup):
    """Отдельная (не мульти-turn) машина состояний для решалки по лекциям —
    см. gemini_solver.py. Не переиспользует SolverState: там subject — это
    произвольная категория из фиксированного SUBJECTS, здесь — обязательно
    точное название предмета, по которому реально есть загруженные лекции
    (иначе неоткуда взять контекст)."""
    choose_subject = State()
    waiting_task   = State()


@router.message(Command("solve"))
@router.message(Command("solve_ds"))
@router.message(F.text == "🤖 Решить")
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    backend = "deepseek" if (message.text or "").startswith("/solve_ds") else "gemini"
    await state.update_data(backend=backend)
    await state.set_state(SolverState.choose_subject)
    label = " (🐋 DeepSeek)" if backend == "deepseek" else ""
    await message.answer(f"📚 Выбери предмет{label}:", reply_markup=SUBJECT_KB)


@router.message(SolverState.choose_subject, F.text)
async def choose_subject(message: Message, state: FSMContext):
    # Защита на случай, если MenuInterruptMiddleware почему-то не сработал
    # (например, при апдейте aiogram) — не даём тексту кнопки меню стать
    # "названием предмета".
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    data = await state.get_data()
    backend = data.get("backend", "gemini")
    await state.update_data(subject=message.text.strip(), history=[], msg_ids=[], backend=backend, hinted=False)
    await state.set_state(SolverState.waiting_task)
    note = "\n\n(фото — всегда через Gemini, у DeepSeek нет зрения)" if backend == "deepseek" else ""
    msg = await message.answer(
        f"✅ Предмет: <b>{esc(message.text)}</b>\n\nПришли задачу — текстом или фото 📸{note}",
        parse_mode="HTML", reply_markup=STOP_DIALOG_KB
    )
    await state.update_data(msg_ids=[msg.message_id])


@router.message(F.text == "🛑 Завершить диалог")
async def stop_dialog(message: Message, state: FSMContext, bot: Bot, interrupted_fsm_data: dict | None = None):
    # "🛑 Завершить диалог" входит в MENU_BUTTON_TEXTS, поэтому к этому моменту
    # MenuInterruptMiddleware уже сбросил state — msg_ids берём из того, что он
    # успел сохранить перед сбросом.
    data = interrupted_fsm_data if interrupted_fsm_data is not None else await state.get_data()
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


async def answer_model_text(message: Message, answer: str) -> list[Message]:
    """Ответ модели -> сообщения с HTML-разметкой (см. md_to_tg_html_chunks).
    Если Telegram всё же не принял разметку куска — тот же кусок без неё."""
    sent = []
    plain_chunks = split_by_lines(answer)
    for i, chunk in enumerate(md_to_tg_html_chunks(answer)):
        try:
            sent.append(await message.answer(chunk, parse_mode="HTML"))
        except Exception as e:
            logger.warning(f"Ответ модели не прошёл как HTML, шлю текстом: {e}")
            fallback = plain_chunks[i] if i < len(plain_chunks) else chunk
            sent.append(await message.answer(fallback))
    return sent


async def send_answer(message: Message, state: FSMContext, answer: str):
    """Отправляем ответ и сохраняем msg_id."""
    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])

    for msg in await answer_model_text(message, answer):
        msg_ids.append(msg.message_id)

    # Подсказка — один раз за диалог, а не после каждого ответа
    if not data.get("hinted"):
        hint = await message.answer(
            "💬 Можно задать уточняющий вопрос — я помню условие.\n"
            "Закончил — жми <b>🛑 Завершить диалог</b>.",
            parse_mode="HTML"
        )
        msg_ids.append(hint.message_id)
    await state.update_data(msg_ids=msg_ids, hinted=True)


@router.message(SolverState.waiting_task, F.text)
async def handle_first_task(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    backend = data.get("backend", "gemini")
    wait    = await message.answer("🧠 Решаю, секунду...")
    try:
        answer = await solve_text(message.text, subject, backend=backend)
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
    backend = data.get("backend", "gemini")
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])

    # Сохраняем ID входящего сообщения
    msg_ids.append(message.message_id)
    history.append({"role": "user", "content": message.text})

    wait = await message.answer("🧠 Думаю...")
    try:
        answer = await solve_with_history(history, subject, backend=backend)
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
        # Экранирование обязательно: в условиях задач постоянно встречаются
        # "<"/">" ("x < 5"), и одна такая задача среди последних пяти
        # раньше навсегда ломала /history ("can't parse entities").
        subj = f" [{esc(h['subject'])}]" if h.get("subject") else ""
        task = esc(h["task_text"][:80]) + ("..." if len(h["task_text"]) > 80 else "")
        lines.append(f"{i}.{subj} {task}\n   <i>{utc_to_msk_date(h['created_at'])}</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# StateFilter(None) обязателен: этот catch-all зарегистрирован в роутере РАНЬШЕ
# хендлеров решалки по лекциям (LectureSolverState ниже). Без фильтра он
# забирал себе любой текст в любом состоянии и просто выходил по проверке
# state ниже — апдейт считался обработанным, и lecture_choose_subject /
# lecture_handle_task не вызывались никогда (/solve_lectures зависал на
# выборе предмета).
@router.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_plain_text(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        return
    if await state.get_state() is not None:
        return

    # Фаза 1: сначала пробуем понять намерение без команд/кнопок
    # ("когда следующая пара", "покажи дедлайны" и т.д.). Если не удалось —
    # при достаточной длине считаем это учебной задачей для решалки, как раньше.
    intent = await classify_intent(message.text)
    if intent != "none":
        handled = await dispatch_intent(intent, message)
        if handled:
            return

    text = message.text
    backend = "gemini"
    for prefix in ("дипсик:", "deepseek:", "через дипсик:"):
        if text.lower().startswith(prefix):
            backend = "deepseek"
            text = text[len(prefix):].strip()
            break

    if len(text) < 15:
        return
    wait = await message.answer("🤖 Похоже задание — решаю..." + (" (🐋 DeepSeek)" if backend == "deepseek" else ""))
    try:
        answer = await solve_text(text, backend=backend)
        if not answer or len(answer.strip()) < 10:
            await wait.delete()
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, text, answer)
        await answer_model_text(message, answer)
    except Exception as e:
        logger.error(e)
        await wait.delete()


# ── Решалка по лекциям (Gemini, Фаза 9) ─────────────────────────────────────

@router.message(Command("solve_lectures"))
async def cmd_solve_lectures(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
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
    await state.set_state(LectureSolverState.choose_subject)
    await message.answer("📖 По какому предмету решаем — на основе загруженных лекций?", reply_markup=kb)


@router.message(LectureSolverState.choose_subject, F.text)
async def lecture_choose_subject(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    subject = message.text.strip()
    subjects = await get_subjects_with_lecture_text()
    if subject not in subjects:
        await message.answer("Не нашёл такой предмет среди тех, где есть лекции — выбери кнопкой из списка выше.")
        return
    await state.update_data(subject=subject)
    await state.set_state(LectureSolverState.waiting_task)
    await message.answer(
        f"✅ Предмет: <b>{esc(subject)}</b>\n\nПришли текст задания (практики) — решу, опираясь на лекции этого предмета.",
        parse_mode="HTML", reply_markup=CANCEL_KB
    )


@router.message(LectureSolverState.waiting_task, F.text)
async def lecture_handle_task(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return

    data    = await state.get_data()
    subject = data.get("subject", "")
    wait = await message.answer("📖 Читаю лекции и решаю — с большим контекстом это может занять чуть больше времени...")
    try:
        context_text = await get_subject_lecture_context(subject)
        answer = await solve_with_lecture_context(message.text, subject, context_text)
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer, subject)
        await answer_model_text(message, answer)
        await message.answer("Готово ✅ (/solve_lectures — ещё раз по этому или другому предмету)", reply_markup=MAIN_KB)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")
    finally:
        await state.clear()
