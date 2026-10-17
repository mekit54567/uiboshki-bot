"""Служебное: история решалки, очистка семестра, события для /stats."""

import aiosqlite

import database
from database._conn import connect


# ── Solver history ────────────────────────────────────────────────────────────

async def add_solver_history(user_id: int, task: str, answer: str, subject: str = ""):
    async with connect() as db:
        await db.execute("""
            INSERT INTO solver_history (user_id, task_text, answer, subject)
            VALUES (?, ?, ?, ?)
        """, (user_id, task[:500], answer[:2000], subject))
        await db.commit()


async def get_solver_history(user_id: int, limit=5) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM solver_history WHERE user_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit))
        return [dict(r) for r in await cursor.fetchall()]


# ── Очистка семестра (для /clearsem) ────────────────────────────────────────
# Сносит "живые" данные конкретного семестра — дедлайны, доску ДЗ, файлы,
# голосования. НЕ трогает: подписки/настройки пользователей, историю решений
# решалки, заметки на пары, ленту "Подслушано", zam_id в settings —
# это либо личные настройки, либо архив, который не привязан к семестру.
async def clear_semester_data():
    async with connect() as db:
        # file_text — вместе с files: иначе извлечённый текст всех лекций
        # семестра навсегда остаётся в базе сиротами (см. delete_file).
        for table in ("deadlines", "deadline_done", "deadline_reminders", "deadlines_skipped", "homework", "files",
                      "file_text", "file_summaries", "vote_answers", "votes"):
            try:
                await db.execute(f"DELETE FROM {table}")
            except Exception:
                pass  # таблицы homework/votes создаются лениво — их может не быть
        await db.commit()


# События /stats — пачкой раз в EVENT_FLUSH_SECONDS, а не commit на каждый
# запрос (Amvera 16.10: запись ~0,2 с, Mini App при открытии шлёт несколько
# запросов — записи вставали в очередь). Падение процесса теряет события за
# эти секунды — для статистики не страшно. 0 — сразу (так в тестах).
EVENT_FLUSH_SECONDS = 10.0
_pending: dict[str, list[tuple[int, str, str]]] = {}     # путь базы → (кто, что, когда)
_flusher = None


async def add_event(user_id: int, kind: str):
    import asyncio
    from datetime import datetime, timezone
    at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")      # как datetime('now')
    _pending.setdefault(database.DATABASE_PATH, []).append((user_id, kind, at))
    if EVENT_FLUSH_SECONDS <= 0:
        await flush_events()
        return
    global _flusher
    if _flusher is None or _flusher.done() or _flusher.get_loop() is not asyncio.get_running_loop():
        _flusher = asyncio.create_task(_flush_later())


async def _flush_later():
    import asyncio
    import logging
    await asyncio.sleep(EVENT_FLUSH_SECONDS)
    try:
        await flush_events()
    except Exception as e:
        logging.getLogger(__name__).info(f"stats: события не записались: {e}")


async def flush_events():
    """Записать накопленные события текущей базы."""
    rows = _pending.pop(database.DATABASE_PATH, [])
    if not rows:
        return
    async with connect() as db:
        await db.executemany("INSERT INTO events (user_id, kind, at) VALUES (?, ?, ?)", rows)
        await db.commit()


def drop_events(user_id: int):
    """Удаление данных человека: его ещё не записанные события — тоже прочь."""
    for path, rows in _pending.items():
        _pending[path] = [r for r in rows if r[0] != user_id]


async def events_since(days: int) -> list[tuple[int, str, str]]:
    await flush_events()
    async with connect() as db:
        cursor = await db.execute(
            "SELECT user_id, kind, at FROM events WHERE at >= datetime('now', ?)", (f"-{int(days)} days",))
        return await cursor.fetchall()


async def purge_events(keep_days: int = 180):
    async with connect() as db:
        await db.execute("DELETE FROM events WHERE at < datetime('now', ?)", (f"-{int(keep_days)} days",))
        await db.commit()


async def get_solver_rating(limit: int = 10) -> list[dict]:
    """Рейтинг активности (/rating): кто больше всех решал задачи через бота."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        # Считаем по solver_history
        cur = await db.execute("""
            SELECT u.full_name, u.username, COUNT(s.id) as cnt
            FROM solver_history s
            JOIN users u ON u.user_id = s.user_id
            GROUP BY s.user_id
            ORDER BY cnt DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in await cur.fetchall()]
