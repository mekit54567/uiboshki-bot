"""kapibara.core.tasks.spawn: фоновая задача не теряется и её ошибка — в логе (RUF006)."""
import asyncio
import logging

from kapibara.core import tasks


async def test_spawn_keeps_task_and_logs_error(caplog):
    done = asyncio.Event()

    async def ok():
        done.set()

    async def boom():
        raise RuntimeError("упало")

    t = tasks.spawn(ok(), name="ok")
    assert t in tasks._running          # ссылка держится, пока задача идёт
    await done.wait()
    await asyncio.sleep(0)
    assert t not in tasks._running
    with caplog.at_level(logging.ERROR, logger="kapibara.core.tasks"):
        b = tasks.spawn(boom(), name="boom")
        await asyncio.gather(b, return_exceptions=True)
        await asyncio.sleep(0)
    assert "boom" in caplog.text and "упало" in caplog.text
