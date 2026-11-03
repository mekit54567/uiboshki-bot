"""Классификатор намерений: короткое сообщение боту → что человек хочет
(расписание, дедлайны, файлы…). Переехал из kapibara/bot/intent_router.py
(03.11): им пользуется ИИ-бенч, а импорт из bot-слоя сцеплял модули в клубок.
Что делать с намерением — по-прежнему intent_router.dispatch_intent (бот)."""

import logging

from kapibara.features.ai import gemini as gemini_solver

logger = logging.getLogger(__name__)

MAX_CLASSIFY_CHARS = 300

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


def parse_intent(raw: str) -> str:
    """Ответ модели → намерение из списка (лишние слова и знаки не мешают)."""
    raw = (raw or "").strip().lower()
    for intent in INTENTS:
        if intent in raw:
            return intent
    return "none"


async def classify_intent(text: str) -> str:
    text = (text or "").strip()
    if not gemini_solver.GEMINI_API_KEY or len(text) < 3 or len(text) > MAX_CLASSIFY_CHARS:
        return "none"
    try:
        # max_output_tokens не задаём: у моделей с "мышлением" служебные
        # токены считаются в тот же лимит, и крошечный лимит дал бы пустой
        # ответ. Одно слово на выходе модель и так вернёт по промпту.
        raw = await gemini_solver.generate_text(
            [{"role": "user", "content": text}], SYSTEM_PROMPT,
            temperature=0, max_output_tokens=None, timeout=10, fallback=False,
        )
        return parse_intent(raw)
    except Exception as e:
        logger.warning(f"intent classify failed: {e}")
        return "none"
