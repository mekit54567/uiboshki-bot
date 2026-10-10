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

import asyncio
import json
import logging

import net

import gemini_solver
from config import DEEPSEEK_API_KEY, GROUP_NAME, GROUP_PROGRAM

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


# Ответ читают в Telegram с телефона: формулы — как пишут от руки (их же
# дополнительно причёсывает utils.pretty_math, если модель всё-таки напишет
# x^2 или LaTeX), без приветствий в каждом ответе и без markdown-заголовков.
ANSWER_STYLE = (
    "Оформление (ответ читают в Telegram с телефона):\n"
    "- Не здоровайся и не прощайся — сразу к делу.\n"
    "- Если это задача: **Ответ:** — коротко, в одну-две строки; **Решение:** — по шагам "
    "(1., 2., 3.); если уместно — **Проверка:**. Если это обычный вопрос (про расписание, "
    "дедлайны, «объясни понятие») — отвечай коротко и по-человечески, без разделов "
    "«Ответ/Решение».\n"
    "- Формулы пиши как от руки, Unicode-символами: степени x², eˣ, 10⁻³; корни √x, √(x+1); "
    "индексы x₁, aₙ; знаки ·, ×, ÷, ±, ≤, ≥, ≠, ≈, →, π, ∞; дроби a/b. "
    "НЕ используй LaTeX ($, \\frac, \\cdot) и не пиши x^2 или sqrt(x).\n"
    "- Жирным (**…**) — только названия разделов и итоговый ответ; заголовки через # не используй.\n"
    "- Эмодзи — не больше двух-трёх на ответ.\n\n"
)


def build_system_prompt(subject: str = "") -> str:
    subj_part = f" по предмету «{subject}»" if subject and subject != "Другое" else ""
    return (
        f"Ты помощник студентов группы {GROUP_NAME} РТУ МИРЭА ({GROUP_PROGRAM}){subj_part}. "
        "Решай задания на русском языке и объясняй так, чтобы студент понял и смог повторить сам.\n\n"
        + ANSWER_STYLE +
        "Если пользователь задаёт уточняющий вопрос — отвечай в контексте предыдущего разговора, коротко."
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
    async with net.client(timeout=90) as client:
        resp = await client.post(DEEPSEEK_URL, headers=headers, content=body)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


def _fit(lectures: str, max_chars: int | None) -> tuple[str, bool]:
    return (gemini_solver._fit_context_budget(lectures, max_chars) if max_chars
            else gemini_solver._fit_context_budget(lectures))


def lecture_system_prompt(subject: str, lectures: str, max_chars: int | None = None) -> str:
    """Промпт решалки с лекциями — только правила. Сами лекции (обрезанные
    по бюджету Gemini целыми лекциями, см. gemini_solver._fit_context_budget)
    идут в сообщении студента в рамке — with_lectures: их может загрузить
    любой, и в systemInstruction они звучали бы как правила."""
    _, truncated = _fit(lectures, max_chars)
    note = " (часть последних лекций не влезла в лимит)" if truncated else ""
    source = ("К сообщению студента приложены материалы лекций этого предмета, загруженные группой" if subject else
              "К сообщению студента приложены отрывки лекций группы, подобранные под вопрос (по совпадению слов — могут быть не в тему)")
    if lectures.lstrip().startswith("=== [1]"):
        # куски от поиска по смыслу (semantic_search.build_context): с номерами —
        # пусть ИИ ссылается на них, а под ответом будут «Лекция 5 · слайд 12»
        source = ("К сообщению студента приложены фрагменты лекций группы, найденные под вопрос по смыслу и по словам, с номерами "
                  "[1], [2]… Когда опираешься на фрагмент, ставь его номер в квадратных скобках прямо в "
                  "тексте, например «…дисконтируют [2]». Номера не выдумывай")
    return (
        build_system_prompt(subject) + "\n\n" +
        source + note + ". Опирайся на них "
        "в первую очередь: их определения, методы, обозначения и формулировки. Если какой-то части "
        "задания в лекциях нет — реши сам и пометь её «(не из лекций)».\n\n" + gemini_solver.LECTURES_RULE
    )


def lecture_block(lectures: str, max_chars: int | None = None) -> str:
    return gemini_solver.frame_lectures(_fit(lectures, max_chars)[0])


def with_lectures(history: list, lectures: str, max_chars: int | None = None) -> list:
    """Копия истории: лекции в рамке — перед последним вопросом студента
    (отдельный ход подряд с user deepseek-reasoner не принимает)."""
    out = [dict(m) for m in history]
    i = next((k for k in range(len(out) - 1, -1, -1) if out[k]["role"] == "user"), None)
    if i is None:
        return out + [{"role": "user", "content": lecture_block(lectures, max_chars)}]
    out[i]["content"] = f"{lecture_block(lectures, max_chars)}\n\n=== Сообщение студента ===\n{out[i]['content']}"
    return out


# ── Запасной ИИ ─────────────────────────────────────────────────────────────
# Gemini на бесплатном лимите: бывают 429, таймауты, 5xx. Тогда: таймаут/5xx —
# ещё одна попытка через пару секунд; не вышло или лимит — DeepSeek (если есть
# ключ), с пометкой в конце ответа. И наоборот: упал DeepSeek — отвечает Gemini.
RETRY_DELAY = 2.0
FALLBACK_LECTURE_CHARS = 40_000      # у DeepSeek окно меньше, лекции — короче
FALLBACK_NOTE_DS = "\n\n_↪ Gemini сейчас перегружен — ответил запасной ИИ (DeepSeek)._"
FALLBACK_NOTE_GEMINI = "\n\n_↪ DeepSeek не ответил — ответил Gemini._"


async def _gemini_with_retry(history: list, system: str) -> str:
    try:
        return await gemini_solver.generate_text(history, system)
    except gemini_solver.GeminiError as e:
        if not e.transient or e.status == 429:      # на лимит повтор не поможет
            raise
        logger.info(f"Gemini: {e} — повторяю")
        await asyncio.sleep(RETRY_DELAY)
        return await gemini_solver.generate_text(history, system)


async def _gemini_then_deepseek(history: list, system: str, ds_system: str,
                                ds_history: list | None = None) -> str:
    try:
        return await _gemini_with_retry(history, system)
    except gemini_solver.GeminiError as e:
        if not (e.transient and DEEPSEEK_API_KEY):
            raise
        logger.warning(f"Gemini недоступен ({e}) — отвечает DeepSeek")
        try:
            msg = await _deepseek_chat([{"role": "system", "content": ds_system}, *(ds_history or history)],
                                       max_tokens=2048, temperature=0.3)
        except Exception as ds_error:
            logger.warning(f"Запасной DeepSeek тоже не ответил: {ds_error}")
            raise e
        return msg["content"] + FALLBACK_NOTE_DS


async def _deepseek_then_gemini(history: list, ds_system: str, gemini_system: str, **params) -> dict:
    try:
        return await _deepseek_chat([{"role": "system", "content": ds_system}, *history], **params)
    except Exception as e:
        logger.warning(f"DeepSeek не ответил ({type(e).__name__}) — отвечает Gemini")
        text = await _gemini_with_retry(history, gemini_system)
        return {"content": text + FALLBACK_NOTE_GEMINI, "reasoning_content": ""}


async def solve_with_history(history: list, subject: str = "", backend: str = "gemini",
                             lectures: str = "", extra_system: str = "") -> str:
    """history — [{"role": "user"|"assistant", "content": str}, ...].
    lectures — текст лекций предмета (только для Gemini: у DeepSeek окно
    меньше); extra_system — доп. контекст в конец системного промпта
    (например, дедлайны группы для чата WebApp)."""
    ds_history = None
    if lectures.strip():
        backend = "gemini"
        system = lecture_system_prompt(subject, lectures)
        ds_system = lecture_system_prompt(subject, lectures, FALLBACK_LECTURE_CHARS)
        history, ds_history = (with_lectures(history, lectures),
                               with_lectures(history, lectures, FALLBACK_LECTURE_CHARS))
    else:
        system = ds_system = build_system_prompt(subject)
    if extra_system:
        system += "\n\n" + extra_system
        ds_system += "\n\n" + extra_system
    if _resolve_backend(backend) == "deepseek":
        msg = await _deepseek_then_gemini(history, system, system, max_tokens=2048, temperature=0.3)
        return msg["content"]
    return await _gemini_then_deepseek(history, system, ds_system, ds_history)


async def solve_text(task: str, subject: str = "", backend: str = "gemini", lectures: str = "") -> str:
    return await solve_with_history([{"role": "user", "content": f"Задание:\n{task}"}], subject, backend,
                                    lectures=lectures)


async def solve_image(image_bytes: bytes, mime: str = "image/jpeg", subject: str = "",
                      lectures: str = "", prompt: str = "") -> str:
    prompt = prompt or "Реши задание на фото с подробным объяснением. Не используй LaTeX."
    if lectures.strip():
        system = lecture_system_prompt(subject, lectures)
        prompt = f"{lecture_block(lectures)}\n\n=== Сообщение студента ===\n{prompt}"
    else:
        system = build_system_prompt(subject)
    return await gemini_solver.generate_from_image(image_bytes, mime, prompt, system)


async def extract_text_from_image(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """OCR фото для дедлайнов: только достаёт текст с картинки, ничего не решает
    и не комментирует (в отличие от solve_image) — используется, когда к
    дедлайну прикладывают фото задания вместо того, чтобы печатать текст руками.
    Если текста на фото нет, Gemini отдаёт пустой ответ -> GeminiError, и
    хендлер честно пишет "не смог распознать"."""
    return await gemini_solver.generate_from_image(
        image_bytes, mime, "Извлеки весь текст с этого фото.", OCR_SYSTEM_PROMPT,
        temperature=0.0, mark_truncated=False,     # текст пойдёт в описание дедлайна — без пометок
    )


async def chat_with_reasoning(history: list, subject: str = "", extra_system: str = "",
                              lectures: str = "") -> dict:
    """Для WebApp-чата: всегда deepseek-reasoner — единственная модель
    DeepSeek, которая отдаёт отдельное поле reasoning_content ("как думала")
    в дополнение к обычному content ("что ответила"). Раздельно, чтобы фронт
    мог свернуть/развернуть трейс независимо от самого ответа — см. PLAN.md,
    идея владельца про "мышление" как в приложениях DeepSeek/ChatGPT.
    Без DEEPSEEK_API_KEY — тот же Gemini, что и у решалки в боте (без
    трейса рассуждений): иначе чат в WebApp просто не работал бы у тех, кто
    не заводил ключ DeepSeek. Возвращает {"content": str, "reasoning": str}."""
    if not DEEPSEEK_API_KEY or lectures.strip():
        content = await solve_with_history(history, subject, backend="gemini",
                                           lectures=lectures, extra_system=extra_system)
        return {"content": content, "reasoning": ""}
    system = build_system_prompt(subject) + (f"\n\n{extra_system}" if extra_system else "")
    msg = await _deepseek_then_gemini(history, system, system,
                                      model=MODEL_DEEPSEEK_REASONER, max_tokens=4096)
    return {
        "content": msg.get("content", ""),
        "reasoning": msg.get("reasoning_content", ""),
    }
