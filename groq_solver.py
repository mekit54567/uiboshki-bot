import httpx
import base64
import logging
import json
import os

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY", "")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")

MODEL_TEXT      = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_PHOTO     = "meta-llama/llama-4-scout-17b-16e-instruct"
MODEL_DEEPSEEK  = "deepseek-chat"
MODEL_DEEPSEEK_REASONER = "deepseek-reasoner"

# Фото понимает только Groq (llama-4-scout умеет в vision, DeepSeek chat — нет),
# поэтому solve_image всегда идёт через Groq вне зависимости от backend.
BACKENDS = ("groq", "deepseek")

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
        "Структура ответа:\n"
        "1. Краткий ответ\n"
        "2. Решение\n"
        "3. Итог\n\n"
        "Используй эмодзи, будь дружелюбен и понятен. "
        "Если пользователь задаёт уточняющий вопрос — отвечай в контексте предыдущего разговора."
    )


def get_headers(backend: str = "groq") -> dict:
    key = DEEPSEEK_KEY if backend == "deepseek" else GROQ_KEY
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _url_and_model(backend: str) -> tuple[str, str]:
    if backend == "deepseek":
        return DEEPSEEK_URL, MODEL_DEEPSEEK
    return GROQ_URL, MODEL_TEXT


async def solve_text(task: str, subject: str = "", backend: str = "groq") -> str:
    if backend not in BACKENDS:
        backend = "groq"
    if backend == "deepseek" and not DEEPSEEK_KEY:
        logger.warning("DeepSeek запрошен, но DEEPSEEK_API_KEY не задан — фолбэк на Groq")
        backend = "groq"
    url, model = _url_and_model(backend)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": build_system_prompt(subject)},
            {"role": "user",   "content": f"Задание:\n{task}"},
        ],
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=get_headers(backend), content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def solve_with_history(history: list, subject: str = "", backend: str = "groq") -> str:
    if backend not in BACKENDS:
        backend = "groq"
    if backend == "deepseek" and not DEEPSEEK_KEY:
        logger.warning("DeepSeek запрошен, но DEEPSEEK_API_KEY не задан — фолбэк на Groq")
        backend = "groq"
    url, model = _url_and_model(backend)
    messages = [{"role": "system", "content": build_system_prompt(subject)}]
    messages.extend(history)
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.3,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=get_headers(backend), content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def chat_with_reasoning(history: list, subject: str = "") -> dict:
    """Для WebApp-чата: в отличие от solve_text/solve_with_history (модель
    deepseek-chat, без видимого мышления), тут всегда deepseek-reasoner —
    единственная модель DeepSeek, которая отдаёт отдельное поле
    reasoning_content ("как думала") в дополнение к обычному content
    ("что ответила"). Раздельно, чтобы фронт мог свернуть/развернуть трейс
    независимо от самого ответа — см. PLAN.md, идея владельца про "мышление"
    как в приложениях DeepSeek/ChatGPT/Claude.
    Фолбэк не нужен (в отличие от solve_text) — чат в WebApp это отдельная,
    опциональная фича, а не подмена решалки в боте: если DEEPSEEK_API_KEY не
    задан, честно кидаем исключение, WebApp покажет пользователю понятную
    ошибку вместо того, чтобы тихо подсунуть другую модель под тем же UI.
    Возвращает {"content": str, "reasoning": str}."""
    if not DEEPSEEK_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY не настроен на сервере")
    messages = [{"role": "system", "content": build_system_prompt(subject)}]
    messages.extend(history)
    payload = {
        "model": MODEL_DEEPSEEK_REASONER,
        "messages": messages,
        "max_tokens": 4096,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(DEEPSEEK_URL, headers=get_headers("deepseek"), content=body)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        return {
            "content": msg.get("content", ""),
            "reasoning": msg.get("reasoning_content", ""),
        }


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
