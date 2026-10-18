"""Рейтинг по опыту (xp.py): экран «Рейтинг», свой ник и согласие."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


@router.get("/api/rating")
async def api_rating(user: dict = CurrentUser):
    import xp
    from database.groups import get_user_group, home
    gid = await get_user_group(user["id"]) or home()
    return await xp.for_user(user["id"], gid)


class ProfileBody(BaseModel):
    nick: str | None = None      # '' — ник по умолчанию (имя и буква фамилии)
    show: bool | None = None     # показывать меня группе в рейтинге


@router.put("/api/rating/me")
async def api_rating_me(body: ProfileBody, user: dict = CurrentUser):
    import ratelimit
    import xp
    if body.nick is not None and not ratelimit.allow("nick", user["id"]):
        raise HTTPException(429, "Много смен ника подряд — подожди немного")
    try:
        return await xp.save(user["id"], nick=body.nick, show=body.show)
    except ValueError as e:
        raise HTTPException(400, str(e))
