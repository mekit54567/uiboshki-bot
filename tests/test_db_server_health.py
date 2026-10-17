"""Amvera 16.10: «database is locked» в напоминаниях и ответы бота по минуте.
Подключение ждёт занятую базу дольше и в WAL не делает fsync на каждый commit;
/status показывает режим базы, её скорость и зависания бота."""

import asyncio
import time

import health


async def test_connect_waits_and_skips_fsync_in_wal(db):
    from database._conn import BUSY_SECONDS, connect
    async with connect() as c:
        assert (await (await c.execute("PRAGMA journal_mode")).fetchone())[0] == "wal"
        assert (await (await c.execute("PRAGMA busy_timeout")).fetchone())[0] == BUSY_SECONDS * 1000
        assert (await (await c.execute("PRAGMA synchronous")).fetchone())[0] == 1     # NORMAL


async def test_status_shows_db_and_loop_lag(db, monkeypatch):
    monkeypatch.setattr(health, "_LAGS", health.deque([(time.time(), 3.4), (time.time() - 7200, 99.0)]))
    text = await health.report()
    assert "База: wal, чтение" in text
    assert "Самое долгое зависание за час: 3.4 с" in text      # то, что старше часа, не в счёт


async def test_watch_loop_notices_blocked_loop(monkeypatch):
    monkeypatch.setattr(health, "_LAGS", health.deque(maxlen=10))
    task = asyncio.create_task(health.watch_loop(period=0.05))
    await asyncio.sleep(0.01)
    time.sleep(0.3)                     # кто-то занял цикл событий
    await asyncio.sleep(0.1)
    task.cancel()
    assert health.loop_lag() >= 0.2


async def test_status_shows_slow_requests(db, monkeypatch):
    now = time.time()
    monkeypatch.setattr(health, "_SLOW", health.deque(maxlen=10))
    health.note_request("/api/today", 0.4, now)                      # быстрый — не в счёт
    health.note_request("/api/sdo/grades", 52.3, now - 60)
    health.note_request("/api/sdo/grades", 12.0, now - 30)
    health.note_request("/api/chat", 31.0, now - 10)
    health.note_request("/api/files", 70.0, now - 7200)              # старше часа
    assert health.slow_requests(now) == (3, [("/api/sdo/grades", 52.3), ("/api/chat", 31.0)])
    text = await health.report()
    assert "Долгих запросов (от 5 с) за час: 3 — /api/sdo/grades 52 с, /api/chat 31 с" in text

    monkeypatch.setattr(health, "_SLOW", health.deque(maxlen=10))
    assert "Долгих запросов (от 5 с) за час нет" in await health.report()


def test_server_notes_api_requests_by_route(monkeypatch):
    from fastapi.testclient import TestClient
    from webapp import server
    seen = []
    monkeypatch.setattr(health, "note_request", lambda path, s, now=None: seen.append(path))
    TestClient(server.app).get("/api/v1/meta")
    TestClient(server.app).get("/health")
    assert seen == ["/api/meta"]                 # v1 → тот же путь, /health не API
