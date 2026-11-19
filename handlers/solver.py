"""Решалка: /solve, свободный текст и фото, /history. Общая часть — в solver_reply, «Подумать» — в solver_think, решалка по лекциям — в solver_lectures."""

import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (KeyboardButton, Message,
                           ReplyKeyboardMarkup)

from kapibara.features.ai.solver import solve_text, solve_image, solve_with_history, SUBJECTS
from database import (
    add_solver_history, get_solver_history,
    get_subjects_with_lecture_text,
)
from kapibara.features.privacy.privacy import upsert_user  # до согласия — без имени (152-ФЗ)
from kapibara.bot.keyboards import MAIN_KB, STOP_DIALOG_KB, MENU_BUTTON_TEXTS
from kapibara.bot.intent_router import classify_intent, dispatch_intent
from kapibara.core.utils import esc, utc_to_msk_date
from kapibara.core.telegram import cosmetic
from kapibara.bot.tg import download_bytes, sender, text_of
from handlers import solver_reply

logger = logging.getLogger(__name__)

router = Router()


SUBJECT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SUBJECTS],
    resize_keyboard=True, one_time_keyboard=True
)
LECTURE_MARK = "📖 "


async def solve_subject_kb() -> ReplyKeyboardMarkup:
    """Кнопки предметов для /solve: сначала те, по которым загружены лекции
    (📖 — решалка будет опираться на них), потом остальные предметы группы
    из расписания, в конце «Другое». Раньше был фиксированный список
    «Математика/Экономика/…», который не совпадал ни с одним предметом, по
    которому есть лекции, — и лекции в обычной решалке не участвовали."""
    from kapibara.features.schedule.parser import get_group_subjects
    with_lectures = await get_subjects_with_lecture_text()
    rest = [s for s in await get_group_subjects() if s not in with_lectures]
    if not with_lectures and not rest:
        return SUBJECT_KB
    rows = [[KeyboardButton(text=LECTURE_MARK + s)] for s in with_lectures]
    rows += [[KeyboardButton(text=s)] for s in rest]
    rows.append([KeyboardButton(text="Другое")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


@router.message(Command("solve"), solver_reply.PRIVATE)
@router.message(Command("solve_ds"), solver_reply.PRIVATE)
@router.message(F.text == "🤖 Решить", solver_reply.PRIVATE)
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(sender(message).id, sender(message).username or "", sender(message).full_name or "")
    backend = "deepseek" if (message.text or "").startswith("/solve_ds") else "gemini"
    await state.update_data(backend=backend)
    await state.set_state(solver_reply.SolverState.choose_subject)
    label = " (🐋 DeepSeek)" if backend == "deepseek" else ""
    await message.answer(f"📚 Выбери предмет{label}:", reply_markup=await solve_subject_kb())


@router.message(solver_reply.SolverState.choose_subject, F.text)
async def choose_subject(message: Message, state: FSMContext):
    # Защита на случай, если MenuInterruptMiddleware почему-то не сработал
    # (например, при апдейте aiogram) — не даём тексту кнопки меню стать
    # "названием предмета".
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    data = await state.get_data()
    backend = data.get("backend", "gemini")
    subject = text_of(message).strip().removeprefix(LECTURE_MARK.strip()).strip()
    has_lectures = backend == "gemini" and subject in await get_subjects_with_lecture_text()
    await state.update_data(subject=subject, history=[], msg_ids=[], backend=backend, hinted=False,
                            has_lectures=has_lectures)
    await state.set_state(solver_reply.SolverState.waiting_task)
    note = "\n\n(фото — всегда через Gemini, у DeepSeek нет зрения)" if backend == "deepseek" else ""
    lectures_note = "\n📖 Буду опираться на загруженные лекции по этому предмету." if has_lectures else ""
    msg = await message.answer(
        f"✅ Предмет: <b>{esc(subject)}</b>{lectures_note}\n\nПришли задачу — текстом или фото 📸{note}",
        parse_mode="HTML", reply_markup=STOP_DIALOG_KB
    )
    msg_ids = [msg.message_id]
    if backend == "gemini":
        arm = await solver_think.offer_arm(message)
        if arm:
            msg_ids.append(arm.message_id)
            await state.update_data(think_arm=arm.message_id)
    await state.update_data(msg_ids=msg_ids)


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
        with cosmetic("solver: удалить сообщение диалога"):   # уже удалено или старше 48 ч — не страшно
            await bot.delete_message(message.chat.id, mid)

    await message.answer("✅ Диалог завершён.", reply_markup=MAIN_KB)


@router.message(Command("cancel"), solver_reply.SolverState.waiting_task)
@router.message(Command("cancel"), solver_reply.SolverState.choose_subject)
@router.message(Command("cancel"), solver_reply.SolverState.in_dialog)
async def cancel_solve(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


@router.message(solver_reply.SolverState.waiting_task, F.text, solver_reply.PRIVATE)
async def handle_first_task(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    backend = data.get("backend", "gemini")
    if data.get("think_next"):
        await solver_think.first_think(message, state, data)
        return
    if (why := await solver_reply.ai_block(message)):
        await message.answer(why)
        return
    await solver_think.drop_arm(message, state, data)
    wait    = await message.answer("🧠 Решаю, секунду...")
    async with solver_reply.ai_reply(wait, "решалка"):
        lectures = await solver_reply.lectures_for(data, text_of(message))
        answer = solver_reply.with_sources(await solve_text(text_of(message), subject, backend=backend, lectures=lectures), lectures)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог обработать. Попробуй переформулировать.")
            return
        await wait.delete()
        await add_solver_history(sender(message).id, text_of(message), answer, subject)

        history = [
            {"role": "user",      "content": f"Задание:\n{message.text}"},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(solver_reply.SolverState.in_dialog)
        await solver_reply.send_answer(message, state, answer)


def _photo_prompt(caption: str, history: list | None = None) -> str:
    """Подпись к фото («реши только 2 пункт») — в запрос: раньше она терялась.
    В диалоге — ещё и прошлые реплики, чтобы фото было в контексте."""
    earlier = "\n".join(f"{'Студент' if m['role'] == 'user' else 'Ты'}: {m['content'][:500]}"
                        for m in (history or [])[-6:])
    question = caption.strip() or "Реши задание на фото с подробным объяснением."
    return ((f"Предыдущий разговор:\n{earlier}\n\n" if earlier else "")
            + f"Сообщение студента: {question}\n\nНе используй LaTeX.")


async def _photo_answer(message: Message, bot: Bot, data: dict, history: list | None = None) -> str:
    photo      = (message.photo or [])[-1]           # фильтр F.photo: фото есть всегда
    file_bytes = await download_bytes(bot, photo.file_id)
    caption    = message.caption or ""
    lectures   = await solver_reply.lectures_for(data, caption)
    return solver_reply.with_sources(await solve_image(file_bytes, subject=data.get("subject", ""), lectures=lectures,
                                                       prompt=_photo_prompt(caption, history)), lectures)


def _photo_task(message: Message) -> str:
    return "Задание на фото" + (f": {message.caption}" if message.caption else "")


PHOTO_FAIL = ("📝 Не смог распознать фото.\n\n"
              "Попробуй:\n• Переслать текстом\n• Сделать чёткое фото\n• Прислать скриншот")


@router.message(solver_reply.SolverState.waiting_task, F.photo, solver_reply.PRIVATE)
async def handle_first_photo(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    subject = data.get("subject", "")
    if (why := await solver_reply.ai_block(message)):
        await message.answer(why)
        return
    await solver_think.drop_arm(message, state, data)        # к фото «Подумать» нет — решаем как обычно
    wait    = await message.answer("🧠 Анализирую фото...")
    async with solver_reply.ai_reply(wait, "решалка (предмет)"):
        answer = await _photo_answer(message, bot, data)

        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return

        await wait.delete()
        await add_solver_history(sender(message).id, ("[фото] " + (message.caption or "")).strip(), answer, subject)

        history = [
            {"role": "user",      "content": _photo_task(message)},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(solver_reply.SolverState.in_dialog)
        await solver_reply.send_answer(message, state, answer)


@router.message(solver_reply.SolverState.in_dialog, F.text, solver_reply.PRIVATE)
async def handle_dialog(message: Message, state: FSMContext):
    from kapibara.features.lectures import picker as lecture_picker
    data    = await state.get_data()
    subject = data.get("subject", "")
    backend = data.get("backend", "gemini")
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])

    # Сохраняем ID входящего сообщения
    msg_ids.append(message.message_id)
    if (why := await solver_reply.ai_block(message)):
        msg_ids.append((await message.answer(why)).message_id)
        await state.update_data(msg_ids=msg_ids)
        return
    history.append({"role": "user", "content": message.text})

    wait = await message.answer("🧠 Думаю...")
    async with solver_reply.ai_reply(wait, "решалка (диалог)"):
        # «а почему?», «подробнее» — лекции ищем по теме прошлых вопросов
        query = lecture_picker.search_query(history)
        lectures = await solver_reply.lectures_for(data, query)
        answer = solver_reply.with_sources(await solve_with_history(history, subject, backend=backend, lectures=lectures), lectures)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог ответить. Попробуй иначе.")
            return

        await wait.delete()
        history.append({"role": "assistant", "content": answer})
        if len(history) > 10:
            history = history[-10:]
        await state.update_data(history=history, msg_ids=msg_ids)
        await solver_reply.send_answer(message, state, answer)


@router.message(solver_reply.SolverState.in_dialog, F.photo, solver_reply.PRIVATE)
async def handle_dialog_photo(message: Message, state: FSMContext, bot: Bot):
    """Фото посреди диалога («а вот ещё задача») — раньше молча терялось."""
    data    = await state.get_data()
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)
    if (why := await solver_reply.ai_block(message)):
        msg_ids.append((await message.answer(why)).message_id)
        await state.update_data(msg_ids=msg_ids)
        return
    wait = await message.answer("🧠 Анализирую фото...")
    async with solver_reply.ai_reply(wait, "решалка (фото в диалоге)"):
        answer = await _photo_answer(message, bot, data, history)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return
        await wait.delete()
        history += [{"role": "user", "content": _photo_task(message)}, {"role": "assistant", "content": answer}]
        await state.update_data(history=history[-10:], msg_ids=msg_ids)
        await solver_reply.send_answer(message, state, answer)


@router.message(Command("history"))
async def cmd_history(message: Message):
    history = await get_solver_history(sender(message).id, limit=5)
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
@router.message(F.text & ~F.text.startswith("/"), StateFilter(None), solver_reply.PRIVATE)
async def handle_plain_text(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        return
    if await state.get_state() is not None:
        return

    # «скинь практику 3 по основам предпр деят» — файл, а не вопрос к ИИ
    from handlers.files import answer_file_request
    if await answer_file_request(message):
        return

    # классификатор — тоже запрос к ИИ, но не «вопрос»: только минутный лимит
    if len(text_of(message).strip()) >= 3 and (why := await solver_reply.ai_block(message, day=False)):
        await message.answer(why)
        return

    # Фаза 1: сначала пробуем понять намерение без команд/кнопок
    # ("когда следующая пара", "покажи дедлайны" и т.д.). Если не удалось —
    # при достаточной длине считаем это учебной задачей для решалки, как раньше.
    intent = await classify_intent(text_of(message))
    if intent == "history":
        await cmd_history(message)
        return
    if intent != "none":
        handled = await dispatch_intent(intent, message)
        if handled:
            return

    text = text_of(message)
    backend = "gemini"
    for prefix in ("дипсик:", "deepseek:", "через дипсик:"):
        if text.lower().startswith(prefix):
            backend = "deepseek"
            text = text[len(prefix):].strip()
            break

    if len(text) < 15:
        return
    if (why := await solver_reply.ai_day(message)):          # а вот это уже вопрос к ИИ — в дневной счёт
        await message.answer(why)
        return
    wait = await message.answer("🤖 Похоже задание — решаю..." + (" (🐋 DeepSeek)" if backend == "deepseek" else ""))
    async with solver_reply.ai_reply(wait, "решалка (свободный текст)"):
        answer = await solve_text(text, backend=backend)
        if not answer or len(answer.strip()) < 10:
            # раньше «решаю…» молча пропадало — человек оставался без ответа
            await wait.edit_text("🤷 ИИ вернул пустой ответ — попробуй переформулировать или /solve")
            return
        await wait.delete()
        await add_solver_history(sender(message).id, text, answer)
        sent = await solver_reply.answer_model_text(message, answer)
        await solver_reply.offer_think(sender(message).id, state, sent, [{"role": "user", "content": f"Задание:\n{text}"}], {})


# /start обещает «пришли фото задачи — отвечу», а фото без /solve раньше
# никто не ловил. Подпись к фото — вопрос к нему.
@router.message(F.photo, StateFilter(None), solver_reply.PRIVATE)
async def handle_plain_photo(message: Message, bot: Bot):
    if (why := await solver_reply.ai_block(message)):
        await message.answer(why)
        return
    wait = await message.answer("🧠 Анализирую фото...")
    async with solver_reply.ai_reply(wait, "решалка (фото)"):
        answer = await _photo_answer(message, bot, {})
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return
        await wait.delete()
        await add_solver_history(sender(message).id, ("[фото] " + (message.caption or "")).strip(), answer)
        await solver_reply.answer_model_text(message, answer)


# «Подумать» и решалка по лекциям — свои роутеры, после основного:
# обработчики там ловят только свои состояния, команды и кнопки.
from handlers import solver_lectures, solver_think  # noqa: E402
router.include_router(solver_think.router)
router.include_router(solver_lectures.router)
