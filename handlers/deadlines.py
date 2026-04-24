import re
import json
from datetime import date
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import (
    add_deadline, get_active_deadlines, mark_deadline_done,
    delete_deadline, upsert_user, get_deadline_stats,
)
from config import STAROSTA_ID

router = Router()
TZ = ZoneInfo("Europe/Moscow")

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),      KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),    KeyboardButton(text="➕ Дедлайн")],
    [KeyboardButton(text="🤖 Решить"),      KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="🗳 Голосование")],
    [KeyboardButton(text="❓ Вопрос анон"), KeyboardButton(text="🔔 Подписка"),    KeyboardButton(text="⚙️ Настройки")],
], resize_keyboard=True)


class AddDeadline(StatesGroup):
    subject     = State()
    description = State()
    due_date    = State()
    due_time    = State()


def format_date(date_str: str) -> str:
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%d.%m.%Y")
    except:
        return date_str


def progress_bar(delta: int, max_days: int = 14) -> str:
    if delta <= 0:
        return "━━━━━━━━━━ 100%"
    filled = max(0, 10 - min(int(delta / max_days * 10), 10))
    bar = "━" * filled + "╌" * (10 - filled)
    pct = max(0, min(100, filled * 10))
    return f"{bar} {pct}%"


def format_deadlines(deadlines: list[dict]) -> str:
    if not deadlines:
        return "📋 Дедлайнов нет — можно расслабиться! 🎉"

    today = date.today()
    lines = ["📋 <b>Дедлайны группы</b>\n"]

    for d in deadlines:
        due   = date.fromisoformat(d["due_date"])
        delta = (due - today).days

        if delta < 0:    badge = "💀 просрочен"
        elif delta == 0: badge = "🔴 сегодня!"
        elif delta == 1: badge = "🟠 завтра"
        elif delta <= 3: badge = f"🟡 через {delta} дн."
        else:            badge = f"🟢 через {delta} дн."

        tp       = f" в {d['due_time']}" if d.get("due_time") else ""
        desc_str = f"\n   📝 {d['description']}" if d.get("description") and d["description"] not in ("", "-") else ""

        lines.append(
            f"[{d['id']}] <b>{d['subject']}</b>\n"
            f"   📅 {format_date(d['due_date'])}{tp} — {badge}\n"
            f"   {progress_bar(delta)}{desc_str}"
        )

    lines.append("\n/done ID — выполнено  •  /del ID — удалить")
    return "\n\n".join(lines)


@router.message(Command("deadlines"))
@router.message(F.text == "📋 Дедлайны")
async def cmd_deadlines(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    deadlines = await get_active_deadlines()
    await message.answer(format_deadlines(deadlines), parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    s      = await get_deadline_stats()
    total  = s["total"]
    done   = s["done"]
    active = s["active"]
    over   = s["overdue"]
    pct    = int(done / total * 100) if total else 0
    filled = pct // 10
    bar    = "━" * filled + "╌" * (10 - filled)
    await message.answer(
        f"📊 <b>Статистика дедлайнов</b>\n\n"
        f"Всего: {total}\n"
        f"✅ Выполнено: {done}\n"
        f"🔥 Активных: {active}\n"
        f"💀 Просрочено: {over}\n\n"
        f"Прогресс: {bar} {pct}%",
        parse_mode="HTML"
    )


@router.message(Command("add"))
@router.message(F.text == "➕ Дедлайн")
async def cmd_add_start(message: Message, state: FSMContext):
    await state.set_state(AddDeadline.subject)
    await message.answer("📌 Название предмета/задания?\n(например: <i>Алгоритмы, лаб.1</i>)", parse_mode="HTML", reply_markup=CANCEL_KB)


@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


@router.message(AddDeadline.subject)
async def add_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(AddDeadline.description)
    await message.answer("📝 Описание? (или <i>–</i> пропустить)", parse_mode="HTML")


@router.message(AddDeadline.description)
async def add_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(description="" if desc == "–" else desc)
    await state.set_state(AddDeadline.due_date)
    await message.answer("📅 Дата? Формат: <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>", parse_mode="HTML")


@router.message(AddDeadline.due_date)
async def add_due_date(message: Message, state: FSMContext):
    raw   = message.text.strip()
    match = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$", raw)
    if not match:
        await message.answer("❌ Неверный формат. Например: <b>30.05</b>", parse_mode="HTML")
        return
    day, month, year = match.groups()
    year = year or str(date.today().year)
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        await message.answer("❌ Такой даты не существует.")
        return
    await state.update_data(due_date=parsed.isoformat())
    await state.set_state(AddDeadline.due_time)
    await message.answer("⏰ Время? Формат <b>ЧЧ:ММ</b> или <i>–</i>", parse_mode="HTML")


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
    did = await add_deadline(data["subject"], data.get("description", ""), data["due_date"], due_time, message.from_user.id)
    tp  = f" в {due_time}" if due_time else ""
    await message.answer(
        f"✅ <b>Дедлайн добавлен!</b> (ID: {did})\n\n"
        f"📌 {data['subject']}\n"
        f"📅 {format_date(data['due_date'])}{tp}",
        parse_mode="HTML", reply_markup=MAIN_KB
    )


@router.message(Command("done"))
async def cmd_done(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /done 3")
        return
    await mark_deadline_done(int(parts[1]))
    await message.answer(f"✅ Дедлайн #{parts[1]} выполнен!")


@router.message(Command("del"))
async def cmd_del(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /del 3")
        return
    await delete_deadline(int(parts[1]))
    await message.answer(f"🗑 Дедлайн #{parts[1]} удалён.")


# ── Импорт дедлайнов из СДО ──────────────────────────────────────────────────

SKIP_KEYWORDS = [
    "практикум", "пример решения", "образец решения",
    "методические указания", "активность", "мероприятие",
    "достижение", "научная конференция", "пример программы",
]

TODAY = date.today().isoformat()


def should_skip(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in SKIP_KEYWORDS)


@router.message(Command("importdeadlines"))
async def cmd_import_deadlines(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await message.answer("📤 Пришли файл <b>deadlines.json</b>", parse_mode="HTML")


@router.message(F.document)
async def handle_deadlines_json(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        return
    if not message.document.file_name.endswith('.json'):
        return
    if 'deadline' not in message.document.file_name.lower():
        return

    wait = await message.answer("⏳ Импортирую дедлайны...")
    try:
        bot  = message.bot
        file = await bot.get_file(message.document.file_id)
        data = await bot.download_file(file.file_path)
        content = json.loads(data.read().decode('utf-8'))
        assignments = content.get("assignments", content) if isinstance(content, dict) else content

        added = skipped = 0
        for a in assignments:
            if not a.get("due_date") or a["due_date"] < TODAY:
                skipped += 1
                continue
            if should_skip(a.get("name", "")):
                skipped += 1
                continue
            subject = f"{a['name']} ({a.get('course_name', '')})"
            await add_deadline(
                subject=subject,
                description="",
                due_date=a["due_date"],
                due_time=a.get("due_time"),
                created_by=0
            )
            added += 1

        await wait.edit_text(
            f"✅ Импорт завершён!\n\nДобавлено: {added}\nПропущено: {skipped}"
        )
    except Exception as e:
        await wait.edit_text(f"❌ Ошибка: {e}")
