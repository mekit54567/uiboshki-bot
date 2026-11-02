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

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def cosmetic(what: str):
    try:
        yield
    except TelegramAPIError as e:      # не изменилось, уже удалено, бот заблокирован, сеть — ожидаемо
        logger.debug(f"{what}: {e}")
    except Exception:                  # граница вспомогательного действия: ответ не ломаем, но и не молчим
        logger.warning(f"{what}: неожиданная ошибка", exc_info=True)
