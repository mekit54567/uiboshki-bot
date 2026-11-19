"""Капибара в чате своей группы: приветствие при добавлении и ответы на тег
(Никита 11.11). Только чат своей группы (members.chat_id) — в остальных молчит.
Логика, модели и лимиты — kapibara/features/ai/group_talk.py.

В BotFather «Group Privacy» оставляем как есть: бот и так получает сообщения
с @упоминанием и ответы на свои сообщения; если теги не доходят — выключить."""
import asyncio
import logging
from pathlib import Path

from aiogram import BaseMiddleware, F, Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, FSInputFile, Message

from kapibara.core import config
from kapibara.core.errors import EXTERNAL, aside
from kapibara.features.ai import group_talk
from kapibara.features.groups import members

logger = logging.getLogger(__name__)
router = Router()

GROUP = F.chat.type.in_({"group", "supergroup"})


class GroupTrace(BaseMiddleware):
    """Строка в лог на каждое обращение к боту в группе (тег, /ask, ответ ему) — видно, доходят ли такие
    сообщения до бота вообще, раньше любых фильтров (Telegram, privacy mode, inline-режим)."""

    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None)
        if chat and chat.type in ("group", "supergroup"):
            text = (getattr(event, "text", None) or "").lower()
            reply = getattr(event, "reply_to_message", None)
            to_bot = f"@{config.BOT_USERNAME}".lower() in text or text.startswith(("/ask", "/kapi"))
            if to_bot or (reply and reply.from_user and reply.from_user.is_bot):
                user = getattr(event, "from_user", None)
                logger.info(f"группа: пришло {text[:30]!r} от {user.id if user else '?'} в чате {chat.id}, "
                            f"тема {getattr(event, 'message_thread_id', None)}")
        return await handler(event, data)


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
    text = (message.text or "").lower()
    if low in text or text.startswith(("/ask ", "/ask@", "/kapi ", "/kapi@")) or text in ("/ask", "/kapi"):
        return True
    reply = message.reply_to_message
    return bool(reply and reply.from_user and reply.from_user.id == bot_id)


async def answer_without_consent(message, bot: Bot):
    """Обращение к боту в чате своей группы от человека без согласия на обработку данных (Никита 18.11:
    отвечаем и ему — это его группа в Telegram). Идёт только текст вопроса, без имени и id, ничего не
    сохраняется; ConsentMiddleware пропускает сюда только такие обращения."""
    if message.chat.type not in ("group", "supergroup") or not message.from_user or message.from_user.is_bot:
        return
    me = await bot.me()
    if not _is_for_bot(message, me.id, me.username or config.BOT_USERNAME):
        return
    text = message.text or ""
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        if parts[0].split("@")[0].lower() not in ("/ask", "/kapi"):
            return
        text = parts[1] if len(parts) > 1 else ""
    if text.strip():
        await respond(message, text)


@router.message(GROUP, F.text, ~F.text.startswith("/"))
async def talk(message: Message, bot: Bot):
    """Тег @бота в тексте или ответ на сообщение бота."""
    if not message.from_user or message.from_user.is_bot:
        return
    me = await bot.me()
    if not _is_for_bot(message, me.id, me.username or config.BOT_USERNAME):
        return
    await respond(message, message.text or "")


@router.message(GROUP, Command("ask", "kapi"))
async def ask(message: Message, command: CommandObject):
    """/ask вопрос — то же, что тег. Нужна, потому что в Telegram сообщение, которое НАЧИНАЕТСЯ с @бота,
    для бота с inline-режимом превращается в inline-запрос и не отправляется."""
    if not message.from_user or message.from_user.is_bot:
        return
    question = (command.args or "").strip()
    if not question:
        reply = message.reply_to_message
        question = (reply.text or "") if reply else ""
    if not question:
        await message.reply("Напиши вопрос после команды: /ask как тебя скачать?")
        return
    await respond(message, question)


async def respond(message: Message, question: str):
    if not message.from_user:
        return
    uid = message.from_user.id
    starosta = config.is_starosta(uid)
    chat = await members.chat_id()
    logger.info(f"группа: обратились к боту в чате {message.chat.id} (запомнен {chat}), "
                f"включено: {group_talk.enabled()}")
    if not group_talk.enabled():
        if starosta:                                        # диагностика только старосте
            await message.reply("Не отвечаю: на сервере нет OPENROUTER_API_KEY (или стоит GROUP_TALK=off).")
        return
    if message.chat.id != chat:
        if starosta:
            await message.reply(f"Не отвечаю: этот чат (id {message.chat.id}) не запомнен как чат группы"
                                f"{f', запомнен {chat}' if chat else ''}. Напиши здесь /groupchat.")
        return
    refusal = None if starosta else group_talk.allow(uid, message.chat.id)
    if refusal:
        logger.info(f"группа: не отвечаю {uid}: {refusal}")
    if refusal == "user":
        return                                              # слишком часто — молча
    if refusal == "day":
        await message.reply("Я на сегодня выговорилась 🦫 Завтра отвечу, а расписание и дедлайны — в боте.")
        return
    with aside(logger, "«печатает» в группе", EXTERNAL):
        await message.bot.send_chat_action(message.chat.id, "typing",
                                           message_thread_id=message.message_thread_id if message.is_topic_message else None)
    try:
        async with asyncio.timeout(group_talk.TOTAL_TIMEOUT):
            text = await group_talk.answer(question)
    except (group_talk.TalkError, TimeoutError):
        await message.reply("Сейчас не могу ответить — задумалась. Попробуй чуть позже.")
        return
    await message.reply(text)


@router.message(GROUP, Command("groupchat"))
async def groupchat(message: Message):
    """Староста: запомнить этот чат как чат своей группы (если бот не отвечает на теги)."""
    from database import set_setting
    if not message.from_user or not config.is_starosta(message.from_user.id):
        return
    if config.GROUP_CHAT_ID and message.chat.id != config.GROUP_CHAT_ID:
        await message.reply("Чат задан в переменных сервера (GROUP_CHAT_ID) и это другой чат.")
        return
    await set_setting("group_chat_id", str(message.chat.id))
    members.forget_chat()
    await message.reply("Запомнила этот чат как чат группы. Теперь отвечаю на теги.")


@router.message(GROUP, Command("groupintro"))
async def groupintro(message: Message, bot: Bot):
    """Староста: прислать приветствие в чат ещё раз (после смены видео)."""
    if not message.from_user or not config.is_starosta(message.from_user.id):
        return
    if message.chat.id != await members.chat_id():
        return
    await send_intro(bot, message.chat.id, force=True)


@router.message(F.chat.type == "private", Command("talktest"))
async def talktest(message: Message):
    """Староста: прогнать 30 вопросов настоящей моделью и получить ответы файлом (смотрим характер)."""
    if not message.from_user or not config.is_starosta(message.from_user.id):
        return
    if not group_talk.enabled():
        await message.answer("Нет OPENROUTER_API_KEY — нечем отвечать.")
        return
    await message.answer(f"Гоняю {len(group_talk.TEST_QUESTIONS)} вопросов, минуты две…")
    report = await group_talk.run_test()
    await message.answer_document(BufferedInputFile(report.encode(), filename="talktest.txt"))
