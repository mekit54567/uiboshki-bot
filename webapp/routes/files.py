"""Файлы курсов: список по предметам и типам, «В чат», подписанные ссылки
/dl для «📥 Скачать», удаление и правка."""

import logging
import re
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from config import STAROSTA_ID, is_starosta
from webapp import deps
from webapp.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Файлы ────────────────────────────────────────────────────────────────────

@router.get("/api/files")
async def api_files(subject: str = "", q: str = "", user: dict = CurrentUser):
    from database import get_files, search_files
    if q.strip():
        items = await search_files(q.strip())
    else:
        items = await get_files(subject or None)
    import ugc
    items = ugc.without_hidden(items, await ugc.hidden(user["id"]), "uploaded_by")
    # file_id намеренно не отдаём наружу как "ссылку на скачивание" — Telegram
    # file_id не резолвится в прямой URL без похода через getFile от лица
    # бота, а светить его в браузерном JS не хочется. Вместо этого фронт
    # открывает диплинк на сам бот (t.me/<bot>?start=file_<id>), который уже
    # шлёт документ — см. handlers/start.py: cmd_start_deeplink.
    from database import get_file_ids_with_summary, get_file_ids_with_text
    from file_categories import CATEGORIES, LABELS, category_of
    from file_names import split_title
    from database import is_editor
    with_text = await get_file_ids_with_text()
    with_summary = await get_file_ids_with_summary()
    editor = await is_editor(user["id"])
    out = []
    for f in items:
        cat = category_of(f)
        # «Лекция 8. Тема» — номер заголовком, тема строкой под ним (владелец, 09.10);
        # «Презентация» не тема: PDF и слайды одной лекции — одна строка в приложении
        head, topic = split_title(f["title"])
        out.append({
            "id": f["id"], "title": f["title"], "subject": f.get("subject") or "",
            "head": head or f["title"], "topic": "" if topic == "Презентация" else topic,
            "file_name": f.get("file_name") or "", "has_text": f["id"] in with_text,
            "has_summary": f["id"] in with_summary,
            "category": cat, "category_label": LABELS[cat],
            # как /delfile в боте: тот, кто загрузил, или староста/зам
            "can_edit": editor or f.get("uploaded_by") == user["id"],
        })
    return {"items": out, "categories": [{"key": k, "label": v} for k, v in CATEGORIES],
            "can_delete": not STAROSTA_ID or is_starosta(user["id"])}


@router.post("/api/files/{file_id}/send")
async def api_send_file(file_id: int, user: dict = CurrentUser):
    """Кнопка «Открыть»: бот шлёт файл в личку. Раньше фронт открывал
    диплинк t.me/<бот>?start=file_<id>, и в чате копились «/start file_…»."""
    from handlers.start import send_file_to
    import ratelimit
    from database.identities import is_local
    if is_local(user["id"]):
        raise HTTPException(400, "Telegram не подключён — скачай файл кнопкой «Скачать»")
    if not ratelimit.allow("send", user["id"]):
        raise HTTPException(429, "Много файлов подряд — подожди минутку")
    if not await send_file_to(deps.tg_bot(), user["id"], file_id):
        raise HTTPException(404, "Файл не найден")
    return {"ok": True}


# «📥 Скачать»: Telegram.WebApp.downloadFile качает по обычной ссылке без
# initData, поэтому ссылка подписана (HMAC от токена бота) и живёт 10 минут.
# Сам файл бот берёт у Telegram по file_id — Bot API отдаёт до 20 МБ, файлы
# больше фронт отправляет в чат, как «В чат».
DL_TTL = 600


def _dl_sig(file_id: int, exp: int) -> str:
    import hashlib
    import hmac
    return hmac.new(deps.BOT_TOKEN.encode(), f"dl:{file_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def _download_name(f: dict, file_path: str = "") -> str:
    name = (f.get("file_name") or "").strip()
    if name:
        return name
    ext = Path(file_path).suffix if file_path else ""
    return re.sub(r'[\\/:*?"<>|]+', " ", f.get("title") or "file").strip()[:100] + ext


async def _visible_file(file_id: int, user: dict) -> dict:
    """Файл по номеру — только если виден группе человека. Раньше ссылка на
    скачивание, страница и конспект отдавались по любому номеру: перебором
    выкачивались файлы всех групп (ревью безопасности 09.10)."""
    from database import get_file_by_id
    from database.files import file_visible
    from database.groups import viewer_group
    f = await get_file_by_id(file_id)
    if not f or not await file_visible(file_id, await viewer_group(user["id"])):
        raise HTTPException(404, "Файл не найден")
    return f


@router.post("/api/files/{file_id}/link")
async def api_file_link(file_id: int, request: Request, user: dict = CurrentUser):
    import time
    from urllib.parse import quote
    f = await _visible_file(file_id, user)
    try:
        tf = await deps.tg_bot().get_file(f["file_id"])
    except Exception as e:
        logger.info(f"файл {file_id} не скачать через Bot API: {e}")
        raise HTTPException(413, "Файл слишком большой для скачивания — отправлю в чат")
    name = _download_name(f, tf.file_path or "")
    exp = int(time.time()) + DL_TTL
    base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
    return {"url": f"{base}/dl/{file_id}/{quote(name, safe='')}?exp={exp}&sig={_dl_sig(file_id, exp)}", "file_name": name}


# «Просмотр» в браузере (?view=1) — только типы, которые браузер не исполнит:
# PDF, картинки, офисные файлы (Safari на iPhone их листает); остальное — загрузкой
_VIEW_TYPES = {"application/pdf", "image/png", "image/jpeg", "text/plain",
               "application/vnd.openxmlformats-officedocument.presentationml.presentation",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               "application/vnd.ms-powerpoint", "application/msword", "application/vnd.ms-excel"}


@router.get("/dl/{file_id}/{name}")
async def download_file(file_id: int, name: str, exp: int, sig: str, view: int = 0):
    import hmac
    import mimetypes
    import time
    from urllib.parse import quote
    from database import get_file_by_id
    if exp < time.time() or not hmac.compare_digest(sig, _dl_sig(file_id, exp)):
        raise HTTPException(403, "Ссылка устарела — нажми «Скачать» ещё раз")
    f = await get_file_by_id(file_id)
    if not f:
        raise HTTPException(404, "Файл не найден")
    bot = deps.tg_bot()
    tf = await bot.get_file(f["file_id"])
    data = await bot.download_file(tf.file_path)
    # Имя в пути — только для красоты ссылки: подпись его не покрывает, так
    # что имя и Content-Type берём из базы (иначе подменой пути .pdf
    # превращается в .html с типом text/html).
    name = _download_name(f, tf.file_path or "")
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    how = "inline" if view and mime in _VIEW_TYPES else "attachment"
    return Response(data.getvalue(), media_type=mime,
                    headers={"Content-Disposition": f"{how}; filename*=UTF-8''{quote(name, safe='')}"})



class FileIds(BaseModel):
    ids: list[int]


@router.post("/api/files/delete")
async def api_files_delete(body: FileIds, user: dict = CurrentUser):
    """Удалить файл или сразу папку/раздел (лишнее из выгрузки СДО) — у
    всей группы. Как /delfile в боте: только староста."""
    from database import delete_files, get_files
    if STAROSTA_ID and not is_starosta(user["id"]):
        raise HTTPException(status_code=403, detail="удалять файлы может только староста")
    ids = sorted(set(body.ids))
    if not ids or len(ids) > 1000:
        raise HTTPException(status_code=400, detail="от 1 до 1000 файлов за раз")
    by_id = {f["id"]: f for f in await get_files()}
    files = [by_id[i] for i in ids if i in by_id]
    if not files:
        raise HTTPException(status_code=404, detail="файлы не найдены")
    return {"ok": True, "deleted": await delete_files([f["id"] for f in files])}


class FileMeta(BaseModel):
    title: str
    subject: str = ""
    category: str


@router.patch("/api/files/{file_id}")
async def api_file_edit(file_id: int, body: FileMeta, user: dict = CurrentUser):
    """Поправить название, предмет и тип файла (например, если тип по
    названию угадан неверно). Предмет меняется вместе с контекстом ИИ:
    текст лекции привязан к файлу, а не к предмету."""
    from database import get_files, update_file_meta
    from file_categories import LABELS
    from database import is_editor
    f = next((x for x in await get_files() if x["id"] == file_id), None)
    if not f:
        raise HTTPException(status_code=404, detail="файл не найден")
    from database.groups import row_group
    # староста — группы самого файла: файл своей группы, общий с чужой, её староста не правит
    if f.get("uploaded_by") != user["id"] and not await is_editor(user["id"], row_group(f.get("group_id"))):
        raise HTTPException(status_code=403, detail="править файл может тот, кто его загрузил, или староста")
    title, subject = body.title.strip(), body.subject.strip()
    if not title or len(title) > 120:
        raise HTTPException(status_code=400, detail="название — от 1 до 120 символов")
    if len(subject) > 80:
        raise HTTPException(status_code=400, detail="предмет — до 80 символов")
    if body.category not in LABELS:
        raise HTTPException(status_code=400, detail="неизвестный тип файла")
    await update_file_meta(file_id, title, subject, body.category)
    return {"ok": True, "id": file_id}


# ── Конспект лекции (lecture_summary.py) ─────────────────────────────────────
# Свой путь /api/summary, а не /api/files/{id}/…: stats.kind_for считает
# любой POST на /api/files/ скачиванием.

async def _summary_view(f: dict, s: dict | None = None) -> dict:
    """s — только что сделанный конспект: неполный (запасной ИИ) в базу не
    пишется, поэтому показываем его отсюда, а не из базы."""
    import lecture_summary
    from database import get_file_summary, get_file_text
    from file_categories import LABELS, category_of
    s = s or await get_file_summary(f["id"])
    return {
        "id": f["id"], "title": f["title"], "subject": f.get("subject") or "",
        "category_label": LABELS[category_of(f)], "has_text": bool(s) or bool(await get_file_text(f["id"])),
        "summary": lecture_summary.to_html(s["content"]) if s else None,
        "created_at": (s["created_at"] or "")[:10] if s else None,
    }


@router.get("/api/summary/{file_id}")
async def api_summary(file_id: int, user: dict = CurrentUser):
    """Конспект файла, если его уже кто-то сделал (иначе summary: null)."""
    return await _summary_view(await _visible_file(file_id, user))


@router.post("/api/summary/{file_id}")
async def api_summary_make(file_id: int, user: dict = CurrentUser):
    """«Сделать конспект»: первый нажавший ждёт ИИ, дальше конспект у всех."""
    import lecture_summary
    from database import get_file_summary
    f = await _visible_file(file_id, user)
    import ai_quota
    why = None if await get_file_summary(file_id) else await ai_quota.gate(user["id"], kind="summary")
    if why:
        raise HTTPException(429, ai_quota.text(why, capital=True))
    try:
        made = await lecture_summary.make(file_id, f["title"], f.get("subject") or "", user["id"])
    except lecture_summary.NoText:
        raise HTTPException(422, "В файле нет текста — конспект делать не из чего")
    except Exception as e:
        logger.warning(f"конспект файла {file_id}: {e!r}")
        raise HTTPException(502, "ИИ сейчас не ответил — попробуй через минуту")
    return await _summary_view(f, made)



# ── Поиск внутри лекций (вкладка «Файлы») ────────────────────────────────────
# Поиск по названиям не находит «где было про NPV»: это внутри лекций. Тот же
# гибридный поиск, что у ИИ-чата (semantic_search), только без ответа ИИ —
# сразу места: «Лекция 5 · слайд 12» и отрывок; нажал — открылась страница.

def _snippet(text: str, query: str, width: int = 180) -> str:
    """Отрывок вокруг первого слова запроса (по началу слова, без окончаний)."""
    import re
    flat = re.sub(r"\s+", " ", text or "").strip()
    low = flat.lower()
    stems = [w[:5] for w in re.findall(r"[\wё]+", (query or "").lower()) if len(w) >= 3]
    pos = min((i for i in (low.find(s) for s in stems) if i >= 0), default=-1)
    if pos < 0:
        return flat[:width] + ("…" if len(flat) > width else "")
    start = max(0, pos - 60)
    piece = flat[start:start + width]
    return ("…" if start else "") + piece + ("…" if start + width < len(flat) else "")


@router.get("/api/lecture-search")
async def api_lecture_search(q: str = "", subject: str = "", user: dict = CurrentUser):
    import ratelimit
    import semantic_search
    q = q.strip()[:120]
    if len(q) < 3:
        return {"items": [], "ready": True}
    if not ratelimit.allow("lsearch", user["id"]):
        raise HTTPException(429, "Слишком часто — подожди минуту")
    if not await semantic_search.ready():
        return {"items": [], "ready": False}
    try:
        hits = await semantic_search.search(q, subject=subject, k=8)
    except Exception as e:
        logger.warning(f"поиск в лекциях: {e!r}")
        raise HTTPException(502, "Поиск в лекциях сейчас не работает")
    return {"ready": True, "items": [{
        "file_id": h["file_id"], "title": h["title"], "subject": h["subject"],
        "place": semantic_search.place(h), "page": h["page_from"], "snippet": _snippet(h["text"], q),
    } for h in hits]}


# ── Страница лекции по ссылке из ответа ИИ («Лекция 5 · слайд 12») ─────────
# Текст страницы — из индекса поиска (semantic_index), а у PDF — ещё и сама
# страница картинкой: pypdfium2 рисует её на сервере. Картинку Telegram-
# браузер грузит обычным <img> без initData, поэтому ссылка подписана, как /dl.

_pdf_cache: dict[int, bytes] = {}           # последние PDF (байты) — листать страницы без перекачки
_page_cache: dict[tuple[int, int], bytes] = {}


def _pg_sig(file_id: int, page: int, exp: int) -> str:
    import hashlib
    import hmac
    return hmac.new(deps.BOT_TOKEN.encode(), f"pg:{file_id}:{page}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


@router.get("/api/files/{file_id}/page/{page}")
async def api_file_page(file_id: int, page: int, request: Request, user: dict = CurrentUser):
    import time
    from semantic_index import open_index
    f = await _visible_file(file_id, user)
    async with open_index() as db:
        rows = await (await db.execute(
            "SELECT page_from, page_to, kind, text FROM chunks WHERE file_id=? ORDER BY page_from, id", (file_id,))).fetchall()
    if not rows:
        raise HTTPException(404, "Файл ещё не разобран по страницам")
    last = max(r[1] for r in rows)
    page = max(1, min(page, last))
    text = "\n\n".join(r[3] for r in rows if r[0] <= page <= r[1])
    kind = rows[0][2]
    out = {"id": file_id, "title": f["title"], "page": page, "pages": last, "kind": kind, "text": text, "image": None}
    if (f.get("file_name") or "").lower().endswith(".pdf"):
        exp = int(time.time()) + 600
        base = (deps.WEBAPP_URL or str(request.base_url)).rstrip("/")
        out["image"] = f"{base}/pg/{file_id}/{page}.jpg?exp={exp}&sig={_pg_sig(file_id, page, exp)}"
    return out


# PDFium не потокобезопасен: две страницы, которые рисуются в to_thread
# одновременно, давали сотни «Data format error» (и могут портить память).
# Вся работа с pypdfium2 — строго под одним замком.
_pdfium_lock = threading.Lock()


def _render_pdf_page(data: bytes, page: int) -> bytes:
    import io
    import pypdfium2 as pdfium
    with _pdfium_lock:
        pdf = pdfium.PdfDocument(data)
        try:
            img = pdf[page - 1].render(scale=1.6).to_pil().convert("RGB")
        finally:
            pdf.close()
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


@router.get("/pg/{file_id}/{page}.jpg")
async def file_page_image(file_id: int, page: int, exp: int, sig: str):
    import asyncio
    import hmac
    import time
    from database import get_file_by_id
    if exp < time.time() or not hmac.compare_digest(sig, _pg_sig(file_id, page, exp)):
        raise HTTPException(403, "Ссылка устарела")
    key = (file_id, page)
    if key not in _page_cache:
        data = _pdf_cache.get(file_id)
        if data is None:
            f = await get_file_by_id(file_id)
            if not f:
                raise HTTPException(404, "Файл не найден")
            try:
                bot = deps.tg_bot()
                tf = await bot.get_file(f["file_id"])
                data = (await bot.download_file(tf.file_path)).read()
            except Exception as e:
                logger.info(f"страница {file_id}/{page}: файл не скачался: {e}")
                raise HTTPException(413, "Файл слишком большой — открой его целиком")
            _pdf_cache[file_id] = data
            while len(_pdf_cache) > 4:
                _pdf_cache.pop(next(iter(_pdf_cache)))
        try:
            _page_cache[key] = await asyncio.to_thread(_render_pdf_page, data, page)
        except Exception as e:
            logger.info(f"страница {file_id}/{page}: не нарисовалась: {e}")
            raise HTTPException(422, "Страница не нарисовалась")
        while len(_page_cache) > 60:
            _page_cache.pop(next(iter(_page_cache)))
    return Response(_page_cache[key], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})
