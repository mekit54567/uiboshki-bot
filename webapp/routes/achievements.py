"""Ачивки приложения (5.91): GET — что открыто, POST — приложение присылает
открытые у себя ({id: мс}), в ответ — всё, что есть на сервере."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


class AchBody(BaseModel):
    items: dict[str, int] = {}


@router.get("/api/achievements")
async def api_achievements(user: dict = CurrentUser):
    import achievements
    return {"items": await achievements.of_user(user["id"])}


@router.post("/api/achievements")
async def api_achievements_add(body: AchBody, user: dict = CurrentUser):
    import achievements
    return {"items": await achievements.add(user["id"], dict(list(body.items.items())[:64]),
                                            int(time.time() * 1000))}
