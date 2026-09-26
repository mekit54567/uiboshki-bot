import asyncio
import json
import re
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
)

from database import add_file, get_files, delete_file, search_files
from config import STAROSTA_ID
from keyboards import MAIN_KB, CANCEL_KB
from utils import esc, today_msk

router = Router()


class UploadFile(StatesGroup):
    waiting_subject = State()
    waiting_file    = State()


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
        f"📁 <b>{esc(title)}</b> ({len(files)} файлов):",
        parse_mode="HTML",
        reply_markup=files_keyboard(files)
    )
    await callback.answer()


@router.callback_query(F.data == "fbk")
async def files_back(callback: CallbackQuery):
    files = await get_files()
    subjects = sorted(set(f["subject"] for f in files if f.get("subject")))
    await callback.message.edit_text(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )
    await callback.answer()


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
            caption=f"📄 {f['title']}" + (f"\n📚 {f['subject']}" if f.get("subject") else "")
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ── Загрузка файла вручную ────────────────────────────────────────────────────

# ── Загрузка файлов: пачкой, предмет выбирается один раз ─────────────────────
# Раньше /upload принимал ровно один файл и спрашивал его название и предмет
# текстом — залить лекции за семестр было мучением. Теперь: выбрал предмет
# (кнопки — настоящие названия из расписания группы и уже известные по
# файлам), дальше пересылаешь сколько угодно файлов подряд (хоть альбомом
# из чата группы). Название — из имени файла, текст PDF/DOCX/PPTX/TXT сразу
# уходит в контекст ИИ (решалка по лекциям). Прогресс — одним сообщением,
# которое обновляется, а не ответом на каждый файл.

UPLOAD_DONE = "✅ Готово"
UPLOAD_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=UPLOAD_DONE), KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)
_upload_locks: dict[int, asyncio.Lock] = {}


def title_from_filename(file_name: str) -> str:
    """"Лекция_3_Бизнес-анализ.pdf" -> "Лекция 3 Бизнес-анализ"."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", (file_name or "").strip())
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .-")
    return stem[:120] or "Файл"


async def _upload_subjects() -> list[str]:
    from schedule_parser import get_group_subjects
    known = {f["subject"] for f in await get_files() if f.get("subject")}
    return sorted(known | set(await get_group_subjects()))


def _upload_subjects_kb(subjects: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=s[:60], callback_data=f"upsj:{i}")] for i, s in enumerate(subjects[:40])]
    rows.append([InlineKeyboardButton(text="📂 Без предмета", callback_data="upsj:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    subjects = await _upload_subjects()
    await state.set_state(UploadFile.waiting_subject)
    await state.update_data(upload_subjects=subjects)
    await message.answer(
        "📤 <b>Загрузка файлов</b>\n\n"
        "Для какого предмета? Выбери кнопкой или напиши название сам.\n"
        "Дальше можно прислать сразу много файлов — хоть переслать пачкой из чата группы.",
        parse_mode="HTML", reply_markup=_upload_subjects_kb(subjects),
    )
    await message.answer("Отменить — «❌ Отмена».", reply_markup=CANCEL_KB)


async def _start_collecting(target: Message, state: FSMContext, subject: str):
    await state.set_state(UploadFile.waiting_file)
    await state.update_data(subject=subject, added=0, with_text=0, dupes=0, status_id=None)
    where = f"в «{esc(subject)}»" if subject else "без предмета"
    await target.answer(
        f"📥 Кидай файлы {where} — сколько угодно, можно пачкой.\n"
        f"PDF, DOCX, PPTX и TXT я ещё и прочитаю, чтобы ИИ отвечал по лекциям.\n\n"
        f"Закончил — жми «{UPLOAD_DONE}».",
        parse_mode="HTML", reply_markup=UPLOAD_KB,
    )


@router.callback_query(UploadFile.waiting_subject, F.data.startswith("upsj:"))
async def upload_pick_subject(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    subjects = (await state.get_data()).get("upload_subjects", [])
    subject = "" if key == "none" or not key.isdigit() or int(key) >= len(subjects) else subjects[int(key)]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_collecting(callback.message, state, subject)


@router.message(UploadFile.waiting_subject, F.text)
async def upload_type_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await _start_collecting(message, state, message.text.strip()[:80])


@router.message(UploadFile.waiting_file, F.document | F.photo)
async def receive_file(message: Message, state: FSMContext):
    # Альбом из 10 файлов — это 10 апдейтов почти одновременно: без замка
    # счётчики в FSM и одно сообщение-прогресс перетирали бы друг друга.
    lock = _upload_locks.setdefault(message.from_user.id, asyncio.Lock())
    async with lock:
        data = await state.get_data()
        subject = data.get("subject", "")
        if message.document:
            tg_file_id = message.document.file_id
            file_name = message.document.file_name or "файл"
        else:
            tg_file_id = message.photo[-1].file_id
            file_name = f"фото_{message.message_id}.jpg"

        existing = {(f.get("file_name"), f.get("subject") or "") for f in await get_files(subject or None)}
        if message.document and (file_name, subject) in existing:
            data["dupes"] = data.get("dupes", 0) + 1
        else:
            fid = await add_file(title_from_filename(file_name), subject, tg_file_id, file_name, message.from_user.id)
            from file_text import extract_and_save
            if await extract_and_save(message.bot, fid, tg_file_id, file_name):
                data["with_text"] = data.get("with_text", 0) + 1
            data["added"] = data.get("added", 0) + 1

        text = (f"📥 Загружено: <b>{data['added']}</b>"
                f" · 📖 прочитано для ИИ: <b>{data.get('with_text', 0)}</b>"
                + (f" · ♻️ уже были: {data['dupes']}" if data.get("dupes") else ""))
        status_id = data.get("status_id")
        try:
            if status_id:
                await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=status_id, parse_mode="HTML")
            else:
                status_id = (await message.answer(text, parse_mode="HTML")).message_id
        except Exception:
            status_id = (await message.answer(text, parse_mode="HTML")).message_id
        await state.update_data(added=data["added"], with_text=data.get("with_text", 0),
                                dupes=data.get("dupes", 0), status_id=status_id)


@router.message(UploadFile.waiting_file, F.text)
async def upload_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if message.text != UPLOAD_DONE:
        await message.answer("Загрузка закончена.", reply_markup=MAIN_KB)
        return
    added, with_text = data.get("added", 0), data.get("with_text", 0)
    if not added:
        await message.answer("Файлов не было — ничего не сохранил.", reply_markup=MAIN_KB)
        return
    subject = data.get("subject", "")
    lecture = (f"\n📖 {with_text} из них — в контексте ИИ: /solve_lectures"
               + (f" → «{esc(subject)}»" if subject else "")) if with_text else ""
    await message.answer(
        f"✅ Сохранено файлов: <b>{added}</b>" + (f" в «{esc(subject)}»" if subject else "") + lecture +
        "\n\nНайти: /files",
        parse_mode="HTML", reply_markup=MAIN_KB,
    )


@router.message(Command("delfile"))
async def cmd_delfile(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delfile ID")
        return
    fid = int(parts[1])
    f = next((x for x in await get_files() if x["id"] == fid), None)
    if not f:
        await message.answer("❌ Файл с таким ID не найден.")
        return
    # Раньше проверки не было вообще: любой участник мог удалить любой файл
    # группы — и вместе с ним текст лекции из контекста решалки (delete_file
    # чистит и file_text). Теперь — только тот, кто загрузил, или староста/зам.
    # STAROSTA_ID не задан — как и у остальных админ-команд, без ограничений.
    from handlers.announce import is_editor
    if (STAROSTA_ID and f.get("uploaded_by") != message.from_user.id
            and not await is_editor(message.from_user.id)):
        await message.answer("❌ Удалить файл может только тот, кто его загрузил, или староста.")
        return
    await delete_file(fid)
    await message.answer(f"🗑 Файл #{fid} удалён.")


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
    fname = (message.document.file_name or "").lower()
    if not fname.endswith('.json'):
        return

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

            today = today_msk().isoformat()

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
