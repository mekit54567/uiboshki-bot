"""Подписки на веб-пуши (этап 2 (г), delivery.py): устройство = endpoint."""

import aiosqlite

from database._conn import connect

MAX_SUBS = 5


async def save_push_sub(user_id: int, endpoint: str, p256dh: str, auth: str, device: str = "",
                        session_id: int | None = None):
    async with connect() as db:
        await db.execute(
            "INSERT INTO push_subs (endpoint, user_id, p256dh, auth, device, session_id) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh, "
            "auth = excluded.auth, device = excluded.device, session_id = excluded.session_id",
            (endpoint, user_id, p256dh, auth, device[:120], session_id))
        # не больше MAX_SUBS устройств на человека — старые вытесняются (ревью безопасности 09.10:
        # сотни подписок на «висящий» адрес задерживали рассылку всем)
        await db.execute(
            "DELETE FROM push_subs WHERE user_id = ? AND endpoint NOT IN "
            "(SELECT endpoint FROM push_subs WHERE user_id = ? ORDER BY rowid DESC LIMIT ?)",
            (user_id, user_id, MAX_SUBS))
        await db.commit()


async def get_push_subs(user_id: int) -> list[dict]:
    """Подписки человека — только устройств с живой сессией (sessions.LIVE_SESSION_SQL)."""
    from database.sessions import LIVE_SESSION_SQL, live_now
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(f"SELECT * FROM push_subs WHERE user_id = ? AND {LIVE_SESSION_SQL}",
                                       (user_id, live_now()))).fetchall()
        return [dict(r) for r in rows]


async def delete_push_sub(endpoint: str, user_id: int | None = None) -> int:
    sql, args = "DELETE FROM push_subs WHERE endpoint = ?", [endpoint]
    if user_id is not None:
        sql, args = sql + " AND user_id = ?", args + [user_id]
    async with connect() as db:
        cur = await db.execute(sql, args)
        await db.commit()
        return cur.rowcount


async def delete_user_push_subs(user_id: int) -> int:
    """«Выйти везде» — и пуши со всех устройств."""
    async with connect() as db:
        cur = await db.execute("DELETE FROM push_subs WHERE user_id = ?", (user_id,))
        await db.commit()
        return cur.rowcount
