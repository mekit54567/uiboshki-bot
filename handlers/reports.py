"""Жалобы на записи людей (ugc.py): кнопки «Удалить» / «Оставить» у владельца."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

import config

router = Router()


@router.callback_query(F.data.startswith("rep:"))
async def report_decision(callback: CallbackQuery):
    import ugc
    if not config.is_starosta(callback.from_user.id):
        await callback.answer("Это кнопка владельца бота", show_alert=True)
        return
    _, verdict, rid = callback.data.split(":", 2)
    status = await ugc.decide(int(rid), remove=verdict == "del")
    note = {"removed": "🗑 Удалено — запись пропала у всех.", "kept": "Оставлено.",
            "missing": "Жалобы уже нет."}.get(status, "Уже решено.")
    await callback.answer(note)
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<b>{note}</b>", parse_mode="HTML")
    except Exception:
        pass
