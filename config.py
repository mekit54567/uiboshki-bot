import os

# ─── Токены и ключи ───────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ─── iCal расписание МИРЭА ────────────────────────────────────────────────────
ICAL_URL = os.getenv("ICAL_URL", "https://english.mirea.ru/schedule/api/ical/1/4928")

# ─── БД ──────────────────────────────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", "mirea_bot.db")

# ─── Groq ─────────────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"

# ─── Часовой пояс ─────────────────────────────────────────────────────────────
TIMEZONE = "Europe/Moscow"

# ─── Время утреннего расписания (МСК) ─────────────────────────────────────────
SCHEDULE_HOUR   = 6
SCHEDULE_MINUTE = 30

# ─── Время напоминания о дедлайнах (МСК) ──────────────────────────────────────
DEADLINE_REMINDER_HOUR   = 8
DEADLINE_REMINDER_MINUTE = 0
