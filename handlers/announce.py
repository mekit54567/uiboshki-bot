from datetime import date

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import get_all_subscribed_users, upsert_user
from config import STAROSTA_ID
from utils import esc, parse_day_month, today_msk

router = Router()

# ── Рассылка объявлений ───────────────────────────────────────────────────────

class AnnounceState(StatesGroup):
    waiting = State()


class ClearSemState(StatesGroup):
    confirm = State()


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
            elif message.text:
                # html_text, а не text: сохраняет форматирование старосты
                # (жирный, ссылки) и экранирует "<", "&" — с сырым text любое
                # "<3" или "R&D" в объявлении валило рассылку ВСЕМ получателям.
                await bot.send_message(uid, f"📢 <b>Объявление от старосты:</b>\n\n{message.html_text}",
                                       parse_mode="HTML")
            else:
                # Голосовое, видео, стикер и т.п. — раньше уходило текстом "None".
                await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1

    await wait.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}"
    )


# ── Очистка семестра ─────────────────────────────────────────────────────────

@router.message(Command("clearsem"))
async def cmd_clearsem(message: Message, state: FSMContext):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await state.set_state(ClearSemState.confirm)
    await message.answer(
        "⚠️ <b>Это сбросит данные прошлого семестра:</b>\n\n"
        "• Дедалйн-трекер 🗓\n"
        "• Доску ДЗ 📝\n"
        "• Файлы 📁\n"
        "• Голосования 🗳\n\n"
        "<b>Подписки, настройки напоминаний и историю решений это НЕ тронет.</b>\n\n"
        "Продолжить? Напиши <b>да</b> для подтверждения, или <b>нет</b> для отмены.",
        parse_mode="HTML"
    )


@router.message(ClearSemState.confirm, F.text)
async def clearsem_confirm(message: Message, state: FSMContext):
    answer = message.text.strip().lower()
    if answer in ("да", "yes", "y", "д"):
        from database import clear_semester_data
        await clear_semester_data()
        await state.clear()
        await message.answer("🧹 Готово! Доска чистого семестра.")
    else:
        await state.clear()
        await message.answer("Отменено — данные сохранены.")


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
        # lesson_date — привязка ДЗ к конкретной дате/паре (Фаза 12, календарь),
        # а не только к предмету "вообще". NULL — старое поведение (общее ДЗ по
        # предмету без даты), как было раньше и остаётся по умолчанию.
        try:
            await db.execute("ALTER TABLE homework ADD COLUMN lesson_date TEXT")
        except Exception:
            pass  # колонка уже есть
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


async def get_setting(key: str) -> str | None:
    # settings создаётся лениво в init_hw_table — без этого вызова is_editor
    # на свежей базе (первый /addhw до любого /hw) падал с "no such table".
    await init_hw_table()
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
    # Без isdigit() одно кривое значение (например "/setzam @username" до
    # появления проверки в cmd_setzam) навсегда роняло ValueError в каждом
    # /hw и /addhw у всех.
    zam_id = int(zam) if zam and zam.isdigit() else 0
    return user_id == STAROSTA_ID or user_id == zam_id


async def add_hw(subject: str, content: str, file_id: str, file_type: str, created_by: int,
                  lesson_date: str | None = None) -> int:
    await init_hw_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            INSERT INTO homework (subject, content, file_id, file_type, created_by, lesson_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (subject, content, file_id, file_type, created_by, lesson_date))
        await db.commit()
        return cur.lastrowid


def parse_lesson_date(raw: str, today: date | None = None) -> tuple[bool, str | None]:
    """Разбор даты пары для привязки ДЗ (Фаза 12, календарь). Возвращает
    (валидно, значение): (True, None) — пропущено ("–"/"-", ДЗ без даты, как
    раньше), (True, "YYYY-MM-DD") — валидная дата, (False, None) — неверный
    формат/несуществующая дата. Формат и выбор года без явного указания —
    как у дедлайнов (/add), см. utils.parse_day_month."""
    raw = raw.strip()
    if raw in ("–", "-"):
        return True, None
    parsed = parse_day_month(raw, today or today_msk())
    if parsed is None:
        return False, None
    return True, parsed.isoformat()


async def get_hw_for_date(date_str: str) -> list[dict]:
    """ДЗ, привязанные к конкретной дате (используется генератором ICS-фида,
    см. webapp/calendar_feed.py — матчинг по дате + вхождению предмета в
    название пары из расписания)."""
    await init_hw_table()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM homework WHERE lesson_date=? ORDER BY created_at", (date_str,)
        )
        return [dict(r) for r in await cur.fetchall()]


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
    lesson_date = State()


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

    lines = [f"📝 <b>{esc(subject)}</b>\n"]
    for item in items:
        dt = item["created_at"][:10]
        lesson_badge = ""
        if item.get("lesson_date"):
            from datetime import date as date_cls
            lesson_badge = f" 📅 к паре {date_cls.fromisoformat(item['lesson_date']).strftime('%d.%m')}"
        lines.append(f"• {esc(item['content']) or '[файл]'} <i>({dt})</i>{lesson_badge}")

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
    await callback.answer()

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
    await callback.answer()


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
    await message.answer(
        "📚 Предмет? (если будешь привязывать к дате пары — пиши словом, "
        "которое встречается в названии пары из расписания, например "
        "«анализ», а не сокращением вроде «Матан» — иначе ДЗ не найдётся "
        "в календаре)"
    )


@router.message(HWAdd.subject)
async def hw_subject_input(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("📚 Предмет пришли текстом.")
        return
    await state.update_data(subject=message.text.strip())
    await state.set_state(HWAdd.content)
    await message.answer("📝 Текст ДЗ или прикрепи файл/фото:")


@router.message(HWAdd.content)
async def hw_content_input(message: Message, state: FSMContext):
    file_id = file_type = None
    content = message.text or message.caption or ""

    if message.photo:
        file_id   = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id   = message.document.file_id
        file_type = "document"

    await state.update_data(content=content, file_id=file_id, file_type=file_type)
    await state.set_state(HWAdd.lesson_date)
    await message.answer(
        "📅 К какой паре относится? Дата в формате <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b> — "
        "тогда ДЗ появится в личном календаре (см. /calendar) у карточки этой пары. "
        "Или <i>–</i> — без привязки к дате, как раньше (только доска /hw).",
        parse_mode="HTML"
    )


@router.message(HWAdd.lesson_date)
async def hw_lesson_date_input(message: Message, state: FSMContext):
    ok, lesson_date = parse_lesson_date(message.text or "")
    if not ok:
        await message.answer(
            "❌ Неверный формат. Например: <b>30.05</b>, или <i>–</i> — без даты.",
            parse_mode="HTML"
        )
        return
    data = await state.get_data()
    await state.clear()

    await add_hw(data["subject"], data["content"], data["file_id"], data["file_type"],
                 message.from_user.id, lesson_date)
    date_note = ""
    if lesson_date:
        from datetime import date as date_cls
        date_note = f"\n📅 Привязано к паре {date_cls.fromisoformat(lesson_date).strftime('%d.%m.%Y')}"
    await message.answer(
        f"✅ ДЗ добавлено в раздел <b>{esc(data['subject'])}</b>!{date_note}", parse_mode="HTML"
    )


@router.message(Command("setzam"))
async def cmd_setzam(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Использование: /setzam ID (числовой Telegram ID, не @username)\n"
            "Например: /setzam 123456789"
        )
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
        # f"@{username}" всегда truthy (даже "@None"/"@"), поэтому "Аноним"
        # раньше не показывался никогда — вместо него было "@None".
        name = r["full_name"] or (f"@{r['username']}" if r["username"] else "Аноним")
        lines.append(f"{medals[i]} {esc(name)} — {r['cnt']} задач")

    await message.answer("\n".join(lines), parse_mode="HTML")
