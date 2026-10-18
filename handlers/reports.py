"""Жалобы на записи людей (ugc.py): у владельца «Удалить» / «Оставить», у автора
удалённой записи — «Оспорить» (бот просит написать, с чем не согласен и почему),
у владельца по спору — «Вернуть» / «Оставить скрытым»."""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config

router = Router()

NOTES = {"removed": "🗑 Удалено — запись пропала у всех. Автору написал, он может оспорить.",
         "kept": "Оставлено.", "restored": "↩️ Вернул запись, автору ответил.",
         "upheld": "Оставил скрытой, автору ответил.", "missing": "Жалобы уже нет."}
NOT_NOW = {"expired": "Срок спора прошёл — записи уже нет.",
           "missing": "Это не твоя запись или её уже нет.",
           "disputed": "Заявка уже у владельца — ответ придёт сюда.",
           "disputed_already": "Заявка уже у владельца — ответ придёт сюда."}
SENT = "Отправил на пересмотр — ответ придёт сюда."
CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="dis:cancel")]])


class Dispute(StatesGroup):
    why = State()


@router.callback_query(F.data.startswith("rep:"))
async def report_decision(callback: CallbackQuery):
    import ugc
    if not config.is_starosta(callback.from_user.id):
        await callback.answer("Это кнопка владельца бота", show_alert=True)
        return
    _, verdict, rid = callback.data.split(":", 2)
    if verdict in ("back", "hold"):
        status = await ugc.settle(callback.bot, int(rid), restore=verdict == "back")
    else:
        status = await ugc.decide(int(rid), remove=verdict == "del")
        if status == "removed":
            await ugc.tell_author(callback.bot, int(rid))
    note = NOTES.get(status, "Уже решено.")
    await callback.answer(note)
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<b>{note}</b>", parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data == "dis:cancel")
async def dispute_cancel(callback: CallbackQuery, state: FSMContext):
    import ugc
    await state.clear()
    await callback.answer("Отменил")
    try:
        await callback.message.edit_text(f"Отменил. Передумаешь — «Оспорить» можно нажать снова "
                                         f"в течение {ugc.DISPUTE_DAYS} дней после удаления.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("dis:"))
async def dispute(callback: CallbackQuery, state: FSMContext):
    """«Оспорить» под сообщением «Твою запись убрали» → просим объяснение одним сообщением."""
    import ugc
    rid = int(callback.data.split(":", 1)[1])
    status = await ugc.can_dispute(rid, callback.from_user.id)
    if status != "removed":
        await callback.answer(NOT_NOW.get(status, "Уже пересмотрели — ответ выше."), show_alert=True)
        return
    await state.set_state(Dispute.why)
    await state.update_data(rid=rid, notice=callback.message.message_id if callback.message else None)
    await callback.answer()
    await callback.bot.send_message(
        callback.from_user.id,
        "⚖️ Напиши одним сообщением, с чем ты не согласен и почему запись не нарушает правила — "
        f"от {ugc.APPEAL_MIN} до {ugc.APPEAL_MAX} знаков. Его прочитает только владелец бота, "
        "вместе с твоей записью и жалобой.\n\n/cancel — отмена",
        reply_markup=CANCEL_KB)


@router.message(StateFilter(Dispute.why))
async def dispute_why(message: Message, state: FSMContext):
    import ugc
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст: напиши словами, с чем не согласен.", reply_markup=CANCEL_KB)
        return
    if len(text) < ugc.APPEAL_MIN:
        await message.answer(f"Коротко — напиши чуть подробнее, почему запись не нарушает правила "
                             f"(от {ugc.APPEAL_MIN} знаков).", reply_markup=CANCEL_KB)
        return
    if len(text) > ugc.APPEAL_MAX:
        await message.answer(f"Длинновато: {len(text)} знаков, а можно до {ugc.APPEAL_MAX}. "
                             "Сократи и пришли ещё раз.", reply_markup=CANCEL_KB)
        return
    data = await state.get_data()
    await state.clear()
    status = await ugc.dispute(message.bot, int(data.get("rid") or 0), message.from_user.id, text)
    if status != "disputed":
        await message.answer(NOT_NOW.get(status, "Уже пересмотрели — ответ выше."))
        return
    await message.answer(SENT)
    if data.get("notice"):                          # у сообщения «убрали» — без кнопки, с отметкой
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=data["notice"],
                                                        reply_markup=None)
        except Exception:
            pass
