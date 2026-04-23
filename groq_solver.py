import httpx
import base64
import logging
from config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SUBJECTS = [
    "Математика", "Информатика", "Экономика", "Менеджмент",
    "Иностранный язык", "Программирование", "Статистика",
    "Бизнес-анализ", "Базы данных", "Другое"
]


def build_system_prompt(subject: str = "") -> str:
    subj_part = f" по предмету «{subject}»" if subject and subject != "Другое" else ""
    return (
        f"Ты умный помощник студентов группы УИБО-03-24 МИРЭА (Бизнес-информатика){subj_part}.\n"
        "Решай задания с подробным объяснением на русском языке.\n"
        "Структура ответа:\n"
        "1. Краткий ответ\n"
        "2. Решение шаг за шагом\n"
        "3. Итог\n\n"
        "Используй эмодзи, будь дружелюбен и понятен."
    )


async def solve_text(task: str, subject: str = "") -> str:
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt(subject)},
            {"role": "user",   "content": f"Задание:\n{task}"},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def solve_image(image_bytes: bytes, mime: str = "image/jpeg", subject: str = "") -> str:
    b64 = base64.b64encode(image_bytes).decode()
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": build_system_prompt(subject)},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text",      "text": "Реши задание на фото с подробным объяснением."},
            ]},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
