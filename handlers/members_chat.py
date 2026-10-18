"""Бот добавлен в чат группы (members.py, владелец 09.10): староста добавил —
запоминаем этот чат как чат своей группы (если GROUP_CHAT_ID не задан) и
пишем старосте. Дальше «своя группа» = участники этого чата."""

import logging

from aiogram import F, Router
from aiogram.types import ChatMemberUpdated

from utils import esc

logger = logging.getLogger(__name__)
router = Router()


@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def bot_added_to_group(event: ChatMemberUpdated):
    import config
    import members
    from database import set_setting
    status = str(event.new_chat_member.status).split(".")[-1].lower()
    if status not in ("member", "administrator") or not config.is_starosta(event.from_user.id):
        return
    if config.GROUP_CHAT_ID and config.GROUP_CHAT_ID != event.chat.id:
        return                                  # чат задан в переменных хостинга — он главнее
    if await members.chat_id() == event.chat.id:
        return
    await set_setting("group_chat_id", str(event.chat.id))
    logger.info(f"чат своей группы: {event.chat.id} ({event.chat.title})")
    try:
        await event.bot.send_message(
            event.from_user.id,
            f"👥 Запомнил чат <b>{esc(event.chat.title or '')}</b> как чат своей группы.\n\n"
            "Теперь своя группа — это его участники: только они могут выбрать её в боте и "
            "приложении, видеть её файлы и пользоваться ИИ без пробного лимита. Остальные "
            "выбирают свою группу как обычно.", parse_mode="HTML")
    except Exception as e:
        logger.info(f"сообщение старосте о чате: {e}")
