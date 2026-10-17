"""Ачивки приложения (5.91): GET — что открыто, POST — приложение присылает
открытые у себя ({id: мс}), в ответ — всё, что есть на сервере."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from config import is_starosta
from webapp.deps import CurrentUser

router = APIRouter()


class AchBody(BaseModel):
    items: dict[str, int] = {}


def _now() -> int:
    return int(time.time() * 1000)


@router.get("/api/achievements")
async def api_achievements(user: dict = CurrentUser):
    import achievements
    if is_starosta(user["id"]):
        return {"items": await achievements.grant_all(user["id"], _now())}
    return {"items": await achievements.of_user(user["id"])}


@router.post("/api/achievements")
async def api_achievements_add(body: AchBody, user: dict = CurrentUser):
    import achievements
    items = await achievements.add(user["id"], dict(list(body.items.items())[:64]), _now())
    if is_starosta(user["id"]):
        items = await achievements.grant_all(user["id"], _now())
    return {"items": items}
