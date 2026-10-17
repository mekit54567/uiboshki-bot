"""Amvera 16.10: запись в базу ~0,2 с (/status «Сервер»), а каждый запрос
WebApp писал users и events. Теперь события — пачкой, users — не чаще раза
в 10 минут с теми же именем и ником."""

import asyncio

import pytest


async def _count(db, sql, *args):
    from database._conn import connect
    async with connect() as c:
        return (await (await c.execute(sql, args)).fetchone())[0]


async def test_events_are_written_in_one_batch(db, monkeypatch):
    import database.service as svc
    monkeypatch.setattr(svc, "EVENT_FLUSH_SECONDS", 0.05)
    for kind in ("open", "files", "chat"):
        await svc.add_event(1, kind)
    assert await _count(db, "SELECT COUNT(*) FROM events") == 0      # ещё копятся
    await asyncio.sleep(0.15)
    assert await _count(db, "SELECT COUNT(*) FROM events") == 3


async def test_stats_read_sees_pending_events(db, monkeypatch):
    import database.service as svc
    monkeypatch.setattr(svc, "EVENT_FLUSH_SECONDS", 60)
    await svc.add_event(2, "open")
    assert [r[:2] for r in await svc.events_since(1)] == [(2, "open")]


async def test_erase_drops_pending_events(db, monkeypatch):
    import database.service as svc
    import privacy
    monkeypatch.setattr(svc, "EVENT_FLUSH_SECONDS", 60)
    await db.upsert_user(3, "x", "X")
    await svc.add_event(3, "open")
    await svc.add_event(4, "open")
    await privacy.erase(3)
    await svc.flush_events()
    assert await _count(db, "SELECT COUNT(*) FROM events WHERE user_id=3") == 0
    assert await _count(db, "SELECT COUNT(*) FROM events WHERE user_id=4") == 1


@pytest.fixture
def throttled(monkeypatch):
    import database.users as users
    monkeypatch.setattr(users, "UPSERT_EVERY", 600)
    users.forget_user()
    yield
    users.forget_user()


async def test_upsert_user_skips_repeat_but_not_new_name(db, throttled):
    from database._conn import connect
    await db.upsert_user(5, "nick", "Имя")
    async with connect() as c:
        await c.execute("UPDATE users SET last_seen='2000-01-01' WHERE user_id=5")
        await c.commit()
    await db.upsert_user(5, "nick", "Имя")              # то же самое — в базу не идём
    assert await _count(db, "SELECT last_seen FROM users WHERE user_id=5") == "2000-01-01"
    await db.upsert_user(5, "nick2", "Имя")             # сменил ник — пишем
    assert await _count(db, "SELECT username FROM users WHERE user_id=5") == "nick2"


async def test_upsert_user_after_erase_writes_again(db, throttled):
    import privacy
    await db.upsert_user(6, "n", "N")
    await privacy.erase(6)
    await db.upsert_user(6, "n", "N")
    assert await _count(db, "SELECT COUNT(*) FROM users WHERE user_id=6") == 1


async def test_seen_marks_do_not_wait_for_busy_db(db, monkeypatch):
    # после перезапуска почти каждый запрос писал «заходил» (сессия, users,
    # last_seen) и ждал замок базы до 15 с, пока писал кто-то другой:
    # дедлайны, ДЗ, «СДО» по 30–35 с (Никита 17.10, /status). Теперь — в фоне.
    import time

    import aiosqlite

    import database
    import database._conn as conn
    import database.sessions as sessions
    import privacy
    monkeypatch.setattr(conn, "WAIT", False)
    monkeypatch.setattr(privacy, "_seen", {})
    await db.upsert_user(5, "u", "U")
    token = await sessions.create_session(5, "test")
    async with conn.connect() as c:                     # сессия «давно не продлевалась»
        await c.execute("UPDATE sessions SET last_seen = '2000-01-01 00:00:00'")
        await c.commit()

    busy = await aiosqlite.connect(database.DATABASE_PATH)
    await busy.execute("BEGIN IMMEDIATE")               # кто-то держит запись
    monkeypatch.setattr(conn, "BUSY_SECONDS", 5)
    t = time.monotonic()
    assert await sessions.session_user(token) == 5
    await db.upsert_user(5, "u2", "U2", wait=False)
    await privacy.seen(5)
    assert time.monotonic() - t < 1                     # никто не ждал замок
    await busy.rollback()
    await busy.close()
    await asyncio.gather(*list(conn._background))
    assert (await db.get_user(5))["username"] == "u2"
    assert await _count(db, "SELECT COUNT(*) FROM sessions WHERE last_seen > '2001'") == 1


async def test_new_user_upsert_is_written_at_once(db, monkeypatch):
    # нового в базе ещё нет — его строку запрос читает дальше: пишем сразу
    import database._conn as conn
    monkeypatch.setattr(conn, "WAIT", False)
    await db.upsert_user(6, "n", "N", wait=False)
    assert (await db.get_user(6))["username"] == "n"
