"""Жалоба на запись и «Скрыть автора» (ugc.py, правило Apple 1.2, 5.99.0)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp import deps
from webapp.deps import CurrentUser

router = APIRouter()


class ItemBody(BaseModel):
    kind: str                 # note | hw | file | deadline
    id: int
    reason: str = ""


@router.post("/api/report")
async def api_report(body: ItemBody, user: dict = CurrentUser):
    """Пожаловаться: запись уходит владельцу в бота с «Удалить / Оставить»."""
    import ugc
    try:
        await ugc.report(deps.tg_bot(), user["id"], body.kind, body.id, body.reason)
    except ugc.ReportError as e:
        raise HTTPException(e.status, e.message)
    return {"ok": True}


@router.post("/api/hide-author")
async def api_hide_author(body: ItemBody, user: dict = CurrentUser):
    """Скрыть автора записи — только у себя."""
    import ugc
    try:
        await ugc.hide_author(user["id"], body.kind, body.id)
    except ugc.ReportError as e:
        raise HTTPException(e.status, e.message)
    return {"ok": True}


@router.get("/api/hidden-authors")
async def api_hidden(user: dict = CurrentUser):
    import ugc
    return {"count": len(await ugc.hidden(user["id"]))}


@router.delete("/api/hidden-authors")
async def api_unhide(user: dict = CurrentUser):
    """«Показать всех снова» (Ещё → Безопасность)."""
    import ugc
    return {"ok": True, "count": await ugc.unhide_all(user["id"])}
