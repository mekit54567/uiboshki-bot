from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .start    import router as start_router
from .privacy  import router as privacy_router
from .group_pick import router as group_router
from .members_chat import router as members_chat_router
from .schedule import router as schedule_router
from .deadlines import router as deadline_router
from .files    import router as files_router
from .social   import router as social_router
from .weather  import router as weather_router
from .announce import router as announce_router
from .feed     import router as feed_router
from .inline   import router as inline_router
from .channel  import router as channel_router
from .rating   import router as rating_router
from .solver   import router as solver_router  # всегда последним

# Общий /cancel для любого диалога — первым роутером. Раньше /cancel был не
# во всех сценариях (/add, /addhw, /upload…), и там он становился вводом:
# предметом дедлайна, текстом ДЗ. Само состояние к этому моменту уже сбросил
# MenuInterruptMiddleware (любая команда прерывает диалог) — здесь только ответ.
cancel_router = Router(name="cancel")


@cancel_router.message(Command("cancel"))
async def cmd_cancel_any(message: Message, state: FSMContext, interrupted_fsm_state: str | None = None):
    current = interrupted_fsm_state or await state.get_state()
    await state.clear()
    from keyboards import MAIN_KB
    await message.answer("Отменил." if current else "Отменять нечего.", reply_markup=MAIN_KB)


async def _anonymize_feed_on_startup():
    """Старые посты «Подслушано» — с хэшем вместо id автора (database/social.py)."""
    import logging
    from database.social import anonymize_feed_authors
    try:
        await anonymize_feed_authors()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Подслушано: старые авторы не обезличены: {e!r}")


async def _ensure_home_group():
    """Своя группа (ICAL_URL) — в справочнике групп (groups.py)."""
    import groups
    await groups.ensure_home()


def register_handlers(dp: Dispatcher):
    dp.include_router(cancel_router)
    dp.include_router(privacy_router)
    dp.include_router(start_router)
    dp.include_router(group_router)
    dp.include_router(members_chat_router)
    dp.include_router(schedule_router)
    dp.include_router(deadline_router)
    dp.include_router(files_router)
    dp.include_router(social_router)
    dp.include_router(weather_router)
    dp.include_router(announce_router)
    dp.include_router(feed_router)
    dp.include_router(inline_router)
    dp.include_router(channel_router)
    dp.include_router(rating_router)
    dp.include_router(solver_router)
    dp.startup.register(_anonymize_feed_on_startup)
    dp.startup.register(_ensure_home_group)
