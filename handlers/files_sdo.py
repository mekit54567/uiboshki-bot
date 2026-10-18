"""Файлы из СДО (/sdofiles): пробный прогон, перенос по предметам, выгрузка по кнопке."""

import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)

from config import STAROSTA_ID, is_starosta
from utils import esc

router = Router()


# ── Файлы из СДО: пробный прогон, потом выгрузка по кнопке ─────────────────────
# См. sdo_files.py. Результат пробного прогона держим в памяти до нажатия
# кнопки: после перезапуска бота кнопка просит прогнать /sdofiles заново.

_sdo_scans: dict[int, list] = {}
_sdo_moves: dict[int, list[tuple[int, str]]] = {}
_sdo_tasks: set[asyncio.Task] = set()


def sdo_moves(courses, current: dict[str, tuple[int, str]]) -> list[tuple[int, str]]:
    """Уже выгруженные файлы, чей курс теперь сопоставлен с другим предметом:
    [(id, новый предмет)]."""
    out = []
    for c in courses:
        if c.old or c.error:
            continue
        for f in c.files:
            fid, subject = current.get(f.source, (None, None))
            if fid is not None and subject != f.subject:
                out.append((fid, f.subject))
    return out


def _sdo_report(courses, known: set[str], current: dict | None = None) -> tuple[list[str], int]:
    from file_categories import CATEGORIES
    from utils import plural
    total = sum(len(c.files) for c in courses)
    new = sum(f.source not in known for c in courses for f in c.files)
    lines = [
        f"📚 <b>СДО: {len(courses)} {plural(len(courses), 'курс', 'курса', 'курсов')}, "
        f"{total} {plural(total, 'файл', 'файла', 'файлов')}</b> (новых: {new})",
        "Это пробный прогон — ничего не сохранил. Проверь, куда что ляжет:",
    ]
    empty, old = [], []
    for c in courses:
        if c.old:
            old.append(c.name)
            continue
        if c.error:
            lines.append(f"\n⚠️ <b>{esc(c.name)}</b> — не прочиталось: {esc(c.error[:120])}")
            continue
        if not c.files:
            empty.append(c.name)
            continue
        counts: dict[str, int] = {}
        for f in c.files:
            counts[f.category] = counts.get(f.category, 0) + 1
        by_type = " · ".join(f"{label.split(' ')[0]} {counts[key]}" for key, label in CATEGORIES if key in counts)
        fresh = sum(f.source not in known for f in c.files)
        state = "" if fresh == len(c.files) else (" · уже в боте" if not fresh else f" · новых {fresh}")
        moved = len(sdo_moves([c], current or {}))
        if moved:
            state += f" · 🔀 переложу {moved} из других папок"
        lines.append(f"\n<b>{esc(c.name)}</b>\n→ 📁 {esc(c.subject)} · {len(c.files)}: {by_type}{state}")
    if empty:
        lines.append(f"\nБез файлов: {esc(', '.join(empty))}")
    if old:
        lines.append(f"\nНе этого семестра (нет в расписании) — пропустил: {esc(', '.join(old))}")
    lines.append("\nПредмет и тип потом можно поправить в WebApp (✏️ у файла).")
    chunks, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + line
    return chunks + [cur], new


@router.message(Command("sdofiles"))
async def cmd_sdo_files(message: Message):
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        await message.answer("❌ Только для старосты.")
        return
    import sdo_files
    import sdo_parser
    from database import get_file_sources, get_sdo_file_subjects
    from schedule_parser import get_group_subjects
    if not sdo_parser.SDO_SESSION_COOKIE:
        await message.answer("⚠️ Кука СДО не задана (SDO_SESSION_COOKIE в переменных хостинга) — см. /syncsdo.")
        return
    wait = await message.answer("⏳ Смотрю, что лежит в СДО: курсы, файлы, папки… Это может занять минуту.")
    subjects = await get_group_subjects(**sdo_parser.SEMESTER_WINDOW)
    try:
        async with sdo_files.make_client(sdo_parser.SDO_SESSION_COOKIE) as client:
            courses = await sdo_files.scan(client, subjects)
    except sdo_parser.SdoSessionExpired:
        await wait.edit_text("⚠️ Кука СДО протухла — обнови SDO_SESSION_COOKIE в переменных хостинга (подробно — /syncsdo).")
        return
    except Exception as e:
        await wait.edit_text(f"❌ СДО не ответил: {esc(str(e) or type(e).__name__)}", parse_mode="HTML")
        return
    if not courses:
        await wait.edit_text("🤷 В СДО не нашёл ни одного курса — возможно, кука от другого аккаунта.")
        return
    current = await get_sdo_file_subjects()
    chunks, new = _sdo_report(courses, await get_file_sources(), current)
    moves = sdo_moves(courses, current)
    from utils import plural
    rows = []
    if moves:
        _sdo_moves[message.from_user.id] = moves
        rows.append([InlineKeyboardButton(
            text=f"🔀 Переложить {len(moves)} {plural(len(moves), 'файл', 'файла', 'файлов')} по предметам",
            callback_data="sdof:mv")])
    if new:
        _sdo_scans[message.from_user.id] = courses
        rows.append([InlineKeyboardButton(
            text=f"📥 Загрузить {new} {plural(new, 'файл', 'файла', 'файлов')}", callback_data="sdof:go")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    await wait.edit_text(chunks[0], parse_mode="HTML", reply_markup=kb if len(chunks) == 1 else None)
    for i, chunk in enumerate(chunks[1:], 2):
        await message.answer(chunk, parse_mode="HTML", reply_markup=kb if i == len(chunks) else None)


@router.callback_query(F.data == "sdof:mv")
async def sdo_files_move(callback: CallbackQuery):
    if STAROSTA_ID and not is_starosta(callback.from_user.id):
        await callback.answer("Только для старосты", show_alert=True)
        return
    moves = _sdo_moves.pop(callback.from_user.id, None)
    if not moves:
        await callback.answer("Список устарел — запусти /sdofiles ещё раз", show_alert=True)
        return
    from database import set_files_subject
    await set_files_subject(moves)
    from utils import plural
    await callback.answer(f"Переложил {len(moves)} {plural(len(moves), 'файл', 'файла', 'файлов')}", show_alert=True)
    try:
        kb = callback.message.reply_markup
        rows = [r for r in (kb.inline_keyboard if kb else []) if r[0].callback_data != "sdof:mv"]
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    except Exception:
        pass


@router.callback_query(F.data == "sdof:go")
async def sdo_files_go(callback: CallbackQuery):
    if STAROSTA_ID and not is_starosta(callback.from_user.id):
        await callback.answer("Только для старосты", show_alert=True)
        return
    if any(not t.done() for t in _sdo_tasks):
        # вторая выгрузка тех же файлов параллельно — дубли в «Файлах»
        await callback.answer("Выгрузка уже идёт — дождись сообщения о ней", show_alert=True)
        return
    courses = _sdo_scans.pop(callback.from_user.id, None)
    if not courses:
        await callback.answer("Список устарел — запусти /sdofiles ещё раз", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    files = [f for c in courses for f in c.files]
    status = await callback.message.answer("📥 Выгружаю файлы из СДО… Займёт несколько минут, я напишу.")
    task = asyncio.create_task(_sdo_import(callback.bot, callback.message.chat.id, status, files))
    _sdo_tasks.add(task)
    task.add_done_callback(_sdo_tasks.discard)


async def _sdo_import(bot: Bot, chat_id: int, status: Message, files: list):
    import sdo_files
    import sdo_parser
    last = [0.0]

    async def progress(done, total):
        now = asyncio.get_running_loop().time()
        if done == total or now - last[0] > 5:   # не чаще раза в 5 с — лимиты на правку
            last[0] = now
            try:
                await status.edit_text(f"📥 Выгружаю файлы из СДО… {done} из {total}")
            except Exception:
                pass

    try:
        async with sdo_files.make_client(sdo_parser.SDO_SESSION_COOKIE) as client:
            st = await sdo_files.import_files(bot, chat_id, client, files, progress)
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Выгрузка прервалась: {esc(str(e) or type(e).__name__)}", parse_mode="HTML")
        return
    lines = [f"✅ <b>Из СДО добавлено: {st['added']}</b>"]
    if st["with_text"]:
        lines.append(f"📖 ИИ прочитал: {st['with_text']} — отвечает по ним в чате и /solve_lectures")
    if st["skipped"]:
        lines.append(f"♻️ Уже были: {st['skipped']}")
    if st["too_big"]:
        lines.append(f"🐘 Больше 45 МБ, не пролезли в Telegram: {st['too_big']}")
    if st["not_file"]:
        lines.append(f"🔗 Не файлы (ссылки/страницы): {st['not_file']}")
    if st["failed"]:
        lines.append(f"⚠️ Не скачались: {st['failed']} — можно повторить /sdofiles")
    if st.get("expired"):
        lines.append("⚠️ Кука СДО протухла посередине — обнови SDO_SESSION_COOKIE и повтори /sdofiles.")
    lines.append("\nСмотреть: /files или в приложении: ☰ Ещё → Файлы.")
    if st["added"]:
        lines.append("Названия как в СДО — сделать понятными («Лекция 3. Тема»): /tidyfiles")
    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
