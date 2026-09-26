"""
Анонимная лента группы ("Подслушано").

Гипотеза: то, чего боту не хватало — не улучшение утилити-функций (расписание/
дедлайны/файлы), а социальный слой, который дают открывать бота без конкретного
повода. У большинства "залипательных" студенческих приложений именно анонимная
лента даёт основную частоту возврата.

/feed — пользователь пишет текст/фото анонимно (никто, включая старосту,
не видит автора в самом посте — id сохраняется в БД только для антиспама
и модерации), бот публикует это в общий групповой чат (GROUP_CHAT_ID) с
кнопками-реакциями. Старосте доступна ручная модерация через /delpost ID.

Это ОТДЕЛЬНАЯ сущность от старого приватного /anon (handlers/social.py) —
там сообщение уходит лично старосте и не видно остальной группе. Оставляем
оба варианта: не всё, что хочет сказать студент, должно быть публичным.
"""

import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_last_feed_post_time, add_feed_post, set_feed_post_message_id,
    get_feed_post, delete_feed_post, set_feed_reaction, get_feed_reaction_counts,
)
from config import GROUP_CHAT_ID, FEED_COOLDOWN_MINUTES, STAROSTA_ID
from utils import esc

logger = logging.getLogger(__name__)
router = Router()

REACTIONS = ["👍", "😂", "🔥"]


class FeedPost(StatesGroup):
    waiting = State()


def feed_keyboard(post_id: int, counts: dict) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{emoji} {counts.get(emoji, 0)}" if counts.get(emoji) else emoji,
            callback_data=f"freact:{post_id}:{emoji}"
        )
        for emoji in REACTIONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@router.message(Command("feed"))
@router.message(F.text == "🗣 Подслушано")
async def cmd_feed_start(message: Message, state: FSMContext):
    if not GROUP_CHAT_ID:
        await message.answer(
            "⚠️ Лента ещё не настроена (не задан GROUP_CHAT_ID). "
            "Попроси старосту это исправить."
        )
        return

    last = await get_last_feed_post_time(message.from_user.id)
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            elapsed = datetime.utcnow() - last_dt
            cooldown = timedelta(minutes=FEED_COOLDOWN_MINUTES)
            if elapsed < cooldown:
                wait_min = int((cooldown - elapsed).total_seconds() // 60) + 1
                await message.answer(
                    f"⏳ Не так быстро — следующий пост можно отправить через {wait_min} мин. "
                    f"(антиспам, лимит {FEED_COOLDOWN_MINUTES} мин между постами)"
                )
                return
        except Exception:
            pass

    await state.set_state(FeedPost.waiting)
    await message.answer(
        "🗣 <b>Подслушано</b>\n\n"
        "Напиши текст или пришли фото — опубликую анонимно в общий чат группы. "
        "Никто (включая старосту) не увидит, что это ты.\n\n"
        "/cancel — отмена",
        parse_mode="HTML"
    )


@router.message(Command("cancel"), FeedPost.waiting)
async def cancel_feed(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(FeedPost.waiting, F.text | F.photo)
async def publish_feed_post(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

    text = message.text or message.caption or ""
    photo_file_id = message.photo[-1].file_id if message.photo else None

    if not text and not photo_file_id:
        await message.answer("Пустой пост не отправлю. Попробуй ещё раз через /feed.")
        return

    post_id = await add_feed_post(text, photo_file_id, message.from_user.id)
    caption = f"🗣 <b>Подслушано</b>\n\n{esc(text)}" if text else "🗣 <b>Подслушано</b>"

    try:
        if photo_file_id:
            sent = await bot.send_photo(GROUP_CHAT_ID, photo_file_id, caption=caption, parse_mode="HTML")
        else:
            sent = await bot.send_message(GROUP_CHAT_ID, caption, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось опубликовать в ленту: {e}")
        # Пост так и не появился в группе — помечаем удалённым, иначе
        # неудачная попытка всё равно запускала антиспам-кулдаун
        # (get_last_feed_post_time смотрит на deleted=0) и повторить
        # можно было только через FEED_COOLDOWN_MINUTES.
        await delete_feed_post(post_id)
        await message.answer(
            f"❌ Не смог опубликовать в группу ({e}). "
            "Возможно, бота нет в группе или у него нет прав постить."
        )
        return

    # Дальше пост уже в группе — сбой кнопок-реакций не делает его
    # неопубликованным (иначе автор увидел бы "не смог" и запостил дубль).
    await set_feed_post_message_id(post_id, sent.message_id)
    try:
        await bot.edit_message_reply_markup(
            GROUP_CHAT_ID, sent.message_id,
            reply_markup=feed_keyboard(post_id, {})
        )
    except Exception as e:
        logger.warning(f"Пост #{post_id} опубликован, но кнопки реакций не повесились: {e}")
    await message.answer("✅ Опубликовано анонимно!")


@router.callback_query(F.data.startswith("freact:"))
async def handle_reaction(callback: CallbackQuery):
    _, post_id, emoji = callback.data.split(":")
    post_id = int(post_id)

    post = await get_feed_post(post_id)
    if not post or post.get("deleted"):
        await callback.answer("Этот пост уже удалён.", show_alert=True)
        return

    await set_feed_reaction(post_id, callback.from_user.id, emoji)
    counts = await get_feed_reaction_counts(post_id)

    try:
        await callback.message.edit_reply_markup(reply_markup=feed_keyboard(post_id, counts))
    except Exception:
        pass
    await callback.answer(f"{emoji} учтено")


@router.message(Command("delpost"))
async def cmd_delpost(message: Message, bot: Bot):
    if STAROSTA_ID and message.from_user.id != STAROSTA_ID:
        await message.answer("❌ Только для старосты.")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /delpost ID")
        return

    post_id = int(parts[1])
    post = await get_feed_post(post_id)
    if not post:
        await message.answer("Пост не найден.")
        return

    if post.get("message_id"):
        try:
            await bot.delete_message(GROUP_CHAT_ID, post["message_id"])
        except Exception as e:
            logger.warning(f"Не смог удалить сообщение из чата: {e}")

    await delete_feed_post(post_id)
    await message.answer(f"🗑 Пост #{post_id} удалён из ленты.")
