"""
Конспект лекции от ИИ (WebApp: нажатие на файл с текстом → «Сделать конспект»).

Один конспект на файл и общий для всех: его делает первый, кто нажал, дальше
он лежит в базе (file_summaries) и открывается мгновенно у всей группы. Пока
никто не нажимал — конспекта нет и ИИ не тратится.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Лекции бывают огромными (презентации на сотню слайдов) — хвост отрезаем,
# главное обычно в начале и середине.
MAX_CHARS = 150_000

PROMPT = (
    "Сделай короткий конспект этой лекции для студента: главное, что нужно "
    "понять и запомнить — определения, ключевые идеи, формулы и важные примеры. "
    "Сгруппируй по темам: короткий жирный подзаголовок и под ним пункты списком. "
    "Всего не больше 15 пунктов, каждый — одна-две строки. Без вступления, без "
    "заключения и без вопросов. Только по тексту лекции, ничего не выдумывай."
)

_locks: dict[int, asyncio.Lock] = {}
NOT_SAVED = "\n\n_Конспект не сохранён — нажми ещё раз чуть позже, сделаю полный._"


def _final(content: str) -> bool:
    """Нет пометок запасного ИИ и обрыва ответа (ai_solver, gemini_solver)."""
    import ai_solver
    import gemini_solver
    notes = (ai_solver.FALLBACK_NOTE_DS, ai_solver.FALLBACK_NOTE_GEMINI, gemini_solver.TRUNCATED_NOTE)
    return not any(n.strip() in content for n in notes)


class NoText(Exception):
    """У файла нет текста — конспект делать не из чего."""


def to_html(content: str) -> str:
    """Тот же вид, что и ответы ИИ: жирный, списки, x² вместо x^2."""
    from utils import md_to_tg_html_chunks
    return "\n".join(md_to_tg_html_chunks(content))


async def make(file_id: int, title: str, subject: str, user_id: int) -> dict:
    """Готовый конспект или новый. Два нажатия одновременно — ИИ зовётся один
    раз: второй дождётся первого и возьмёт его конспект из базы."""
    from database import get_file_summary, get_file_text, save_file_summary
    lock = _locks.setdefault(file_id, asyncio.Lock())
    async with lock:
        done = await get_file_summary(file_id)
        if done:
            return done
        text = (await get_file_text(file_id)).strip()
        if not text:
            raise NoText()
        from ai_solver import chat_with_reasoning
        result = await chat_with_reasoning([{"role": "user", "content": PROMPT}], subject=subject,
                                           lectures=f"=== {title} ===\n{text[:MAX_CHARS]}")
        content = (result.get("content") or "").strip()
        if len(content) < 40:
            raise RuntimeError("ИИ вернул пустой конспект")
        if not _final(content):
            # запасной ИИ по урезанной лекции или обрыв по лимиту ответа:
            # показываем, но не сохраняем навсегда для всех — следующее
            # нажатие сделает полный конспект
            logger.info(f"конспект файла {file_id}: неполный, не сохраняю")
            return {"file_id": file_id, "content": content + NOT_SAVED, "created_by": user_id,
                    "created_at": None, "temporary": True}
        await save_file_summary(file_id, content, user_id)
        logger.info(f"конспект файла {file_id}: {len(content)} символов")
        return await get_file_summary(file_id)
