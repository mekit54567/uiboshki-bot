import json
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import get_all_subscribed_users, upsert_user
from config import STAROSTA_ID, TIMEZONE

router = Router()
TZ = ZoneInfo(TIMEZONE)

# ── Рассылка объявлений ───────────────────────────────────────────────────────

class AnnounceState(StatesGroup):
    waiting = State()


@router.message(Command("announce"))
async def cmd_announce(message: Message, state: FSMContext):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await state.set_state(AnnounceState.waiting)
    await message.answer(
        "📢 Напиши объявление — отправлю всей группе.\n"
        "Можно текст, фото или документ.\n\n"
        "/cancel — отмена"
    )


@router.message(Command("cancel"), AnnounceState.waiting)
async def cancel_announce(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(AnnounceState.waiting)
async def send_announce(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    users = await get_all_subscribed_users()

    sent = 0
    failed = 0
    wait = await message.answer(f"⏳ Рассылаю {len(users)} пользователям...")

    for uid in users:
        if uid == message.from_user.id:
            continue
        try:
            if message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id,
                                     caption=f"📢 {message.caption or ''}")
            elif message.document:
                await bot.send_document(uid, message.document.file_id,
                                        caption=f"📢 {message.caption or ''}")
            else:
                await bot.send_message(uid, f"📢 <b>Объявление от старосты:</b>\n\n{message.text}",
                                       parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await wait.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )


# ── Доска ДЗ ─────────────────────────────────────────────────────────────────

import aiosqlite
from config import DATABASE_PATH

ZAM_ID = 0  # ID зама — добавишь через /setzam


async def init_hw_table():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                content     TEXT,
                file_id     TEXT,
                file_type   TEXT,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


async def get_setting(key: str) -> str | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def is_editor(user_id: int) -> bool:
    zam = await get_setting("zam_id")
    zam_id = int(zam) if zam else 0
    return user_id == STAROSTA_ID or user_id == zam_id


async def add_hw(subject: str, content: str, file_id: str, file_type: str, created_by: int) -> int:
    await init_hw_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            INSERT INTO homework (subject, content, file_id, file_type, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (subject, content, file_id, file_type, created_by))
        await db.commit()
        return cur.lastrowid


async def get_hw_subjects() -> list[str]:
    await init_hw_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT DISTINCT subject FROM homework ORDER BY subject")
        return [r[0] for r in await cur.fetchall()]


async def get_hw_by_subject(subject: str) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM homework WHERE subject=? ORDER BY created_at DESC
        """, (subject,))
        return [dict(r) for r in await cur.fetchall()]


async def delete_hw(hw_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM homework WHERE id=?", (hw_id,))
        await db.commit()


class HWAdd(StatesGroup):
    subject = State()
    content = State()


@router.message(Command("hw"))
async def cmd_hw(message: Message):
    await init_hw_table()
    subjects = await get_hw_subjects()
    if not subjects:
        can_edit = await is_editor(message.from_user.id)
        text = "📝 <b>Доска ДЗ</b>\n\nПока пусто."
        if can_edit:
            text += "\n\nДобавить: /addhw"
        await message.answer(text, parse_mode="HTML")
        return

    buttons = [[InlineKeyboardButton(text=s, callback_data=f"hw:{i}")] for i, s in enumerate(subjects)]
    await message.answer(
        "📝 <b>Доска ДЗ</b>\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("hw:"))
async def hw_subject(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    subjects = await get_hw_subjects()
    if idx >= len(subjects):
        await callback.answer("Ошибка")
        return
    subject = subjects[idx]
    items = await get_hw_by_subject(subject)

    lines = [f"📝 <b>{subject}</b>\n"]
    for item in items:
        dt = item["created_at"][:10]
        lines.append(f"• {item['content'] or '[файл]'} <i>({dt})</i>")

    can_edit = await is_editor(callback.from_user.id)
    kb = None
    if can_edit:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="hw_back"),
            InlineKeyboardButton(text="🗑 Удалить последнее", callback_data=f"hwdel:{subject[:20]}")
        ]])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Назад", callback_data="hw_back")
        ]])

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)

    # Отправляем файлы если есть
    for item in items:
        if item.get("file_id"):
            try:
                if item["file_type"] == "photo":
                    await callback.message.answer_photo(item["file_id"], caption=item["content"] or "")
                else:
                    await callback.message.answer_document(item["file_id"], caption=item["content"] or "")
            except:
                pass


@router.callback_query(F.data == "hw_back")
async def hw_back(callback: CallbackQuery):
    subjects = await get_hw_subjects()
    buttons = [[InlineKeyboardButton(text=s, callback_data=f"hw:{i}")] for i, s in enumerate(subjects)]
    await callback.message.edit_text(
        "📝 <b>Доска ДЗ</b>\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("hwdel:"))
async def hw_del_last(callback: CallbackQuery):
    if not await is_editor(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    subject_prefix = callback.data.split(":", 1)[1]
    subjects = await get_hw_subjects()
    subject = next((s for s in subjects if s.startswith(subject_prefix)), None)
    if not subject:
        await callback.answer("Не найдено")
        return
    items = await get_hw_by_subject(subject)
    if items:
        await delete_hw(items[0]["id"])
        await callback.answer("✅ Удалено!")
    else:
        await callback.answer("Нечего удалять")


@router.message(Command("addhw"))
async def cmd_addhw(message: Message, state: FSMContext):
    if not await is_editor(message.from_user.id):
        await message.answer("❌ Только для старосты и зама.")
        return
    await state.set_state(HWAdd.subject)
    await message.answer("📚 Предмет?")


@router.message(HWAdd.subject)
async def hw_subject_input(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(HWAdd.content)
    await message.answer("📝 Текст ДЗ или прикрепи файл/фото:")


@router.message(HWAdd.content)
async def hw_content_input(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    file_id = file_type = None
    content = message.text or message.caption or ""

    if message.photo:
        file_id   = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id   = message.document.file_id
        file_type = "document"

    await add_hw(data["subject"], content, file_id, file_type, message.from_user.id)
    await message.answer(f"✅ ДЗ добавлено в раздел <b>{data['subject']}</b>!", parse_mode="HTML")


@router.message(Command("setzam"))
async def cmd_setzam(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /setzam ID\nНапример: /setzam 123456789")
        return
    await init_hw_table()
    await set_setting("zam_id", parts[1])
    await message.answer(f"✅ Зам установлен: {parts[1]}")


# ── Рейтинг активности ────────────────────────────────────────────────────────

@router.message(Command("rating"))
async def cmd_rating(message: Message):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Считаем по solver_history
        cur = await db.execute("""
            SELECT u.full_name, u.username, COUNT(s.id) as cnt
            FROM solver_history s
            JOIN users u ON u.user_id = s.user_id
            GROUP BY s.user_id
            ORDER BY cnt DESC
            LIMIT 10
        """)
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        await message.answer("📊 Рейтинг пока пустой — никто ещё не решал задачи через бота.")
        return

    medals = ["🥇", "🥈", "🥉"] + ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = ["🏆 <b>Рейтинг активности</b>\n(по количеству решённых задач)\n"]

    for i, r in enumerate(rows):
        name = r["full_name"] or f"@{r['username']}" or "Аноним"
        lines.append(f"{medals[i]} {name} — {r['cnt']} задач")

    await message.answer("\n".join(lines), parse_mode="HTML")
