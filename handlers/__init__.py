from aiogram import Dispatcher
from .start    import router as start_router
from .schedule import router as schedule_router
from .deadlines import router as deadline_router
from .files    import router as files_router
from .social   import router as social_router
from .weather  import router as weather_router
from .announce import router as announce_router
from .solver   import router as solver_router  # всегда последним


def register_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_router(schedule_router)
    dp.include_router(deadline_router)
    dp.include_router(files_router)
    dp.include_router(social_router)
    dp.include_router(weather_router)
    dp.include_router(announce_router)
    dp.include_router(solver_router)
