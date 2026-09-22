"""
Решалка "по лекциям" — отдельный бэкенд от groq_solver.py (Groq/DeepSeek).
Разница не в провайдере ради провайдера, а в задаче: DeepSeek/Groq решают
задание "с нуля", своими знаниями. Эта решалка получает на вход ПОЛНЫЙ текст
всех лекций выбранного предмета (database.get_subject_lecture_context,
собранный один раз при загрузке файлов через file_text.py — не парсим заново
на каждый запрос, это и есть "кэш" контекста) и должна отвечать в первую
очередь опираясь на них, а к своим знаниям обращаться только там, где лекции
не дают ответа — и явно это помечать.

Почему Gemini, а не Groq/DeepSeek: контекст одного предмета — реально
100-400К+ токенов (проверено на живых лекциях МИРЭА, см. PLAN.md Фаза 9), это
не лезет ни в контекстное окно, ни в лимит токенов/минуту бесплатных тиров
Groq/DeepSeek. У Gemini free tier контекст 1M токенов и достаточный RPD/TPM
для масштаба одной группы. Кэширования на стороне самого Gemini НЕТ на free
tier (и implicit, и explicit caching — платная фича) — поэтому кэшируем не
ответ и не сам запрос к Gemini, а сборку контекста у себя в БД.
"""

import logging
import httpx

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_INSTRUCTION = (
    "Ты помощник студентов группы УИБО-03-24 РТУ МИРЭА (Бизнес-информатика). "
    "Тебе дан текст лекций по предмету — используй его как ОСНОВНОЙ источник при "
    "решении задания: если в лекциях есть подход, определение или метод для части "
    "задания — используй именно его и формулировки из лекции, а не общие знания. "
    "Если какой-то части задания в лекциях нет — реши её сам, своими знаниями, но "
    "явно отметь в ответе, что эта часть не основана на материалах лекций "
    "(например, пометкой «(своё решение, в лекциях не найдено)» рядом с этой частью). "
    "Отвечай на русском, подробно и структурировано. НЕ используй LaTeX-разметку "
    "($, \\frac, \\cdot и т.д.) — пиши математику обычным текстом (×, ÷, дроби через /)."
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
    """Кидает исключение (RuntimeError/ValueError/httpx.HTTPStatusError), если
    что-то пошло не так — в отличие от groq_solver.solve_text тут нет фолбэка
    на другой бэкенд: это отдельная, самостоятельная фича, подменять её другой
    моделью под тем же UI было бы вводящим в заблуждение (ответ был бы уже не
    "по лекциям")."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY не настроен на сервере")
    if not lecture_context.strip():
        raise ValueError("По этому предмету нет ни одной лекции с извлечённым текстом")

    fitted_context, truncated = _fit_context_budget(lecture_context)

    user_text = (
        f"Предмет: {subject}\n\n"
        f"=== Материалы лекций предмета ===\n{fitted_context}\n\n"
        f"=== Задание (практика) ===\n{task}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }
    url = GEMINI_URL_TEMPLATE.format(model=GEMINI_MODEL)

    async with httpx.AsyncClient(timeout=120) as client:
        # Ключ — в заголовке, а НЕ в ?key= query-параметре: при ошибке HTTP
        # (429 квота, 400, 404 модели) str(httpx.HTTPStatusError) содержит полный
        # URL запроса, а handlers/solver.py показывает текст исключения
        # пользователю в чате ("❌ Ошибка: ...") — ключ утекал бы в Telegram.
        resp = await client.post(url, headers={"x-goog-api-key": GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise RuntimeError(f"Gemini не вернула вариантов ответа (promptFeedback={feedback})")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        finish_reason = candidate.get("finishReason", "unknown")
        raise RuntimeError(f"Gemini вернула пустой ответ (finishReason={finish_reason})")

    if truncated:
        text = (
            "⚠️ Лекций по предмету оказалось больше, чем влезает в один запрос "
            "(лимит бесплатного тира Gemini) — часть последних лекций не вошла "
            "в контекст, ответ основан не на всех материалах предмета.\n\n" + text
        )
    return text
