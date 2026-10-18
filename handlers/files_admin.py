"""Команды старосты по файлам и базе: /delfile, /backup, /tidyfiles, /restore, /syncfiles."""

import asyncio
import json
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)

from database import add_file, get_files, delete_file
from config import STAROSTA_ID, is_starosta
from utils import esc, today_msk

router = Router()


class RestoreDb(StatesGroup):
    waiting_file = State()


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
    # Файл удаляется у всей группы (вместе с текстом для ИИ), поэтому
    # удалять может только староста — так решил владелец. Раньше мог и тот,
    # кто загрузил, и зам. STAROSTA_ID не задан — как у остальных
    # админ-команд, без ограничений.
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        await message.answer("❌ Удалять файлы может только староста — файл пропадёт у всей группы.")
        return
    await delete_file(fid)
    await message.answer(f"🗑 Файл #{fid} удалён.")


@router.message(Command("backup"))
async def cmd_backup(message: Message):
    """Копия базы прямо сейчас (обычно приходит сама каждую ночь)."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        await message.answer("❌ Только для старосты.")
        return
    from backup import send_backup
    await send_backup(message.bot, message.chat.id, silent=False)


# ── Понятные названия файлов (/tidyfiles) ───────────────────────────────────

async def _tidy_plan() -> tuple[list[dict], dict[int, str], set[int]]:
    """Файлы, все переименования и какие из них — темы из текста лекций."""
    from database import get_text_heads
    from file_categories import category_of
    from file_names import text_titles, tidy_titles
    files = await get_files()
    names = tidy_titles(files)
    lectures = [f["id"] for f in files if category_of(f) == "lecture"]
    topics = text_titles(files, names, await get_text_heads(lectures))
    return files, {**names, **topics}, set(topics)


@router.message(Command("tidyfiles"))
async def cmd_tidyfiles(message: Message):
    """«ЛК3_бизнес.pdf» → «Лекция 3. Бизнес» по всем предметам, «Лекция 8» →
    «Лекция 8. Тема» из текста файла: сначала показать, что поменяется;
    «/tidyfiles undo» — вернуть как было."""
    if not is_starosta(message.from_user.id):
        await message.answer("❌ Только для старосты.")
        return
    from database import undo_file_renames
    from file_names import preview
    if (message.text or "").split()[1:2] == ["undo"]:
        n = await undo_file_renames()
        await message.answer(f"↩️ Вернул прежние названия: {n} файлов." if n else "Нечего возвращать.")
        return
    files, changes, from_text = await _tidy_plan()
    if not changes:
        await message.answer("✨ Все названия уже понятные — менять нечего.")
        return
    lines = preview(files, changes, marked=from_text)
    more = len(changes) - min(len(changes), 25)
    names_only = len(changes) - len(from_text)
    row = [InlineKeyboardButton(text=f"✅ Переименовать ({len(changes)})", callback_data="tidy:yes")]
    if from_text and names_only:
        row.append(InlineKeyboardButton(text=f"Без 📄 ({names_only})", callback_data="tidy:names"))
    kb = InlineKeyboardMarkup(inline_keyboard=[row, [InlineKeyboardButton(text="Отмена", callback_data="tidy:no")]])
    await message.answer(
        "🧹 <b>Понятные названия файлов</b>\nТип и номер по названию, тема — если есть."
        + (f"\n📄 — тема из текста самой лекции или её пары PDF ↔ PPTX ({len(from_text)}), проверь их."
           if from_text else "")
        + " Вот что поменяется:"
        + "\n".join(lines) + (f"\n\n…и ещё {more}" if more > 0 else "")
        + ("\n\nПолный список — в файле ниже." if more > 0 else "")
        + "\n\nВернуть как было — <code>/tidyfiles undo</code>.",
        parse_mode="HTML", reply_markup=kb)
    if more > 0:
        from aiogram.types import BufferedInputFile
        from file_names import full_list
        await message.answer_document(
            BufferedInputFile(full_list(files, changes, marked=from_text).encode("utf-8"), "tidyfiles.txt"),
            caption=f"Все {len(changes)} переименований: было → стало")


@router.callback_query(F.data.startswith("tidy:"))
async def tidy_confirm(callback: CallbackQuery):
    if not is_starosta(callback.from_user.id):
        await callback.answer("Только для старосты", show_alert=True)
        return
    if callback.data not in ("tidy:yes", "tidy:names"):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")
        return
    from database import rename_files
    _, changes, from_text = await _tidy_plan()                 # заново: файлы могли измениться
    if callback.data == "tidy:names":
        changes = {fid: t for fid, t in changes.items() if fid not in from_text}
    n = await rename_files(changes)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Переименовал {n} файлов. Вернуть — <code>/tidyfiles undo</code>.",
                                  parse_mode="HTML")
    await callback.answer()


# ── Восстановление базы из копии (/restore) ─────────────────────────────────
# Проверенная копия ждёт подтверждения тут (uid → путь к временному .db).
_restore_pending: dict[int, str] = {}


@router.message(Command("restore"))
async def cmd_restore(message: Message, state: FSMContext):
    if not is_starosta(message.from_user.id):
        await message.answer("❌ Только для старосты.")
        return
    await state.set_state(RestoreDb.waiting_file)
    await message.answer(
        "♻️ <b>Восстановление базы</b>\n\nПришли файл копии — <code>uiboshki-….db.gz</code> из /backup "
        "(до 20 МБ). Я проверю его и покажу, что внутри; ничего не заменю без твоего «да».\n\n"
        "Передумал — /cancel или «❌ Отмена».", parse_mode="HTML")


@router.message(RestoreDb.waiting_file, F.document)
async def restore_file(message: Message, state: FSMContext):
    import os
    from backup import MAX_RESTORE_BYTES, RestoreError, inspect_backup
    await state.clear()
    if not is_starosta(message.from_user.id):
        return
    doc = message.document
    if doc.file_size and doc.file_size > MAX_RESTORE_BYTES:
        await message.answer("❌ Файл больше 20 МБ — бот не может его скачать (ограничение Telegram). "
                             "Такую копию можно положить на диск /data хостинга вручную.")
        return
    buf = await message.bot.download(doc)
    try:
        # распаковка и integrity_check — секунды; не в event loop, иначе бот и WebApp стоят
        tmp, info = await asyncio.to_thread(inspect_backup, buf.read())
    except RestoreError as e:
        await message.answer(f"❌ Копия не подходит: {esc(str(e))}", parse_mode="HTML")
        return
    old = _restore_pending.pop(message.from_user.id, None)
    if old and os.path.exists(old):
        os.remove(old)
    _restore_pending[message.from_user.id] = tmp
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="♻️ Да, восстановить", callback_data="restore:yes"),
        InlineKeyboardButton(text="Отмена", callback_data="restore:no"),
    ]])
    await message.answer(
        f"✅ Копия целая ({info['size_mb']} МБ).\nВнутри: людей — <b>{info['users']}</b>, дедлайнов — "
        f"<b>{info['deadlines']}</b>, файлов — <b>{info['files']}</b>, входов СДО — <b>{info['sdo']}</b>.\n\n"
        "Заменить ею текущую базу? Перед заменой пришлю копию текущей — на всякий случай.",
        parse_mode="HTML", reply_markup=kb)


@router.message(RestoreDb.waiting_file, F.text)
async def restore_wait_text(message: Message, state: FSMContext):
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("Отменено — база не тронута.")
        return
    await message.answer("Жду файл копии (.db.gz). Передумал — /cancel.")


@router.callback_query(F.data.startswith("restore:"))
async def restore_confirm(callback: CallbackQuery):
    import os
    uid = callback.from_user.id
    tmp = _restore_pending.pop(uid, None)
    if not is_starosta(uid) or not tmp or not os.path.exists(tmp):
        await callback.answer("Нечего восстанавливать — пришли копию заново через /restore", show_alert=True)
        return
    if callback.data != "restore:yes":
        os.remove(tmp)
        await callback.message.edit_text("Отменено — база не тронута.")
        await callback.answer()
        return
    await callback.answer("Восстанавливаю…")
    from backup import apply_backup, keep_local_copy, send_backup
    note = "Копия прежней — сообщением выше."
    if not await send_backup(callback.bot, uid, silent=False):      # сначала — копия текущей
        # в Telegram не ушла (больше 50 МБ или база повреждена — как раз когда
        # и нужен /restore): страхуемся файлом рядом с базой на томе
        local = await keep_local_copy()
        if not local:
            os.remove(tmp)
            await callback.message.edit_text("⚠️ Не смог сохранить копию текущей базы ни в чат, ни на том — "
                                             "восстанавливать не стал.")
            return
        note = f"Прежняя база сохранена на томе: <code>{esc(os.path.basename(local))}</code>."
    try:
        await apply_backup(tmp)
    except Exception as e:
        await callback.message.edit_text(f"❌ Не получилось: {esc(str(e))}. {note}", parse_mode="HTML")
        return
    await callback.message.edit_text(f"✅ База восстановлена из копии. {note}", parse_mode="HTML")


# ── Синхронизация файлов из локальной базы ────────────────────────────────────

@router.message(Command("syncfiles"))
async def cmd_syncfiles(message: Message):
    if STAROSTA_ID and not is_starosta(message.from_user.id):
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
    if STAROSTA_ID and not is_starosta(message.from_user.id):
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
