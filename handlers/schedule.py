from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from schedule_parser import (
    get_today_schedule, get_tomorrow_schedule, get_week_schedule, get_next_lesson,
    get_next_week_schedule, search_by_teacher, search_by_room, format_search_results,
)
from database import upsert_user, add_lesson_note, get_lesson_notes
from keyboards import CANCEL_KB, MAIN_KB

router = Router()


class NoteAdd(StatesGroup):
    choose_day = State()
    waiting_text = State()


def _day_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Сегодня", callback_data="note_day:today"),
        InlineKeyboardButton(text="🌅 Завтра", callback_data="note_day:tomorrow"),
    ], [
        InlineKeyboardButton(text="❌ Отмена", callback_data="note_day:cancel"),
    ]])


async def _notes_block(date_str: str) -> str:
    notes = await get_lesson_notes(date_str)
    if not notes:
        return ""
    lines = ["\n\n📌 <b>Заметки:</b>"]
    for n in notes:
        subj = f"[{n['subject']}] " if n.get("subject") else ""
        lines.append(f"• {subj}{n['text']}")
    return "\n".join(lines)


@router.message(Command("schedule"))
@router.message(F.text == "📅 Сегодня")
async def cmd_today(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    wait = await message.answer("⏳ Загружаю...")
    text = await get_today_schedule()
    text += await _notes_block(date.today().isoformat())
    await wait.edit_text(text, parse_mode="HTML")


@router.message(Command("tomorrow"))
@router.message(F.text == "🌅 Завтра")
async def cmd_tomorrow(message: Message):
    wait = await message.answer("⏳ Загружаю...")
    text = await get_tomorrow_schedule()
    text += await _notes_block((date.today() + timedelta(days=1)).isoformat())
    await wait.edit_text(text, parse_mode="HTML")


@router.message(Command("week"))
@router.message(F.text == "📆 Неделя")
async def cmd_week(message: Message):
    wait = await message.answer("⏳ Загружаю неделю...")
    text = await get_week_schedule()
    await wait.delete()
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("nextweek"))
@router.message(F.text == "📆 След. неделя")
async def cmd_next_week(message: Message):
    wait = await message.answer("⏳ Загружаю следующую неделю...")
    text = await get_next_week_schedule()
    await wait.delete()
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("next"))
@router.message(F.text == "⏭ Следующая")
async def cmd_next(message: Message):
    wait = await message.answer("⏳ Смотрю...")
    await wait.edit_text(await get_next_lesson(), parse_mode="HTML")


# ── Поиск по преподавателю / аудитории ──────────────────────────────────────
# Ищем в рамках расписания своей группы (см. schedule_parser.py — почему не
# сделан поиск по всему университету). На ближайшие 2 недели, чтобы поймать
# и пары через неделю (расписание в основном по INTERVAL=2).

@router.message(Command("teacher"))
async def cmd_teacher(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("👤 Использование: <code>/teacher Дзюрдзя</code>", parse_mode="HTML")
        return
    query = parts[1].strip()
    wait = await message.answer("⏳ Ищу...")
    results = await search_by_teacher(query)
    text = format_search_results(results, f"👤 Пар с «{query}» в ближайшие 2 недели не нашёл.")
    header = f"👤 <b>{query}</b>\n" if results else ""
    await wait.edit_text(header + text, parse_mode="HTML")


@router.message(Command("room"))
async def cmd_room(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("🚪 Использование: <code>/room А-18</code>", parse_mode="HTML")
        return
    query = parts[1].strip()
    wait = await message.answer("⏳ Ищу...")
    results = await search_by_room(query)
    text = format_search_results(results, f"🚪 Пар в «{query}» в ближайшие 2 недели не нашёл.")
    header = f"🚪 <b>{query}</b>\n" if results else ""
    await wait.edit_text(header + text, parse_mode="HTML")


# ── Заметки на пару ─────────────────────────────────────────────────────────
# /note [сегодня|завтра] [Предмет:] текст — быстрый вариант одной строкой,
# либо просто /note без аргументов — тогда спрашиваем день через инлайн-кнопки
# и текст отдельным сообщением (FSM). Заметка привязывается к конкретной дате
# и выводится прямо под расписанием в /schedule и /tomorrow (см. _notes_block).

def _parse_quick_note(text: str) -> tuple[str, str, str] | None:
    """Пытается распарсить '/note сегодня Матан: контрольная' в один проход.
    Возвращает (date_str, subject, note_text) или None, если не похоже на
    короткую форму (тогда идём в пошаговый FSM)."""
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        return None
    _, day_word, rest = parts
    day_word = day_word.lower().strip()
    if day_word in ("сегодня", "today"):
        d = date.today()
    elif day_word in ("завтра", "tomorrow"):
        d = date.today() + timedelta(days=1)
    else:
        return None
    subject = ""
    note_text = rest.strip()
    if ":" in rest:
        maybe_subject, maybe_text = rest.split(":", 1)
        if len(maybe_subject) <= 40 and maybe_text.strip():
            subject, note_text = maybe_subject.strip(), maybe_text.strip()
    if not note_text:
        return None
    return d.isoformat(), subject, note_text


@router.message(Command("note"))
async def cmd_note(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")

    quick = _parse_quick_note(message.text or "")
    if quick:
        date_str, subject, note_text = quick
        await add_lesson_note(date_str, subject, note_text, message.from_user.id)
        await message.answer("✅ Заметка добавлена!", reply_markup=MAIN_KB)
        return

    await state.set_state(NoteAdd.choose_day)
    await message.answer(
        "📌 На какой день заметка?\n\n"
        "Или сразу одной строкой: <code>/note сегодня Матан: контрольная в 401</code>",
        parse_mode="HTML",
        reply_markup=_day_kb(),
    )


@router.callback_query(NoteAdd.choose_day, F.data.startswith("note_day:"))
async def note_choose_day(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    await callback.message.delete()

    if choice == "cancel":
        await state.clear()
        await callback.bot.send_message(callback.from_user.id, "Отменено.", reply_markup=MAIN_KB)
        await callback.answer()
        return

    day = date.today() if choice == "today" else date.today() + timedelta(days=1)
    await state.update_data(note_date=day.isoformat())
    await state.set_state(NoteAdd.waiting_text)
    await callback.bot.send_message(
        callback.from_user.id,
        "✏️ Пришли текст заметки. Можно с предметом через двоеточие:\n"
        "<code>Матан: контрольная в 401</code>\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
        reply_markup=CANCEL_KB,
    )
    await callback.answer()


@router.message(Command("cancel"), NoteAdd.waiting_text)
@router.message(Command("cancel"), NoteAdd.choose_day)
async def note_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


@router.message(NoteAdd.waiting_text, F.text)
async def note_save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    date_str = data.get("note_date")

    subject = ""
    note_text = message.text.strip()
    if ":" in note_text:
        maybe_subject, maybe_text = note_text.split(":", 1)
        if len(maybe_subject) <= 40 and maybe_text.strip():
            subject, note_text = maybe_subject.strip(), maybe_text.strip()

    await add_lesson_note(date_str, subject, note_text, message.from_user.id)
    await state.clear()
    await message.answer("✅ Заметка добавлена!", reply_markup=MAIN_KB)
