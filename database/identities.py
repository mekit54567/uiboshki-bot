"""Вход через VK ID / Яндекс ID (oauth.py): привязки «провайдер + id у
него → человек» и аккаунты без Telegram.

Человек без Telegram получает свой номер ниже LOCAL_BASE (отрицательный и
далеко от ключей ratelimit по IP, webapp/routes/site._client_key): с ним
работает всё, кроме сообщений в Telegram — рассылки идут ему пушами
(delivery.deliver)."""

import secrets
from datetime import datetime, timedelta, UTC

import aiosqlite

from database._conn import connect

LOCAL_BASE = -10_000_000_000
STATE_TTL = timedelta(minutes=10)


def is_local(user_id: int) -> bool:
    """Аккаунт без Telegram (вошёл через VK/Яндекс)."""
    return user_id <= LOCAL_BASE


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _now() -> datetime:
    return datetime.now(UTC)


async def new_state(provider: str, verifier: str, code: str, client: str, link_user: int | None) -> str:
    state = secrets.token_urlsafe(24)
    async with connect() as db:
        await db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (_ts(_now()),))
        await db.execute("INSERT INTO oauth_states (state, provider, verifier, code, client, link_user, expires_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (state, provider, verifier, code, client, link_user, _ts(_now() + STATE_TTL)))
        await db.commit()
    return state


async def take_state(state: str) -> dict | None:
    """Начатый вход по state — один раз (повтор колбэка не пройдёт)."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM oauth_states WHERE state = ? AND expires_at >= ?",
                                      (state, _ts(_now())))).fetchone()
        if row:
            await db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            await db.commit()
        return dict(row) if row else None


async def find_user(provider: str, subject: str) -> int | None:
    async with connect() as db:
        row = await (await db.execute("SELECT user_id FROM identities WHERE provider = ? AND subject = ?",
                                      (provider, subject))).fetchone()
        return row[0] if row else None


async def link(provider: str, subject: str, user_id: int, name: str = ""):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO identities (provider, subject, user_id, name) VALUES (?, ?, ?, ?)",
                         (provider, subject, user_id, name))
        await db.commit()


async def list_for(user_id: int) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT provider, name, created_at FROM identities WHERE user_id = ? "
                                       "ORDER BY created_at", (user_id,))).fetchall()
        return [dict(r) for r in rows]


async def unlink(user_id: int, provider: str) -> bool:
    async with connect() as db:
        cur = await db.execute("DELETE FROM identities WHERE user_id = ? AND provider = ?", (user_id, provider))
        await db.commit()
        return cur.rowcount > 0


async def new_local_user(name: str) -> int:
    """Новый человек без Telegram: следующий свободный номер ниже LOCAL_BASE
    (под замком — два входа сразу не получат один номер)."""
    from kapibara.core import locks
    async with locks.lock("local_user"), connect() as db:
        row = await (await db.execute("SELECT MIN(user_id) FROM users WHERE user_id <= ?", (LOCAL_BASE,))).fetchone()
        uid = (row[0] - 1) if row and row[0] is not None else LOCAL_BASE
        await db.execute("INSERT INTO users (user_id, username, full_name) VALUES (?, '', ?)", (uid, name))
        await db.commit()
    return uid
