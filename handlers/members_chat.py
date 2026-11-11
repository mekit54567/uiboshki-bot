"""Бот в чате своей группы.

Добавлен в чат (members.py, владелец 09.10): староста добавил — запоминаем
этот чат как чат своей группы (если GROUP_CHAT_ID не задан) и пишем старосте.
Дальше «своя группа» = участники этого чата.

/say — староста пишет в чат от имени бота; /groupmorning — утренняя карточка
дня в чат (Никита 03.11; само задание — scheduler.send_group_morning)."""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message

from kapibara.core.utils import esc
from kapibara.core.errors import aside

logger = logging.getLogger(__name__)
router = Router()


@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def bot_added_to_group(event: ChatMemberUpdated):
    from kapibara.core import config
    from kapibara.features.groups import members
    from database import set_setting
    status = str(event.new_chat_member.status).split(".")[-1].lower()
    if status not in ("member", "administrator"):
        return
    if event.chat.id == await members.chat_id():            # чат своей группы — приветствие один раз (group_talk)
        from handlers.group_talk import send_intro
        if event.bot:
            await send_intro(event.bot, event.chat.id)
    if not config.is_starosta(event.from_user.id):
        return
    if config.GROUP_CHAT_ID and event.chat.id != config.GROUP_CHAT_ID:
        return                                  # чат задан в переменных хостинга — он главнее
    if await members.chat_id() == event.chat.id:
        return
    await set_setting("group_chat_id", str(event.chat.id))
    members.forget_chat()
    logger.info(f"чат своей группы: {event.chat.id} ({event.chat.title})")
    from handlers.group_talk import send_intro
    if event.bot:
        await send_intro(event.bot, event.chat.id)
    with aside(logger, "сообщение старосте о чате", level=logging.INFO):
        await event.bot.send_message(
            event.from_user.id,
            f"👥 Запомнил чат <b>{esc(event.chat.title or '')}</b> как чат своей группы.\n\n"
            "Теперь своя группа — это его участники: только они могут выбрать её в боте и "
            "приложении, видеть её файлы и пользоваться ИИ без пробного лимита. Остальные "
            "выбирают свою группу как обычно.\n\n"
            f"☀️ Каждое утро в {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} пришлю в чат карточку "
            "с парами на сегодня (посмотреть — /groupmorning, выключить — /groupmorning off).\n"
            "🗣 Написать в чат от моего имени — /say.\n"
            "📌 Чтобы я мог закреплять, дай мне в чате права админа «Закреплять сообщения».",
            parse_mode="HTML")


# ── Староста пишет в чат группы от имени бота (Никита 03.11) ────────────────
# /say в личке с ботом → присылаешь что угодно (текст, фото, файл, голосовое,
# опрос) → бот показывает и спрашивает «В группу?» → копирует сообщение в чат
# группы от своего имени, по желанию — с закрепом. Только своя группа.

class SayState(StatesGroup):
    waiting = State()


SAY_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📤 В группу", callback_data="say:send"),
     InlineKeyboardButton(text="📌 В группу и закрепить", callback_data="say:pin")],
    [InlineKeyboardButton(text="✖️ Не отправлять", callback_data="say:no")]])


async def _chat_or_explain(message: Message) -> int:
    from kapibara.features.groups import members
    if chat := await members.chat_id():
        return chat
    await message.answer("👥 Чат группы ещё не знаю. Добавь меня в чат группы (со своего аккаунта старосты) — "
                         "я его запомню, и всё заработает.")
    return 0


@router.message(Command("say"), F.chat.type == "private")
async def cmd_say(message: Message, state: FSMContext):
    from kapibara.core import config
    if not config.is_starosta(message.from_user.id) or not await _chat_or_explain(message):
        return
    await state.set_state(SayState.waiting)
    await message.answer("🗣 Пришли, что написать в чат группы от моего имени: текст, фото, файл, "
                         "голосовое, опрос — что угодно. Перед отправкой покажу и спрошу.\n\n/cancel — отмена")


@router.message(SayState.waiting, F.chat.type == "private")
async def say_got(message: Message, state: FSMContext):
    await state.update_data(say_msg=message.message_id)
    await message.reply("Отправить это в чат группы?", reply_markup=SAY_KB)


@router.callback_query(F.data.startswith("say:"))
async def say_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    from kapibara.core import config
    if not config.is_starosta(callback.from_user.id):
        await callback.answer("Только для старосты", show_alert=True)
        return
    msg_id = (await state.get_data()).get("say_msg")
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    if callback.data == "say:no" or not msg_id:
        await callback.message.edit_text("Не отправил." if msg_id else "Уже отправлено или устарело.")
        return
    from kapibara.features.groups import members
    chat = await members.chat_id()
    try:
        sent = await bot.copy_message(chat, callback.message.chat.id, msg_id)
        note = "✅ Отправил в чат группы."
        if callback.data == "say:pin":
            try:
                await bot.pin_chat_message(chat, sent.message_id, disable_notification=False)
                note = "✅ Отправил и закрепил."
            except TelegramAPIError as e:
                note = f"✅ Отправил, но закрепить не вышло — дай мне в чате право закреплять сообщения.\n({e.message})"
    except TelegramAPIError as e:
        note = f"⚠️ Не отправилось: {e.message}"
    await callback.message.edit_text(note)
    await callback.answer()


# ── Утренняя карточка в чате группы ─────────────────────────────────────────

@router.message(Command("groupmorning"), F.chat.type == "private")
async def cmd_group_morning(message: Message, bot: Bot):
    """/groupmorning — показать сегодняшнюю карточку себе; on/off — включить
    или выключить утреннюю отправку в чат группы; now — отправить сейчас."""
    from kapibara.core import config
    from kapibara.features.groups import members
    from kapibara.jobs import scheduler
    from database import get_setting, set_setting
    if not config.is_starosta(message.from_user.id):
        return
    arg = (message.text or "").split(maxsplit=1)[1:] or [""]
    arg = arg[0].strip().lower()
    if arg in ("on", "off"):
        await set_setting("group_morning", arg)
        await message.answer("☀️ Утренняя карточка в чат группы — " + ("включена." if arg == "on" else "выключена."))
        return
    if arg == "now":
        if not await _chat_or_explain(message):
            return
        res = await scheduler.send_group_morning(bot, await members.chat_id())
    else:
        res = await scheduler.send_group_morning(bot, message.chat.id)
    if res == "no_lessons":
        await message.answer("Сегодня пар нет — в такие дни карточку не шлю.")
        return
    state = "выключена" if await get_setting("group_morning") == "off" else \
        f"включена, каждый день в {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d}"
    await message.answer(("✅ Отправил в чат группы.\n" if arg == "now" else "☝️ Так она выглядит в чате группы.\n")
                         + f"Утренняя отправка {state}.\n\n/groupmorning on · off · now")
