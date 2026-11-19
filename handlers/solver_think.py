"""Решалка: «Подумать» — переключатель перед ответом, /think, /aithink и повтор ответа моделью второго уровня («Капибара+»)."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import add_solver_history
from kapibara.bot.tg import bot_of, msg, sender, text_of
from kapibara.core.telegram import cosmetic
from handlers import solver_reply

router = Router()


# ── «Подумать ещё» (think.py, «Капибара+») ────────────────────────────────
# Под ответом подписчика — кнопка: тот же вопрос заново решает модель
# второго уровня со своим дневным лимитом. Вопрос (история до ответа) — в
# данных FSM; к фото кнопки нет: модель читает только текст.


GONE_TEXT = "Этот вопрос уже не найти — задай его ещё раз"


@router.callback_query(F.data == solver_reply.THINK_CB)
async def think_again(callback: CallbackQuery, state: FSMContext):
    from kapibara.features.lectures import picker as lecture_picker
    from kapibara.features.ai import think
    data = await state.get_data()
    question, d = data.get("think_q"), data.get("think_d") or {}
    if not question:
        await callback.answer(GONE_TEXT, show_alert=True)
        return
    await callback.answer()
    with cosmetic("solver.think_again"):
        await msg(callback).edit_reply_markup(reply_markup=None)
    wait = await msg(callback).answer("🧠 Думаю ещё раз…")
    uid = callback.from_user.id
    try:
        lectures = await solver_reply.lectures_for(d, lecture_picker.search_query(question))
        answer = await think.solve(uid, question, d.get("subject", ""), lectures)
    except think.ThinkError as e:
        await wait.edit_text("⏳ " + str(e))
        if "не списана" in str(e):          # не ответила — кнопка снова под ответом
            with cosmetic("solver: вернуть кнопку «Подумать ещё»"):
                offer = await think.offer(uid)
                if offer and offer["left"] != 0:
                    await msg(callback).edit_reply_markup(reply_markup=solver_reply.think_kb(offer["left"]))
        return
    await wait.delete()
    sent = await solver_reply.answer_model_text(msg(callback), answer)
    history = data.get("history") or []
    if await state.get_state() == solver_reply.SolverState.in_dialog.state and history and history[-1]["role"] == "assistant":
        history[-1] = {"role": "assistant", "content": answer}     # уточнять дальше — от нового ответа
        await state.update_data(history=history,
                                msg_ids=data.get("msg_ids", []) + [m.message_id for m in sent])
    await solver_reply.offer_think(uid, state, sent, question, d)


# ── «Подумать» сразу (Никита 18.10: «выбрать перед ответом») ──────────────
# В решалке (/solve) под «Пришли задачу» — кнопка-переключатель: включил —
# задачу сразу решает модель второго уровня, без первого обычного ответа.
# Вне решалки — /think вопрос (или /think, потом вопрос). Лимит — think.py,
# обычный дневной счёт ai_quota не трогается; к фото — нет.
THINK_ARM_CB = "think:arm"
ARM_TEXT = ("🧠 Нужен разбор поглубже? Включи «Подумать» — Капибара решит задачу, "
            "подумав подольше («Капибара+», {left}).\nВне решалки — /think и вопрос.")
ARM_GONE = "Задача уже решена — включи «Подумать» в новой: /solve"
THINK_ASK = ("🧠 Пиши вопрос — Капибара решит его, подумав подольше ({left}).\n"
             "Передумал — /cancel")
PHOTO_NO_THINK = "К фото «Подумать» не работает — пришли задачу текстом или /cancel"


class ThinkState(StatesGroup):
    waiting = State()       # /think без текста: следующий вопрос — «подумав»


def _left_text(left: int | None) -> str:
    return "без лимита" if left is None else f"{left} на сегодня"


def arm_kb(left: int | None, on: bool) -> InlineKeyboardMarkup:
    """left=None — безлимит, без счётчика."""
    n = "" if left is None else f" · {left}"
    text = f"✅ Подумать включено{n}" if on else f"🧠 Подумать{n}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=THINK_ARM_CB)]])


async def offer_arm(message: Message) -> Message | None:
    """Переключатель «Подумать» под «Пришли задачу» — подписчику, пока на
    сегодня не кончилось (кончилось — не предлагаем вовсе)."""
    from kapibara.features.ai import think
    offer = await think.offer(sender(message).id)
    if not offer or offer["left"] == 0:
        return None
    return await message.answer(ARM_TEXT.format(left=_left_text(offer["left"])),
                                reply_markup=arm_kb(offer["left"], False))


async def drop_arm(message: Message, state: FSMContext, data: dict):
    """Задача ушла — переключатель под «Пришли задачу» больше не нужен."""
    mid = data.get("think_arm")
    if not mid:
        return
    await state.update_data(think_arm=None, think_next=False)
    with cosmetic("solver.drop_arm"):
        await bot_of(message).edit_message_reply_markup(chat_id=message.chat.id, message_id=mid, reply_markup=None)


@router.callback_query(F.data == THINK_ARM_CB)
async def toggle_arm(callback: CallbackQuery, state: FSMContext):
    from kapibara.features.ai import think
    data = await state.get_data()
    if await state.get_state() != solver_reply.SolverState.waiting_task.state or data.get("think_arm") != msg(callback).message_id:
        await callback.answer(ARM_GONE, show_alert=True)
        with cosmetic("solver.toggle_arm"):
            await msg(callback).edit_reply_markup(reply_markup=None)
        return
    uid = callback.from_user.id
    on = not data.get("think_next")
    why = await think.why_not(uid) if on else None
    if why:
        await state.update_data(think_next=False)
        await callback.answer(why, show_alert=True)
        with cosmetic("solver.toggle_arm"):
            await msg(callback).edit_reply_markup(reply_markup=None)
        return
    await state.update_data(think_next=on)
    await callback.answer("Капибара решит задачу, подумав подольше" if on else "Решу как обычно")
    with cosmetic("solver.toggle_arm"):
        await msg(callback).edit_reply_markup(reply_markup=arm_kb(await think.left_or_none(uid), on))


async def _think_first(message: Message, question: list, subject: str = "", lectures: str = "") -> str | None:
    """Вопрос сразу моделью второго уровня: ответ или None (причина уже
    написана человеку; попытка при сбое не списана)."""
    from kapibara.features.ai import think
    wait = await message.answer("🧠 Думаю как следует…")
    try:
        answer = await think.solve(sender(message).id, question, subject, lectures, first=True)
    except think.ThinkError as e:
        await wait.edit_text("⏳ " + str(e))
        return None
    with cosmetic("solver._think_first"):
        await wait.delete()
    return answer


async def first_think(message: Message, state: FSMContext, data: dict):
    """Задача в решалке со включённым «Подумать»: дальше — обычный диалог."""
    subject = data.get("subject", "")
    await drop_arm(message, state, data)
    question = [{"role": "user", "content": f"Задание:\n{message.text}"}]
    answer = await _think_first(message, question, subject, await solver_reply.lectures_for(data, text_of(message)))
    if answer is None:
        await message.answer("Можно прислать задачу ещё раз — решу как обычно.")
        return
    await add_solver_history(sender(message).id, text_of(message), answer, subject)
    await state.update_data(history=question + [{"role": "assistant", "content": answer}])
    await state.set_state(solver_reply.SolverState.in_dialog)
    await solver_reply.send_answer(message, state, answer)


async def _think_free(message: Message, state: FSMContext, text: str):
    question = [{"role": "user", "content": f"Задание:\n{text}"}]
    answer = await _think_first(message, question)
    if answer is None:
        return
    await add_solver_history(sender(message).id, text, answer)
    sent = await solver_reply.answer_model_text(message, answer)
    await solver_reply.offer_think(sender(message).id, state, sent, question, {})


@router.message(Command("think"), solver_reply.PRIVATE)
async def cmd_think(message: Message, state: FSMContext):
    """/think вопрос — сразу «подумав»; /think — следующий вопрос «подумав»."""
    from kapibara.features.ai import think
    why = await think.why_not(sender(message).id)
    if why:
        await message.answer("⏳ " + why)
        return
    text = ((message.text or "").split(maxsplit=1)[1:] or [""])[0].strip()
    if text:
        await _think_free(message, state, text)
        return
    await state.set_state(ThinkState.waiting)
    await message.answer(THINK_ASK.format(left=_left_text(await think.left_or_none(sender(message).id))))


@router.message(ThinkState.waiting, F.text, solver_reply.PRIVATE)
async def think_waiting_text(message: Message, state: FSMContext):
    await state.clear()
    await _think_free(message, state, text_of(message))


@router.message(ThinkState.waiting, F.photo, solver_reply.PRIVATE)
async def think_waiting_photo(message: Message):
    await message.answer(PHOTO_NO_THINK)


@router.message(Command("aithink"), solver_reply.PRIVATE)
async def cmd_aithink(message: Message):
    """/aithink on|off — выключатель «Подумать ещё» для отката (у старосты)."""
    from kapibara.features.ai import think
    from kapibara.core.config import is_starosta
    from database import set_setting
    if not is_starosta(sender(message).id):
        return
    arg = (message.text or "").split(maxsplit=1)[1:]
    if arg and arg[0].strip().lower() in ("on", "off"):
        await set_setting("ai_think", arg[0].strip().lower())
    await message.answer(await think.status_line() + "\n\n/aithink on · /aithink off")
