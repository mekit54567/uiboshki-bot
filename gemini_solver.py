"""
Всё общение бота с Gemini — один HTTP-вызов (_generate) на все сценарии:
обычная решалка (/solve, задача обычным текстом, диалог), фото задачи,
распознавание текста с фото для дедлайнов, классификатор намерений
(intent_router.py) и решалка "по лекциям". Раньше всё, кроме решалки по
лекциям, шло через Groq — его API у владельца больше не работает, и
решалка отвечала пользователю ошибкой. Выбор бэкенда (Gemini по умолчанию,
DeepSeek по /solve_ds) и промпты обычной решалки — в ai_solver.py.

Решалка "по лекциям" (solve_with_lecture_context) отличается не
провайдером, а задачей: обычная решалка решает задание "с нуля", своими
знаниями. Эта получает на вход ПОЛНЫЙ текст всех лекций выбранного
предмета (database.get_subject_lecture_context, собранный один раз при
загрузке файлов через file_text.py — не парсим заново на каждый запрос, это
и есть "кэш" контекста) и должна отвечать в первую очередь опираясь на них,
а к своим знаниям обращаться только там, где лекции не дают ответа — и явно
это помечать.

Почему для лекций только Gemini, а не DeepSeek: контекст одного предмета — реально
100-400К+ токенов (проверено на живых лекциях МИРЭА, см. PLAN.md Фаза 9), это
не лезет ни в контекстное окно, ни в лимит токенов/минуту бесплатного тира
DeepSeek. У Gemini free tier контекст 1M токенов и достаточный RPD/TPM
для масштаба одной группы. Кэширования на стороне самого Gemini НЕТ на free
tier (и implicit, и explicit caching — платная фича) — поэтому кэшируем не
ответ и не сам запрос к Gemini, а сборку контекста у себя в БД.
"""

import base64
import logging
import httpx

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(RuntimeError):
    """Ошибка Gemini с уже человекочитаемым текстом — хендлеры показывают
    str(e) пользователю как есть ("❌ Ошибка: ...")."""


# Что показать пользователю вместо сырого httpx-исключения (в нём полный URL
# и английский текст, из которого непонятно, что делать). Тело ответа
# Gemini уходит в лог — там точная причина для владельца.
_HTTP_ERROR_TEXT = {
    400: "Gemini отклонил запрос (HTTP 400) — проверь GEMINI_MODEL или размер запроса",
    403: "Gemini отказал в доступе (HTTP 403) — проверь GEMINI_API_KEY; ещё так бывает, "
         "если сервер бота в стране, где Gemini API недоступен",
    404: "Модель {model} не найдена (HTTP 404) — обнови GEMINI_MODEL (см. config.py)",
    429: "Лимит бесплатного тира Gemini исчерпан (HTTP 429) — попробуй через минуту, "
         "а если не поможет — завтра",
}


async def _generate(contents: list[dict], system_instruction: str | None = None, *,
                    temperature: float = 0.3, max_output_tokens: int | None = None,
                    timeout: float = 60) -> str:
    """Один запрос generateContent, возвращает склеенный текст ответа.
    Кидает GeminiError (RuntimeError) с понятным текстом при любой проблеме."""
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY не настроен на сервере")

    generation_config: dict = {"temperature": temperature}
    if max_output_tokens:
        generation_config["maxOutputTokens"] = max_output_tokens
    payload: dict = {"contents": contents, "generationConfig": generation_config}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    url = GEMINI_URL_TEMPLATE.format(model=GEMINI_MODEL)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Ключ — в заголовке, а НЕ в ?key= query-параметре: текст ошибки
            # показывается пользователю в чате, и с ключом в URL он утекал бы
            # в Telegram (реальный баг, v1.6.3).
            resp = await client.post(url, headers={"x-goog-api-key": GEMINI_API_KEY}, json=payload)
    except httpx.TimeoutException:
        raise GeminiError("Gemini не ответил вовремя — попробуй ещё раз")
    except httpx.HTTPError as e:
        raise GeminiError(f"Не достучался до Gemini ({type(e).__name__})")

    if resp.status_code != 200:
        logger.warning(f"Gemini HTTP {resp.status_code}: {resp.text[:1000]}")
        template = _HTTP_ERROR_TEXT.get(resp.status_code, "Gemini ответил ошибкой HTTP {code}")
        raise GeminiError(template.format(model=GEMINI_MODEL, code=resp.status_code))

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise GeminiError(f"Gemini не вернула вариантов ответа (promptFeedback={feedback})")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        finish_reason = candidate.get("finishReason", "unknown")
        raise GeminiError(f"Gemini вернула пустой ответ (finishReason={finish_reason})")
    return text


def _to_contents(history: list[dict]) -> list[dict]:
    """История в формате бота/OpenAI ({"role": "user"|"assistant", "content"})
    -> contents Gemini (роль ответа модели там называется "model")."""
    return [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in history
    ]


async def generate_text(history: list[dict], system_instruction: str, *,
                        temperature: float = 0.3, max_output_tokens: int | None = 4096,
                        timeout: float = 60) -> str:
    return await _generate(
        _to_contents(history), system_instruction,
        temperature=temperature, max_output_tokens=max_output_tokens, timeout=timeout,
    )


async def generate_from_image(image_bytes: bytes, mime: str, prompt: str, system_instruction: str, *,
                              temperature: float = 0.3, max_output_tokens: int | None = 4096) -> str:
    contents = [{"role": "user", "parts": [
        {"inlineData": {"mimeType": mime, "data": base64.b64encode(image_bytes).decode()}},
        {"text": prompt},
    ]}]
    return await _generate(
        contents, system_instruction,
        temperature=temperature, max_output_tokens=max_output_tokens, timeout=90,
    )

SYSTEM_INSTRUCTION = (
    "Ты помощник студентов группы УИБО-03-24 РТУ МИРЭА (Бизнес-информатика). "
    "Тебе дан текст лекций по предмету — используй его как ОСНОВНОЙ источник при "
    "решении задания: если в лекциях есть подход, определение или метод для части "
    "задания — используй именно его и формулировки из лекции, а не общие знания. "
    "Если какой-то части задания в лекциях нет — реши её сам, своими знаниями, но "
    "явно отметь в ответе, что эта часть не основана на материалах лекций "
    "(например, пометкой «(своё решение, в лекциях не найдено)» рядом с этой частью). "
    "Отвечай на русском, подробно и структурировано. НЕ используй LaTeX-разметку "
    "($, \\frac, \\cdot и т.д.) — формулы пиши как от руки, Unicode-символами: "
    "x², √x, x₁, ≤, ≠, ·, ×, дроби через /. Не здоровайся — сразу к делу; жирным (**…**) "
    "выделяй названия разделов и итоговый ответ, заголовки через # не используй."
)


# Реальный лимит free/AI-Studio тира — 250К токенов/минуту НА ЗАПРОС (не только
# суммарно), проверено на живом аккаунте (см. config.py). Символ/токен для
# русского текста на практике оказался ближе к ~3.7-4 (проверено на реальной
# лекции МИРЭА: 55.7К символов = 14734 токена), но берём консервативно ~3.2,
# чтобы с запасом остался бюджет под системный промпт, текст задания и ответ —
# не выжимаем лимит "впритык". Если контекст предмета всё равно не влезает
# (16 лекций и больше) — режем по ЦЕЛЫМ лекциям, а не обрубаем текст посередине,
# и явно предупреждаем об этом в ответе (см. solve_with_lecture_context).
MAX_CONTEXT_CHARS = 700_000  # ~220К токенов при 3.2 симв/токен


def _fit_context_budget(context: str, max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, bool]:
    """Возвращает (обрезанный_контекст, был_ли_обрезан). Режет по разделителям
    "=== Название лекции ===", которые ставит database.get_subject_lecture_context —
    то есть теряются только САМЫЕ ПОСЛЕДНИЕ лекции целиком, а не хвост текста
    посреди какой-то одной лекции."""
    if len(context) <= max_chars:
        return context, False
    blocks = context.split("\n\n=== ")
    fitted = blocks[0]
    truncated = False
    if len(fitted) > max_chars:
        # Даже первая лекция целиком не влезает — резать по лекциям нечего,
        # обрезаем её саму, иначе запрос уйдёт больше лимита и упадёт.
        return fitted[:max_chars], True
    for block in blocks[1:]:
        candidate = fitted + "\n\n=== " + block
        if len(candidate) > max_chars:
            truncated = True
            break
        fitted = candidate
    return fitted, truncated


async def solve_with_lecture_context(task: str, subject: str, lecture_context: str) -> str:
    """Кидает исключение (GeminiError/ValueError), если что-то пошло не так —
    фолбэка на другой бэкенд тут нет: это отдельная, самостоятельная фича,
    подменять её другой моделью под тем же UI было бы вводящим в заблуждение
    (ответ был бы уже не "по лекциям")."""
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY не настроен на сервере")
    if not lecture_context.strip():
        raise ValueError("По этому предмету нет ни одной лекции с извлечённым текстом")

    fitted_context, truncated = _fit_context_budget(lecture_context)

    user_text = (
        f"Предмет: {subject}\n\n"
        f"=== Материалы лекций предмета ===\n{fitted_context}\n\n"
        f"=== Задание (практика) ===\n{task}"
    )
    text = await _generate(
        [{"role": "user", "parts": [{"text": user_text}]}], SYSTEM_INSTRUCTION,
        temperature=0.3, max_output_tokens=4096, timeout=120,
    )

    if truncated:
        text = (
            "⚠️ Лекций по предмету оказалось больше, чем влезает в один запрос "
            "(лимит бесплатного тира Gemini) — часть последних лекций не вошла "
            "в контекст, ответ основан не на всех материалах предмета.\n\n" + text
        )
    return text
