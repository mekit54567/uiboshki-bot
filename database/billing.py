"""Подписка «Капибара+»: оплаты, срок подписки, бонусы, приглашения (billing.py,
referrals.py). Оплаты не стираются «удалить мои данные» — только payer_id
(налоговый учёт); приглашение стирается вместе с любым из двоих
(database/privacy.erase_user)."""

import secrets

import aiosqlite

from database._conn import connect


# ── Оплаты ───────────────────────────────────────────────────────────────────

async def add_payment(pid: str, provider: str, payer_id: int, plan: str, amount: int, days: int):
    async with connect() as db:
        await db.execute(
            "INSERT INTO payments (id, provider, payer_id, plan, amount, days) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, provider, payer_id, plan, amount, days))
        await db.commit()


async def get_payment(pid: str) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM payments WHERE id = ?", (pid,))).fetchone()
        return dict(row) if row else None


async def set_payment_id(old: str, new: str):
    """Касса дала свой номер платежа после создания (ЮKassa) — пишем его."""
    async with connect() as db:
        await db.execute("UPDATE payments SET id = ? WHERE id = ?", (new, old))
        await db.commit()


async def mark_paid(pid: str) -> bool:
    """pending → succeeded. True — только в первый раз (касса шлёт
    уведомление повторно, подписка не должна продлиться дважды)."""
    async with connect() as db:
        cur = await db.execute(
            "UPDATE payments SET status = 'succeeded', paid_at = datetime('now') "
            "WHERE id = ? AND status = 'pending'", (pid,))
        await db.commit()
        return cur.rowcount == 1


async def mark_payment(pid: str, status: str):
    async with connect() as db:
        await db.execute("UPDATE payments SET status = ? WHERE id = ? AND status = 'pending'", (status, pid))
        await db.commit()


async def user_payments(user_id: int, limit: int = 20) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, plan, amount, days, status, created_at, paid_at FROM payments "
            "WHERE payer_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))).fetchall()
        return [dict(r) for r in rows]


# ── Срок подписки ────────────────────────────────────────────────────────────

async def get_sub(user_id: int) -> dict | None:
    """{until, source, founder} или None."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT until, source, COALESCE(founder, 0) AS founder FROM subscriptions WHERE user_id = ?",
            (user_id,))).fetchone()
        return dict(row) if row else None


async def put_sub(user_id: int, until: str, source: str, founder: bool | None = None):
    """Записать срок; founder=None — отметку «Основатель» не трогать."""
    async with connect() as db:
        await db.execute(
            "INSERT INTO subscriptions (user_id, until, source, founder) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until, source = excluded.source"
            + (", founder = excluded.founder" if founder is not None else ""),
            (user_id, until, source, int(bool(founder))))
        await db.commit()


async def set_founder(user_id: int, founder: bool):
    async with connect() as db:
        await db.execute("UPDATE subscriptions SET founder = ? WHERE user_id = ?", (int(founder), user_id))
        await db.commit()


# ── Бонусы ───────────────────────────────────────────────────────────────────

async def add_bonus(user_id: int, kind: str, key: str, days: int) -> bool:
    """Записать бонус. False — такой уже был (по разу на kind+key)."""
    async with connect() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO bonuses (user_id, kind, key, days) VALUES (?, ?, ?, ?)",
            (user_id, kind, key, days))
        await db.commit()
        return cur.rowcount == 1


async def get_bonuses(user_id: int) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT kind, key, days, at FROM bonuses WHERE user_id = ? ORDER BY at", (user_id,))).fetchall()
        return [dict(r) for r in rows]


async def count_bonuses(user_id: int, kind: str, days_back: int) -> int:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM bonuses WHERE user_id = ? AND kind = ? AND at >= datetime('now', ?)",
            (user_id, kind, f"-{int(days_back)} days"))).fetchone()
        return row[0]


# ── Приглашения ──────────────────────────────────────────────────────────────

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"     # без 0/o, 1/l/i — код читают с экрана


async def ref_code(user_id: int) -> str:
    """Свой код приглашения (t.me/<бот>?start=ref_<код>) — один навсегда."""
    async with connect() as db:
        row = await (await db.execute("SELECT code FROM ref_codes WHERE user_id = ?", (user_id,))).fetchone()
        if row:
            return row[0]
        while True:
            code = "".join(secrets.choice(_ALPHABET) for _ in range(7))
            cur = await db.execute("INSERT OR IGNORE INTO ref_codes (user_id, code) VALUES (?, ?)", (user_id, code))
            if cur.rowcount == 1:
                await db.commit()
                return code


async def user_by_ref(code: str) -> int | None:
    async with connect() as db:
        row = await (await db.execute("SELECT user_id FROM ref_codes WHERE code = ?", (code.lower(),))).fetchone()
        return row[0] if row else None


async def add_referral(friend_id: int, inviter_id: int) -> bool:
    """Друга приглашают один раз — первым, кто успел."""
    async with connect() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO referrals (friend_id, inviter_id) VALUES (?, ?)", (friend_id, inviter_id))
        await db.commit()
        return cur.rowcount == 1


async def get_referral(friend_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM referrals WHERE friend_id = ?", (friend_id,))).fetchone()
        return dict(row) if row else None


async def open_referrals(max_age_days: int) -> list[dict]:
    """Приглашения без награды, моложе max_age_days — проверить, пользуется ли друг."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT friend_id, inviter_id, at FROM referrals WHERE rewarded_at IS NULL "
            "AND at >= datetime('now', ?)", (f"-{int(max_age_days)} days",))).fetchall()
        return [dict(r) for r in rows]


async def mark_rewarded(friend_id: int) -> bool:
    async with connect() as db:
        cur = await db.execute(
            "UPDATE referrals SET rewarded_at = datetime('now') WHERE friend_id = ? AND rewarded_at IS NULL",
            (friend_id,))
        await db.commit()
        return cur.rowcount == 1


async def invited_count(inviter_id: int) -> tuple[int, int]:
    """(пришло по ссылке, засчитано) — для экрана «Пригласи друга»."""
    async with connect() as db:
        row = await (await db.execute(
            "SELECT COUNT(*), COUNT(rewarded_at) FROM referrals WHERE inviter_id = ?", (inviter_id,))).fetchone()
        return row[0], row[1]


# ── Сколько пользуется ───────────────────────────────────────────────────────

async def active_days(user_id: int, since: str | None = None) -> int:
    """Разных дней (по Москве) с заходами — по событиям статистики (stats.py).
    since — 'YYYY-MM-DD HH:MM:SS' UTC, как events.at."""
    async with connect() as db:
        row = await (await db.execute(
            "SELECT COUNT(DISTINCT date(at, '+3 hours')) FROM events WHERE user_id = ?"
            + (" AND at >= ?" if since else ""),
            (user_id, since) if since else (user_id,))).fetchone()
        return row[0]


async def joined_at(user_id: int) -> str | None:
    async with connect() as db:
        row = await (await db.execute("SELECT joined_at FROM users WHERE user_id = ?", (user_id,))).fetchone()
        return row[0] if row else None
