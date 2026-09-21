import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import register_handlers
from scheduler import start_scheduler
from middleware import MenuInterruptMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # Outer middleware — должен успеть сбросить FSM-состояние ДО того, как
    # роутеры начнут сверять его с фильтрами хендлеров. Иначе нажатие кнопки
    # меню посреди диалога (добавление дедлайна, выбор предмета и т.д.)
    # проглатывалось как обычный текстовый ввод. См. middleware.py.
    dp.message.outer_middleware(MenuInterruptMiddleware())

    await init_db()
    register_handlers(dp)

    scheduler = start_scheduler(bot)
    scheduler.start()

    logger.info("🚀 Бот УИБО-03-24 запущен!")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
