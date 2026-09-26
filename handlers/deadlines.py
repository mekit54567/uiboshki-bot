import re
import json
import logging
from datetime import date
from zoneinfo import ZoneInfo

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database import (
    add_deadline, get_active_deadlines, mark_deadline_done, set_deadline_done,
    delete_deadline, upsert_user, get_deadline_stats, get_deadline, is_shared_deadline,
)
from config import STAROSTA_ID, GROUP_CHAT_ID
from scheduler import DEADLINE_POST_QUESTION
from keyboards import MAIN_KB, CANCEL_KB
from utils import esc, parse_day_month, today_msk, esc_attr

logger = logging.getLogger(__name__)
router = Router()
TZ = ZoneInfo("Europe/Moscow")


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


def parse_due_time(raw: str) -> tuple[bool, str | None]:
    """Разбор и валидация времени дедлайна. Возвращает (валидно, значение):
    (True, None) — пользователь пропустил ("–"/"-"), (True, "ЧЧ:ММ") — валидное
    время (разделитель ":" или "." — с телефона часто набирают точкой),
    (False, None) — неверный формат или диапазон (например "22.61", "25:10").
    Вынесено отдельной функцией, чтобы граничные случаи были покрыты
    юнит-тестами напрямую, без прогона через FSM."""
    raw = raw.strip()
    if raw in ("–", "-"):
        return True, None
    match = re.match(r"^(\d{1,2})[:.](\d{2})$", raw)
    if not match:
        return False, None
    hh, mm = int(match.group(1)), int(match.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return False, None
    return True, f"{hh:02d}:{mm:02d}"


def progress_bar(delta: int, max_days: int = 14) -> str:
    if delta <= 0:
        return "━━━━━━━━━━ 100%"
    filled = max(0, 10 - min(int(delta / max_days * 10), 10))
    bar = "━" * filled + "╌" * (10 - filled)
    pct = max(0, min(100, filled * 10))
    return f"{bar} {pct}%"


WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def due_label(due: date, today: date, due_time: str | None = None) -> str:
    """«🔴 сегодня в 23:59», «🟠 завтра», «🟡 пт, 2 октября», «💀 просрочен (29.09)»."""
    from schedule_parser import MONTHS_GEN
    delta = (due - today).days
    tp = f" в {due_time}" if due_time else ""
    if delta < 0:
        return f"💀 просрочен ({due.strftime('%d.%m')})"
    if delta == 0:
        return f"🔴 сегодня{tp}"
    if delta == 1:
        return f"🟠 завтра{tp}"
    human = f"{WEEKDAY_SHORT[due.weekday()]}, {due.day} {MONTHS_GEN[due.month - 1]}{tp}"
    return f"{'🟡' if delta <= 3 else '🟢'} {human} · через {delta} дн."


def _deadline_line(d: dict, today: date) -> str:
    due = date.fromisoformat(d["due_date"])
    mine = " 👤" if "created_by" in d and not is_shared_deadline(d) else ""
    desc = (d.get("description") or "").strip()
    extra = ""
    if desc.startswith(("http://", "https://")):
        extra = f' · <a href="{esc_attr(desc)}">задание</a>'
    elif desc and desc not in ("-", "–"):
        extra = f"\n    📝 {esc(desc[:200])}"
    return f"<code>{d['id']}</code> <b>{esc(d['subject'])}</b>{mine}\n    {due_label(due, today, d.get('due_time'))}{extra}"


def format_deadlines(deadlines: list[dict], done: list[dict] | None = None) -> str:
    """Дедлайны группами по срочности. Раньше — плоский список с полоской
    «━━━━━━━━╌╌ 80%», по которой было непонятно, 80% чего (живой тест).
    done — выполненные этим студентом: коротко внизу, с подсказкой, как
    вернуть (если отметил случайно)."""
    done_block = ""
    if done:
        lines = [f"<code>{d['id']}</code> {esc(d['subject'][:60])}" for d in done[:5]]
        more = f"\n… и ещё {len(done) - 5}" if len(done) > 5 else ""
        done_block = f"✅ <b>Выполнено: {len(done)}</b> — вернуть: /undone ID\n" + "\n".join(lines) + more
    if not deadlines:
        return "📋 Дедлайнов нет — можно расслабиться! 🎉" + (f"\n\n{done_block}" if done_block else "")

    today = today_msk()
    groups = {"💀 Просрочено": [], "🔥 Горит": [], "📅 На неделе": [], "🗓 Позже": []}
    for d in deadlines:
        delta = (date.fromisoformat(d["due_date"]) - today).days
        key = ("💀 Просрочено" if delta < 0 else "🔥 Горит" if delta <= 2
               else "📅 На неделе" if delta <= 7 else "🗓 Позже")
        groups[key].append(d)

    blocks = [f"📋 <b>Дедлайны</b> · {len(deadlines)}"]
    for title, items in groups.items():
        if items:
            blocks.append(f"<b>{title}</b>\n" + "\n".join(_deadline_line(d, today) for d in items))
    if done_block:
        blocks.append(done_block)
    blocks.append("✅ /done ID — выполнено · ↩️ /undone ID — вернуть · 🗑 /del ID · ➕ /add")
    return "\n\n".join(blocks)


@router.message(Command("deadlines"))
@router.message(F.text == "📋 Дедлайны")
async def cmd_deadlines(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    everything = await get_active_deadlines(message.from_user.id, include_done=True)
    active = [d for d in everything if not d.get("done")]
    done = [d for d in everything if d.get("done")]
    await message.answer(format_deadlines(active, done), parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    s      = await get_deadline_stats(message.from_user.id)
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
    if not message.text:
        await message.answer("📌 Название пришли текстом.")
        return
    await state.update_data(subject=message.text.strip())
    await state.set_state(AddDeadline.description)
    await message.answer(
        "📝 Описание? (текстом, фото задания — текст распознаю автоматически, или <i>–</i> пропустить)",
        parse_mode="HTML"
    )


@router.message(AddDeadline.description, F.photo)
async def add_description_photo(message: Message, state: FSMContext, bot: Bot):
    from ai_solver import extract_text_from_image
    from html import escape as html_escape

    wait = await message.answer("🔎 Распознаю текст с фото...")
    text = ""
    try:
        photo      = message.photo[-1]
        file       = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        text       = await extract_text_from_image(file_bytes.read())
    except Exception as e:
        logger.warning(f"Не смог распознать фото дедлайна: {e}")

    text = (text or "").strip()
    if not text:
        await wait.edit_text(
            "❌ Не смог распознать текст на фото. Опиши задание текстом (или <i>–</i> — пропустить):",
            parse_mode="HTML"
        )
        return

    await state.update_data(description=text[:1500])
    await state.set_state(AddDeadline.due_date)
    preview = html_escape(text[:500])
    await wait.edit_text(
        f"📝 Распознал с фото:\n<i>{preview}</i>\n\n📅 Дата? Формат: <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>",
        parse_mode="HTML"
    )


@router.message(AddDeadline.description)
async def add_description(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    # В подсказке длинное тире "–", но с клавиатуры обычно вводят дефис "-" — принимаем оба.
    await state.update_data(description="" if desc in ("–", "-") else desc)
    await state.set_state(AddDeadline.due_date)
    await message.answer("📅 Дата? Формат: <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>", parse_mode="HTML")


@router.message(AddDeadline.due_date)
async def add_due_date(message: Message, state: FSMContext):
    due_date = parse_day_month(message.text or "", today_msk())
    if not due_date:
        await message.answer(
            "❌ Неверная или несуществующая дата. Например: <b>30.05</b> или <b>30.05.2027</b>",
            parse_mode="HTML"
        )
        return
    await state.update_data(due_date=due_date.isoformat())
    await state.set_state(AddDeadline.due_time)
    await message.answer("⏰ Время? Формат <b>ЧЧ:ММ</b> или <i>–</i>", parse_mode="HTML")


@router.message(AddDeadline.due_time)
async def add_due_time(message: Message, state: FSMContext):
    ok, due_time = parse_due_time(message.text or "")
    if not ok:
        await message.answer(
            "❌ Неверное время. Формат <b>ЧЧ:ММ</b>, часы 00–23, минуты 00–59 "
            "(например 09:30 или 22:59), или <i>–</i> — пропустить",
            parse_mode="HTML"
        )
        return
    data = await state.get_data()
    await state.clear()
    did = await add_deadline(data["subject"], data.get("description", ""), data["due_date"], due_time, message.from_user.id)
    tp  = f" в {due_time}" if due_time else ""
    await message.answer(
        f"✅ <b>Дедлайн добавлен!</b> (ID: {did})\n\n"
        f"📌 {esc(data['subject'])}\n"
        f"📅 {format_date(data['due_date'])}{tp}",
        parse_mode="HTML", reply_markup=MAIN_KB
    )


@router.message(Command("done"))
async def cmd_done(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /done 3")
        return
    did = int(parts[1])
    existing = await get_deadline(did)
    if not existing:
        await message.answer("❌ Дедлайн с таким ID не найден.")
        return
    # Персональная отметка: у каждого свой статус "выполнено" — не влияет
    # на то, что видят остальные (в т.ч. по этому же общему дедлайну).
    await mark_deadline_done(did, message.from_user.id)
    await message.answer(f"✅ У тебя дедлайн #{did} отмечен как выполненный!\nОшибся — /undone {did}")


@router.message(Command("undone"))
async def cmd_undone(message: Message):
    """Вернуть дедлайн из выполненных — если отметил случайно (раньше
    вернуть можно было только галочкой в WebApp, в боте — никак)."""
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /undone 3 — вернуть дедлайн в активные")
        return
    did = int(parts[1])
    if not await get_deadline(did):
        await message.answer("❌ Дедлайн с таким ID не найден.")
        return
    await set_deadline_done(did, message.from_user.id, False)
    await message.answer(f"↩️ Дедлайн #{did} снова в активных.")


@router.message(Command("del"))
async def cmd_del(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /del 3")
        return
    did = int(parts[1])
    existing = await get_deadline(did)
    if not existing:
        await message.answer("❌ Дедлайн с таким ID не найден.")
        return

    is_shared = existing["created_by"] in (0, STAROSTA_ID)
    is_owner  = existing["created_by"] == message.from_user.id
    if is_shared:
        if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
            await message.answer("❌ Это общий дедлайн — удалить может только староста.")
            return
    elif not is_owner:
        await message.answer("❌ Это чужой личный дедлайн — удалить его может только автор.")
        return

    await delete_deadline(did)
    await message.answer(f"🗑 Дедлайн #{did} удалён.")


# ── Импорт дедлайнов из СДО ──────────────────────────────────────────────────

SKIP_KEYWORDS = [
    "практикум", "пример решения", "образец решения",
    "методические указания", "активность", "мероприятие",
    "достижение", "научная конференция", "пример программы",
]

def should_skip(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in SKIP_KEYWORDS)


@router.message(Command("importdeadlines"))
async def cmd_import_deadlines(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    await message.answer("📤 Пришли файл <b>deadlines.json</b>", parse_mode="HTML")


@router.message(Command("syncsdo"))
async def cmd_sync_sdo(message: Message):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return

    from sdo_parser import sync_deadlines

    wait = await message.answer("⏳ Синхронизирую дедлайны из СДО...")
    result = await sync_deadlines()

    if result.get("expired"):
        # «Не задана» и «протухла» раньше были одним сообщением — а это разные
        # вещи: во втором случае СДО с сервера открылся (сеть есть), просто
        # попросил войти заново.
        if result.get("missing"):
            await wait.edit_text(
                "⚠️ Кука СДО не задана. Зайди в online-edu.mirea.ru в браузере, "
                "возьми значение MoodleSession (F12 → Application → Cookies) и добавь "
                "его в Railway → Variables как SDO_SESSION_COOKIE."
            )
        else:
            await wait.edit_text(
                "⚠️ Кука СДО протухла: СДО открылся, но попросил войти заново. Зайди в "
                "online-edu.mirea.ru в браузере, возьми свежее значение MoodleSession "
                "(F12 → Application → Cookies) и обнови SDO_SESSION_COOKIE в Railway. "
                "В СДО потом не жми «Выйти» — это убивает сессию."
            )
        return

    if "error" in result:
        await wait.edit_text(f"❌ Ошибка: {result['error']}")
        return

    await wait.edit_text(
        f"✅ Готово!\n\nДобавлено: {result['added']}\n"
        f"Обновлено (сменился срок/название): {result.get('updated', 0)}\n"
        f"Без изменений: {result['skipped']}"
    )

# ── Публикация дедлайнов в группу (ручная модерация старостой) ─────────────
# scheduler.send_deadline_reminders шлёт старосте тот же текст, что ушёл
# подписчикам лично, плюс эти две кнопки — потому что автосинк из СДО
# не всегда достоверен (см. PLAN.md, Фаза 4), и светить непроверенное
# в общий чат всей группы без подтверждения не стоит.

@router.callback_query(F.data == "dlpost:yes")
async def deadline_post_confirm(callback: CallbackQuery):
    if STAROSTA_ID and callback.from_user.id != STAROSTA_ID:
        await callback.answer("Только для старосты", show_alert=True)
        return
    if not GROUP_CHAT_ID:
        await callback.answer("GROUP_CHAT_ID не настроен", show_alert=True)
        return
    text = callback.message.html_text
    group_text = text.removesuffix(DEADLINE_POST_QUESTION.strip()).rstrip()
    try:
        await callback.bot.send_message(GROUP_CHAT_ID, group_text, parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"Ошибка отправки: {e}", show_alert=True)
        return
    await callback.message.edit_text(text + "\n\n✅ Опубликовано в группу.", parse_mode="HTML", reply_markup=None)
    await callback.answer("Опубликовано!")


@router.callback_query(F.data == "dlpost:no")
async def deadline_post_decline(callback: CallbackQuery):
    if STAROSTA_ID and callback.from_user.id != STAROSTA_ID:
        await callback.answer("Только для старосты", show_alert=True)
        return
    text = callback.message.html_text
    await callback.message.edit_text(text + "\n\n🚫 Не опубликовано.", parse_mode="HTML", reply_markup=None)
    await callback.answer()
