"""Жалобы на записи людей (ugc.py): у владельца «Удалить» / «Оставить», у автора
удалённой записи — «Оспорить», у владельца по спору — «Вернуть» / «Оставить скрытым»."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

import config

router = Router()

NOTES = {"removed": "🗑 Удалено — запись пропала у всех. Автору написал, он может оспорить.",
         "kept": "Оставлено.", "restored": "↩️ Вернул запись, автору ответил.",
         "upheld": "Оставил скрытой, автору ответил.", "missing": "Жалобы уже нет."}


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


@router.callback_query(F.data.startswith("dis:"))
async def dispute(callback: CallbackQuery):
    """«Оспорить» под сообщением «Твою запись убрали»."""
    import ugc
    status = await ugc.dispute(callback.bot, int(callback.data.split(":", 1)[1]), callback.from_user.id)
    note = {"disputed": "Отправил на пересмотр — ответ придёт сюда.",
            "expired": "Срок спора прошёл — записи уже нет.",
            "missing": "Это не твоя запись или её уже нет."}.get(status, "Уже пересмотрели — ответ выше.")
    await callback.answer(note, show_alert=status != "disputed")
    if status == "disputed":
        try:
            await callback.message.edit_text(f"{callback.message.html_text}\n\n<b>{note}</b>", parse_mode="HTML")
        except Exception:
            pass
