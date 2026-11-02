"""
Вход в Пульс МИРЭА на сервере (31.10, Никита: «унифицировать как СДО»).

Разведка с телефона (pulse_lab) показала: Пульс держит вход не токеном, а
HttpOnly-кукой сайта pulse.mirea.ru — как MoodleSession у СДО. Приложение
после входа окном отдаёт заголовок Cookie этого сайта (/api/pulse/connect),
сервер хранит его зашифрованным (ключ входов СДО, sdo_accounts) и держит
проверкой по таймеру: раз в PULSE_KEEPALIVE_MIN минут (по умолчанию 55, как
СДО; поднимем, когда узнаем, сколько живёт вход).

Пока — только для старосты (эксперимент). Только чтение своих данных:
проверка — GetMeInfo, тот же запрос, что делает сам сайт при открытии.
Отметка по QR сюда не относится — её делает телефон, не сервер.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import aiosqlite
import httpx

import pulse_probe
from database._conn import connect
from sdo_accounts import decrypt, encrypt, needs_rotation

logger = logging.getLogger(__name__)

ME_METHOD = "rtu_tc.rtu_attend.app.UserService/GetMeInfo"
APP_VERSION = os.getenv("PULSE_APP_VERSION", "1.9.3+10708")   # как у сайта в разведке 31.10
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
_PAIR = re.compile(r"^[A-Za-z0-9_\-.]{1,64}=[^;\s]{1,2048}$")
# аналитика сайта и прочие не нужные для входа куки — не храним
_transport = None      # тесты подставляют httpx.MockTransport
_SKIP = re.compile(r"^(_ga|_gid|_ym|_utm|tmr_|ph_|amplitude|_fbp)", re.I)


def keepalive_minutes() -> int:
    try:
        return max(5, int(os.getenv("PULSE_KEEPALIVE_MIN", "55")))
    except ValueError:
        return 55


def clean_cookie_header(raw: str) -> str | None:
    """«a=1; b=2» из окна приложения → только пары имя=значение, без
    аналитики; None — нечего хранить (не вошёл или мусор)."""
    pairs = []
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or not _PAIR.match(part) or _SKIP.match(part):
            continue
        pairs.append(part)
    header = "; ".join(pairs)
    return header if pairs and len(header) <= 8192 else None


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def check(cookie: str) -> str:
    """Пускает ли Пульс с этим входом: ok · expired (вход не принят) ·
    blocked (DDoS-Guard не пустил сервер). Сеть упала — исключение."""
    headers = pulse_probe._headers(cookie, APP_VERSION)
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}, transport=_transport) as client:
        resp = await client.post(f"{pulse_probe.PULSE}/{ME_METHOD}", content=pulse_probe.frame(), headers=headers)
    if resp.status_code in (401,):
        return "expired"
    if resp.status_code != 200:
        body = resp.text[:2000].lower() if "html" in resp.headers.get("content-type", "") else ""
        return "blocked" if resp.status_code in (403, 429, 451) or "ddos-guard" in body else "expired"
    try:
        msgs, trailer = pulse_probe.unframe(resp.content)
    except (ValueError, IndexError):
        return "expired"
    status = trailer.get("grpc-status", resp.headers.get("grpc-status", "0"))
    if status == "16":            # UNAUTHENTICATED
        return "expired"
    return "ok" if status == "0" and msgs else "expired"


# --- база ---------------------------------------------------------------------

async def _row(user_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM pulse_sessions WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return dict(r) if r else None


async def save(user_id: int, cookie: str, status: str = "ok"):
    now = _now()
    async with connect() as db:
        await db.execute(
            "INSERT INTO pulse_sessions (user_id, cookie_enc, status, created_at, checked_at, next_check_at, alive_until) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET cookie_enc=excluded.cookie_enc, "
            "status=excluded.status, created_at=excluded.created_at, checked_at=excluded.checked_at, "
            "next_check_at=excluded.next_check_at, alive_until=excluded.alive_until",
            (user_id, encrypt(cookie), status, _utc(now), _utc(now),
             _utc(now + timedelta(minutes=keepalive_minutes())), _utc(now) if status == "ok" else None))
        await db.commit()


async def forget(user_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM pulse_sessions WHERE user_id=?", (user_id,))
        await db.commit()


async def cookie_for(user_id: int) -> str | None:
    row = await _row(user_id)
    return decrypt(row["cookie_enc"]) if row and row["status"] == "ok" else None


async def status_for(user_id: int) -> dict:
    """Для экрана: подключён ли вход и сколько он уже прожил (замер для
    интервала поддержания: alive_until − created_at)."""
    row = await _row(user_id)
    if not row:
        return {"state": "off"}
    lived = None
    if row.get("alive_until") and row.get("created_at"):
        a = datetime.fromisoformat(row["alive_until"])
        b = datetime.fromisoformat(row["created_at"])
        lived = int((a - b).total_seconds() // 60)
    return {"state": row["status"], "checked_at": row["checked_at"], "since": row["created_at"],
            "lived_min": lived, "keepalive_min": keepalive_minutes()}


async def connect_from_app(user_id: int, raw_cookie: str) -> dict:
    """Приложение отдало куку сайта Пульса после входа окном: проверить с
    сервера и сохранить. blocked — сервер не пускают, вход не храним."""
    cookie = clean_cookie_header(raw_cookie)
    if not cookie:
        return {"state": "empty"}
    try:
        state = await check(cookie)
    except httpx.HTTPError as e:
        return {"state": "network", "error": type(e).__name__}
    if state == "ok":
        await save(user_id, cookie)
        import asyncio

        import pulse_attendance                 # первые посещения — сразу, фоном
        asyncio.get_running_loop().create_task(pulse_attendance.sync_due(user_id))
    return {"state": state}


async def _check_one(row: dict, now: datetime):
    uid, enc = row["user_id"], row["cookie_enc"]
    cookie = decrypt(enc)
    if cookie is None:
        logger.error(f"Пульс keepalive {uid}: кука не расшифровывается — ключ SDO_CRYPT_*")
        return
    try:
        state = await check(cookie)
    except Exception as e:      # сеть — не повод считать вход протухшим
        logger.info(f"Пульс keepalive {uid}: {type(e).__name__}")
        state = None
    async with connect() as db:
        nxt = _utc(now + timedelta(minutes=keepalive_minutes()))
        if state == "ok":
            new_enc = encrypt(cookie) if needs_rotation(enc) else enc
            await db.execute("UPDATE pulse_sessions SET cookie_enc=?, checked_at=?, next_check_at=?, alive_until=? "
                             "WHERE user_id=? AND cookie_enc=?", (new_enc, _utc(now), nxt, _utc(now), uid, enc))
        elif state in ("expired",):
            await db.execute("UPDATE pulse_sessions SET status='expired', checked_at=? WHERE user_id=? AND cookie_enc=?",
                             (_utc(now), uid, enc))
            logger.info(f"Пульс keepalive {uid}: вход устарел")
        else:                   # blocked или сеть — попробовать в следующий раз
            await db.execute("UPDATE pulse_sessions SET next_check_at=? WHERE user_id=? AND cookie_enc=?", (nxt, uid, enc))
        await db.commit()


async def keepalive_due(now: datetime | None = None):
    """Раз в минуту (scheduler.py): проверить входы, чья очередь подошла."""
    now = now or _now()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM pulse_sessions WHERE status='ok' AND (next_check_at IS NULL OR next_check_at<=?)",
                               (_utc(now),))
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        await _check_one(row, now)
        import pulse_attendance                 # посещения лекций — заодно, не чаще раза в 3 ч
        if await cookie_for(row["user_id"]):
            await pulse_attendance.sync_due(row["user_id"])
