"""Вопрос «ходишь?» про предметы по выбору (optional_subjects.py).

Задают и /start, и выбор группы (handlers/group_pick) — поэтому отдельно
от обоих: раньше жил в handlers/start и сцеплял его с group_pick в клубок.
Ответы на кнопки (opt:…) и /optional — по-прежнему в handlers/start.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from kapibara.core.utils import esc


def _optional_kb(i: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎖 Хожу", callback_data=f"opt:{i}:1"),
        InlineKeyboardButton(text="Не хожу", callback_data=f"opt:{i}:0"),
    ]])


async def ask_optional(message: Message, user_id: int, all_subjects: bool = False):
    """Спросить про предметы по выбору: после /start — только те, на которые
    ещё не ответил; /optional — все (чтобы поменять ответ)."""
    from kapibara.core.config import OPTIONAL_SUBJECTS
    from database import get_optional_answers
    from kapibara.features.groups.optional_subjects import pending_for
    subjects = OPTIONAL_SUBJECTS if all_subjects else await pending_for(user_id)
    answers = await get_optional_answers(user_id) if all_subjects else {}
    for s in subjects:
        now = ("\nСейчас: " + ("хожу" if answers[s] else "не хожу")) if s in answers else ""
        await message.answer(
            f"🎖 <b>{esc(s)}</b> — ходишь?\nЕсли нет, уберу эти пары из твоего расписания и напоминаний.{now}",
            parse_mode="HTML", reply_markup=_optional_kb(OPTIONAL_SUBJECTS.index(s)))
    if all_subjects and not subjects:
        await message.answer("Предметов по выбору нет.")
