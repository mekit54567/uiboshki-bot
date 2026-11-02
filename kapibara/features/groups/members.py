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
import time

logger = logging.getLogger(__name__)

TTL = 12 * 3600
IN_CHAT = {"creator", "administrator", "member"}


# Запомненный чат — в памяти на минуту: chat_id зовётся по 5 раз на запрос
# приложения, и каждый раз — открытие базы (19.10, медленный диск).
_chat: dict[str, tuple[float, int]] = {}
CHAT_TTL = 60


async def chat_id() -> int:
    import config
    import database
    from database import get_setting
    if config.GROUP_CHAT_ID:
        return config.GROUP_CHAT_ID
    hit = _chat.get(database.DATABASE_PATH)
    if hit and time.monotonic() - hit[0] < CHAT_TTL:
        return hit[1]
    v = await get_setting("group_chat_id")
    cid = int(v) if v and v.lstrip("-").isdigit() else 0
    _chat[database.DATABASE_PATH] = (time.monotonic(), cid)
    return cid


def forget_chat():
    _chat.clear()


async def _cached(user_id: int) -> tuple[bool | None, bool]:
    """(ответ, свежий ли) из settings."""
    from database import get_setting
    v = await get_setting(f"member:{user_id}")
    if not v or ":" not in v:
        return None, False
    flag, at = v.split(":", 1)
    return flag == "1", time.time() - float(at or 0) < TTL


async def remember(user_id: int, yes: bool):
    from database import set_setting
    await set_setting(f"member:{user_id}", f"{int(yes)}:{time.time():.0f}")


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


async def known(user_id: int) -> bool | None:
    """Без запроса в Telegram: True/False по последнему ответу, None — не знаем."""
    import config
    if config.is_starosta(user_id):
        return True
    if not await chat_id():
        return None
    return (await _cached(user_id))[0]


async def is_member(user_id: int, bot=None) -> bool | None:
    """Свежий ответ: из памяти, а если устарел — у Telegram (если дан bot)."""
    import config
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
    import config
    if config.is_starosta(user_id) or bot is None or not await chat_id():
        return
    if not (await _cached(user_id))[1]:
        asyncio.create_task(check(bot, user_id))
