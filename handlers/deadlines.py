import re
from datetime import date, datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from database import (
    add_deadline, get_active_deadlines,
    mark_deadline_done, delete_deadline,
    upsert_user,
)

router = Router()


class AddDeadline(StatesGroup):
    subject     = State()
    description = State()
    due_date    = State()
    due_time    = State()


CANCEL_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)

BACK_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Расписание сегодня"), KeyboardButton(text="📋 Дедлайны")],
        [KeyboardButton(text="➕ Добавить дедлайн"),   KeyboardButton(text="🤖 Решить задачу")],
        [KeyboardButton(text="🔕 Отписаться"),         KeyboardButton(text="🔔 Подписаться")],
    ],
    resize_keyboard=True,
)


def format_deadlines(deadlines: list[dict]) -> str:
    if not deadlines:
        return "📋 Дедлайнов нет — можно расслабиться! 🎉"

    today = date.today()
    lines = ["📋 <b>Дедлайны группы:</b>\n"]
    for d in deadlines:
        due = date.fromisoformat(d["due_date"])
        delta = (due - today).days
        if delta < 0:
            badge = "💀 просрочен"
        elif delta == 0:
            badge = "🔴 сегодня!"
        elif delta == 1:
            badge = "🟠 завтра"
        elif delta <= 3:
            badge = f"🟡 через {delta} дн."
        else:
            badge = f"🟢 через {delta} дн."

        time_part = f" {d['due_time']}" if d.get("due_time") else ""
        desc_part = f"\n   📝 {d['description']}" if d.get("description") else ""
        lines.append(
            f"[{d['id']}] <b>{d['subject']}</b>\n"
            f"   📅 {d['due_date']}{time_part} — {badge}{desc_part}"
        )
    lines.append("\n/done ID — выполнено  |  /del ID — удалить")
    return "\n\n".join(lines)


# ── Список дедлайнов ──────────────────────────────────────────────────────────

@router.message(Command("deadlines"))
@router.message(F.text == "📋 Дедлайны")
async def cmd_deadlines(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    deadlines = await get_active_deadlines()
    await message.answer(format_deadlines(deadlines), parse_mode="HTML")


# ── Добавить дедлайн — FSM ────────────────────────────────────────────────────

@router.message(Command("add"))
@router.message(F.text == "➕ Добавить дедлайн")
async def cmd_add_start(message: Message, state: FSMContext):
    await state.set_state(AddDeadline.subject)
    await message.answer(
        "📌 Название предмета/задания?\n(например: <i>Алгоритмы, лаб.1</i>)",
        parse_mode="HTML",
        reply_markup=CANCEL_KB,
    )


@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=BACK_KB)


@router.message(AddDeadline.subject)
async def add_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(AddDeadline.description)
    await message.answer(
        "📝 Краткое описание задания?\n(или отправь <i>–</i> чтобы пропустить)",
        parse_mode="HTML",
    )


@router.message(AddDeadline.description)
async def add_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description="" if desc == "–" else desc)
    await state.set_state(AddDeadline.due_date)
    await message.answer(
        "📅 Дата дедлайна?\nФормат: <b>ДД.ММ.ГГГГ</b> или <b>ДД.ММ</b>",
        parse_mode="HTML",
    )


@router.message(AddDeadline.due_date)
async def add_due_date(message: Message, state: FSMContext):
    raw = message.text.strip()
    # Поддержка ДД.ММ и ДД.ММ.ГГГГ
    match = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$", raw)
    if not match:
        await message.answer("❌ Неверный формат даты. Введи, например: <b>30.05.2025</b>", parse_mode="HTML")
        return

    day, month, year = match.groups()
    year = year or str(date.today().year)
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        await message.answer("❌ Такой даты не существует. Попробуй ещё раз.")
        return

    await state.update_data(due_date=parsed.isoformat())
    await state.set_state(AddDeadline.due_time)
    await message.answer(
        "⏰ Время сдачи?\nФормат: <b>ЧЧ:ММ</b> (например 23:59)\nИли отправь <i>–</i> чтобы пропустить.",
        parse_mode="HTML",
    )


@router.message(AddDeadline.due_time)
async def add_due_time(message: Message, state: FSMContext):
    raw = message.text.strip()
    due_time = None
    if raw != "–":
        match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
        if not match:
            await message.answer("❌ Неверный формат. Введи ЧЧ:ММ или <i>–</i>", parse_mode="HTML")
            return
        due_time = raw

    data = await state.get_data()
    await state.clear()

    deadline_id = await add_deadline(
        subject=data["subject"],
        description=data.get("description", ""),
        due_date=data["due_date"],
        due_time=due_time,
        created_by=message.from_user.id,
    )

    time_part = f" в {due_time}" if due_time else ""
    await message.answer(
        f"✅ Дедлайн добавлен (ID: {deadline_id})!\n\n"
        f"📌 <b>{data['subject']}</b>\n"
        f"📅 {data['due_date']}{time_part}",
        parse_mode="HTML",
        reply_markup=BACK_KB,
    )


# ── Отметить выполненным / удалить ────────────────────────────────────────────

@router.message(Command("done"))
async def cmd_done(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /done ID\nПример: /done 3")
        return
    did = int(parts[1])
    await mark_deadline_done(did)
    await message.answer(f"✅ Дедлайн #{did} отмечен как выполненный!")


@router.message(Command("del"))
async def cmd_del(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /del ID\nПример: /del 3")
        return
    did = int(parts[1])
    await delete_deadline(did)
    await message.answer(f"🗑 Дедлайн #{did} удалён.")
