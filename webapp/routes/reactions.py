"""Реакции на пару (lesson_reactions.py): счёт группы и своя отметка."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


def _when(start: str) -> datetime:
    from utils import TZ
    start = start.strip()
    try:   # «…Z» из приложения: fromisoformat до Python 3.11 его не понимает
        when = datetime.fromisoformat(start[:-1] + "+00:00" if start[-1:] in ("Z", "z") else start)
    except ValueError:
        raise HTTPException(status_code=400, detail="start — время ISO")
    return when.replace(tzinfo=TZ) if when.tzinfo is None else when


async def _group(user: dict) -> int:
    from database.groups import home, viewer_group
    gid = await viewer_group(user["id"])
    if not gid and home():   # не в чате своей группы и другую не выбрал — счёта нет
        raise HTTPException(status_code=403, detail="реакции — для своей группы")
    return gid


def _check(title: str):
    if not title.strip() or len(title) > 200:
        raise HTTPException(status_code=400, detail="название пары")


@router.get("/api/lesson/reactions")
async def api_reactions(start: str, title: str, user: dict = CurrentUser):
    import lesson_reactions as lr
    from utils import TZ
    when = _when(start)
    _check(title)
    out = await lr.get(await _group(user), lr.lesson_key(when, title), user["id"])
    out["open"] = lr.is_open(when, datetime.now(TZ))
    return out


class ReactionBody(BaseModel):
    start: str
    title: str
    kind: str = ""   # пусто — снять свою


@router.post("/api/lesson/reactions")
async def api_reaction_set(body: ReactionBody, user: dict = CurrentUser):
    import lesson_reactions as lr
    import ratelimit
    from utils import TZ
    when = _when(body.start)
    _check(body.title)
    if body.kind and body.kind not in lr.KINDS:
        raise HTTPException(status_code=400, detail="такой реакции нет")
    if not lr.is_open(when, datetime.now(TZ)):
        raise HTTPException(status_code=400, detail="отметить можно, когда пара началась, и две недели после")
    gid = await _group(user)
    if not ratelimit.allow("reaction", user["id"]):
        raise HTTPException(429, "Много отметок подряд — подожди пару минут")
    key = lr.lesson_key(when, body.title)
    await lr.put(gid, key, user["id"], body.kind or None)
    out = await lr.get(gid, key, user["id"])
    out["open"] = True
    return out


# ── Комментарии под парой (lesson_comments.py) ──────────────────────────────

@router.get("/api/lesson/comments")
async def api_comments(start: str, title: str, user: dict = CurrentUser):
    import lesson_comments as lc
    import lesson_reactions as lr
    from utils import TZ
    when = _when(start)
    _check(title)
    items = await lc.items(await _group(user), lr.lesson_key(when, title), user["id"])
    return {"items": items, "open": lc.is_open(when, datetime.now(TZ)), "max": lc.TEXT_MAX}


class CommentBody(BaseModel):
    start: str
    title: str
    text: str


@router.post("/api/lesson/comments")
async def api_comment_add(body: CommentBody, user: dict = CurrentUser):
    import lesson_comments as lc
    import lesson_reactions as lr
    import ratelimit
    from utils import TZ
    when = _when(body.start)
    _check(body.title)
    if not lc.is_open(when, datetime.now(TZ)):
        raise HTTPException(status_code=400, detail="писать можно за неделю до пары и две недели после")
    text = body.text.strip()
    if why := lc.problem(text):
        raise HTTPException(status_code=400, detail=why)
    gid = await _group(user)
    if not ratelimit.allow("comment", user["id"]):
        raise HTTPException(429, "Много комментариев подряд — подожди пару минут")
    key = lr.lesson_key(when, body.title)
    cid = await lc.add(gid, key, user["id"], text)
    return {"ok": True, "id": cid, "items": await lc.items(gid, key, user["id"])}


@router.delete("/api/lesson/comments/{comment_id}")
async def api_comment_delete(comment_id: int, user: dict = CurrentUser):
    """Убрать комментарий: свой — автор, любой своей группы — её староста."""
    import lesson_comments as lc
    from database import is_editor
    c = await lc.get(comment_id)
    gid = await _group(user)
    if not c or c["group_id"] != gid:
        raise HTTPException(status_code=404, detail="комментарий не найден")
    if c["user_id"] != user["id"] and not await is_editor(user["id"], gid):
        raise HTTPException(status_code=403, detail="убрать можно только свой комментарий")
    await lc.delete(comment_id)
    return {"ok": True}


# ── Оценка преподавателя в капибарах (teacher_rating.py) ────────────────────

def _teacher(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > 120:
        raise HTTPException(status_code=400, detail="имя преподавателя")
    return name


@router.get("/api/teacher/rating")
async def api_teacher_rating(name: str, user: dict = CurrentUser):
    import teacher_rating as tr
    name = _teacher(name)
    out = await tr.summary(name, user["id"])
    out["can_rate"] = out["mine"] is not None or await tr.can_rate(user["id"], name)
    return out


class RatingBody(BaseModel):
    name: str
    score: int = 0   # 0 — убрать свою


@router.post("/api/teacher/rating")
async def api_teacher_rate(body: RatingBody, user: dict = CurrentUser):
    import ratelimit
    import teacher_rating as tr
    name = _teacher(body.name)
    if body.score and body.score not in tr.SCORES:
        raise HTTPException(status_code=400, detail="оценка — от 1 до 5")
    if body.score and not await tr.can_rate(user["id"], name):
        raise HTTPException(status_code=403, detail="оценить можно преподавателя из расписания своей группы")
    if not ratelimit.allow("rating", user["id"]):
        raise HTTPException(429, "Много оценок подряд — подожди пару минут")
    await tr.put(name, user["id"], body.score or None)
    out = await tr.summary(name, user["id"])
    out["can_rate"] = True
    return out
