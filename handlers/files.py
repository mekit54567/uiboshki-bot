import json
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import add_file, get_files, delete_file, search_files
from config import STAROSTA_ID
from keyboards import MAIN_KB, CANCEL_KB

router = Router()


class UploadFile(StatesGroup):
    waiting_file    = State()
    waiting_title   = State()
    waiting_subject = State()


def subjects_keyboard(subjects: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура с предметами — используем индекс вместо названия."""
    buttons = []
    for i, s in enumerate(subjects):
        buttons.append([InlineKeyboardButton(text=s, callback_data=f"fsj:{i}")])
    buttons.append([InlineKeyboardButton(text="📋 Все файлы", callback_data="fsj:all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def files_keyboard(files: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for f in files[:30]:
        name = f["title"][:35]
        buttons.append([InlineKeyboardButton(text=f"📄 {name}", callback_data=f"fget:{f['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="fbk")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("files"))
@router.message(F.text == "📁 Файлы")
async def cmd_files(message: Message):
    files = await get_files()
    if not files:
        await message.answer("📁 Файлов пока нет.\n\nЗагрузить: /upload")
        return
    subjects = sorted(set(f["subject"] for f in files if f.get("subject")))
    await message.answer(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )


@router.message(Command("search"))
async def cmd_search(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "🔎 Использование: <code>/search матстат лекция</code>\n"
            "Ищет по названию, предмету и имени файла.",
            parse_mode="HTML"
        )
        return

    results = await search_files(parts[1])
    if not results:
        await message.answer(f"🔎 По запросу «{parts[1]}» ничего не найдено.")
        return

    await message.answer(
        f"🔎 <b>Нашёл {len(results)}:</b>",
        parse_mode="HTML",
        reply_markup=files_keyboard(results)
    )


@router.callback_query(F.data.startswith("fsj:"))
async def files_by_subject(callback: CallbackQuery):
    idx = callback.data.split(":", 1)[1]
    all_files = await get_files()

    if idx == "all":
        files = all_files
        title = "Все файлы"
    else:
        subjects = sorted(set(f["subject"] for f in all_files if f.get("subject")))
        try:
            subject = subjects[int(idx)]
        except (ValueError, IndexError):
            await callback.answer("Ошибка")
            return
        files = [f for f in all_files if f.get("subject") == subject]
        title = subject

    if not files:
        await callback.answer("Файлов нет")
        return

    await callback.message.edit_text(
        f"📁 <b>{title}</b> ({len(files)} файлов):",
        parse_mode="HTML",
        reply_markup=files_keyboard(files)
    )


@router.callback_query(F.data == "fbk")
async def files_back(callback: CallbackQuery):
    files = await get_files()
    subjects = sorted(set(f["subject"] for f in files if f.get("subject")))
    await callback.message.edit_text(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )


@router.callback_query(F.data.startswith("fget:"))
async def send_file(callback: CallbackQuery, bot: Bot):
    fid = int(callback.data.split(":")[1])
    files = await get_files()
    f = next((x for x in files if x["id"] == fid), None)
    if not f:
        await callback.answer("Файл не найден")
        return
    try:
        await bot.send_document(
            callback.message.chat.id,
            f["file_id"],
            caption=f"📄 {f['title']}\n📚 {f['subject']}"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ── Загрузка файла вручную ────────────────────────────────────────────────────

@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    await state.set_state(UploadFile.waiting_file)
    await message.answer("📎 Прикрепи файл:", reply_markup=CANCEL_KB)


@router.message(UploadFile.waiting_file, F.document | F.photo)
async def receive_file(message: Message, state: FSMContext):
    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name or "файл"
    else:
        file_id   = message.photo[-1].file_id
        file_name = "фото"
    await state.update_data(file_id=file_id, file_name=file_name)
    await state.set_state(UploadFile.waiting_title)
    await message.answer("📝 Название файла?")


@router.message(UploadFile.waiting_title, F.text)
async def receive_title(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(UploadFile.waiting_subject)
    await message.answer("📚 Предмет? (или <i>–</i> пропустить)", parse_mode="HTML")


@router.message(UploadFile.waiting_subject, F.text)
async def receive_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    data    = await state.get_data()
    subject = "" if message.text.strip() == "–" else message.text.strip()
    await state.clear()
    fid = await add_file(data["title"], subject, data["file_id"], data["file_name"], message.from_user.id)

    # Пытаемся сразу вытащить текст (PDF/DOCX/PPTX/TXT) для решалки по лекциям
    # (Фаза 9) — не блокирует сохранение файла, если не получилось (скан,
    # неподдерживаемый формат, файл недоступен для скачивания и т.д.).
    from file_text import extract_and_save
    got_text = await extract_and_save(message.bot, fid, data["file_id"], data["file_name"])
    lecture_note = "\n📖 Добавлен в контекст лекций для решалки." if got_text else ""

    await message.answer(
        f"✅ Файл сохранён! (ID: {fid})\n📄 <b>{data['title']}</b>{lecture_note}",
        parse_mode="HTML", reply_markup=MAIN_KB
    )


@router.message(Command("delfile"))
async def cmd_delfile(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delfile ID")
        return
    await delete_file(int(parts[1]))
    await message.answer(f"🗑 Файл #{parts[1]} удалён.")


# ── Синхронизация файлов из локальной базы ────────────────────────────────────

@router.message(Command("syncfiles"))
async def cmd_syncfiles(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await message.answer(
        "📤 Пришли файл <b>files_export.json</b>",
        parse_mode="HTML"
    )


# ВАЖНО: StateFilter(None) — без этого фильтра этот хендлер перехватывал ЛЮБОЙ
# документ в ЛЮБОМ активном FSM-состоянии (включая HWAdd.content из announce.py,
# т.к. files_router регистрируется раньше announce_router в register_handlers),
# и /addhw с прикреплённым файлом молча ломался: документ сюда прилетал, имя не
# оканчивалось на .json, хендлер тихо выходил — а hw_content_input так и не
# вызывался. Теперь этот хендлер реагирует только вне активных диалогов.
@router.message(F.document, StateFilter(None))
async def handle_sync_json(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        return
    if not message.document.file_name.endswith('.json'):
        return

    fname = message.document.file_name.lower()
    is_files_sync     = 'files' in fname or 'export' in fname
    is_deadline_sync  = 'deadline' in fname

    if not is_files_sync and not is_deadline_sync:
        return

    # ── Импорт дедлайнов ──────────────────────────────────────────────────────
    if is_deadline_sync:
        from database import add_deadline
        wait = await message.answer("⏳ Импортирую дедлайны...")
        try:
            bot  = message.bot
            file = await bot.get_file(message.document.file_id)
            data = await bot.download_file(file.file_path)
            deadlines = json.loads(data.read().decode('utf-8'))

            # Поддержка формата {"assignments": [...]} и просто [...]
            if isinstance(deadlines, dict):
                assignments = deadlines.get('assignments', [])
            else:
                assignments = deadlines

            from datetime import date
            today = date.today().isoformat()

            added = skipped = 0
            for d in assignments:
                if not isinstance(d, dict):
                    skipped += 1
                    continue
                due = d.get('due_date', '')
                if not due or due < today:
                    skipped += 1
                    continue
                # Формируем название: "СР-2 (Математика)"
                name = d.get('name') or d.get('subject') or 'Без названия'
                course = d.get('course_name', '')
                subject = f"{name} ({course})" if course else name
                try:
                    await add_deadline(
                        subject=subject,
                        description=d.get('description', ''),
                        due_date=due,
                        due_time=d.get('due_time', ''),
                        created_by=0
                    )
                    added += 1
                except Exception:
                    skipped += 1

            await wait.edit_text(
                f"✅ Дедлайны импортированы!\n\nДобавлено: {added}\nПропущено: {skipped}"
            )
        except Exception as e:
            await wait.edit_text(f"❌ Ошибка: {e}")
        return

    # ── Импорт файлов ─────────────────────────────────────────────────────────
    wait = await message.answer("⏳ Синхронизирую файлы...")
    try:
        bot  = message.bot
        file = await bot.get_file(message.document.file_id)
        data = await bot.download_file(file.file_path)
        files = json.loads(data.read().decode('utf-8'))

        # Загружаем все существующие file_id одним запросом — правильная проверка дублей
        all_existing = await get_files()
        existing_ids = {x['file_id'] for x in all_existing}

        added = skipped = with_text = 0
        for f in files:
            if not f.get('file_id') or f.get('title') == 'Файл':
                skipped += 1
                continue
            if f['file_id'] in existing_ids:
                skipped += 1
                continue
            new_fid = await add_file(
                title=f.get('title', 'Без названия'),
                subject=f.get('subject', ''),
                file_id=f['file_id'],
                file_name=f.get('file_name', ''),
                uploaded_by=0
            )
            existing_ids.add(f['file_id'])  # чтобы не дублировать внутри одного JSON
            added += 1

            # Тот же текст-экстрактор, что и в ручной загрузке (см. receive_subject
            # выше) — при массовом импорте это может занять время (последовательно
            # качаем и парсим каждый файл), но синк — редкая ручная операция
            # старосты, а не то, что дёргается на каждый чих.
            from file_text import extract_and_save
            if await extract_and_save(bot, new_fid, f['file_id'], f.get('file_name', '')):
                with_text += 1

        await wait.edit_text(
            f"✅ Синхронизация завершена!\n\nДобавлено: {added}\nС текстом лекции: {with_text}\nПропущено: {skipped}"
        )
    except Exception as e:
        await wait.edit_text(f"❌ Ошибка: {e}")
