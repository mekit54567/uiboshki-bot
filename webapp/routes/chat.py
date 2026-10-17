"""Чат с ИИ в WebApp: лекции под вопрос, вложения (фото, документы), файл
по просьбе («скинь практику 3»), запасной ответ без лекций."""

import logging
import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from webapp.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Чат с ИИ (DeepSeek с трейсом рассуждений, без его ключа — Gemini) ─────

def _short_reason(e: Exception) -> str:
    """Причина ошибки ИИ для пользователя: у GeminiError она уже человеческая
    («не ответил вовремя», «лимит запросов»), у прочих — хотя бы тип."""
    text = str(e) if isinstance(e, RuntimeError) and str(e) else type(e).__name__
    return text[:160]


async def _chat_with_fallback(history: list, subject: str, context: str, lectures: str) -> dict:
    """С лекциями запрос уходит в Gemini с большим контекстом — если он не
    прошёл (живой тест: «Дебет и кредит — что это?» без предмета → «ИИ
    недоступен», а «Привет» без лекций — ок), отвечаем без лекций и честно
    пишем почему, а не оставляем человека без ответа."""
    from ai_solver import chat_with_reasoning
    try:
        return await chat_with_reasoning(history, subject=subject, extra_system=context, lectures=lectures)
    except Exception as e:
        if not lectures:
            raise
        logger.warning(f"webapp chat: с лекциями не вышло ({e!r}) — отвечаю без них")
        result = await chat_with_reasoning(history, subject=subject, extra_system=context, lectures="")
        result["content"] = (result.get("content") or "") + f"\n\n_(ответ без лекций: {_short_reason(e)})_"
        result["no_lectures"] = True
        return result


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatAttachment(BaseModel):
    name: str = "файл"
    mime: str = ""
    data: str  # base64


class ChatBody(BaseModel):
    history: list[ChatMessage]
    subject: str = ""
    attachment: ChatAttachment | None = None
    # «Подумать ещё» (think.py): история кончается вопросом, ответ на него
    # заново решает модель второго уровня; дневной лимит — свой
    think: bool = False


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
DOC_TEXT_LIMIT = 60_000
# Сколько текста вложенного документа фронт помнит в истории чата (file_text):
# файл уходит ИИ один раз, а следующие вопросы («а что во втором разделе?»)
# без него оставались без файла.
FILE_MEMORY_LIMIT = 10_000


@router.get("/api/subjects")
async def api_subjects(user: dict = CurrentUser):
    """Предметы для чата: с загруженными лекциями (чат будет опираться на
    них) — сверху, дальше остальные предметы группы из расписания. quota —
    сколько вопросов осталось сегодня (null — без лимита, например староста)."""
    import ai_quota
    from database import get_subjects_with_lecture_text
    from schedule_parser import get_group_subjects
    with_lectures = await get_subjects_with_lecture_text()
    rest = [s for s in await get_group_subjects() if s not in with_lectures]
    return {"subjects": [{"name": s, "lectures": True} for s in with_lectures]
                        + [{"name": s, "lectures": False} for s in rest],
            "quota": await ai_quota.left(user["id"])}


async def _lecture_sources(lectures: str, subject: str) -> list[dict]:
    """Какие лекции ушли ИИ вместе с вопросом — «📖 по: ЛК3 · ЛК5» под
    ответом, с переходом к файлу. Заголовки блоков — «файл» (выбран предмет)
    или «предмет: файл» (get_all_lecture_context)."""
    from database import get_files
    titles = re.findall(r"^=== (.+?) ===$", lectures, re.M)
    if not titles:
        return []
    by_key = {}
    for f in await get_files():
        by_key.setdefault(((f.get("subject") or "Без предмета"), f["title"]), f)
        by_key.setdefault(("", f["title"]), f)
    out, seen = [], set()
    for t in titles:
        f = by_key.get((subject, t)) if subject else None
        if not f and ": " in t:
            subj, _, title = t.partition(": ")
            f = by_key.get((subj, title))
        f = f or by_key.get(("", t))
        if f and f["id"] not in seen:
            seen.add(f["id"])
            out.append({"id": f["id"], "title": f["title"]})
    return out


async def _chat_file_request(text: str) -> dict | None:
    """«Скинь 5 лк по уч деят на предпрят» в чате WebApp — файлы карточками
    (📥 / «В чат»), а не пересказ лекции от ИИ (живой тест). Не просьба о
    файле или предмет не угадан — None, отвечает ИИ."""
    import file_request
    from database import get_file_ids_with_text, get_files
    from file_categories import LABELS, category_of
    from utils import esc
    if not file_request.is_request(text):
        return None
    subjects, items = file_request.find(text, await get_files())
    if not subjects:
        return None
    if len(subjects) > 1:
        msg = "🤔 По какому предмету? Подходят: " + "; ".join(subjects[:8]) + ". Напиши чуть подробнее."
        return {"content": msg, "html": esc(msg), "reasoning": ""}
    if not items:
        msg = f"🤷 В папке «{subjects[0]}» такого не нашёл — загляни в «Файлы» (☰ Ещё)."
        return {"content": msg, "html": esc(msg), "reasoning": ""}
    with_text = await get_file_ids_with_text()
    msg = f"📁 {subjects[0]} — " + ("вот файл:" if len(items) == 1 else f"нашёл {len(items)}" +
                                    (", показываю 8:" if len(items) > 8 else ":"))
    files = [{"id": f["id"], "title": f["title"], "subject": f.get("subject") or "",
              "file_name": f.get("file_name") or "", "has_text": f["id"] in with_text,
              "category": category_of(f), "category_label": LABELS[category_of(f)], "can_edit": False}
             for f in items[:8]]
    return {"content": msg, "html": esc(msg), "reasoning": "", "files": files}


@router.post("/api/chat")
async def api_chat(body: ChatBody, user: dict = CurrentUser, x_app: str = Header(default="")):
    """Чат WebApp: история (последние 20), по желанию предмет (если по нему
    есть лекции — ответ опирается на них) и одно вложение — фото (решает
    Gemini по картинке) или документ PDF/DOCX/PPTX/TXT (его текст уходит в
    сообщение). В системный промпт — контекст группы: пары, дедлайны, ДЗ."""
    import asyncio
    import base64
    from ai_solver import solve_image
    from database import get_subject_lecture_context, get_subjects_with_lecture_text
    from file_text import SUPPORTED_EXTENSIONS, extract_text
    from group_context import build_group_context
    from utils import md_to_tg_html_chunks

    import ai_quota
    import think
    if body.think:
        if body.attachment or not await think.offer(user["id"], x_app):
            raise HTTPException(status_code=403, detail=think.PLUS_TEXT)
    else:
        why = await ai_quota.gate(user["id"])
        if why:
            raise HTTPException(status_code=429, detail=ai_quota.text(why))
    # Роли — только user/assistant, и первым — вопрос: срез [-20:] мог
    # начаться с ответа ИИ, а deepseek-reasoner такое не принимает.
    history = [{"role": m.role, "content": m.content} for m in body.history[-20:]
               if m.role in ("user", "assistant")]
    while history and history[0]["role"] != "user":
        history.pop(0)
    if not history:
        raise HTTPException(status_code=400, detail="пустая история")
    subject = body.subject.strip()
    # Лекции — только подходящие к вопросу (lecture_picker): после выгрузки
    # СДО их у предмета сотни тысяч символов. Без выбранного предмета — из
    # всех предметов, но только при явном совпадении с вопросом.
    import lecture_picker
    from database import get_all_lecture_context
    # «Подробнее», «Пример», «а почему?» — ищем по теме прошлых вопросов,
    # заглушку вложения («Разбери этот файл.») не ищем вовсе
    query = lecture_picker.search_query(history)
    last = history[-1]["content"] if history[-1]["role"] == "user" else ""
    if body.think and history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="нет вопроса")
    if not body.attachment and not body.think and history[-1]["role"] == "user":
        found = await _chat_file_request(history[-1]["content"])
        if found:
            return found
    lectures, sources = "", None
    with_text = await get_subjects_with_lecture_text()
    # Сначала — поиск по смыслу (semantic_search): куски лекций с номером
    # страницы/слайда. «Объясни 3 лекцию» (номер лекции, а не смысл) и пустой
    # индекс (сразу после деплоя) — по-старому, целыми лекциями.
    if query.strip() and (not subject or subject in with_text) and not lecture_picker.wants_course(query):
        try:
            import semantic_search
            if await semantic_search.ready():
                hits = await semantic_search.search(query, subject)
                if hits:
                    lectures, sources = semantic_search.build_context(hits)
        except Exception as e:
            logger.warning(f"поиск по смыслу: {type(e).__name__}: {e} — подбираю лекции по словам")
            lectures, sources = "", None
    if lectures:
        pass
    elif subject and subject in with_text:
        lectures = lecture_picker.pick(await get_subject_lecture_context(subject), query)
    elif not subject and query.strip():
        all_lectures = await get_all_lecture_context()
        if not body.attachment and not body.think and lecture_picker.wants_course(last):
            # «объясни 3 лекцию» без предмета: вопрос явно про лекции, а предмет
            # не угадывается — не отвечаем наугад, а даём выбрать (фронт
            # переключит предмет и задаст тот же вопрос)
            ranked = await asyncio.to_thread(lecture_picker.subject_scores, all_lectures, query)
            if not ranked or (len(ranked) > 1 and ranked[1][1] * 4 >= ranked[0][1] * 3):
                options = [s for s, _ in ranked[:4]] or (await get_subjects_with_lecture_text())[:8]
                if options:
                    msg = "🤔 По какому предмету? Выбери — и я отвечу по его лекциям."
                    return {"content": msg, "html": msg, "reasoning": "", "choose": options}
        lectures = await asyncio.to_thread(lecture_picker.pick, all_lectures, query,
                                           lecture_picker.AUTO_BUDGET, lecture_picker.AUTO_MIN_SCORE, True)
    context = await build_group_context(user["id"])

    try:
        if body.think:
            try:
                result = {"content": await think.solve(user["id"], history, subject, lectures, context),
                          "reasoning": ""}
            except think.ThinkError as e:
                raise HTTPException(status_code=502, detail=str(e))
        elif body.attachment:
            try:
                raw = base64.b64decode(body.attachment.data, validate=False)
            except Exception:
                raise HTTPException(status_code=400, detail="вложение повреждено")
            if len(raw) > MAX_ATTACHMENT_BYTES:
                raise HTTPException(status_code=413, detail="файл больше 10 МБ")
            name = body.attachment.name or "файл"
            if body.attachment.mime.startswith("image/"):
                question = history[-1]["content"].strip() or "Реши задание на фото с подробным объяснением."
                earlier = "\n".join(f"{'Студент' if m['role'] == 'user' else 'Ты'}: {m['content'][:500]}"
                                     for m in history[-7:-1])
                prompt = (f"Предыдущий разговор:\n{earlier}\n\n" if earlier else "") + f"Сообщение студента: {question}"
                content = await solve_image(raw, body.attachment.mime, subject=subject,
                                            lectures=lectures, prompt=prompt + "\n\n" + context)
                result = {"content": content, "reasoning": ""}
            else:
                if not name.lower().endswith(SUPPORTED_EXTENSIONS):
                    raise HTTPException(status_code=415, detail="умею читать PDF, DOCX, PPTX и TXT, а ещё фото")
                text = (await asyncio.to_thread(extract_text, raw, name)).strip()
                if not text:
                    raise HTTPException(status_code=422, detail="не смог достать текст из файла (скан без текстового слоя?)")
                note = "\n\n(файл обрезан — слишком длинный)" if len(text) > DOC_TEXT_LIMIT else ""
                history[-1]["content"] = (
                    (history[-1]["content"].strip() or "Разбери этот файл.")
                    + f"\n\n=== Файл «{name}» ===\n{text[:DOC_TEXT_LIMIT]}{note}"
                )
                result = await _chat_with_fallback(history, subject, context, lectures)
                result["file_text"] = (f"=== Файл «{name}» ===\n{text[:FILE_MEMORY_LIMIT]}"
                                       + ("\n(дальше файл обрезан)" if len(text) > FILE_MEMORY_LIMIT else ""))
        else:
            result = await _chat_with_fallback(history, subject, context, lectures)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"webapp chat failed: {e!r}")
        raise HTTPException(status_code=502, detail=f"ИИ сейчас недоступен ({_short_reason(e)}), попробуй чуть позже")
    # Тот же вид, что и в боте: жирный, код, x² вместо x^2 (всё экранировано).
    result["html"] = "\n".join(md_to_tg_html_chunks(result.get("content", "")))
    # ответ без лекций (запасной путь _chat_with_fallback) — источников нет
    if lectures and not result.pop("no_lectures", False):
        result["sources"] = sources if sources is not None else await _lecture_sources(lectures, subject)
    # кнопка «Подумать ещё» под ответом (подписчикам, не на iPhone); к фото и
    # файлу — нет: модель второго уровня читает только текст
    offer = None if body.attachment else await think.offer(user["id"], x_app)
    if offer:
        result["think"] = offer
    return result
