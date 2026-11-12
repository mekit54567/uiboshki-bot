"""Мелкие действия в Telegram, которые не должны ломать основной ответ:
убрать кнопки, поправить текст, удалить «⏳ думаю…», сообщить старосте.

Раньше каждое такое место было `try: … except Exception: pass` — и
ожидаемое «message is not modified», и настоящий баг пропадали молча
(docs/adr/0004-errors.md). Теперь ожидаемые ответы Telegram глотаем, а всё
остальное пишем в лог с traceback — оно видно в /status.

    with cosmetic("solver: убрать кнопки"):
        await callback.message.edit_reply_markup(reply_markup=None)
"""
import contextlib
import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from kapibara.core.errors import StaleMessage

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def cosmetic(what: str):
    try:
        yield
    except (TelegramAPIError, StaleMessage) as e:   # не изменилось, уже удалено или устарело, бот заблокирован — ожидаемо
        logger.debug(f"{what}: {e}")
    except Exception:                  # граница вспомогательного действия: ответ не ломаем, но и не молчим
        logger.warning(f"{what}: неожиданная ошибка", exc_info=True)


def app_button(text: str = "🚀 Открыть приложение", tab: str = "") -> InlineKeyboardMarkup | None:
    """Кнопка, которая открывает приложение сразу на нужном экране (?tab=…,
    js/main.js): уведомление «дедлайн завтра» → «Открыть дедлайны». None без
    WEBAPP_URL — тогда уведомление уходит без кнопки."""
    from kapibara.core.config import WEBAPP_URL     # читаем при вызове: тесты подменяют config
    if not WEBAPP_URL:
        return None
    url = WEBAPP_URL + (("&" if "?" in WEBAPP_URL else "?") + "tab=" + tab if tab else "")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]])
