"""152-ФЗ: согласия, «удалить все мои данные», срок хранения (privacy.py).

erase_user убирает человека отовсюду: все строки таблиц с колонкой user_id
(список берётся из схемы — новая таблица попадёт сама, тест следит), его
настройки (goals:, member:, счётчики ИИ), входы, устройства и куку СДО.
Общее для группы (дедлайны старосты и СДО, файлы, ДЗ, заметки, конспекты,
голосования, посты «Подслушано») остаётся, но без его id."""

import json

import aiosqlite

from database._conn import connect


# ── Согласия ─────────────────────────────────────────────────────────────────

async def give_consent(user_id: int, kind: str, version: str, via: str):
    async with connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO consents (user_id, kind, version, via) VALUES (?, ?, ?, ?)",
            (user_id, kind, version, via))
        await db.commit()


async def has_consent(user_id: int, kind: str, version: str) -> bool:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT 1 FROM consents WHERE user_id=? AND kind=? AND version=?",
            (user_id, kind, version))).fetchone()
        return row is not None


async def has_any_consent(user_id: int, kind: str = "pd") -> bool:
    """Давал согласие хоть какой-то версии текста."""
    async with connect() as db:
        row = await (await db.execute(
            "SELECT 1 FROM consents WHERE user_id=? AND kind=?", (user_id, kind))).fetchone()
        return row is not None


async def is_legacy(user_id: int) -> bool:
    """Пользовался ботом до согласий — пользуется и без него (Никита, 11.10)."""
    async with connect() as db:
        row = await (await db.execute("SELECT legacy FROM users WHERE user_id=?", (user_id,))).fetchone()
        return bool(row and row[0])


async def asked_version(user_id: int) -> str:
    async with connect() as db:
        row = await (await db.execute("SELECT consent_asked FROM users WHERE user_id=?", (user_id,))).fetchone()
        return (row and row[0]) or ""


async def mark_asked(user_id: int, version: str) -> bool:
    """Отметить «спросили о согласии этой версии». True — отметили сейчас
    (раньше не спрашивали), False — уже спрашивали или человека нет."""
    async with connect() as db:
        cur = await db.execute(
            "UPDATE users SET consent_asked=? WHERE user_id=? AND COALESCE(consent_asked, '')<>?",
            (version, user_id, version))
        await db.commit()
        return cur.rowcount == 1


async def get_consents(user_id: int) -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT kind, version, via, at FROM consents WHERE user_id=? ORDER BY at", (user_id,))).fetchall()
        return [dict(r) for r in rows]


# ── Удаление ─────────────────────────────────────────────────────────────────

# Колонки «кто создал» в общих таблицах: запись остаётся группе, id — нет.
AUTHOR_COLUMNS = (
    ("files", "uploaded_by"),
    ("lesson_notes", "created_by"),
    ("homework", "created_by"),
    ("votes", "created_by"),
    ("file_summaries", "created_by"),
    ("group_admins", "added_by"),
)


async def user_tables(db) -> list[str]:
    """Таблицы, где есть колонка user_id (кроме служебных FTS)."""
    names = [r[0] for r in await (await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
    out = []
    for t in names:
        cols = [r[1] for r in await (await db.execute(f"PRAGMA table_info({t})")).fetchall()]
        if "user_id" in cols:
            out.append(t)
    return out


async def _columns(db, table: str) -> list[str]:
    return [r[1] for r in await (await db.execute(f"PRAGMA table_info({table})")).fetchall()]


async def erase_user(user_id: int, starosta_ids=()) -> dict:
    """Стереть человека. → {таблица: сколько строк} — для лога и теста."""
    from database.social import feed_author_hash
    uid = int(user_id)
    done: dict[str, int] = {}
    async with connect() as db:
        # Его личные дедлайны (не общие: см. deadlines.is_shared_deadline) — целиком,
        # общие, созданные им, остаются группе.
        staro = tuple(int(s) for s in starosta_ids) or (-1,)
        marks = ",".join("?" * len(staro))
        cur = await db.execute(
            f"""DELETE FROM deadlines WHERE created_by=? AND (personal=1
                OR (group_id IS NULL AND created_by NOT IN ({marks})))""", (uid, *staro))
        done["deadlines"] = cur.rowcount
        await db.execute("UPDATE deadlines SET created_by=0 WHERE created_by=?", (uid,))

        for table, col in AUTHOR_COLUMNS:
            if col in await _columns(db, table):
                await db.execute(f"UPDATE {table} SET {col}=NULL WHERE {col}=?", (uid,))

        await db.execute("UPDATE feed_posts SET author_id=0 WHERE author_id IN (?, ?)",
                         (uid, feed_author_hash(uid)))
        await db.execute("DELETE FROM oauth_states WHERE link_user=?", (uid,))

        for table in await user_tables(db):
            cur = await db.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
            if cur.rowcount:
                done[table] = cur.rowcount

        # Настройки: свои ключи и счётчики ИИ (JSON {id: число} по дням и неделям).
        await db.execute("DELETE FROM settings WHERE key IN (?, ?)", (f"goals:{uid}", f"member:{uid}"))
        rows = await (await db.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'ai_day:%' OR key LIKE 'ai_sum:%'")).fetchall()
        for key, value in rows:
            try:
                data = json.loads(value or "{}")
            except ValueError:
                continue
            if isinstance(data, dict) and str(uid) in data:
                data.pop(str(uid))
                await db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(data), key))
        await db.commit()
    return done


# ── Срок хранения ────────────────────────────────────────────────────────────

# ── Отложенное удаление (7 дней на «удалил по ошибке») ──────────────────────

async def request_erase(user_id: int, due: str):
    """Запрос «удалить мои данные»: сразу — согласия, входы на устройствах,
    пуши и вход в СДО; остальное стирает erase_user в день due."""
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO erase_requests (user_id, due) VALUES (?, ?)", (user_id, due))
        for table in ("consents", "sessions", "push_subs", "sdo_sessions"):
            await db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        # восстановили — согласие спросят заново, «был до согласий» больше не в счёт
        await db.execute("UPDATE users SET legacy=0, consent_asked=NULL WHERE user_id=?", (user_id,))
        await db.commit()


async def erase_due(user_id: int) -> str | None:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT due FROM erase_requests WHERE user_id=?", (user_id,))).fetchone()
        return row[0] if row else None


async def due_erasures(today: str) -> list[int]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT user_id FROM erase_requests WHERE due <= ?", (today,))).fetchall()
        return [r[0] for r in rows]


async def cancel_erase(user_id: int) -> bool:
    async with connect() as db:
        cur = await db.execute("DELETE FROM erase_requests WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount > 0


async def touch_seen(user_id: int):
    async with connect() as db:
        await db.execute("UPDATE users SET last_seen=datetime('now') WHERE user_id=?", (user_id,))
        await db.commit()


async def inactive_users(days: int) -> list[int]:
    """Кто не заходил больше days дней (последний заход — users.last_seen)."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT user_id FROM users WHERE COALESCE(last_seen, joined_at) < datetime('now', ?)",
            (f"-{int(days)} days",))).fetchall()
        return [r[0] for r in rows]


async def purge_solver_history(keep_days: int) -> int:
    async with connect() as db:
        cur = await db.execute("DELETE FROM solver_history WHERE created_at < datetime('now', ?)",
                               (f"-{int(keep_days)} days",))
        await db.commit()
        return cur.rowcount
