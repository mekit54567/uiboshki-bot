"""Дедлайны: общие и личные, «сделано» у каждого своё, свои напоминания."""

import aiosqlite

from config import STAROSTA_ID, STAROSTA_IDS
from utils import today_msk
from database._conn import connect


# ── Deadlines ─────────────────────────────────────────────────────────────────

async def add_deadline(subject, description, due_date, due_time, created_by, external_id=None,
                       personal: bool = False) -> int:
    """personal — только автору, даже если автор — староста (иначе дедлайн
    старосты общий для группы: «Сходить к врачу» из WebApp видели все)."""
    async with connect() as db:
        cursor = await db.execute("""
            INSERT INTO deadlines (subject, description, due_date, due_time, created_by, external_id, personal)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (subject, description, due_date, due_time, created_by, external_id, 1 if personal else 0))
        await db.commit()
        return cursor.lastrowid


async def edit_deadline(did: int, subject: str, description: str, due_date: str, due_time: str | None):
    """Ручная правка (WebApp): помечает manual_edit, чтобы автосинк СДО не
    вернул старое название/срок при следующем проходе."""
    async with connect() as db:
        await db.execute(
            "UPDATE deadlines SET subject=?, description=?, due_date=?, due_time=?, manual_edit=1 WHERE id=?",
            (subject, description, due_date, due_time, did),
        )
        await db.commit()


async def update_deadline_due(did: int, subject: str, due_date: str, due_time: str | None):
    """Новый срок или название (синк СДО). Свои напоминания, которые ещё не
    пришли, едут вместе со сроком: «за день» до старого срока после переноса
    пришло бы мимо."""
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M"
    async with connect() as db:
        old = await (await db.execute("SELECT due_date, due_time FROM deadlines WHERE id=?", (did,))).fetchone()
        await db.execute(
            "UPDATE deadlines SET subject=?, due_date=?, due_time=? WHERE id=?",
            (subject, due_date, due_time, did)
        )
        try:
            shift = (datetime.strptime(f"{due_date} {(due_time or '23:59')[:5]}", fmt)
                     - datetime.strptime(f"{old[0]} {(old[1] or '23:59')[:5]}", fmt)) if old else None
        except (TypeError, ValueError):
            shift = None
        if shift:
            rows = await (await db.execute(
                "SELECT user_id, remind_at FROM deadline_reminders WHERE deadline_id=? AND sent=0", (did,))).fetchall()
            for uid, at in rows:
                try:
                    new_at = (datetime.strptime(at, fmt) + shift).strftime(fmt)
                except ValueError:
                    continue
                await db.execute("UPDATE OR IGNORE deadline_reminders SET remind_at=? "
                                 "WHERE user_id=? AND deadline_id=? AND remind_at=?", (new_at, uid, did, at))
        await db.commit()


async def is_deadline_skipped(external_id: str) -> bool:
    async with connect() as db:
        return (await (await db.execute("SELECT 1 FROM deadlines_skipped WHERE external_id=?",
                                        (external_id,))).fetchone()) is not None


async def get_deadline_by_external_id(external_id: str) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE external_id=?", (external_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# Дедлайн считается "общим" (видят все), если его добавил/утвердил староста,
# либо это автосинк из СДО (created_by=0) — всё остальное видит только автор.
_DEADLINE_COLS = ("d.id, d.subject, d.description, d.due_date, d.due_time, d.created_by, d.created_at, "
                  "d.external_id, d.manual_edit, d.personal")


def _shared_in() -> tuple[str, tuple]:
    """«created_by IN (0, старосты…)» — общие дедлайны: от СДО (0) и от любого
    аккаунта старосты (STAROSTA_ID через запятую)."""
    ids = tuple(STAROSTA_IDS)
    return "(0" + ", ?" * len(ids) + ")", ids


def is_shared_deadline(d: dict) -> bool:
    return d.get("created_by") in (0, *STAROSTA_IDS) and not d.get("personal")


async def get_active_deadlines(viewer_id: int, include_done: bool = False) -> list[dict]:
    """Дедлайны, видимые viewer_id: общие (старосты/СДО) + свои личные.
    "done" в каждой записи — персональный статус именно viewer_id, не общий."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        query = f"""
            SELECT {_DEADLINE_COLS},
                   EXISTS(
                       SELECT 1 FROM deadline_done dd
                       WHERE dd.deadline_id = d.id AND dd.user_id = ?
                   ) AS done
            FROM deadlines d
            WHERE (d.created_by = ? OR (d.created_by IN {_shared_in()[0]} AND COALESCE(d.personal, 0) = 0))
        """
        params = [viewer_id, viewer_id, *_shared_in()[1]]
        if not include_done:
            query += """
                AND NOT EXISTS (
                    SELECT 1 FROM deadline_done dd2
                    WHERE dd2.deadline_id = d.id AND dd2.user_id = ?
                )
            """
            params.append(viewer_id)
        query += " ORDER BY d.due_date, d.due_time"
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


async def get_deadlines_soon(days=3, viewer_id: int | None = None, shared_only: bool = False) -> list[dict]:
    """shared_only=True — для группового поста (модерация старостой): только
    общие дедлайны, не выполненные старостой. Иначе — персональная подборка
    для viewer_id (общие + его личные, не отмеченные им самим).

    "Сегодня" — по Москве, передаётся параметром, а не date('now'): в SQLite
    это дата по UTC, и в рассылке после полуночи МСК вчерашние дедлайны ещё
    считались бы "сегодняшними"."""
    today = today_msk().isoformat()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if shared_only:
            query = f"""
                SELECT {_DEADLINE_COLS} FROM deadlines d
                WHERE (d.created_by IN {_shared_in()[0]} AND COALESCE(d.personal, 0) = 0)
                AND d.due_date BETWEEN ? AND date(?, ? || ' days')
                AND NOT EXISTS (SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)
                ORDER BY d.due_date, d.due_time
            """
            params = (*_shared_in()[1], today, today, str(days), STAROSTA_ID)
        else:
            if viewer_id is None:
                raise ValueError("viewer_id обязателен при shared_only=False")
            query = f"""
                SELECT {_DEADLINE_COLS} FROM deadlines d
                WHERE (d.created_by = ? OR (d.created_by IN {_shared_in()[0]} AND COALESCE(d.personal, 0) = 0))
                AND d.due_date BETWEEN ? AND date(?, ? || ' days')
                AND NOT EXISTS (SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)
                ORDER BY d.due_date, d.due_time
            """
            params = (viewer_id, *_shared_in()[1], today, today, str(days), viewer_id)
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]


async def get_deadline_stats(viewer_id: int) -> dict:
    """Статистика по дедлайнам, видимым viewer_id, с учётом его личного done.
    Просрочено/активно — относительно сегодняшней даты по Москве (см.
    get_deadlines_soon)."""
    today = today_msk().isoformat()
    async with connect() as db:
        visible = f"(d.created_by = ? OR (d.created_by IN {_shared_in()[0]} AND COALESCE(d.personal, 0) = 0))"
        vparams = (viewer_id, *_shared_in()[1])
        done_expr = "EXISTS(SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)"

        total = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible}", vparams
        )).fetchone())[0]
        done = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND {done_expr}",
            vparams + (viewer_id,)
        )).fetchone())[0]
        overdue = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND d.due_date < ? AND NOT {done_expr}",
            vparams + (today, viewer_id)
        )).fetchone())[0]
        active = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND d.due_date >= ? AND NOT {done_expr}",
            vparams + (today, viewer_id)
        )).fetchone())[0]
        return {"total": total, "done": done, "overdue": overdue, "active": active}


async def mark_deadline_done(did: int, user_id: int):
    async with connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO deadline_done (deadline_id, user_id) VALUES (?, ?)",
            (did, user_id)
        )
        await db.commit()


async def unmark_deadline_done(did: int, user_id: int):
    async with connect() as db:
        await db.execute(
            "DELETE FROM deadline_done WHERE deadline_id=? AND user_id=?", (did, user_id)
        )
        await db.commit()


async def set_deadline_done(did: int, user_id: int, done: bool):
    """Персональная отметка "выполнено" — у каждого своя, не влияет на других
    (ни в боте через /done, ни в WebApp через чекбокс)."""
    if done:
        await mark_deadline_done(did, user_id)
    else:
        await unmark_deadline_done(did, user_id)


async def is_deadline_done(did: int, user_id: int) -> bool:
    async with connect() as db:
        cursor = await db.execute(
            "SELECT 1 FROM deadline_done WHERE deadline_id=? AND user_id=?", (did, user_id)
        )
        return (await cursor.fetchone()) is not None


async def get_deadline(did: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE id=?", (did,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_sdo_deadlines() -> list[dict]:
    """Все дедлайны, пришедшие из СДО (для /sdoclean)."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM deadlines WHERE external_id LIKE 'sdo:%' ORDER BY due_date, due_time")
        return [dict(r) for r in await cursor.fetchall()]


async def delete_deadline(did: int, remember: bool = True):
    """Удалить дедлайн с отметками и напоминаниями. Дедлайн из СДО запоминаем
    в deadlines_skipped — иначе следующий синк вернул бы его заново
    (remember=False — пропал из самого СДО: вернётся там — вернётся и тут)."""
    async with connect() as db:
        row = await (await db.execute("SELECT external_id FROM deadlines WHERE id=?", (did,))).fetchone()
        if remember and row and (row[0] or "").startswith("sdo:"):
            await db.execute("INSERT OR IGNORE INTO deadlines_skipped (external_id) VALUES (?)", (row[0],))
        await db.execute("DELETE FROM deadline_done WHERE deadline_id=?", (did,))
        await db.execute("DELETE FROM deadline_reminders WHERE deadline_id=?", (did,))
        await db.execute("DELETE FROM deadlines WHERE id=?", (did,))
        await db.commit()


async def add_deadline_reminder(user_id: int, deadline_id: int, remind_at: str):
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO deadline_reminders (user_id, deadline_id, remind_at) VALUES (?, ?, ?)",
                         (user_id, deadline_id, remind_at))
        await db.commit()


async def delete_deadline_reminder(user_id: int, deadline_id: int, remind_at: str):
    async with connect() as db:
        await db.execute("DELETE FROM deadline_reminders WHERE user_id=? AND deadline_id=? AND remind_at=?",
                         (user_id, deadline_id, remind_at))
        await db.commit()


async def get_user_deadline_reminders(user_id: int) -> dict[int, list[str]]:
    """Будущие (ещё не пришедшие) напоминания человека: дедлайн → времена."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT deadline_id, remind_at FROM deadline_reminders WHERE user_id=? AND sent=0 ORDER BY remind_at",
            (user_id,))).fetchall()
    out: dict[int, list[str]] = {}
    for did, at in rows:
        out.setdefault(did, []).append(at)
    return out


async def due_deadline_reminders(now: str) -> list[dict]:
    """Напоминания, время которых пришло: с дедлайном и отметкой «сделал»."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("""
            SELECT r.user_id, r.deadline_id, r.remind_at, d.subject, d.description, d.due_date, d.due_time,
                   EXISTS(SELECT 1 FROM deadline_done x WHERE x.deadline_id = r.deadline_id AND x.user_id = r.user_id) AS done
            FROM deadline_reminders r JOIN deadlines d ON d.id = r.deadline_id
            WHERE r.sent = 0 AND r.remind_at <= ?
        """, (now,))).fetchall()
        return [dict(r) for r in rows]


async def mark_deadline_reminder_sent(user_id: int, deadline_id: int, remind_at: str):
    async with connect() as db:
        await db.execute("UPDATE deadline_reminders SET sent=1 WHERE user_id=? AND deadline_id=? AND remind_at=?",
                         (user_id, deadline_id, remind_at))
        # старше месяца — не нужны
        await db.execute("DELETE FROM deadline_reminders WHERE sent=1 AND remind_at < datetime('now', '-30 days')")
        # дедлайна уже нет (удалили, /clearsem) — такие никогда не придут
        await db.execute("DELETE FROM deadline_reminders WHERE deadline_id NOT IN (SELECT id FROM deadlines)")
        await db.commit()
