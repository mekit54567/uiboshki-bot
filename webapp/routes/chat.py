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


BUSY_TEXT = "Не получилось ответить — ИИ сейчас перегружен. Нажми «Повторить» через минуту."


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
        result["content"] = (result.get("content") or "") + "\n\n_(ответил без лекций — с ними сейчас не получилось)_"
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
    # «Подумать» включили до вопроса (переключатель у поля ввода): вопрос
    # сразу решает та же модель, первого обычного ответа не было
    think_first: bool = False


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
DOC_TEXT_LIMIT = 60_000
# Сколько текста вложенного документа фронт помнит в истории чата (file_text):
# файл уходит ИИ один раз, а следующие вопросы («а что во втором разделе?»)
# без него оставались без файла.
FILE_MEMORY_LIMIT = 10_000


@router.get("/api/subjects")
async def api_subjects(user: dict = CurrentUser, x_app: str = Header(default="")):
    """Предметы для чата: с загруженными лекциями (чат будет опираться на
    них) — сверху, дальше остальные предметы группы из расписания. quota —
    сколько вопросов осталось сегодня (null — без лимита, например староста).
    think — переключатель «Подумать» у поля ввода ({label, left, daily};
    null — не подписчик, выключено, iPhone)."""
    import ai_quota
    import think
    from database import get_subjects_with_lecture_text
    from schedule_parser import get_group_subjects
    with_lectures = await get_subjects_with_lecture_text()
    rest = [s for s in await get_group_subjects() if s not in with_lectures]
    return {"subjects": [{"name": s, "lectures": True} for s in with_lectures]
                        + [{"name": s, "lectures": False} for s in rest],
            "quota": await ai_quota.left(user["id"]),
            "think": await think.offer(user["id"], x_app)}


_HEAD = re.compile(r"^=== (?:\[(\d+)\] )?(.+?) ===$", re.M)
_CITE = re.compile(r"\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]")


def _number_lectures(lectures: str) -> str:
    """Целые лекции (lecture_picker) — с номерами [n], как куски поиска по
    смыслу: ИИ ссылается на номер, и под ответом остаются только лекции, на
    которые он опирался (Никита 20.10: на «погоду глянешь?» — шесть плашек)."""
    if not lectures or lectures.lstrip().startswith("=== [1]"):
        return lectures
    n = 0

    def head(m):
        nonlocal n
        n += 1
        return f"=== [{n}] {m.group(2)} ==="
    return _HEAD.sub(head, lectures)


def _natural(text: str) -> list:
    """«Лекция 10» после «Лекция 9»: числа в названии сравниваются как числа."""
    return [(0, int(x), "") if x.isdigit() else (1, 0, x.lower()) for x in re.split(r"(\d+)", text) if x]


def cited(answer: str) -> set[int]:
    """Номера материалов, на которые сослался ИИ: [2], [1, 3]. Диапазон
    «[1–10]» — не ссылка: так ИИ говорит о материалах вообще («в [1–10] этого
    нет», живой тест 20.10), а не опирается на них."""
    out = set()
    for group in _CITE.findall(answer or ""):
        out.update(int(x) for x in re.split(r"\s*[,;]\s*", group))
    return out


async def _lecture_sources(lectures: str, subject: str) -> list[dict]:
    """Какие лекции ушли ИИ вместе с вопросом — «📖 по: ЛК3 · ЛК5» под
    ответом, с переходом к файлу. Заголовки блоков — «[n] файл» (выбран
    предмет) или «[n] предмет: файл» (get_all_lecture_context); n — для
    отбора процитированных, наружу не уходит."""
    from database import get_files
    heads = _HEAD.findall(lectures)
    if not heads:
        return []
    by_key = {}
    for f in await get_files():
        by_key.setdefault(((f.get("subject") or "Без предмета"), f["title"]), f)
        by_key.setdefault(("", f["title"]), f)
    out, seen = [], set()
    for n, t in heads:
        f = by_key.get((subject, t)) if subject else None
        if not f and ": " in t:
            subj, _, title = t.partition(": ")
            f = by_key.get((subj, title))
        f = f or by_key.get(("", t))
        if f and f["id"] not in seen:
            seen.add(f["id"])
            out.append({"n": int(n) if n else None, "id": f["id"], "title": f["title"]})
    return out


async def _lecture_of_day(user_id: int, subject: str, text: str, query: str) -> tuple[str, str]:
    """(тексты лекции, строка для ИИ) — вопрос про лекцию конкретного дня
    («завтра», «сегодня на первой паре», «что будет на лекции») по предмету.
    Не про лекцию дня — ("", "")."""
    from datetime import datetime
    import attendance
    import lecture_day
    import lecture_picker
    from database import get_subject_lecture_context
    from schedule_parser import raw_for_user
    from utils import TZ
    if not lecture_day.asks_about_lecture(text):
        return "", ""
    now = datetime.now(TZ)
    raw = await raw_for_user(user_id)
    found = lecture_day.lecture_on(attendance.lecture_dates(raw, subject, now.date()), text, now)
    if not found:
        return "", ""
    day, n = found
    when = f"{day:%d.%m}, {'сегодня' if day == now.date() else 'по расписанию'}"
    block = lecture_day.numbered_blocks(await get_subject_lecture_context(subject), n)
    if not block:
        return "", (f"Вопрос — про лекцию №{n} по предмету «{subject}» ({when}). Файла этой лекции "
                    "в материалах нет: так и скажи и предположи темы по соседним лекциям, не пересказывай весь курс.")
    return (lecture_picker.pick(block, query),
            f"Вопрос — про лекцию №{n} по предмету «{subject}» ({when}). Материал ниже — эта лекция: "
            "отвечай по ней, а не обзором всего курса.")


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


def clean_history(messages: list[ChatMessage]) -> list[dict]:
    """Последние 20 сообщений. Роли — только user/assistant, и первым — вопрос:
    срез [-20:] мог начаться с ответа ИИ, а deepseek-reasoner такое не принимает."""
    history = [{"role": m.role, "content": m.content} for m in messages[-20:]
               if m.role in ("user", "assistant")]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


async def _solve(history: list, subject: str, context: str, lectures: str,
                 attachment: ChatAttachment | None) -> dict:
    """Вопрос (и вложение — фото решает Gemini по картинке, у документа текст
    уходит в сообщение) → {"content", "reasoning"} от модели."""
    import asyncio
    import base64
    from ai_solver import solve_image
    from file_text import SUPPORTED_EXTENSIONS, extract_text
    if not attachment:
        return await _chat_with_fallback(history, subject, context, lectures)
    try:
        raw = base64.b64decode(attachment.data, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="вложение повреждено")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="файл больше 10 МБ")
    name = attachment.name or "файл"
    if attachment.mime.startswith("image/"):
        question = history[-1]["content"].strip() or "Реши задание на фото с подробным объяснением."
        earlier = "\n".join(f"{'Студент' if m['role'] == 'user' else 'Ты'}: {m['content'][:500]}"
                             for m in history[-7:-1])
        prompt = (f"Предыдущий разговор:\n{earlier}\n\n" if earlier else "") + f"Сообщение студента: {question}"
        content = await solve_image(raw, attachment.mime, subject=subject,
                                    lectures=lectures, prompt=prompt + "\n\n" + context)
        return {"content": content, "reasoning": ""}
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
    return result


async def reply(history: list, subject: str, context: str, lectures: str, sources: list[dict] | None = None,
                attachment: ChatAttachment | None = None, solve=None) -> dict:
    """Контекст + лекции + история → ответ /api/chat (content, html, reasoning,
    sources). Общая часть настоящего чата и демо-входа проверяющих магазинов
    (review_demo.demo_chat). sources — куски с номерами [n] (поиск по смыслу);
    None — целые лекции, источники ищутся по заголовкам. solve — своя модель
    вместо обычной («Подумать»). Сбой модели — 502 BUSY_TEXT."""
    from utils import md_to_tg_html_chunks
    try:
        result = await (solve() if solve else _solve(history, subject, context, lectures, attachment))
    except HTTPException:
        raise
    except Exception as e:
        # причина (какая модель, код) — в лог для /status; человеку — без
        # названий провайдеров и кодов (Никита 21.10: «причём тут Gemini?»)
        logger.warning(f"webapp chat failed: {_short_reason(e)} ({e!r})")
        raise HTTPException(status_code=502, detail=BUSY_TEXT)
    # Тот же вид, что и в боте: жирный, код, x² вместо x^2 (всё экранировано).
    result["html"] = "\n".join(md_to_tg_html_chunks(result.get("content", "")))
    # Под ответом — только материалы, на которые ИИ сослался номером: на
    # болтовню и вопросы не по учёбе плашек нет. Ответ без лекций (запасной
    # путь _chat_with_fallback) — источников нет.
    if lectures and not result.pop("no_lectures", False):
        used = cited(result.get("content", ""))
        if sources is None:     # целые лекции: номер не нужен фронту (страницы нет)
            sources = [{k: v for k, v in s.items() if k != "n"}
                       for s in await _lecture_sources(lectures, subject) if s["n"] in used]
        else:
            sources = [s for s in sources if s["n"] in used]
        if sources:
            # чипы по порядку: «Лекция 2, Лекция 3 · стр. 28, Лекция 3 · стр. 37»,
            # а не в порядке релевантности (Никита 21.10: «почему 2, 4?»)
            sources.sort(key=lambda s: (_natural(str(s.get("title") or "")), s.get("page") or 0))
            result["sources"] = sources
    return result


@router.post("/api/chat")
async def api_chat(body: ChatBody, user: dict = CurrentUser, x_app: str = Header(default="")):
    """Чат WebApp: история (последние 20), по желанию предмет (если по нему
    есть лекции — ответ опирается на них) и одно вложение — фото (решает
    Gemini по картинке) или документ PDF/DOCX/PPTX/TXT (его текст уходит в
    сообщение). В системный промпт — контекст группы: пары, дедлайны, ДЗ."""
    import asyncio
    from database import get_subject_lecture_context, get_subjects_with_lecture_text
    from group_context import build_group_context

    import ai_quota
    import think
    deep = body.think or body.think_first
    again = deep and not body.think_first        # «Подумать ещё» под ответом
    if deep:
        if body.attachment or not await think.offer(user["id"], x_app):
            raise HTTPException(status_code=403, detail=think.PLUS_TEXT)
    else:
        why = await ai_quota.gate(user["id"])
        if why:
            raise HTTPException(status_code=429, detail=ai_quota.text(why, app=x_app))
    history = clean_history(body.history)
    if not history:
        raise HTTPException(status_code=400, detail="пустая история")
    subject = body.subject.strip()
    with_text = await get_subjects_with_lecture_text()
    picked_subject = ""
    if not subject and history[-1]["role"] == "user":
        # «завтра МБП, что на лекции?» — предмет по сокращению, без списка
        # «по какому предмету?» (фронт переключит предмет в шапке)
        import lecture_picker as _lp
        picked_subject = _lp.subject_by_abbrev(history[-1]["content"], with_text) or ""
        subject = picked_subject
    # Лекции — только подходящие к вопросу (lecture_picker): после выгрузки
    # СДО их у предмета сотни тысяч символов. Без выбранного предмета — из
    # всех предметов, но только при явном совпадении с вопросом.
    import lecture_picker
    from database import get_all_lecture_context
    # «Подробнее», «Пример», «а почему?» — ищем по теме прошлых вопросов,
    # заглушку вложения («Разбери этот файл.») не ищем вовсе
    query = lecture_picker.search_query(history)
    last = history[-1]["content"] if history[-1]["role"] == "user" else ""
    if deep and history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="нет вопроса")
    # «скинь практику 3» и «по какому предмету?» — без ИИ, попытку
    # «Подумать» не тратят; у «Подумать ещё» вопрос уже был отвечен
    if not body.attachment and not again and history[-1]["role"] == "user":
        found = await _chat_file_request(history[-1]["content"])
        if found:
            return found
    lectures, sources = "", None
    searched = False        # поиск по смыслу отработал: пусто — значит, вопрос не про лекции
    # «что будет на лекции завтра / на первой паре?» с известным предметом —
    # какая это лекция по счёту по расписанию и её файл «Лекция N», а не обзор
    # всего курса и случайные куски (Никита 21.10)
    lecture_note = ""
    if subject and subject in with_text and not body.attachment and last:
        try:
            lectures, lecture_note = await _lecture_of_day(user["id"], subject, last, query)
        except Exception as e:
            logger.info(f"лекция дня: {type(e).__name__}: {e}")
            lectures, lecture_note = "", ""
    # Потом — поиск по смыслу (semantic_search): куски лекций с номером
    # страницы/слайда. «Объясни 3 лекцию» (номер лекции, а не смысл) и пустой
    # индекс (сразу после деплоя) — по-старому, целыми лекциями.
    if lectures:
        pass
    elif query.strip() and (not subject or subject in with_text) and not lecture_picker.wants_course(query):
        try:
            import semantic_search
            if await semantic_search.ready():
                import embedder
                hits = await semantic_search.search(query, subject)
                searched = embedder.rel_min(embedder.provider()) is not None   # у модели есть порог
                if hits:
                    lectures, sources = semantic_search.build_context(hits)
        except Exception as e:
            logger.warning(f"поиск по смыслу: {type(e).__name__}: {e} — подбираю лекции по словам")
            lectures, sources = "", None
            searched = False
    if lectures or searched:
        # нашлось — или поиск решил, что вопрос не про лекции («Буря мглою»,
        # «тебя обижают?»): целые лекции по словам тогда не подмешиваем
        pass
    elif subject and subject in with_text:
        lectures = lecture_picker.pick(await get_subject_lecture_context(subject), query)
    elif not subject and query.strip():
        all_lectures = await get_all_lecture_context()
        if not body.attachment and not again and lecture_picker.wants_course(last):
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
    lectures = _number_lectures(lectures)
    context = await build_group_context(user["id"])
    if lecture_note:
        context += "\n" + lecture_note

    solve = None
    if deep:
        async def solve():
            try:
                return {"content": await think.solve(user["id"], history, subject, lectures, context,
                                                     first=body.think_first),
                        "reasoning": ""}
            except think.ThinkError as e:
                raise HTTPException(status_code=502, detail=str(e))
    result = await reply(history, subject, context, lectures, sources, body.attachment, solve)
    # кнопка «Подумать ещё» под ответом (подписчикам, не на iPhone); к фото и
    # файлу — нет: модель второго уровня читает только текст
    offer = None if body.attachment else await think.offer(user["id"], x_app)
    if offer:
        result["think"] = offer
    if picked_subject:
        result["subject"] = picked_subject
    return result
