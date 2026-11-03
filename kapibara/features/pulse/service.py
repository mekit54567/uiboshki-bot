"""Вход в Пульс и посещения вместе (03.11, клубок импортов).

accounts — только вход (кука, проверка, хранение), attendance — посещения
по этому входу и сам зовёт accounts.cookie_for. Чтобы accounts не звал
attendance обратно, «вошёл → подтянуть посещения» живёт здесь, слоем выше
обоих: сюда ходят API (/api/pulse/connect) и планировщик.
"""
from datetime import datetime

from kapibara.core.tasks import spawn
from kapibara.features.pulse import accounts, attendance


async def connect_from_app(user_id: int, raw_cookie: str) -> dict:
    """Вход из окна приложения; удался — первые посещения сразу, фоном."""
    result = await accounts.connect_from_app(user_id, raw_cookie)
    if result["state"] == "ok":
        spawn(attendance.sync_due(user_id), name=f"pulse-sync-{user_id}")
    return result


async def keepalive_due(now: datetime | None = None):
    """Раз в минуту (scheduler.py): проверить входы, чья очередь, и заодно
    посещения лекций у тех, чей вход жив (sync_due — не чаще раза в 3 ч)."""
    for uid in await accounts.keepalive_due(now):
        if await accounts.cookie_for(uid):
            await attendance.sync_due(uid)
