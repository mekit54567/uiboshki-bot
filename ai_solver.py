"""
Обычная решалка бота: /solve, «🤖 Решить», задача обычным текстом без
команды, уточняющий диалог, фото задачи, распознавание текста с фото для
дедлайнов. Основной бэкенд — Gemini (gemini_solver.py), DeepSeek — по
желанию: /solve_ds или префикс "дипсик:" в тексте.

Раньше основным бэкендом был Groq (файл назывался groq_solver.py). Его API
у владельца больше не работает — решалка отвечала пользователю ошибкой, —
а нужен ему Gemini, поэтому Groq удалён целиком, без фолбэка на него.
Фото и OCR всегда идут через Gemini: у deepseek-chat нет зрения.
"""

import json
import logging

import httpx

import gemini_solver
from config import DEEPSEEK_API_KEY

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL_DEEPSEEK = "deepseek-chat"
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"

BACKENDS = ("gemini", "deepseek")

SUBJECTS = [
    "Математика", "Информатика", "Экономика", "Менеджмент",
    "Иностранный язык", "Программирование", "Статистика",
    "Бизнес-анализ", "Базы данных", "Другое"
]

OCR_SYSTEM_PROMPT = (
    "Ты просто распознаёшь текст с фотографии. Не решай задачи, не комментируй "
    "и не добавляй ничего от себя — верни только текст, который есть на фото, как есть."
)


def build_system_prompt(subject: str = "") -> str:
    subj_part = f" по предмету «{subject}»" if subject and subject != "Другое" else ""
    return (
        f"Ты умный помощник студентов группы УИБО-03-24 МИРЭА (Бизнес-информатика){subj_part}. "
        "Решай задания с подробным объяснением на русском языке. "
        "ВАЖНО: НЕ используй LaTeX разметку ($, \\cdot, \\div, \\frac и т.д.). "
        "Пиши математику обычным текстом: умножение через ×, деление через ÷, дроби через /. "
        "Структура ответа:\n"
        "1. Краткий ответ\n"
        "2. Решение\n"
        "3. Итог\n\n"
        "Используй эмодзи, будь дружелюбен и понятен. "
        "Если пользователь задаёт уточняющий вопрос — отвечай в контексте предыдущего разговора."
    )


def _resolve_backend(backend: str) -> str:
    if backend not in BACKENDS:
        return "gemini"
    if backend == "deepseek" and not DEEPSEEK_API_KEY:
        logger.warning("DeepSeek запрошен, но DEEPSEEK_API_KEY не задан — фолбэк на Gemini")
        return "gemini"
    return backend


async def _deepseek_chat(messages: list[dict], model: str = MODEL_DEEPSEEK, **params) -> dict:
    body = json.dumps({"model": model, "messages": messages, **params}, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(DEEPSEEK_URL, headers=headers, content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


async def solve_with_history(history: list, subject: str = "", backend: str = "gemini") -> str:
    """history — [{"role": "user"|"assistant", "content": str}, ...]."""
    system = build_system_prompt(subject)
    if _resolve_backend(backend) == "deepseek":
        msg = await _deepseek_chat(
            [{"role": "system", "content": system}, *history], max_tokens=2048, temperature=0.3,
        )
        return msg["content"]
    return await gemini_solver.generate_text(history, system)


async def solve_text(task: str, subject: str = "", backend: str = "gemini") -> str:
    return await solve_with_history([{"role": "user", "content": f"Задание:\n{task}"}], subject, backend)


async def solve_image(image_bytes: bytes, mime: str = "image/jpeg", subject: str = "") -> str:
    return await gemini_solver.generate_from_image(
        image_bytes, mime,
        "Реши задание на фото с подробным объяснением. Не используй LaTeX.",
        build_system_prompt(subject),
    )


async def extract_text_from_image(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """OCR фото для дедлайнов: только достаёт текст с картинки, ничего не решает
    и не комментирует (в отличие от solve_image) — используется, когда к
    дедлайну прикладывают фото задания вместо того, чтобы печатать текст руками.
    Если текста на фото нет, Gemini отдаёт пустой ответ -> GeminiError, и
    хендлер честно пишет "не смог распознать"."""
    return await gemini_solver.generate_from_image(
        image_bytes, mime, "Извлеки весь текст с этого фото.", OCR_SYSTEM_PROMPT,
        temperature=0.0,
    )


async def chat_with_reasoning(history: list, subject: str = "") -> dict:
    """Для WebApp-чата: всегда deepseek-reasoner — единственная модель
    DeepSeek, которая отдаёт отдельное поле reasoning_content ("как думала")
    в дополнение к обычному content ("что ответила"). Раздельно, чтобы фронт
    мог свернуть/развернуть трейс независимо от самого ответа — см. PLAN.md,
    идея владельца про "мышление" как в приложениях DeepSeek/ChatGPT/Claude.
    Фолбэка нет — чат в WebApp это отдельная, опциональная фича: если
    DEEPSEEK_API_KEY не задан, честно кидаем исключение, WebApp покажет
    понятную ошибку вместо того, чтобы тихо подсунуть другую модель под тем
    же UI. Возвращает {"content": str, "reasoning": str}."""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY не настроен на сервере")
    msg = await _deepseek_chat(
        [{"role": "system", "content": build_system_prompt(subject)}, *history],
        model=MODEL_DEEPSEEK_REASONER, max_tokens=4096,
    )
    return {
        "content": msg.get("content", ""),
        "reasoning": msg.get("reasoning_content", ""),
    }
