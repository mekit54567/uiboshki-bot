import os

# ─── Токены ───────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ICAL_URL     = os.getenv("ICAL_URL", "https://english.mirea.ru/schedule/api/ical/1/4928")

# ─── БД ───────────────────────────────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", "mirea_bot.db")

# ─── Groq ─────────────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"

# ─── Группа ───────────────────────────────────────────────────────────────────
GROUP_NAME = "УИБО-03-24"
TIMEZONE   = "Europe/Moscow"

# ─── ID старосты (твой Telegram ID) ───────────────────────────────────────────
# Узнать свой ID: написать @userinfobot в Telegram
STAROSTA_ID = int(os.getenv("STAROSTA_ID", "0"))

# ─── Расписание рассылок ──────────────────────────────────────────────────────
SCHEDULE_HOUR   = 7
SCHEDULE_MINUTE = 30
DEADLINE_REMINDER_HOUR   = 8
DEADLINE_REMINDER_MINUTE = 0

# ─── Уведомление до пары (минут, можно менять через /setreminder) ─────────────
DEFAULT_REMINDER_MINUTES = 15
