"""Расписание: снимки для диффов, запасная копия календаря, закреплённое в поиске."""

from database._conn import connect


# ── Диффы расписания ─────────────────────────────────────────────────────────

async def get_schedule_snapshot(date_str: str) -> list | None:
    async with connect() as db:
        cursor = await db.execute("SELECT events_json FROM schedule_snapshots WHERE date=?", (date_str,))
        row = await cursor.fetchone()
        if not row:
            return None
        import json
        return json.loads(row[0])


async def save_schedule_snapshot(date_str: str, events: list):
    import json
    async with connect() as db:
        await db.execute("""
            INSERT INTO schedule_snapshots (date, events_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(date) DO UPDATE SET
                events_json = excluded.events_json,
                updated_at  = excluded.updated_at
        """, (date_str, json.dumps(events, ensure_ascii=False)))
        await db.commit()


async def save_schedule_backup(data: bytes, saved_at: str):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO schedule_backup (id, data, saved_at) VALUES (1, ?, ?)",
                         (data, saved_at))
        await db.commit()


async def load_schedule_backup() -> tuple[bytes, str] | None:
    async with connect() as db:
        row = await (await db.execute("SELECT data, saved_at FROM schedule_backup WHERE id = 1")).fetchone()
        return (bytes(row[0]), row[1]) if row else None


# ── Закреплённое в поиске расписания (WebApp) ────────────────────────────────

MAX_PINS = 20


async def get_pins(user_id: int) -> list[dict]:
    async with connect() as db:
        cursor = await db.execute(
            "SELECT target_type, target_id, title FROM pinned_targets WHERE user_id=? ORDER BY created_at, rowid",
            (user_id,))
        return [{"type": t, "id": i, "title": title} for t, i, title in await cursor.fetchall()]


async def pin_target(user_id: int, target_type: int, target_id: int, title: str) -> bool:
    """False — уже MAX_PINS закреплённых (повторное закрепление — не ошибка)."""
    async with connect() as db:
        cursor = await db.execute(
            "SELECT COUNT(*), SUM(target_type=? AND target_id=?) FROM pinned_targets WHERE user_id=?",
            (target_type, target_id, user_id))
        count, exists = await cursor.fetchone()
        if not exists and count >= MAX_PINS:
            return False
        await db.execute(
            "INSERT OR REPLACE INTO pinned_targets (user_id, target_type, target_id, title) VALUES (?, ?, ?, ?)",
            (user_id, target_type, target_id, title))
        await db.commit()
        return True


async def unpin_target(user_id: int, target_type: int, target_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM pinned_targets WHERE user_id=? AND target_type=? AND target_id=?",
                         (user_id, target_type, target_id))
        await db.commit()


# ── Напоминания перед парой: что уже ушло ────────────────────────────────────

async def mark_lesson_reminder(user_id: int, day: str, at: str, minutes: int) -> bool:
    """Отметить «ушло»; True — только в первый раз. Отметка в базе переживает
    перезапуск бота (иначе после деплоя напоминание приходило дважды)."""
    async with connect() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO lesson_reminders_sent (user_id, day, at, minutes) VALUES (?, ?, ?, ?)",
            (user_id, day, at, minutes))
        await db.commit()
        return cur.rowcount == 1


async def purge_lesson_reminders(before: str):
    """Отметки за дни раньше before («ГГГГ-ММ-ДД») больше не нужны."""
    async with connect() as db:
        await db.execute("DELETE FROM lesson_reminders_sent WHERE day < ?", (before,))
        await db.commit()
