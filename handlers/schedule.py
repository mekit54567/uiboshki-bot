from datetime import timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from schedule_parser import (
    get_today_schedule, get_tomorrow_schedule, get_week_schedule, get_next_lesson,
    get_next_week_schedule, format_target_schedule,
)
from mirea_schedule_api import (
    search_targets, get_baseinfo, fetch_ical, SearchUnavailable, TARGET_GROUP, TARGET_TEACHER, TARGET_ROOM,
)
from database import upsert_user, add_lesson_note, get_lesson_notes, get_or_create_calendar_token
from keyboards import CANCEL_KB, MAIN_KB
from config import WEBAPP_URL
from utils import esc, split_by_lines, today_msk

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
        subj = f"[{esc(n['subject'])}] " if n.get("subject") else ""
        lines.append(f"• {subj}{esc(n['text'])}")
    return "\n".join(lines)


@router.message(Command("schedule"))
@router.message(F.text == "📅 Сегодня")
async def cmd_today(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    wait = await message.answer("⏳ Загружаю...")
    text = await get_today_schedule()
    text += await _notes_block(today_msk().isoformat())
    await wait.edit_text(text, parse_mode="HTML")


@router.message(Command("tomorrow"))
@router.message(F.text == "🌅 Завтра")
async def cmd_tomorrow(message: Message):
    wait = await message.answer("⏳ Загружаю...")
    text = await get_tomorrow_schedule()
    text += await _notes_block((today_msk() + timedelta(days=1)).isoformat())
    await wait.edit_text(text, parse_mode="HTML")


@router.message(Command("week"))
@router.message(F.text == "📆 Неделя")
async def cmd_week(message: Message):
    wait = await message.answer("⏳ Загружаю неделю...")
    text = await get_week_schedule()
    await wait.delete()
    for chunk in split_by_lines(text):
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("nextweek"))
@router.message(F.text == "📆 След. неделя")
async def cmd_next_week(message: Message):
    wait = await message.answer("⏳ Загружаю следующую неделю...")
    text = await get_next_week_schedule()
    await wait.delete()
    for chunk in split_by_lines(text):
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("next"))
@router.message(F.text == "⏭ Следующая")
async def cmd_next(message: Message):
    wait = await message.answer("⏳ Смотрю...")
    await wait.edit_text(await get_next_lesson(), parse_mode="HTML")


# ── Личная ссылка на ICS-календарь (Фаза 12) ────────────────────────────────
# Подписка (не разовый экспорт) — календарь студента сам подтягивает
# изменения расписания/ДЗ по этой ссылке (Google/Apple/Outlook кэшируют и
# переопрашивают её сами, обычно раз в несколько часов — это поведение
# самого календарного приложения, бот на него не влияет). Ссылка приватная
# и своя у каждого (см. database.get_or_create_calendar_token) — генерируется
# лениво при первом /calendar, не при /start.
@router.message(Command("calendar"))
async def cmd_calendar(message: Message):
    if not WEBAPP_URL:
        await message.answer(
            "📅 Личный календарь скоро появится — его ещё не включили "
            "(нужен WebApp бота). Как заработает, /calendar сразу выдаст ссылку."
        )
        return
    token = await get_or_create_calendar_token(message.from_user.id)
    https_url  = f"{WEBAPP_URL.rstrip('/')}/ics/{token}"
    webcal_url = https_url.replace("https://", "webcal://", 1).replace("http://", "webcal://", 1)
    await message.answer(
        "📅 <b>Твоя личная ссылка на календарь</b>\n\n"
        "Добавляет пары как события — с ДЗ и заметками к каждой паре, если они "
        "есть (ДЗ, привязанное к дате: см. /addhw). Ссылка приватная, не делись ей.\n\n"
        f"<code>{https_url}</code>\n\n"
        "<b>Google Calendar:</b> «Другие календари» → «+» → «По URL» → вставить ссылку.\n"
        "<b>Apple Calendar:</b> Файл → «Новая подписка» → вставить ссылку "
        f"(или открой <code>{webcal_url}</code> на iPhone/Mac напрямую).\n"
        "<b>Outlook:</b> «Добавить календарь» → «Подписаться из интернета» → вставить ссылку.",
        parse_mode="HTML"
    )


# ── Поиск по преподавателю / аудитории (по всему университету) ─────────────
# Раньше искали только в рамках расписания своей группы (не было известно
# публичного API). Оказалось — есть: schedule-of.mirea.ru/schedule/api/search
# (см. mirea_schedule_api.py — как нашли и откуда). Ищем по всей базе МИРЭА,
# при нескольких совпадениях — уточняем инлайн-кнопками, дальше тянем ical
# именно этого препода/аудитории (не только пары с моей группой) на 2 недели.

_TARGET_EMOJI = {TARGET_GROUP: "👥", TARGET_TEACHER: "👤", TARGET_ROOM: "🚪"}
_TARGET_CB_PREFIX = {TARGET_GROUP: "ssg", TARGET_TEACHER: "sst", TARGET_ROOM: "ssr"}
_CB_PREFIX_TARGET = {v: k for k, v in _TARGET_CB_PREFIX.items()}
SEARCH_BUILDING_TEXT = (
    "⏳ Справочник преподавателей и групп ещё собирается — бот делает это сам "
    "после запуска, примерно полчаса. Попробуй чуть позже."
)


def _target_pick_kb(results: list[dict], target_type: int) -> InlineKeyboardMarkup:
    prefix = _TARGET_CB_PREFIX[target_type]
    buttons = [[InlineKeyboardButton(text=r["fullTitle"], callback_data=f"{prefix}:{r['id']}")] for r in results]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def render_target_schedule(target_id: int, target_type: int, title: str) -> str:
    emoji = _TARGET_EMOJI[target_type]
    title = esc(title)
    ical = await fetch_ical(target_id, target_type)
    if ical is None:
        return f"{emoji} <b>{title}</b>\n\n⚠️ Не удалось получить расписание."
    return f"{emoji} <b>{title}</b> · 2 недели\n\n{format_target_schedule(ical, target_type)}"


async def _handle_target_search(message: Message, query: str, target_type: int, label: str):
    wait = await message.answer("⏳ Ищу...")
    try:
        results = await search_targets(query, target_type)
    except SearchUnavailable:
        await wait.edit_text(SEARCH_BUILDING_TEXT)
        return
    if not results:
        await wait.edit_text(f"{_TARGET_EMOJI[target_type]} {label} «{query}» не нашёл.")
        return
    if len(results) == 1:
        r = results[0]
        text = await render_target_schedule(r["id"], target_type, r["fullTitle"])
        for i, chunk in enumerate(split_by_lines(text)):
            if i == 0:
                await wait.edit_text(chunk, parse_mode="HTML")
            else:
                await message.answer(chunk, parse_mode="HTML")
        return
    await wait.edit_text(
        f"{_TARGET_EMOJI[target_type]} Нашёл несколько совпадений — выбери:",
        reply_markup=_target_pick_kb(results, target_type)
    )


@router.message(Command("teacher"))
async def cmd_teacher(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("👤 Использование: <code>/teacher Дзюрдзя</code>", parse_mode="HTML")
        return
    await _handle_target_search(message, parts[1].strip(), TARGET_TEACHER, "Препода")


@router.message(Command("group"))
async def cmd_group(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("👥 Использование: <code>/group УИБО-03-24</code>", parse_mode="HTML")
        return
    await _handle_target_search(message, parts[1].strip(), TARGET_GROUP, "Группу")


@router.message(Command("room"))
async def cmd_room(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("🚪 Использование: <code>/room А-18</code>", parse_mode="HTML")
        return
    await _handle_target_search(message, parts[1].strip(), TARGET_ROOM, "Аудиторию")


@router.callback_query(F.data.regexp(r"^ss[gtr]:\d+$"))
async def target_pick(callback: CallbackQuery):
    prefix, raw_id = callback.data.split(":", 1)
    target_type, target_id = _CB_PREFIX_TARGET[prefix], int(raw_id)
    await callback.answer()
    info = await get_baseinfo(target_id, target_type)
    title = info["fullTitle"] if info else str(target_id)
    text = await render_target_schedule(target_id, target_type, title)
    for i, chunk in enumerate(split_by_lines(text)):
        if i == 0:
            await callback.message.edit_text(chunk, parse_mode="HTML")
        else:
            await callback.message.answer(chunk, parse_mode="HTML")


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
        d = today_msk()
    elif day_word in ("завтра", "tomorrow"):
        d = today_msk() + timedelta(days=1)
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

    day = today_msk() if choice == "today" else today_msk() + timedelta(days=1)
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
