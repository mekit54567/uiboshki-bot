import httpx
import base64
import logging
from config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Ты умный помощник студентов направления «Бизнес-информатика» МИРЭА.
Твоя задача — решать учебные задания с подробным объяснением на русском языке.
Структурируй ответ:
1. Краткое решение
2. Подробное объяснение шаг за шагом
3. Итог / ответ

Используй эмодзи для наглядности. Будь дружелюбен."""


async def solve_text(task: str) -> str:
    """Решить текстовую задачу через Groq."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Задание:\n{task}"},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def solve_image(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Решить задачу с фото через Groq Vision (llama-4)."""
    b64 = base64.b64encode(image_bytes).decode()
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # vision модель
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": "Реши задание на фото с подробным объяснением.",
                    },
                ],
            },
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
