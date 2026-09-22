import logging
import os

logger = logging.getLogger(__name__)

# ─── Токены ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
ICAL_URL      = os.getenv("ICAL_URL", "https://english.mirea.ru/schedule/api/ical/1/4928")

# ─── БД ───────────────────────────────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", "mirea_bot.db")

# ─── Группа ───────────────────────────────────────────────────────────────────
GROUP_NAME = "УИБО-03-24"
TIMEZONE   = "Europe/Moscow"

# ─── ID старосты (твой Telegram ID) ───────────────────────────────────────────
# Узнать свой ID: написать @userinfobot в Telegram
STAROSTA_ID = int(os.getenv("STAROSTA_ID", "0"))

if not STAROSTA_ID:
    logger.warning(
        "⚠️ STAROSTA_ID не задан (0)! Все admin-команды (/announce, /setzam, "
        "/importdeadlines, /syncfiles, /delpost) сейчас доступны АБСОЛЮТНО ВСЕМ "
        "пользователям бота. Задай STAROSTA_ID в переменных окружения как можно скорее."
    )

# ─── Лента "Подслушано" ─────────────────────────────────────────────────────────
# ID группового чата, куда бот постит анонимные сообщения (лента).
# Узнать: добавить бота в группу админом, отправить туда любое сообщение,
# и посмотреть update.message.chat.id в логах (обычно отрицательное число).
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
FEED_COOLDOWN_MINUTES = int(os.getenv("FEED_COOLDOWN_MINUTES", "10"))

if not GROUP_CHAT_ID:
    logger.warning(
        "⚠️ GROUP_CHAT_ID не задан — лента 'Подслушано' работать не будет, "
        "пока не укажешь ID группового чата в переменных окружения."
    )

# ─── Расписание рассылок ──────────────────────────────────────────────────────
SCHEDULE_HOUR   = 7
SCHEDULE_MINUTE = 30
DEADLINE_REMINDER_HOUR   = 8
DEADLINE_REMINDER_MINUTE = 0

# ─── Уведомление до пары (минут, можно менять через /setreminder) ─────────────
DEFAULT_REMINDER_MINUTES = 15

# ─── Кэш расписания (минут) ────────────────────────────────────────────────────
SCHEDULE_CACHE_TTL_SECONDS = int(os.getenv("SCHEDULE_CACHE_TTL_SECONDS", "300"))

# ─── СДО (Moodle) ───────────────────────────────────────────────────────────────
# Значение куки MoodleSession, полученное один раз обычным логином в браузере
# (с "запомнить меня"). Когда протухнет — старосте прилетит уведомление,
# нужно будет зайти в СДО в браузере и обновить значение здесь.
SDO_SESSION_COOKIE = os.getenv("SDO_SESSION_COOKIE", "")
SDO_BASE_URL = os.getenv("SDO_BASE_URL", "https://online-edu.mirea.ru")
SDO_SYNC_INTERVAL_HOURS = int(os.getenv("SDO_SYNC_INTERVAL_HOURS", "6"))

if not SDO_SESSION_COOKIE:
    logger.warning(
        "⚠️ SDO_SESSION_COOKIE не задана — автосинк дедлайнов из СДО работать не будет."
    )
