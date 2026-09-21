"""
Общие middleware диспетчера.

MenuInterruptMiddleware чинит системный баг: нажатие любой кнопки меню
(MENU_BUTTON_TEXTS) во время активного FSM-диалога (добавление дедлайна,
загрузка файла, выбор предмета для решателя и т.д.) раньше могло улететь
как обычный текстовый ввод в базу вместо того, чтобы прервать диалог.
Теперь это проверяется в одном месте для всего бота, а не дублируется
(с расхождениями) в каждом хендлере отдельно.
"""

import logging
from aiogram import BaseMiddleware
from aiogram.types import Message

from keyboards import MENU_BUTTON_TEXTS

logger = logging.getLogger(__name__)


class MenuInterruptMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        state = data.get("state")
        if state is not None and event.text and event.text in MENU_BUTTON_TEXTS:
            current = await state.get_state()
            if current is not None:
                logger.info(f"Menu button '{event.text}' interrupted FSM state {current} for user {event.from_user.id}")
                await state.clear()
        return await handler(event, data)
