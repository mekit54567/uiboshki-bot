"""
Лёгкий классификатор намерений поверх свободного текста.

Идея Фазы 1: не заставлять пользователя лезть в меню/команды для простых
вещей типа "когда следующая пара" или "покажи дедлайны" — дать распознавать
такие фразы автоматически и роутить на существующие обработчики. Команды
и кнопки остаются как раньше — это дополнительный, а не единственный путь.

Использует маленькую быструю модель Groq отдельно от groq_solver.py
(там модель заточена под решение задач с полным объяснением — сюда
это не нужно, нужен один короткий токен-ответ).

Fail-safe: при любой ошибке (нет ключа, таймаут, неожиданный ответ) —
возвращает "none", и вызывающий код просто ведёт себя как раньше
(fallback на решалку/игнор).
"""

import logging
import httpx

from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLASSIFIER_MODEL = "llama-3.1-8b-instant"

INTENTS = [
    "schedule_today", "schedule_tomorrow", "schedule_week", "schedule_next_week",
    "next_lesson", "deadlines_list", "files", "weather", "homework", "rating",
    "history", "none",
]

SYSTEM_PROMPT = (
    "Ты классификатор намерений для Telegram-бота студенческой группы. "
    "Тебе дают одно сообщение пользователя. Определи, что он хочет, из списка:\n"
    "schedule_today — расписание на сегодня\n"
    "schedule_tomorrow — расписание на завтра\n"
    "schedule_week — расписание на эту неделю\n"
    "schedule_next_week — расписание на следующую неделю\n"
    "next_lesson — когда следующая/ближайшая пара\n"
    "deadlines_list — показать дедлайны/что сдавать/когда сдача\n"
    "files — файлы/материалы/лекции/методички\n"
    "weather — погода\n"
    "homework — доска домашних заданий (что задано)\n"
    "rating — рейтинг активности\n"
    "history — история решённых через бота задач\n"
    "none — ничего из этого не подходит (учебная задача для решения, "
    "вопрос не по функциям бота, обычная фраза/болтовня)\n\n"
    "Отвечай СТРОГО одним словом из списка выше, без пояснений и знаков препинания."
)


async def classify_intent(text: str) -> str:
    if not GROQ_API_KEY or not text or len(text.strip()) < 3:
        return "none"
    try:
        payload = {
            "model": CLASSIFIER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:500]},
            ],
            "max_tokens": 10,
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
            for intent in INTENTS:
                if intent in raw:
                    return intent
            return "none"
    except Exception as e:
        logger.warning(f"intent classify failed: {e}")
        return "none"


async def dispatch_intent(intent: str, message) -> bool:
    """Вызывает соответствующий существующий хендлер напрямую.
    Возвращает True, если что-то обработали, False — если intent неизвестен
    (тогда вызывающий код сам решает, что делать дальше, обычно — решалка)."""
    if intent == "schedule_today":
        from handlers.schedule import cmd_today
        await cmd_today(message)
    elif intent == "schedule_tomorrow":
        from handlers.schedule import cmd_tomorrow
        await cmd_tomorrow(message)
    elif intent == "schedule_week":
        from handlers.schedule import cmd_week
        await cmd_week(message)
    elif intent == "schedule_next_week":
        from handlers.schedule import cmd_next_week
        await cmd_next_week(message)
    elif intent == "next_lesson":
        from handlers.schedule import cmd_next
        await cmd_next(message)
    elif intent == "deadlines_list":
        from handlers.deadlines import cmd_deadlines
        await cmd_deadlines(message)
    elif intent == "files":
        from handlers.files import cmd_files
        await cmd_files(message)
    elif intent == "weather":
        from handlers.weather import cmd_weather
        await cmd_weather(message)
    elif intent == "homework":
        from handlers.announce import cmd_hw
        await cmd_hw(message)
    elif intent == "rating":
        from handlers.announce import cmd_rating
        await cmd_rating(message)
    elif intent == "history":
        from handlers.solver import cmd_history
        await cmd_history(message)
    else:
        return False
    return True
