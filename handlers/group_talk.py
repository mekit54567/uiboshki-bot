"""Капибара в чате своей группы: приветствие при добавлении и ответы на тег
(Никита 11.11). Только чат своей группы (members.chat_id) — в остальных молчит.
Логика, модели и лимиты — kapibara/features/ai/group_talk.py.

В BotFather «Group Privacy» оставляем как есть: бот и так получает сообщения
с @упоминанием и ответы на свои сообщения; если теги не доходят — выключить."""
import asyncio
import logging
from pathlib import Path

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from kapibara.core import config
from kapibara.core.errors import EXTERNAL, aside
from kapibara.features.ai import group_talk
from kapibara.features.groups import members

logger = logging.getLogger(__name__)
router = Router()

GROUP = F.chat.type.in_({"group", "supergroup"})


async def send_intro(bot: Bot, chat_id: int, *, force: bool = False) -> bool:
    """Знакомство: видео (если файл лежит) и следом отдельный пост. Раз на чат; force — ещё раз."""
    from database import get_setting, set_setting
    key = f"group_intro:{chat_id}"
    if not force and await get_setting(key):
        return False
    video = Path(group_talk.INTRO_VIDEO)
    sent = False
    with aside(logger, "приветствие в чате группы", EXTERNAL):
        if await asyncio.to_thread(video.is_file):
            await bot.send_video(chat_id, FSInputFile(video))
        await bot.send_message(chat_id, group_talk.intro_text(), parse_mode="HTML", disable_web_page_preview=True)
        sent = True
    if sent:
        await set_setting(key, "1")
    return sent


def _is_for_bot(message: Message, bot_id: int, username: str) -> bool:
    low = f"@{username}".lower()
    if (message.text or "").lower().find(low) != -1:
        return True
    reply = message.reply_to_message
    return bool(reply and reply.from_user and reply.from_user.id == bot_id)


@router.message(GROUP, F.text, ~F.text.startswith("/"))
async def talk(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot or not group_talk.enabled():
        return
    if message.chat.id != await members.chat_id():
        return
    me = await bot.me()
    if not _is_for_bot(message, me.id, me.username or config.BOT_USERNAME):
        return
    refusal = group_talk.allow(message.from_user.id, message.chat.id)
    if refusal == "user":
        return                                              # слишком часто — молча
    if refusal == "day":
        await message.reply("Я на сегодня выговорилась 🦫 Завтра отвечу, а расписание и дедлайны — в боте.")
        return
    try:
        text = await group_talk.answer(message.text or "")
    except group_talk.TalkError:
        await message.reply("Сейчас не могу ответить — задумалась. Попробуй чуть позже.")
        return
    await message.reply(text)


@router.message(GROUP, Command("groupintro"))
async def groupintro(message: Message, bot: Bot):
    """Староста: прислать приветствие в чат ещё раз (после смены видео)."""
    if not message.from_user or not config.is_starosta(message.from_user.id):
        return
    if message.chat.id != await members.chat_id():
        return
    await send_intro(bot, message.chat.id, force=True)
