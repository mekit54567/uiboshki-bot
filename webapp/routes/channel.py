"""Обложки постов канала (channel_posts.cover_jpeg) для превью ссылки:
длинный пост уходит одним сообщением, а картинку над текстом Telegram
забирает сам по /chimg/<пост>.jpg — без initData, посты и так публичные."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()


@router.get("/chimg/{slug}.jpg")
async def channel_cover(slug: str):
    import asyncio
    from kapibara.features.content import channel_posts
    post = next((p for p in channel_posts.load_posts() if p["slug"] == slug), None)
    if not post or not post["images"]:
        raise HTTPException(404)
    data = await asyncio.to_thread(channel_posts.cover_jpeg, post)
    # ссылка с ?v=<метка содержимого> — можно кэшировать надолго
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
