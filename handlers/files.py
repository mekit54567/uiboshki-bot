"""Файлы курсов в боте: /files, поиск, листание по предметам и типам, отправка
файла, «скинь практику 3 по …» в чате. Загрузка — files_upload.py, выгрузка
из СДО — files_sdo.py, команды старосты — files_admin.py (подключены ниже)."""

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo,
)

from database import get_files, search_files
from kapibara.bot.tg import data_of, msg, sender, text_of
from kapibara.core.utils import esc
from kapibara.core.errors import EXTERNAL

router = Router()


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
    subjects = sorted({f["subject"] for f in files if f.get("subject")})
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
    from kapibara.core.categories import sort_files
    if idx == "all":
        return "Все файлы", sort_files(all_files)
    subjects = sorted({f["subject"] for f in all_files if f.get("subject")})
    try:
        subject = subjects[int(idx)]
    except (ValueError, IndexError):
        return None
    return subject, sort_files([f for f in all_files if f.get("subject") == subject])


@router.callback_query(F.data.startswith("fsj:"))
async def files_by_subject(callback: CallbackQuery):
    """Предмет → сначала типы (лекции/практики/КР/…) с количеством, если
    их больше одного, иначе сразу файлы."""
    from kapibara.core.categories import CATEGORIES, category_of
    idx = data_of(callback).split(":", 1)[1]
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
        await msg(callback).edit_text(
            f"📁 <b>{esc(title)}</b>\n\nЧто нужно?", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    else:
        await msg(callback).edit_text(
            f"📁 <b>{esc(title)}</b> ({len(files)}){pages_label(len(files), 0)}:", parse_mode="HTML",
            reply_markup=files_keyboard(files, page_cb=f"fct:{idx}:*"),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fct:"))
async def files_by_category(callback: CallbackQuery):
    from kapibara.core.categories import LABELS, category_of
    parts = data_of(callback).split(":")
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
    await msg(callback).edit_text(
        f"📁 <b>{esc(title)}</b> → {label} ({len(files)}){pages_label(len(files), page)}:",
        parse_mode="HTML", reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "fbk")
async def files_back(callback: CallbackQuery):
    files = await get_files()
    subjects = sorted({f["subject"] for f in files if f.get("subject")})
    await msg(callback).edit_text(
        f"📁 <b>Файлы группы</b> ({len(files)} шт.)\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(subjects)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fget:"))
async def send_file(callback: CallbackQuery, bot: Bot):
    fid = int(data_of(callback).split(":")[1])
    files = await get_files()
    f = next((x for x in files if x["id"] == fid), None)
    if not f:
        await callback.answer("Файл не найден")
        return
    from handlers.start import send_stored_file
    try:
        await send_stored_file(
            bot, msg(callback).chat.id, f,
            f"📄 {f['title']}" + (f"\n📚 {f['subject']}" if f.get("subject") else "")
        )
        await callback.answer()
    except EXTERNAL as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)


# ── Файл по запросу в чате ──────────────────────────────────────────────────
# «скинь практику 3 по основам предпр деят» — зовётся из handle_plain_text
# (handlers/solver.py) до ИИ. False — не просьба о файле, пусть решает ИИ.

async def answer_file_request(message: Message) -> bool:
    from kapibara.features.lectures import request as file_request
    from kapibara.core.config import WEBAPP_URL
    from handlers.start import send_file_to
    if not file_request.is_request(message.text or ""):
        return False
    subjects, items = file_request.find(text_of(message), await get_files())
    if not subjects:
        return False
    if len(subjects) > 1:
        await message.answer("🤔 По какому предмету? Подходят:\n" + "\n".join(f"• {esc(s)}" for s in subjects[:8]) +
                             "\n\nНапиши название чуть подробнее.", parse_mode="HTML")
        return True
    subject = subjects[0]
    if not items:
        await message.answer(f"🤷 В папке «{esc(subject)}» такого не нашёл. Все файлы предмета — /files или в приложении.",
                             parse_mode="HTML")
        return True
    if len(items) == 1:
        await send_file_to(message.bot, sender(message).id, items[0]["id"])
        return True
    rows = [[InlineKeyboardButton(text=f["title"][:60], callback_data=f"frq:{f['id']}")] for f in items[:8]]
    if WEBAPP_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(text="📂 Открыть в приложении", web_app=WebAppInfo(
            url=WEBAPP_URL.rstrip("/") + f"/?file={items[0]['id']}"))])
    more = f" (показал 8 из {len(items)})" if len(items) > 8 else ""
    await message.answer(f"📁 <b>{esc(subject)}</b> — нашёл {len(items)}{more}. Какой прислать?",
                         parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    return True


@router.callback_query(F.data.startswith("frq:"))
async def file_request_pick(callback: CallbackQuery):
    from handlers.start import send_file_to
    ok = await send_file_to(callback.bot, callback.from_user.id, data_of(callback).split(":", 1)[1])
    await callback.answer("" if ok else "Файл не найден — возможно, его удалили", show_alert=not ok)


# ── Остальное про файлы — отдельными модулями (v5.0.1) ─────────────────────
# Порядок как был в одном файле: просмотр и «файл по просьбе» выше,
# дальше загрузка, выгрузка из СДО, команды старосты.
from handlers import files_admin, files_sdo, files_upload  # noqa: E402

for _sub in (files_upload, files_sdo, files_admin):
    router.include_router(_sub.router)
