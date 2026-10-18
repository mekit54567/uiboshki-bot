"""Пользователи: регистрация, подписка, уведомления, календарный токен, предметы по выбору."""

import secrets
import time

import aiosqlite

import database
from database._conn import connect, write_later
from database.privacy import NOT_ERASING

# Amvera (16.10): запись в базу ~0,2 с (сетевой диск), а upsert_user шёл на
# каждый запрос WebApp. Те же имя и ник — пишем не чаще раза в 10 минут
# (last_seen для «Кто пользуется» точнее и не нужен). Ключ — с путём базы:
# тесты и /restore подменяют её; удаление данных — forget_user.
UPSERT_EVERY = 600
_upserted: dict[tuple[str, int], tuple[str, str, float]] = {}


def forget_user(user_id: int | None = None):
    """Забыть, что человек уже записан (None — всех): после удаления или /restore."""
    if user_id is None:
        _upserted.clear()
    else:
        for key in [k for k in _upserted if k[1] == user_id]:
            del _upserted[key]


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str, named: bool = True, wait: bool = True):
    """До согласия на обработку данных (privacy.blocked) — только id, без
    имени и ника (152-ФЗ); имя запишется при следующем заходе после согласия.
    wait=False (запросы WebApp): уже есть в базе — запись в фоне
    (_conn.write_later), новый — сразу: дальше запрос читает его строку."""
    import privacy
    if not named or await privacy.blocked(user_id):
        username = full_name = ""
    key, now = (database.DATABASE_PATH, user_id), time.monotonic()
    last = _upserted.get(key)
    if last and last[:2] == (username, full_name) and now - last[2] < UPSERT_EVERY:
        return
    if not wait and await get_user(user_id):
        _upserted[key] = (username, full_name, now)     # пачка запросов разом — одна запись
        await write_later(_upsert(key, user_id, username, full_name, now))
        return
    await _upsert(key, user_id, username, full_name, now)


async def _upsert(key, user_id: int, username: str, full_name: str, now: float):
    async with connect() as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name, last_seen)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name,
                last_seen = excluded.last_seen
        """, (user_id, username, full_name))
        await db.commit()
    _upserted[key] = (username, full_name, now)


async def get_all_subscribed_users() -> list[int]:
    async with connect() as db:
        cursor = await db.execute(f"SELECT user_id FROM users WHERE subscribed = 1 AND {NOT_ERASING}")
        return [r[0] for r in await cursor.fetchall()]


async def get_reminder_users() -> list[dict]:
    """Подписчики с их настройками уведомлений — одним запросом (напоминания
    о парах проверяются раз в минуту, по запросу на человека — лишнее)."""
    async with connect() as db:
        cursor = await db.execute(f"SELECT user_id, notify, group_id FROM users WHERE subscribed = 1 AND {NOT_ERASING}")
        return [{"user_id": r[0], "notify": r[1], "group_id": r[2]} for r in await cursor.fetchall()]


async def get_all_optional_answers() -> dict[int, dict[str, bool]]:
    async with connect() as db:
        out: dict[int, dict[str, bool]] = {}
        for uid, subject, attend in await (await db.execute(
                "SELECT user_id, subject, attend FROM optional_subjects")).fetchall():
            out.setdefault(uid, {})[subject] = bool(attend)
        return out


async def set_notify(user_id: int, prefs: dict):
    import json
    async with connect() as db:
        await db.execute("UPDATE users SET notify = ? WHERE user_id = ?",
                         (json.dumps(prefs, ensure_ascii=False), user_id))
        await db.commit()


# ── Персональные ссылки на ICS-календарь ────────────────────────────────────
# Токен — случайная непредсказуемая строка (не user_id), чтобы ссылку нельзя
# было подобрать перебором и увидеть чужое расписание/ДЗ. Ссылка привязана к
# конкретному студенту, но сам .ics-эндпоинт не требует initData (календарные
# приложения не умеют слать кастомные заголовки при периодическом опросе
# webcal-подписки) — секретность держится на непредсказуемости токена, как у
# большинства calendar-share ссылок (Google/Apple делают так же).

async def get_or_create_calendar_token(user_id: int) -> str:
    async with connect() as db:
        cursor = await db.execute("SELECT calendar_token FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            return row[0]
        token = secrets.token_urlsafe(24)
        # INSERT ... ON CONFLICT — а не UPDATE — потому что get_or_create_calendar_token
        # может быть вызвана до /start (юзер ещё не встречался upsert_user), тогда
        # обычный UPDATE тихо обновит 0 строк и токен нигде не сохранится.
        await db.execute("""
            INSERT INTO users (user_id, calendar_token) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET calendar_token = excluded.calendar_token
        """, (user_id, token))
        await db.commit()
        return token


async def get_user_by_calendar_token(token: str) -> dict | None:
    if not token:
        return None
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE calendar_token = ?", (token,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_subscription(user_id: int, value: int):
    async with connect() as db:
        await db.execute("UPDATE users SET subscribed = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def get_reminder_minutes(user_id: int) -> int:
    async with connect() as db:
        cursor = await db.execute("SELECT reminder_minutes FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 15


async def set_reminder_minutes(user_id: int, minutes: int):
    async with connect() as db:
        await db.execute("UPDATE users SET reminder_minutes = ? WHERE user_id = ?", (minutes, user_id))
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_optional_answers(user_id: int) -> dict[str, bool]:
    """Предметы по выбору, на которые человек уже ответил: предмет → ходит ли."""
    async with connect() as db:
        cursor = await db.execute("SELECT subject, attend FROM optional_subjects WHERE user_id=?", (user_id,))
        return {r[0]: bool(r[1]) for r in await cursor.fetchall()}


async def set_optional_answer(user_id: int, subject: str, attend: bool):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO optional_subjects (user_id, subject, attend) VALUES (?, ?, ?)",
                         (user_id, subject, int(attend)))
        await db.commit()


async def get_all_users() -> list[dict]:
    """Все, кто запускал бота: id, ник, имя (для «кто пользуется» в /stats)."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"SELECT user_id, username, full_name, joined_at FROM users WHERE {NOT_ERASING}")
        return [dict(r) for r in await cursor.fetchall()]


async def count_users() -> int:
    async with connect() as db:
        return (await (await db.execute(f"SELECT COUNT(*) FROM users WHERE {NOT_ERASING}")).fetchone())[0]
