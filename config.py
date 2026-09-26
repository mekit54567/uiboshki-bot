import logging
import os

logger = logging.getLogger(__name__)

# ─── Токены ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN")
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

# ─── Gemini — основной ИИ-бэкенд бота ───────────────────────────────────────────
# Обычная решалка (/solve, задачи текстом и фото), OCR фото дедлайнов,
# классификатор намерений и решалка по лекциям — всё через Gemini (см.
# gemini_solver.py, ai_solver.py). Groq раньше был основным бэкендом — удалён:
# его API у владельца больше не работает. DeepSeek остался опцией (/solve_ds).
#
# Решалка по лекциям решает задание, опираясь на полный текст лекций
# выбранного предмета (см. file_text.py, database.get_subject_lecture_context).
# Для неё нужен именно Gemini из-за размера контекста — целый предмет (8-16
# лекций) легко превышает 100-300К токенов, это не лезет в бесплатный лимит
# DeepSeek. У Gemini
# контекстное окно 1M токенов, но реальный free/AI-Studio тир (проверено на
# аккаунте владельца, сентябрь 2026) даёт всего 250К токенов/минуту на запрос —
# это тоже жёсткий потолок на размер контекста одного запроса, не только скорость
# (см. gemini_solver._fit_context_budget — обрезка по целым лекциям, если предмет
# не влезает). GEMINI_MODEL — gemini-3.1-flash-lite выбран не как "самая мощная",
# а как модель с лучшим дневным лимитом на этом тире (500 RPD против 20 RPD у
# gemini-3-flash/2.5-flash/3.5-flash — TPM у всех одинаковый, 250К). Эти 500
# запросов в день теперь общие на решалку, фото, OCR и классификатор намерений
# (длинные сообщения классификатор пропускает — см. intent_router.py).
# Google меняет линейку моделей быстро — если решалка отвечает 404 на имя модели,
# смотри актуальный список в Google AI Studio → ключ API → "Copy cURL quickstart".
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# ─── WebApp (Mini App) ─────────────────────────────────────────────────────────
# HTTPS-адрес, на котором крутится webapp/server.py (см. webapp/README.md).
# Пока не задан — кнопки "Открыть приложение" в боте просто не показываются,
# это не критическая функция, ничего не падает без неё.
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

# ─── Расписание рассылок ──────────────────────────────────────────────────────
SCHEDULE_HOUR   = 7
SCHEDULE_MINUTE = 30
DEADLINE_REMINDER_HOUR   = 8
DEADLINE_REMINDER_MINUTE = 0

# ─── Уведомление до пары (минут, можно менять через /setreminder) ─────────────
DEFAULT_REMINDER_MINUTES = 15

# ─── Кэш расписания (минут) ────────────────────────────────────────────────────
SCHEDULE_CACHE_TTL_SECONDS = int(os.getenv("SCHEDULE_CACHE_TTL_SECONDS", "300"))

# ─── Диффы расписания ───────────────────────────────────────────────────────────
SCHEDULE_DIFF_CHECK_MINUTES = int(os.getenv("SCHEDULE_DIFF_CHECK_MINUTES", "20"))

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
