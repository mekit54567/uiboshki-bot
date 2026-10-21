"""Пуши своего приложения (app_push.py): устройство = токен сервиса доставки
(fcm — Google, rustore — RuStore, apns — Apple) и его ключ AES-256. Ключ в
базе только зашифрованным (Fernet, как входы СДО — sdo_accounts.encrypt)."""

import aiosqlite

from database._conn import connect

MAX_DEVICES = 5
PLATFORMS = ("fcm", "rustore", "apns")


async def save_app_push(user_id: int, platform: str, token: str, key_enc: str, device: str = "",
                        session_id: int | None = None):
    """Новое устройство или новый ключ/владелец у старого токена (вышел и вошёл
    другим аккаунтом — токен тот же, человек другой)."""
    async with connect() as db:
        await db.execute(
            "INSERT INTO app_push (user_id, platform, token, key_enc, device, session_id) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(platform, token) DO UPDATE SET user_id = excluded.user_id, "
            "key_enc = excluded.key_enc, device = excluded.device, session_id = excluded.session_id, "
            "created_at = datetime('now')",
            (user_id, platform, token, key_enc, device[:120], session_id))
        # не больше MAX_DEVICES на человека — старые вытесняются (как push_subs)
        await db.execute(
            "DELETE FROM app_push WHERE user_id = ? AND id NOT IN "
            "(SELECT id FROM app_push WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?)",
            (user_id, user_id, MAX_DEVICES))
        await db.commit()


async def get_app_pushes(user_id: int) -> list[dict]:
    """Устройства человека — только с живой сессией (sessions.LIVE_SESSION_SQL)."""
    from database.sessions import LIVE_SESSION_SQL, live_now
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(f"SELECT * FROM app_push WHERE user_id = ? AND {LIVE_SESSION_SQL} ORDER BY id",
                                       (user_id, live_now()))).fetchall()
        return [dict(r) for r in rows]


async def all_app_pushes() -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM app_push")).fetchall()]


async def update_app_push_key(row_id: int, key_enc: str, only_if: str) -> bool:
    async with connect() as db:
        cur = await db.execute("UPDATE app_push SET key_enc = ? WHERE id = ? AND key_enc = ?",
                               (key_enc, row_id, only_if))
        await db.commit()
        return cur.rowcount > 0


async def delete_app_push(platform: str, token: str, user_id: int | None = None) -> int:
    sql, args = "DELETE FROM app_push WHERE platform = ? AND token = ?", [platform, token]
    if user_id is not None:
        sql, args = sql + " AND user_id = ?", args + [user_id]
    async with connect() as db:
        cur = await db.execute(sql, args)
        await db.commit()
        return cur.rowcount


async def delete_user_app_pushes(user_id: int) -> int:
    """«Выйти везде» — и пуши приложения со всех телефонов."""
    async with connect() as db:
        cur = await db.execute("DELETE FROM app_push WHERE user_id = ?", (user_id,))
        await db.commit()
        return cur.rowcount
