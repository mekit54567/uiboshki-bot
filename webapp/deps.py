"""
Общее для обработчиков WebApp (webapp/routes/*): вход по initData
(get_current_user / CurrentUser), бот для отправки файлов и настройки.

BOT_TOKEN и WEBAPP_URL обработчики читают отсюда в момент запроса
(deps.BOT_TOKEN), а не копируют себе при импорте — тогда тесты подменяют их
в одном месте.
"""

from fastapi import Depends, Header, HTTPException, Request

from config import BOT_TOKEN, WEBAPP_URL  # noqa: F401 — читают routes/* и server.py
from webapp.auth import InitDataError, validate_init_data


async def _session_user(request: Request) -> dict | None:
    """Вход без Telegram (этап 2): «Authorization: Bearer <токен>» — сессия
    устройства (database/sessions.py). → пользователь как из initData."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    from database import get_user
    from database.sessions import session_user
    uid = await session_user(auth[7:].strip())
    if not uid:
        raise HTTPException(status_code=401, detail="сессия закончилась — войди заново")
    row = await get_user(uid) or {}
    first, _, last = (row.get("full_name") or "").partition(" ")
    return {"id": uid, "first_name": first, "last_name": last, "username": row.get("username") or "",
            "via": "session"}


async def get_current_user(request: Request, x_telegram_init_data: str = Header(default="")) -> dict:
    """FastAPI dependency: валидирует initData, апсертит пользователя в общую
    с ботом таблицу users (тем же способом, что и /start в самом боте — тогда
    и утренний дайджест, и всё остальное видят его одинаково), возвращает
    telegram user dict (id, first_name, username, ...)."""
    user = None if x_telegram_init_data else await _session_user(request)
    if user is None:
        try:
            data = validate_init_data(x_telegram_init_data, BOT_TOKEN)
        except InitDataError as e:
            raise HTTPException(status_code=401, detail=str(e))
        user = data.get("user")
        if not user or "id" not in user:
            raise HTTPException(status_code=401, detail="нет данных пользователя в initData")

        from database import upsert_user
        # full_name — как у бота (aiogram User.full_name = "first last"), иначе каждый
        # заход в WebApp перетирал в users фамилию, записанную ботом.
        full_name = " ".join(p for p in (user.get("first_name", ""), user.get("last_name", "")) if p)
        await upsert_user(user["id"], user.get("username", ""), full_name)
    from optional_subjects import apply_for
    await apply_for(user["id"])   # пары предметов по выбору, на которые не ходит — скрыть
    import members                # своя группа — по чату группы в Telegram (members.py)
    await members.refresh_later(tg_bot() if BOT_TOKEN else None, user["id"])
    from database.groups import enter
    await enter(user["id"])       # его группа — для файлов, ДЗ, заметок, контекста ИИ (этап 1 (б))
    import stats                  # «кто, что, когда» для /stats старосты (без содержимого)
    await stats.track(user["id"], stats.kind_for(request.method, request.url.path))
    await stats.track(user["id"], stats.via(bool(x_telegram_init_data), request.headers.get("x-app", "")))
    return user


CurrentUser = Depends(get_current_user)


_tg_bot = None


def tg_bot():
    """Свой экземпляр Bot для отправки файлов из WebApp (тот же токен)."""
    global _tg_bot
    if _tg_bot is None:
        from aiogram import Bot
        import net
        _tg_bot = Bot(BOT_TOKEN, session=net.tg_session())
    return _tg_bot
