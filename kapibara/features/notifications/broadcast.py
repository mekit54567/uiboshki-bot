"""Общее для рассылок (утро, пары, вечер, обзор недели, награды групп):
календари групп по разу на рассылку и пауза между сообщениями. Переехало из
kapibara/jobs/scheduler.py (03.11): дайджесты брали это из планировщика, и
импорт снизу вверх сцеплял модули в клубок."""
import asyncio
import logging

from kapibara.core.errors import aside

logger = logging.getLogger("kapibara.jobs.scheduler")   # в /status — раздел «Расписание», как было

PACE_SECONDS = 0.05


async def pace():
    """Пауза между сообщениями рассылки: Telegram пускает ~30 в секунду, а
    групп и людей станет много (этап 1 (г))."""
    await asyncio.sleep(PACE_SECONDS)


async def group_raws(fetch_home):
    """Календари групп для рассылки: {группа: (raw, свой корпус)} — каждый
    качается один раз на рассылку; своя группа — прежним вызовом (с кэшем и
    запасной копией), чужие — через общий кэш календарей МИРЭА."""
    from kapibara.features.notifications import prefs as notify_prefs
    cache: dict = {}

    async def get(gid):
        from kapibara.features.groups import groups
        key = None if not gid or gid == groups.home_id() else gid
        if key not in cache:
            from kapibara.features.schedule import parser as schedule_parser
            cache[key] = (None, None)          # не загрузилось — этой группе рассылки нет, остальным есть
            with aside(logger, f"Рассылка: расписание группы {key or 'своей'} не загрузилось",
                       expected=schedule_parser.FETCH_ERRORS, level=logging.ERROR):
                raw = await (fetch_home() if key is None else schedule_parser.fetch_schedule_raw(group_id=key))
                cache[key] = (raw, notify_prefs.home_campus(raw))
        return cache[key]
    return get
