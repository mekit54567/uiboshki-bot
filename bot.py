import asyncio
import contextlib
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, MenuButtonWebApp, WebAppInfo

from config import BOT_TOKEN, STAROSTA_ID, WEBAPP_PORT, WEBAPP_URL, GROUP_NAME
from database import init_db
import health
from handlers import register_handlers
from scheduler import start_scheduler
from middleware import GroupContextMiddleware, MenuInterruptMiddleware, OptionalSubjectsMiddleware, StatsMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
health.install()   # ошибки из логов за сутки — в /status у старосты
# httpx на INFO пишет полный адрес каждого запроса — с sesskey СДО в query.
# Секрету в логах не место (и шума меньше).
logging.getLogger("httpx").setLevel(logging.WARNING)
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


# Команды в меню «/» клиента Telegram — коротко: главное в приложении
# («Корнилов»). Старосте (всем его аккаунтам) — ещё свои, остальным не видны.
BOT_COMMANDS = [
    BotCommand(command="app", description="🚀 Открыть приложение"),
    BotCommand(command="schedule", description="📅 Расписание на сегодня"),
    BotCommand(command="next", description="⏭ Следующая пара"),
    BotCommand(command="deadlines", description="📋 Дедлайны"),
    BotCommand(command="settings", description="⚙️ Уведомления"),
    BotCommand(command="help", description="📖 Что умеет бот"),
]
STAROSTA_COMMANDS = BOT_COMMANDS + [
    BotCommand(command="announce", description="📣 Рассылка группе"),
    BotCommand(command="sdofiles", description="📥 Файлы из СДО"),
    BotCommand(command="tidyfiles", description="🧹 Понятные названия файлов"),
    BotCommand(command="stats", description="📊 Статистика"),
    BotCommand(command="status", description="🩺 Состояние бота"),
    BotCommand(command="channel", description="📢 Посты канала"),
    BotCommand(command="delnote", description="🗑 Удалить заметку к паре"),
    BotCommand(command="pulsecheck", description="📡 Пускает ли Пульс"),
    BotCommand(command="netcheck", description="🌐 Сеть сервера: прокси и доступность"),
    BotCommand(command="backup", description="💾 Копия базы"),
    BotCommand(command="restore", description="♻️ Восстановить базу из копии"),
]


# Что Telegram показывает до /start: «Что умеет этот бот?» в пустом чате и
# короткая строка в профиле бота и при пересылке ссылки. Задаём из кода —
# описание всегда совпадает с тем, что бот умеет сейчас, без похода в BotFather.
BOT_DESCRIPTION = (
    "Бот и мини-приложение для студентов РТУ МИРЭА — любой группы. Сделан в {group}.\n\n"
    "📅 Расписание твоей группы, любого преподавателя или аудитории\n"
    "🎓 Баллы и дедлайны из СДО, сдача работ прямо из Telegram\n"
    "📂 Файлы курсов, поиск внутри лекций и конспекты\n"
    "✨ ИИ, который отвечает по лекциям группы и показывает слайд\n"
    "🔔 Новые задания, сроки и пары — напоминания под себя\n\n"
    "📱 И без Telegram: uiboshki.ru/app ставится на телефон и компьютер как приложение"
)
BOT_SHORT_DESCRIPTION = "Расписание, СДО, лекции и ИИ для любой группы МИРЭА — в Telegram и на uiboshki.ru"


async def setup_bot_menu(bot: Bot):
    """Список команд и кнопка меню слева от поля ввода. Если WebApp поднят —
    кнопка меню открывает его сразу (как у приложений-ботов), без отдельной
    настройки в BotFather. Не критично: при ошибке бот работает дальше."""
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        from aiogram.types import BotCommandScopeChat
        from config import STAROSTA_IDS
        for sid in STAROSTA_IDS:
            try:
                await bot.set_my_commands(STAROSTA_COMMANDS, scope=BotCommandScopeChat(chat_id=sid))
            except Exception as e:      # староста ещё не писал боту — чата нет
                logger.info(f"Команды старосты {sid}: {e}")
        from config import GROUP_NAME
        try:
            await bot.set_my_description(BOT_DESCRIPTION.format(group=GROUP_NAME))
            await bot.set_my_short_description(BOT_SHORT_DESCRIPTION.format(group=GROUP_NAME))
        except Exception as e:          # лимит Telegram на частую смену — не страшно
            logger.info(f"Описание бота: {e}")
        if WEBAPP_URL:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))
            )
    except Exception as e:
        logger.warning(f"Не смог настроить меню бота: {e}")


def start_webapp(port: int):
    """WebApp (webapp/server.py) в том же процессе, что и бот: одна служба на
    Railway, один том с SQLite — отдельный процесс не видел бы ту же базу.
    Сигналы (SIGTERM при редеплое) ловит aiogram, uvicorn свои не ставит —
    останавливаем его сами (stop_webapp) после выхода из polling. Падение
    WebApp не роняет бота. Возвращает (server, task) или (None, None)."""
    try:
        import uvicorn
        from webapp.server import app
    except Exception as e:
        logger.error(f"WebApp не запустился: {e}")
        return None, None
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    server.capture_signals = contextlib.nullcontext

    async def serve():
        try:
            logger.info(f"🌐 WebApp слушает порт {port}")
            await server.serve()
        except Exception as e:
            logger.error(f"WebApp упал: {e}")

    return server, asyncio.create_task(serve())


async def stop_webapp(server, task):
    if not task:
        return
    server.should_exit = True
    try:
        await asyncio.wait_for(task, timeout=10)
    except Exception:
        task.cancel()


async def main():
    import net
    bot = Bot(token=BOT_TOKEN, session=net.tg_session())   # прокси для Telegram из России (net.py)
    # Длиннее лимита Telegram — несколькими сообщениями (long_messages.py)
    from long_messages import SplitLongMessages
    bot.session.middleware(SplitLongMessages())
    dp  = Dispatcher(storage=MemoryStorage())

    # Outer middleware — должен успеть сбросить FSM-состояние ДО того, как
    # роутеры начнут сверять его с фильтрами хендлеров. Иначе нажатие кнопки
    # меню посреди диалога (добавление дедлайна, выбор предмета и т.д.)
    # проглатывалось как обычный текстовый ввод. См. middleware.py.
    dp.message.outer_middleware(MenuInterruptMiddleware())
    dp.update.outer_middleware(OptionalSubjectsMiddleware())
    dp.update.outer_middleware(GroupContextMiddleware())
    dp.message.outer_middleware(StatsMiddleware())
    dp.error.register(notify_starosta_on_error)

    await init_db()
    register_handlers(dp)

    scheduler = start_scheduler(bot)
    scheduler.start()

    await setup_bot_menu(bot)

    async def offer_post():         # новый пост канала — превью старосте после деплоя
        try:
            from handlers.channel import offer_next
            await offer_next(bot)
        except Exception as e:
            logger.info(f"превью поста канала: {e}")
    asyncio.create_task(offer_post())
    webapp_server, webapp_task = start_webapp(WEBAPP_PORT) if WEBAPP_PORT else (None, None)
    # Справочник для /teacher, /group, /room и поиска в WebApp — в фоне:
    # первый обход ~полчаса, дальше продолжается с места остановки.
    import schedule_index
    index_task = asyncio.create_task(schedule_index.ensure_fresh())

    logger.info(f"🚀 Бот {GROUP_NAME} запущен!")
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
        index_task.cancel()
        await stop_webapp(webapp_server, webapp_task)
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
