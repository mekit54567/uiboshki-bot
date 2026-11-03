"""
Лёгкий классификатор намерений поверх свободного текста.

Идея Фазы 1: не заставлять пользователя лезть в меню/команды для простых
вещей типа "когда следующая пара" или "покажи дедлайны" — дать распознавать
такие фразы автоматически и роутить на существующие обработчики. Команды
и кнопки остаются как раньше — это дополнительный, а не единственный путь.

Использует Gemini (тот же gemini_solver._generate, что и решалка, но со
своим коротким промптом — нужен один токен-ответ, а не решение). Раньше
здесь был Groq — его API у владельца больше не работает.

Каждый вызов тратит запрос из дневного лимита Gemini (общего с решалкой),
поэтому длинные сообщения не классифицируем вовсе: "покажи дедлайны" и
"когда следующая пара" — это короткие фразы, а текст длиннее
MAX_CLASSIFY_CHARS — почти наверняка условие задачи, и он сразу идёт в
решалку без лишнего запроса.

Fail-safe: при любой ошибке (нет ключа, таймаут, неожиданный ответ) —
возвращает "none", и вызывающий код просто ведёт себя как раньше
(fallback на решалку/игнор).
"""

import logging

# классификатор (промпт, разбор ответа) — в features: им пользуется и ИИ-бенч
from kapibara.features.ai.intent import (  # noqa: F401 — здесь их брали раньше
    INTENTS, MAX_CLASSIFY_CHARS, SYSTEM_PROMPT, classify_intent, parse_intent,
)

logger = logging.getLogger(__name__)


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
        from handlers.homework import cmd_hw
        await cmd_hw(message)
    elif intent == "rating":
        from handlers.group_tools import cmd_rating
        await cmd_rating(message)
    elif intent == "history":
        from handlers.solver import cmd_history
        await cmd_history(message)
    else:
        return False
    return True
