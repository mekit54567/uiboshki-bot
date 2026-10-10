import logging
import os
import re

logger = logging.getLogger(__name__)

# ─── Токены ───────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# OpenRouter — выбор модели ИИ для других групп (/aitest, ai_bench.py); без ключа команда объясняет, что задать
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Запасная модель через OpenRouter, когда у всех моделей Gemini кончился
# бесплатный лимит (429): по отбору /aitest 10.10 — Ling 3.0 Flash VL, почти
# на уровне Gemini, видит фото, ~10 ₽ за 1000 вопросов. Пусто — без неё.
AI_SPARE_MODEL = os.getenv("AI_SPARE_MODEL", "inclusionai/ling-3.0-flash-vl") if OPENROUTER_API_KEY else ""
ICAL_URL      = os.getenv("ICAL_URL", "https://english.mirea.ru/schedule/api/ical/1/4928")

# ─── БД ───────────────────────────────────────────────────────────────────────
DATABASE_PATH = os.getenv("DATABASE_PATH", "mirea_bot.db")

# ─── Группа ───────────────────────────────────────────────────────────────────
GROUP_NAME = os.getenv("GROUP_NAME", "УИБО-03-24")
BOT_USERNAME = os.getenv("BOT_USERNAME", "uiboshkibot").lstrip("@")   # для ссылок t.me/…
GROUP_PROGRAM = os.getenv("GROUP_PROGRAM", "Бизнес-информатика")        # направление — для промптов ИИ
# Плитки «Канал бота» и «Написать нам» в меню «Ещё» WebApp (дизайн-ревью, п. 18):
# ссылки t.me/… (или любые). Пока пусто — плитка видна, по нажатию «Скоро».
CHANNEL_URL = os.getenv("CHANNEL_URL", "").strip()
CONTACT_URL = os.getenv("CONTACT_URL", "").strip()
# Куда бот публикует посты канала (/channel у старосты): «@uiboshki_dev» или
# id «-100…». Не задан — берём @имя из CHANNEL_URL вида t.me/<имя>.
def channel_id_from(explicit: str, url: str) -> str:
    m = re.search(r"t\.me/([A-Za-z0-9_]{4,})/?$", url or "")
    return (explicit or "").strip() or (f"@{m.group(1)}" if m else "")


CHANNEL_ID = channel_id_from(os.getenv("CHANNEL_ID", ""), CHANNEL_URL)
# Предметы по выбору: ходят не все (военная кафедра — двое из группы).
# Пары скрыты, пока человек не ответит «хожу» (WebApp спросит на главной,
# бот — при /start). Через запятую.
OPTIONAL_SUBJECTS = [s.strip() for s in os.getenv("OPTIONAL_SUBJECTS", "Военная кафедра").split(",") if s.strip()]
TIMEZONE   = "Europe/Moscow"

# ─── ID старосты (твой Telegram ID) ───────────────────────────────────────────
# Узнать свой ID: написать @userinfobot в Telegram
# Можно несколько через запятую — второй аккаунт старосты: «111,222».
# Первый — основной: ему приходят уведомления, бэкапы, вопросы; права старосты
# у всех перечисленных (is_starosta).
def parse_ids(raw: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.split(r"[\s,;]+", raw or "") if x.lstrip("-").isdigit() and int(x))


STAROSTA_IDS = parse_ids(os.getenv("STAROSTA_ID", "0"))
STAROSTA_ID = STAROSTA_IDS[0] if STAROSTA_IDS else 0


def is_starosta(user_id) -> bool:
    return user_id in STAROSTA_IDS

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
# Запасные модели через запятую: основная упёрлась в лимит (HTTP 429) — тот же
# запрос уходит следующей. Лимиты бесплатного тира у каждой модели свои
# (у основной 500 в день, у остальных по 20), так что это ещё десятки
# ответов в день, когда основная кончилась. Пусто — без запасных.
# gemini-flash-latest — псевдоним Google на текущую Flash (имена у Google
# меняются: 10.10 gemini-2.5-flash отдавала 404); какой нет — пропускается.
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS",
                                                       "gemini-flash-latest,gemini-2.5-flash").split(",")
                          if m.strip()]
# Вопросов к ИИ в сутки на человека (ИИ-чат, решалка, конспекты); 0 — без
# дневного лимита. Бесплатный лимит Gemini — один на всю группу: если его
# начнут выжигать за день — задать, например, 40. Старосты — без лимита.
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "0") or 0)
# Любая группа института (этап 1, PLAN.md «Своё приложение»). «Своя» группа
# (id на зеркале — из ICAL_URL) пользуется ИИ как раньше; другие группы —
# база: проба ИИ (AI_TRIAL_DAILY вопросов в день на человека и не больше
# AI_TRIAL_DAY_TOTAL на всех за день — потолок пробы ~5 тыс. ₽ в месяц) и
# SUMMARY_WEEKLY новых конспектов в неделю; подписка — до AI_SUB_DAILY в день.
_home = __import__("re").search(r"/ical/1/(\d+)", ICAL_URL)
HOME_GROUP_ID = int(_home.group(1)) if _home else 0
AI_TRIAL_DAILY = int(os.getenv("AI_TRIAL_DAILY", "3") or 0)
AI_TRIAL_DAY_TOTAL = int(os.getenv("AI_TRIAL_DAY_TOTAL", "1500") or 0)
AI_SUB_DAILY = int(os.getenv("AI_SUB_DAILY", "100") or 0)
SUMMARY_WEEKLY = int(os.getenv("SUMMARY_WEEKLY", "3") or 0)
# Поиск по смыслу (semantic_search.py): модель эмбеддингов и длина вектора
# (Matryoshka — урезается без переобучения; 768 — баланс точности и размера).
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_EMBED_DIMS = int(os.getenv("GEMINI_EMBED_DIMS", "768"))

# ─── WebApp (Mini App) ─────────────────────────────────────────────────────────
# HTTPS-адрес, на котором крутится webapp/server.py (см. webapp/README.md).
# Пока не задан — кнопки "Открыть приложение" в боте просто не показываются,
# это не критическая функция, ничего не падает без неё.
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
# Порт HTTP-сервера WebApp внутри того же процесса, что и бот (см. bot.py).
# Railway сам кладёт PORT в окружение сервиса и проксирует на него публичный
# домен. 0 — WebApp не поднимаем (локальный запуск без WEBAPP_URL и PORT).
WEBAPP_PORT = int(os.getenv("PORT") or os.getenv("WEBAPP_PORT") or (8080 if WEBAPP_URL else 0))

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
