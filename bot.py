import asyncio
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from config import BOT_TOKEN, STAROSTA_ID
from database import init_db
from handlers import register_handlers
from scheduler import start_scheduler
from middleware import MenuInterruptMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Минимальный алертинг без внешних сервисов: любая необработанная ошибка
# внутри хендлера (aiogram сам ловит такие на уровне апдейта и не роняет
# polling) логируется как раньше, но ТЕПЕРЬ ещё и коротко летит старосте в
# личку — иначе о падении фичи узнаёшь только от жалоб студентов через
# день-два. Троттлинг на 5 минут, чтобы одна и та же повторяющаяся ошибка
# (например упавшее внешнее API) не заспамила личку сотней сообщений подряд.
#
# Сентинел -inf, а не 0.0: time.monotonic() отсчитывается от старта процесса
# (не от эпохи!) — на свежем контейнере/хосте в первые минуты жизни он сам
# может быть маленьким числом (реально пойман на CI: now=106.58 на 106-й
# секунде жизни джобы). C 0.0 в качестве "никогда не алертили" первый же
# настоящий алерт в первые 5 минут работы бота молча проглатывался бы.
_LAST_ERROR_ALERT_AT = float("-inf")
_ERROR_ALERT_COOLDOWN_SECONDS = 5 * 60


async def notify_starosta_on_error(event: ErrorEvent, bot: Bot):
    global _LAST_ERROR_ALERT_AT
    logger.exception(f"Необработанная ошибка в хендлере: {event.exception}")

    if not STAROSTA_ID:
        return
    now = time.monotonic()
    if now - _LAST_ERROR_ALERT_AT < _ERROR_ALERT_COOLDOWN_SECONDS:
        return
    _LAST_ERROR_ALERT_AT = now
    try:
        await bot.send_message(
            STAROSTA_ID,
            f"⚠️ Бот словил ошибку: {type(event.exception).__name__}: {event.exception}\n\n"
            f"Подробности — в логах (следующий такой алерт не раньше чем через 5 минут).",
        )
    except Exception as e:
        logger.warning(f"Не смог отправить алерт старосте: {e}")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # Outer middleware — должен успеть сбросить FSM-состояние ДО того, как
    # роутеры начнут сверять его с фильтрами хендлеров. Иначе нажатие кнопки
    # меню посреди диалога (добавление дедлайна, выбор предмета и т.д.)
    # проглатывалось как обычный текстовый ввод. См. middleware.py.
    dp.message.outer_middleware(MenuInterruptMiddleware())
    dp.error.register(notify_starosta_on_error)

    await init_db()
    register_handlers(dp)

    scheduler = start_scheduler(bot)
    scheduler.start()

    logger.info("🚀 Бот УИБО-03-24 запущен!")
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        # Сюда попадают только фатальные сбои самого polling (не ошибки
        # хендлеров — те ловит dp.error выше): невалидный токен, обрыв сети
        # на уровне aiogram и т.п. Лучший эффорт — предупредить старосту,
        # хотя если причина именно в сети, само сообщение тоже может не уйти.
        logger.critical(f"Polling упал целиком: {e}")
        if STAROSTA_ID:
            try:
                await bot.send_message(STAROSTA_ID, f"🔴 Бот полностью упал: {type(e).__name__}: {e}")
            except Exception:
                pass
        raise
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
