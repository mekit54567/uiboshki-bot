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
    waiting_subject  = State()
    waiting_category = State()
    waiting_file     = State()


def subjects_keyboard(subjects: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура с предметами — используем индекс вместо названия."""
    buttons = []
    for i, s in enumerate(subjects):
        buttons.append([InlineKeyboardButton(text=s, callback_data=f"fsj:{i}")])
    buttons.append([InlineKeyboardButton(text="📋 Все файлы", callback_data="fsj:all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


FILES_PAGE = 25


def pages_label(total: int, page: int) -> str:
    pages = (total + FILES_PAGE - 1) // FILES_PAGE
    return f" · стр. {page + 1}/{pages}" if pages > 1 else ""


def files_keyboard(files: list[dict], back: str = "fbk", page: int = 0, page_cb: str | None = None) -> InlineKeyboardMarkup:
    """По FILES_PAGE файлов на страницу. Раньше показывались первые 30, а
    остальные молча пропадали — после выгрузки из СДО (сотни файлов) в
    разделе «Лекции» предмета их легко больше."""
    buttons = []
    for f in files[page * FILES_PAGE:(page + 1) * FILES_PAGE]:
        name = f["title"][:35]
        buttons.append([InlineKeyboardButton(text=f"📄 {name}", callback_data=f"fget:{f['id']}")])
    nav = []
    if page_cb and page > 0:
        nav.append(InlineKeyboardButton(text="‹ Назад", callback_data=f"{page_cb}:{page - 1}"))
    if page_cb and (page + 1) * FILES_PAGE < len(files):
        nav.append(InlineKeyboardButton(text="Дальше ›", callback_data=f"{page_cb}:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back)])
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


def _subject_files(all_files: list[dict], idx: str) -> tuple[str, list[dict]] | None:
    from file_categories import sort_files
    if idx == "all":
        return "Все файлы", sort_files(all_files)
    subjects = sorted(set(f["subject"] for f in all_files if f.get("subject")))
    try:
        subject = subjects[int(idx)]
    except (ValueError, IndexError):
        return None
    return subject, sort_files([f for f in all_files if f.get("subject") == subject])


@router.callback_query(F.data.startswith("fsj:"))
async def files_by_subject(callback: CallbackQuery):
    """Предмет → сначала типы (лекции/практики/КР/…) с количеством, если
    их больше одного, иначе сразу файлы."""
    from file_categories import CATEGORIES, category_of
    idx = callback.data.split(":", 1)[1]
    picked = _subject_files(await get_files(), idx)
    if not picked:
        await callback.answer("Ошибка")
        return
    title, files = picked
    if not files:
        await callback.answer("Файлов нет")
        return
    counts: dict[str, int] = {}
    for f in files:
        counts[category_of(f)] = counts.get(category_of(f), 0) + 1
    if len(counts) > 1:
        rows = [[InlineKeyboardButton(text=f"{label} · {counts[key]}", callback_data=f"fct:{idx}:{key}")]
                for key, label in CATEGORIES if key in counts]
        rows.append([InlineKeyboardButton(text=f"📋 Все файлы · {len(files)}", callback_data=f"fct:{idx}:*")])
        rows.append([InlineKeyboardButton(text="◀️ Предметы", callback_data="fbk")])
        await callback.message.edit_text(
            f"📁 <b>{esc(title)}</b>\n\nЧто нужно?", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    else:
        await callback.message.edit_text(
            f"📁 <b>{esc(title)}</b> ({len(files)}){pages_label(len(files), 0)}:", parse_mode="HTML",
            reply_markup=files_keyboard(files, page_cb=f"fct:{idx}:*"),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fct:"))
async def files_by_category(callback: CallbackQuery):
    from file_categories import LABELS, category_of
    parts = callback.data.split(":")
    idx, cat = parts[1], parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    picked = _subject_files(await get_files(), idx)
    if not picked:
        await callback.answer("Ошибка")
        return
    title, files = picked
    if cat != "*":
        files = [f for f in files if category_of(f) == cat]
    if not files:
        await callback.answer("Файлов нет")
        return
    label = LABELS.get(cat, "📋 Все файлы")
    page = min(page, (len(files) - 1) // FILES_PAGE)
    kb = files_keyboard(files, back=f"fsj:{idx}", page=page, page_cb=f"fct:{idx}:{cat}")
    await callback.message.edit_text(
        f"📁 <b>{esc(title)}</b> → {label} ({len(files)}){pages_label(len(files), page)}:",
        parse_mode="HTML", reply_markup=kb,
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


async def _ask_category(target: Message, state: FSMContext, subject: str):
    """Второй шаг: тип файлов (лекции/практики/КР/…) — или «определить по
    названию» для смешанной пачки."""
    from file_categories import CATEGORIES
    await state.update_data(subject=subject)
    await state.set_state(UploadFile.waiting_category)
    rows = [[InlineKeyboardButton(text=label, callback_data=f"upct:{key}")] for key, label in CATEGORIES]
    rows.insert(0, [InlineKeyboardButton(text="✨ Определить по названию каждого файла", callback_data="upct:auto")])
    where = f"«{esc(subject)}»" if subject else "без предмета"
    await target.answer(f"📚 {where}\n\nЧто загружаешь?", parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(UploadFile.waiting_category, F.data.startswith("upct:"))
async def upload_pick_category(callback: CallbackQuery, state: FSMContext):
    from file_categories import LABELS
    key = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_collecting(callback.message, state, (await state.get_data()).get("subject", ""),
                            key if key in LABELS else None)


async def _start_collecting(target: Message, state: FSMContext, subject: str, category: str | None = None):
    from file_categories import LABELS
    await state.set_state(UploadFile.waiting_file)
    await state.update_data(subject=subject, category=category, added=0, with_text=0, dupes=0, status_id=None)
    where = f"в «{esc(subject)}»" if subject else "без предмета"
    if category:
        where += f" → {LABELS[category]}"
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
    await _ask_category(callback.message, state, subject)


@router.message(UploadFile.waiting_subject, F.text)
async def upload_type_subject(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await _ask_category(message, state, message.text.strip()[:80])


@router.message(UploadFile.waiting_category, F.text)
async def upload_category_text(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    await message.answer("Выбери тип кнопкой выше — или сразу кидай файлы, тип определю по названию.")


# Файлы, присланные сразу после предмета (не нажав тип), тоже принимаем —
# с типом по названию: пересылать пачку и потом обнаружить, что ничего не
# сохранилось, обиднее, чем лишний раз не выбрать кнопку.
@router.message(StateFilter(UploadFile.waiting_file, UploadFile.waiting_category), F.document | F.photo)
async def receive_file(message: Message, state: FSMContext):
    # Альбом из 10 файлов — это 10 апдейтов почти одновременно: без замка
    # счётчики в FSM и одно сообщение-прогресс перетирали бы друг друга.
    lock = _upload_locks.setdefault(message.from_user.id, asyncio.Lock())
    async with lock:
        if await state.get_state() == UploadFile.waiting_category.state:
            await state.set_state(UploadFile.waiting_file)
            await state.update_data(category=None, added=0, with_text=0, dupes=0, status_id=None)
            await message.answer(f"✨ Тип определю по названию каждого файла. Закончишь — жми «{UPLOAD_DONE}».",
                                 reply_markup=UPLOAD_KB)
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
            fid = await add_file(title_from_filename(file_name), subject, tg_file_id, file_name,
                                 message.from_user.id, category=data.get("category"))
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
    # Файл удаляется у всей группы (вместе с текстом для ИИ), поэтому
    # удалять может только староста — так решил владелец. Раньше мог и тот,
    # кто загрузил, и зам. STAROSTA_ID не задан — как у остальных
    # админ-команд, без ограничений.
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Удалять файлы может только староста — файл пропадёт у всей группы.")
        return
    await delete_file(fid)
    await message.answer(f"🗑 Файл #{fid} удалён.")


# ── Файлы из СДО: пробный прогон, потом выгрузка по кнопке ─────────────────────
# См. sdo_files.py. Результат пробного прогона держим в памяти до нажатия
# кнопки: после перезапуска бота кнопка просит прогнать /sdofiles заново.

_sdo_scans: dict[int, list] = {}
_sdo_tasks: set[asyncio.Task] = set()


def _sdo_report(courses, known: set[str]) -> tuple[list[str], int]:
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
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    import sdo_files
    import sdo_parser
    from database import get_file_sources
    from schedule_parser import get_group_subjects
    if not sdo_parser.SDO_SESSION_COOKIE:
        await message.answer("⚠️ Кука СДО не задана (SDO_SESSION_COOKIE в Railway) — см. /syncsdo.")
        return
    wait = await message.answer("⏳ Смотрю, что лежит в СДО: курсы, файлы, папки… Это может занять минуту.")
    subjects = await get_group_subjects()
    try:
        async with sdo_files.make_client(sdo_parser.SDO_SESSION_COOKIE) as client:
            courses = await sdo_files.scan(client, subjects)
    except sdo_parser.SdoSessionExpired:
        await wait.edit_text("⚠️ Кука СДО протухла — обнови SDO_SESSION_COOKIE в Railway (подробно — /syncsdo).")
        return
    except Exception as e:
        await wait.edit_text(f"❌ СДО не ответил: {esc(str(e) or type(e).__name__)}", parse_mode="HTML")
        return
    if not courses:
        await wait.edit_text("🤷 В СДО не нашёл ни одного курса — возможно, кука от другого аккаунта.")
        return
    chunks, new = _sdo_report(courses, await get_file_sources())
    kb = None
    if new:
        _sdo_scans[message.from_user.id] = courses
        from utils import plural
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=f"📥 Загрузить {new} {plural(new, 'файл', 'файла', 'файлов')}", callback_data="sdof:go")]])
    await wait.edit_text(chunks[0], parse_mode="HTML", reply_markup=kb if len(chunks) == 1 else None)
    for i, chunk in enumerate(chunks[1:], 2):
        await message.answer(chunk, parse_mode="HTML", reply_markup=kb if i == len(chunks) else None)


@router.callback_query(F.data == "sdof:go")
async def sdo_files_go(callback: CallbackQuery):
    if STAROSTA_ID and callback.from_user.id != STAROSTA_ID:
        await callback.answer("Только для старосты", show_alert=True)
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
    lines.append("\nСмотреть: /files или вкладка «Файлы» в приложении.")
    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


@router.message(Command("backup"))
async def cmd_backup(message: Message):
    """Копия базы прямо сейчас (обычно приходит сама каждую ночь)."""
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    from backup import send_backup
    await send_backup(message.bot, message.chat.id, silent=False)


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
