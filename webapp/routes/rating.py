"""Рейтинг по опыту (xp.py): экран «Рейтинг», группа по нажатию, свой ник и согласия."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


@router.get("/api/rating")
async def api_rating(user: dict = CurrentUser):
    from kapibara.features.social import xp
    from database.groups import get_user_group, home, viewer_group
    gid = await get_user_group(user["id"]) or home()
    # люди «своей» группы с тумблером «группе» — только тем, кто правда в ней
    # (своя группа бота с 19.11 открыта всем, кто её выбрал)
    member = await viewer_group(user["id"]) == gid
    return await xp.for_user(user["id"], gid, member=member)


@router.get("/api/rating/group/{group_id}")
async def api_rating_group(group_id: int, user: dict = CurrentUser):
    from kapibara.features.social import xp
    from database.groups import viewer_group
    data = await xp.group_view(user["id"], await viewer_group(user["id"]), group_id)
    if data is None:
        raise HTTPException(404, "Такой группы в рейтинге нет")
    return data


class ProfileBody(BaseModel):
    nick: str | None = None      # '' — ник по умолчанию (имя и буква фамилии)
    show: bool | None = None     # показывать меня группе в рейтинге
    show_all: bool | None = None  # показывать меня всем пользователям (ст. 10.1)
    consent: str | None = None    # версия текста отдельного согласия, с show_all=true


@router.put("/api/rating/me")
async def api_rating_me(body: ProfileBody, user: dict = CurrentUser,
                        x_telegram_init_data: str = Header(default=""), x_app: str = Header(default="")):
    from kapibara.core import ratelimit
    from kapibara.features.social import xp
    from webapp.routes.legal import _via
    if body.nick is not None and not ratelimit.allow("nick", user["id"]):
        raise HTTPException(429, "Много смен ника подряд — подожди немного")
    try:
        return await xp.save(user["id"], nick=body.nick, show=body.show, show_all=body.show_all,
                             consent=body.consent, via=_via(x_telegram_init_data, x_app))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/rating/offer")
async def api_rating_offer(user: dict = CurrentUser):
    """Предложить показаться: {'card': ..., 'sheet': ...} (rating_offer.py).
    Ничего не включает — только говорит клиенту, можно ли спросить."""
    from kapibara.features.social import rating_offer
    return await rating_offer.state(user["id"])


class OfferBody(BaseModel):
    action: str                    # shown / later / stop / accepted
    source: str | None = None      # card / sheet / event — для accepted


@router.post("/api/rating/offer")
async def api_rating_offer_act(body: OfferBody, user: dict = CurrentUser):
    from kapibara.features.social import rating_offer
    try:
        return await rating_offer.act(user["id"], body.action, body.source)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
