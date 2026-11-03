"""Участники чата своей группы — что помнит база (kapibara/features/groups/
members.py — что спрашивает Telegram). Переехало оттуда 03.11: это чтение
settings и config, а database.groups.viewer_group звал его из фич.

settings `member:<id>` = «1|0:время» — последний ответ getChatMember, живёт
12 часов; `group_chat_id` — чат, куда староста добавил бота."""
import time

from database import _conn

TTL = 12 * 3600


# Запомненный чат — в памяти на минуту: chat_id зовётся по 5 раз на запрос
# приложения, и каждый раз — открытие базы (19.10, медленный диск).
_chat: dict[str, tuple[float, int]] = {}
CHAT_TTL = 60


async def chat_id() -> int:
    from kapibara.core import config
    from database.settings import get_setting
    if config.GROUP_CHAT_ID:
        return config.GROUP_CHAT_ID
    hit = _chat.get(_conn.DATABASE_PATH)
    if hit and time.monotonic() - hit[0] < CHAT_TTL:
        return hit[1]
    v = await get_setting("group_chat_id")
    cid = int(v) if v and v.lstrip("-").isdigit() else 0
    _chat[_conn.DATABASE_PATH] = (time.monotonic(), cid)
    return cid


def forget_chat():
    _chat.clear()


async def _cached(user_id: int) -> tuple[bool | None, bool]:
    """(ответ, свежий ли) из settings."""
    from database.settings import get_setting
    v = await get_setting(f"member:{user_id}")
    if not v or ":" not in v:
        return None, False
    flag, at = v.split(":", 1)
    return flag == "1", time.time() - float(at or 0) < TTL


async def remember(user_id: int, yes: bool):
    from database.settings import set_setting
    await set_setting(f"member:{user_id}", f"{int(yes)}:{time.time():.0f}")


async def known(user_id: int) -> bool | None:
    """Без запроса в Telegram: True/False по последнему ответу, None — не знаем."""
    from kapibara.core import config
    if config.is_starosta(user_id):
        return True
    if not await chat_id():
        return None
    return (await _cached(user_id))[0]
