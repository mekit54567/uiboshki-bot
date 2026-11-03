"""Своя группа = участники чата группы в Telegram (владелец, 09.10).

Кто состоит в чате (у владельца — «уибошки»), тот в своей группе: видит её
файлы, ДЗ, заметки и пользуется ИИ без пробного лимита (тариф own, plans.py) —
даже если в приложении выбрал другую группу. Остальные выбрать свою группу не
могут (groups.choose), а без выбранной группы её данных не видят
(database.groups.viewer_group). Раньше в свою группу мог записаться любой.

Чат — GROUP_CHAT_ID или запомненный, когда староста добавил бота в чат
(handlers/members_chat.py). Чат не задан или Telegram не ответил — «не знаем»
(None): тогда всё как раньше, никого не выкидываем по ошибке.

Ответ Telegram (getChatMember — боту нужно быть в чате) помнится 12 часов в
settings `member:<id>` = «1|0:время»; обновляется при заходе в приложение и
боту, при сообщении человека в чате группы и при выборе группы.
"""

import logging

# Что помнит база (чат группы, ответ Telegram за 12 ч) — database/members.py:
# туда смотрит и database.groups.viewer_group, а импорт из базы в фичи
# сцеплял модули в клубок (03.11). Здесь — то, что спрашивает Telegram.
from database.members import (  # noqa: F401 — chat_id, remember, forget_chat зовут отсюда
    CHAT_TTL, TTL, _cached, chat_id, forget_chat, remember,
)

logger = logging.getLogger(__name__)

IN_CHAT = {"creator", "administrator", "member"}


async def check(bot, user_id: int) -> bool | None:
    """Спросить Telegram. None — чат не задан или Telegram не ответил."""
    cid = await chat_id()
    if not cid or bot is None:
        return None
    try:
        m = await bot.get_chat_member(cid, user_id)
    except Exception as e:
        logger.info(f"участник чата {user_id}: {e}")
        return None
    status = str(getattr(m, "status", "")).split(".")[-1].lower()
    yes = status in IN_CHAT or (status == "restricted" and bool(getattr(m, "is_member", False)))
    await remember(user_id, yes)
    return yes


async def is_member(user_id: int, bot=None) -> bool | None:
    """Свежий ответ: из памяти, а если устарел — у Telegram (если дан bot)."""
    from kapibara.core import config
    if config.is_starosta(user_id):
        return True
    if not await chat_id():
        return None
    value, fresh = await _cached(user_id)
    if not fresh and bot is not None:
        asked = await check(bot, user_id)
        if asked is not None:
            return asked
    return value


async def refresh_later(bot, user_id: int):
    """Обновить в фоне, если ответ устарел (заход в приложение или к боту)."""
    import asyncio
    from kapibara.core import config
    if config.is_starosta(user_id) or bot is None or not await chat_id():
        return
    if not (await _cached(user_id))[1]:
        asyncio.create_task(check(bot, user_id))
