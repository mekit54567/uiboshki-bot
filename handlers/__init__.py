from aiogram import Dispatcher
from .start     import router as start_router
from .schedule  import router as schedule_router
from .deadlines import router as deadline_router
from .solver    import router as solver_router


def register_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_router(schedule_router)
    dp.include_router(deadline_router)
    dp.include_router(solver_router)
