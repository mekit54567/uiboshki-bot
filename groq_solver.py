import httpx
import base64
import logging
import json

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = "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"

MODEL_TEXT  = "google/gemini-2.0-flash-exp:free"
MODEL_PHOTO = "google/gemini-2.0-flash-exp:free"

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
        "Структура ответа: 1. Краткий ответ 2. Решение шаг за шагом 3. Итог. "
        "Используй эмодзи, будь дружелюбен."
    )


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/uibo_bot",
        "X-Title": "UIBO-03-24 Bot",
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
        resp = await client.post(
            OPENROUTER_URL,
            headers=get_headers(),
            content=body
        )
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
                {"type": "text", "text": "Реши задание на фото с подробным объяснением."},
            ]},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers=get_headers(),
            content=body
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
