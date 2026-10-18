"""Канал при первом входе через Telegram (Никита 17.10, 5.97.0).

Новый человек — /start в боте или вход в приложение кнопкой «Войти через
Telegram» — сначала подписывается на открытый канал Капибары (LOGIN_CHANNEL),
жмёт «Я в канале, дальше», бот проверяет подписку (getChatMember — боту нужно
быть админом канала) и только потом здоровается или спрашивает «это вы?».

- Только новые: кто пришёл до того, как канал включили (`users.joined_at`
  раньше отметки `login_channel:since`), — как раньше. Прошёл раз — запомнено
  (`login_channel:<id>`), больше не спрашиваем.
- Вход из приложения в App Store / RuStore (устройство «Капибара · …») —
  с кнопкой «Позже»: обязательная подписка ради функций — риск по правилам
  Apple 3.2.2(x) и RuStore, поэтому там только предлагаем.
- Канал не задан или Telegram не ответил (бот не админ) — не держим: вход
  важнее подписки.
- VK ID, Яндекс ID и Apple подписку в Telegram проверить не могут — там канал
  только показываем (экран «Капибара в других местах» в приложении).
"""

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

IN_CHANNEL = {"creator", "administrator", "member"}
BUTTON = "Я в канале, дальше"


def channel() -> str:
    """@имя канала (или id -100…) из LOGIN_CHANNEL; пусто — проверки нет."""
    import config
    v = (config.LOGIN_CHANNEL or "").strip()
    m = re.search(r"t\.me/([A-Za-z0-9_]{4,})/?$", v)
    if m:
        return "@" + m.group(1)
    if v and not v.startswith(("@", "-")):
        return "@" + v
    return v


def link() -> str:
    c = channel()
    return f"https://t.me/{c[1:]}" if c.startswith("@") else ""


def store_app(device: str) -> bool:
    """Вход из своего приложения из стора (webapp/routes/auth._device)."""
    return (device or "").startswith("Капибара ·")


async def _since() -> str:
    """С какого момента канал обязателен (UTC, как users.joined_at)."""
    from database import get_setting, set_setting
    key = f"login_channel:since:{channel()}"
    v = await get_setting(key)
    if not v:
        v = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        await set_setting(key, v)
    return v


async def start():
    """При запуске бота: запомнить, с какого момента канал обязателен, — иначе
    первый новый человек записался бы в users раньше отметки и проскочил."""
    if channel():
        await _since()


async def _passed(user_id: int) -> bool:
    from database import get_setting
    return bool(await get_setting(f"login_channel:{user_id}"))


async def _remember(user_id: int):
    from database import set_setting
    await set_setting(f"login_channel:{user_id}", "1")


async def subscribed(bot, user_id: int) -> bool | None:
    """Спросить Telegram. None — не знаем (канал не задан, бот не админ…)."""
    c = channel()
    if not c or bot is None:
        return None
    try:
        m = await bot.get_chat_member(c, user_id)
    except Exception as e:
        logger.warning(f"канал входа {c}: {e}")
        return None
    status = str(getattr(m, "status", "")).split(".")[-1].lower()
    yes = status in IN_CHANNEL or (status == "restricted" and bool(getattr(m, "is_member", False)))
    if yes:
        await _remember(user_id)
    return yes


async def needed(bot, user_id: int) -> bool:
    """Показать ли человеку канал перед входом."""
    import config
    from database import get_user
    if not channel() or config.is_starosta(user_id) or await _passed(user_id):
        return False
    since = await _since()
    user = await get_user(user_id)
    if user and (user.get("joined_at") or "") <= since:
        return False                                  # был до канала — как раньше
    return await subscribed(bot, user_id) is False


def text(store: bool) -> str:
    if store:
        return ("📣 У Капибары есть канал в Telegram: новости, обновления и подсказки.\n\n"
                f"Подпишись и нажми «{BUTTON}» — или «Позже», вход от этого не зависит.")
    return ("📣 Чтобы войти, подпишись на канал Капибары — там новости, обновления и подсказки.\n\n"
            f"Подписался — нажми «{BUTTON}».")


def keyboard(next_step: str, store: bool):
    """next_step — что после: «login:<код>» или «start»/«start:ios»."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(text="Открыть канал", url=link())]] if link() else []
    rows.append([InlineKeyboardButton(text=BUTTON, callback_data=f"chan:ok:{next_step}")])
    if store:
        rows.append([InlineKeyboardButton(text="Позже", callback_data=f"chan:later:{next_step}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
