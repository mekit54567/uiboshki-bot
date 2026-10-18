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
