"""Вход в приложение без Telegram (этап 2): одноразовые коды входа через
бота и долгие сессии устройств (токен хранится только хэшем)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import aiosqlite

from database._conn import connect, write_later

LOGIN_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=90)          # продлевается при каждом заходе
# Вход в браузере — 30 дней без заходов: Safari и так стирает данные сайта
# через неделю без открытий, токен теряется, а запись висела в «Устройствах»
# 90 дней (Никита 25.10, девять «Safari · iPhone»). Приложение — 90: кто только
# читает пуши, его не открывает.
WEB_TTL = timedelta(days=30)
APP_PREFIX = "Капибара ·"                 # webapp/routes/auth._device для своего приложения
# хвосты названия входа через провайдера (auth.py): то же устройство
VIA = (" · VK ID", " · Яндекс ID", " · Apple")


def ttl(device: str | None) -> timedelta:
    return SESSION_TTL if (device or "").startswith(APP_PREFIX) else WEB_TTL


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def token_hash(token: str) -> str:
    return hashlib.sha256(("uiboshki-session:" + token).encode()).hexdigest()


async def create_login(device: str) -> str:
    code = secrets.token_urlsafe(18)
    async with connect() as db:
        await db.execute("DELETE FROM auth_logins WHERE expires_at < ?", (_ts(_now()),))
        await db.execute("INSERT INTO auth_logins (code, device, expires_at, pick) VALUES (?, ?, ?, ?)",
                         (code, device[:120], _ts(_now() + LOGIN_TTL), 10 + secrets.randbelow(90)))
        await db.commit()
    return code


def pick_options(pick: int) -> list[int]:
    """Три числа для кнопок в боте: верное и два других, вразнобой."""
    out = {pick}
    while len(out) < 3:
        out.add(10 + secrets.randbelow(90))
    return sorted(out, key=lambda _: secrets.randbelow(1000))


async def get_login(code: str) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM auth_logins WHERE code = ?", (code,))).fetchone()
    if not row or row["expires_at"] < _ts(_now()):
        return None
    return dict(row)


async def decide_login(code: str, user_id: int, ok: bool) -> bool:
    """Человек в боте подтвердил («Да, это я») или отклонил вход. → был ли код."""
    async with connect() as db:
        cur = await db.execute("UPDATE auth_logins SET user_id = ?, status = ? WHERE code = ? AND status = 'wait' "
                               "AND expires_at >= ?", (user_id, "ok" if ok else "no", code, _ts(_now())))
        await db.commit()
        return cur.rowcount > 0


async def redeem_login(code: str) -> tuple[str, int] | None:
    """Подтверждённый код → (токен, user_id) один раз; код сгорает."""
    login = await get_login(code)
    if not login or login["status"] != "ok" or not login["user_id"]:
        return None
    async with connect() as db:
        cur = await db.execute("DELETE FROM auth_logins WHERE code = ? AND status = 'ok'", (code,))
        await db.commit()
        if cur.rowcount == 0:
            return None                       # кто-то успел раньше — второй раз не выдаём
    return await create_session(login["user_id"], login["device"]), login["user_id"]


async def create_session(user_id: int, device: str) -> str:
    token = secrets.token_urlsafe(32)
    async with connect() as db:
        await db.execute("INSERT INTO sessions (user_id, token_hash, device, last_seen, expires_at) "
                         "VALUES (?, ?, ?, ?, ?)",
                         (user_id, token_hash(token), device[:120], _ts(_now()), _ts(_now() + ttl(device))))
        await db.commit()
    return token


async def session_user(token: str) -> int | None:
    """Чей токен (и продлить сессию); None — нет, отозван или истёк."""
    found = await session_lookup(token)
    return found[1] if found else None


async def session_lookup(token: str) -> tuple[int, int] | None:
    """(id сессии, user_id) по токену (и продлить сессию); None — нет, отозван или истёк."""
    if not token:
        return None
    h = token_hash(token)
    async with connect() as db:
        row = await (await db.execute("SELECT id, user_id, expires_at, last_seen, device FROM sessions "
                                      "WHERE token_hash = ? AND revoked = 0", (h,))).fetchone()
        if not row or row[2] < _ts(_now()):
            return None
    if row[3] < _ts(_now() - timedelta(minutes=10)) and row[0] not in _prolonging:
        _prolonging.add(row[0])                                   # продлеваем не чаще раза в 10 минут,
        await write_later(_prolong(row[0], ttl(row[4])))         # и запрос этого не ждёт
    return row[0], row[1]


_prolonging: set[int] = set()       # пачка запросов разом — одно продление


async def _prolong(session_id: int, life: timedelta = SESSION_TTL):
    try:
        async with connect() as db:
            await db.execute("UPDATE sessions SET last_seen = ?, expires_at = ? WHERE id = ?",
                             (_ts(_now()), _ts(_now() + life), session_id))
            await db.commit()
    finally:
        _prolonging.discard(session_id)


async def list_sessions(user_id: int) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, device, created_at, last_seen FROM sessions WHERE user_id = ? AND revoked = 0 "
            "AND expires_at >= ? ORDER BY last_seen DESC", (user_id, _ts(_now())))).fetchall()
        return [dict(r) for r in rows]


def base_device(device: str | None) -> str:
    """«Safari · iPhone · VK ID» → «Safari · iPhone»: вход через провайдера — то же устройство."""
    device = device or "Устройство"
    for tail in VIA:
        if device.endswith(tail):
            return device[:-len(tail)]
    return device


def group_sessions(items: list[dict], current_id: int | None = None) -> list[dict]:
    """Одинаковые устройства — одной строкой «Safari · iPhone · 6 входов»
    (каждый перелогин — новая запись, старую закрыть было некому). Текущий
    вход — своей строкой: «Выйти» на нём не трогает соседей. Порядок — по
    последнему заходу; id строки — самый свежий вход, ids — все."""
    from utils import plural
    groups: dict[tuple, dict] = {}
    for it in items:                                   # items — уже по last_seen DESC
        cur = it["id"] == current_id
        key = ("current",) if cur else ("dev", base_device(it["device"]))
        g = groups.get(key)
        if g is None:
            groups[key] = g = {**it, "device": base_device(it["device"]), "ids": [], "current": cur}
        g["ids"].append(it["id"])
    out = list(groups.values())
    for g in out:
        g["count"] = n = len(g["ids"])
        if n > 1:
            g["device"] += f" · {n} {plural(n, 'вход', 'входа', 'входов')}"
    return out


async def revoke_session(user_id: int, session_id: int | None = None, token: str | None = None,
                         ids: list[int] | None = None) -> int:
    """Выйти: одно устройство (по id, списку id или токену) или все (все None)."""
    sql, args = "UPDATE sessions SET revoked = 1 WHERE user_id = ?", [user_id]
    if ids is not None:
        ids = [int(i) for i in ids] or [-1]
        sql, args = sql + f" AND id IN ({','.join('?' * len(ids))})", args + ids
    elif session_id is not None:
        sql, args = sql + " AND id = ?", args + [session_id]
    elif token is not None:
        sql, args = sql + " AND token_hash = ?", args + [token_hash(token)]
    async with connect() as db:
        cur = await db.execute(sql, args)
        # пуши отозванных устройств — тоже: ключ расшифровки у телефона остаётся,
        # пока там не открыли приложение (аудит 21.10, R3)
        for table in ("push_subs", "app_push"):
            await db.execute(f"DELETE FROM {table} WHERE user_id = ? AND session_id IN "
                             "(SELECT id FROM sessions WHERE user_id = ? AND revoked = 1)", (user_id, user_id))
        await db.commit()
        return cur.rowcount


# Подписка на пуш живёт, пока жива её сессия (NULL — Mini App в Telegram или
# подписка старше колонки session_id). Отправка проверяет это ещё раз: сессия
# могла истечь сама.
LIVE_SESSION_SQL = ("(session_id IS NULL OR session_id IN "
                    "(SELECT id FROM sessions WHERE revoked = 0 AND expires_at >= ?))")


def live_now() -> str:
    return _ts(_now())
