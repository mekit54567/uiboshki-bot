import httpx
import base64
import logging
import json
import os

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY", "")

MODEL_TEXT  = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_PHOTO = "meta-llama/llama-4-scout-17b-16e-instruct"

SUBJECTS = [
    "Математика", "Информатика", "Экономика", "Менеджмент",
    "Иностранный язык", "Программирование", "Статистика",
    "Бизнес-анализ", "Базы данных", "Другое"
]


def build_system_prompt(subject: str = "") -> str:
    subj_part = f" по предмету «{subject}»" if subject and subject != "Другое" else ""
    return (
        f"Ты умный помощник студентов группы УИБО-03-24 МИРЭА (Бизнес-информатика){subj_part}. "
        "Решай задания с подробным объяснением на русском языке. "
        "ВАЖНО: НЕ используй LaTeX разметку ($, \\cdot, \\div, \\frac и т.д.). "
        "Пиши математику обычным текстом: умножение через ×, деление через ÷, дроби через /. "
        "Например: 27 × 44 ÷ 2, а не $27 \\cdot 44 \\div 2$. "
        "Структура ответа:\n"
        "1. Краткий ответ\n"
        "2. Решение шаг за шагом\n"
        "3. Итог\n\n"
        "Используй эмодзи, будь дружелюбен и понятен. "
        "Если пользователь задаёт уточняющий вопрос — отвечай в контексте предыдущего разговора."
    )


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }


async def solve_text(task: str, subject: str = "") -> str:
    payload = {
        "model": MODEL_TEXT,
        "messages": [
            {"role": "system", "content": build_system_prompt(subject)},
            {"role": "user",   "content": f"Задание:\n{task}"},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers=get_headers(), content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def solve_with_history(history: list, subject: str = "") -> str:
    """Решение с историей диалога."""
    messages = [{"role": "system", "content": build_system_prompt(subject)}]
    messages.extend(history)
    payload = {
        "model": MODEL_TEXT,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers=get_headers(), content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def solve_image(image_bytes: bytes, mime: str = "image/jpeg", subject: str = "") -> str:
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": MODEL_PHOTO,
        "messages": [
            {"role": "system", "content": build_system_prompt(subject)},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": "Реши задание на фото с подробным объяснением. Не используй LaTeX."},
            ]},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(GROQ_URL, headers=get_headers(), content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
