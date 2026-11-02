"""Доска ДЗ в боте: /hw (по предметам), /addhw (предмет → текст или файл →
дата пары). Хранение — database/homework.py."""

import logging
from datetime import date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import add_hw, delete_hw, get_hw_by_subject, get_hw_subjects, init_hw_table, is_editor
from database.homework import get_hw
from kapibara.core.utils import esc, parse_day_month, today_msk, utc_to_msk_date

router = Router()
logger = logging.getLogger(__name__)


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


class HWAdd(StatesGroup):
    subject = State()
    content = State()
    lesson_date = State()


async def _g(user_id: int) -> int:
    """Группа человека — доска ДЗ у каждой своя (этап 1 (б))."""
    from database.groups import viewer_group
    return await viewer_group(user_id)


@router.message(Command("hw"))
async def cmd_hw(message: Message):
    await init_hw_table()
    subjects = await get_hw_subjects(await _g(message.from_user.id))
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


def _board_view(subjects: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    buttons = [[InlineKeyboardButton(text=s, callback_data=f"hw:{i}")] for i, s in enumerate(subjects)]
    text = "📝 <b>Доска ДЗ</b>\n\n" + ("Выбери предмет:" if subjects else "Пока пусто.")
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def _subject_view(subject: str, items: list[dict], can_edit: bool) -> tuple[str, InlineKeyboardMarkup]:
    lines = [f"📝 <b>{esc(subject)}</b>\n"]
    for item in items:
        dt = utc_to_msk_date(item["created_at"])
        lesson_badge = ""
        if item.get("lesson_date"):
            lesson_badge = f" 📅 к паре {date.fromisoformat(item['lesson_date']).strftime('%d.%m')}"
        lines.append(f"• {esc(item['content']) or '[файл]'} <i>({dt})</i>{lesson_badge}")

    row = [InlineKeyboardButton(text="◀️ Назад", callback_data="hw_back")]
    # В кнопке — id самой записи: раньше там был префикс названия предмета
    # (subject[:20]) и startswith — у предметов с общим началом удалялось ДЗ
    # чужого предмета.
    if can_edit and items:
        row.append(InlineKeyboardButton(text="🗑 Удалить последнее", callback_data=f"hwdel:{items[0]['id']}"))
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[row])


@router.callback_query(F.data.startswith("hw:"))
async def hw_subject(callback: CallbackQuery):
    idx = int(callback.data.split(":")[1])
    subjects = await get_hw_subjects(await _g(callback.from_user.id))
    if idx >= len(subjects):
        await callback.answer("Ошибка")
        return
    subject = subjects[idx]
    items = await get_hw_by_subject(subject, await _g(callback.from_user.id))

    text, kb = _subject_view(subject, items, await is_editor(callback.from_user.id))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

    # Отправляем файлы если есть
    for item in items:
        if item.get("file_id"):
            try:
                if item["file_type"] == "photo":
                    await callback.message.answer_photo(item["file_id"], caption=item["content"] or "")
                else:
                    await callback.message.answer_document(item["file_id"], caption=item["content"] or "")
            except Exception as e:
                logger.warning(f"ДЗ {item.get('id')}: файл не отправился: {e!r}")
                await callback.message.answer("⚠️ Один файл ДЗ не отправился — попроси старосту залить его заново.")


@router.callback_query(F.data == "hw_back")
async def hw_back(callback: CallbackQuery):
    text, kb = _board_view(await get_hw_subjects(await _g(callback.from_user.id)))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("hwdel:"))
async def hw_del_last(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    item = await get_hw(int(key)) if key.isdigit() else None
    if not item:
        # Старая кнопка (уже удалено или сообщение до обновления) — ничего не трогаем
        await callback.answer("Уже удалено")
        return
    from database.groups import row_group
    if not await is_editor(callback.from_user.id, row_group(item.get("group_id"))):
        await callback.answer("Нет прав")
        return
    await delete_hw(item["id"])
    await callback.answer("✅ Удалено!")
    # Перерисовываем: иначе кнопка оставалась прежней, и повторное нажатие
    # удаляло ещё одно ДЗ.
    subject = item["subject"]
    gid = await _g(callback.from_user.id)
    items = await get_hw_by_subject(subject, gid)
    if items:
        text, kb = _subject_view(subject, items, True)
    else:
        text, kb = _board_view(await get_hw_subjects(gid))
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning(f"ДЗ: доска после удаления не перерисовалась: {e!r}")


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
                 message.from_user.id, lesson_date, group_id=await _g(message.from_user.id))
    date_note = ""
    if lesson_date:
        from datetime import date as date_cls
        date_note = f"\n📅 Привязано к паре {date_cls.fromisoformat(lesson_date).strftime('%d.%m.%Y')}"
    await message.answer(
        f"✅ ДЗ добавлено в раздел <b>{esc(data['subject'])}</b>!{date_note}", parse_mode="HTML"
    )
