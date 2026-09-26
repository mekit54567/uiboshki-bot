"""
Свой справочник «имя -> id» преподавателей, групп и аудиторий МИРЭА.

Зачем: официальный поиск (schedule-of.mirea.ru/schedule/api/search, см.
mirea_schedule_api.py) из-за рубежа не отвечает — ни с Railway (US West),
ни из облачной сессии: соединение рвётся. /teacher Морозов в проде ~40 секунд
висел на «Ищу...» и отвечал «не нашёл» (поймано живым тестом 26.09.2026).
А зеркало english.mirea.ru (им же пользуется config.ICAL_URL) отдаёт ical
любой цели по id — /schedule/api/ical/<type>/<id> — и имя стоит в самом
начале файла: "X-WR-CALNAME:Морозов А. В.". Поиска на зеркале нет (404).

Поэтому один раз в фоне обходим id по порядку, читая только начало каждого
файла (Range + обрыв потока после заголовка), и складываем имена в SQLite.
Поиск дальше — мгновенный LIKE по своей таблице. Обход вежливый (несколько
запросов одновременно), продолжается с места остановки после перезапуска
бота (прогресс в schedule_index_state) и повторяется раз в месяц — новые
группы и преподаватели появляются в конце диапазона id.
"""

import asyncio
import logging
import re
import time

import aiosqlite
import httpx

import database

logger = logging.getLogger(__name__)

MIRROR = "https://english.mirea.ru/schedule/api"

TYPES = (1, 2, 3)            # группа, преподаватель, аудитория (как в API МИРЭА)
STOP_AFTER_MISSES = 300      # столько 404 подряд — дальше id этого типа нет
CONCURRENCY = 4
REFRESH_DAYS = 30

_NAME_RE = re.compile(rb"X-WR-CALNAME:([^\r\n]+)")
_build_lock = asyncio.Lock()


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е").strip()


async def _ensure_tables(db):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schedule_targets (
            type     INTEGER NOT NULL,
            id       INTEGER NOT NULL,
            title    TEXT NOT NULL,
            title_lc TEXT NOT NULL,
            PRIMARY KEY (type, id)
        )
    """)
    await db.execute("CREATE TABLE IF NOT EXISTS schedule_index_state (key TEXT PRIMARY KEY, value TEXT)")


async def _get_state(key: str) -> str | None:
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        cur = await db.execute("SELECT value FROM schedule_index_state WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def _set_state(key: str, value: str):
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        await db.execute("INSERT OR REPLACE INTO schedule_index_state (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def fetch_title(client: httpx.AsyncClient, target_type: int, target_id: int) -> str | None:
    """Имя цели по X-WR-CALNAME из начала её ical. None — такого id нет (404).
    Сетевые ошибки пробрасываются: пропуск из-за сбоя не должен считаться
    «id закончились»."""
    url = f"{MIRROR}/ical/{target_type}/{target_id}"
    async with client.stream("GET", url, headers={"Range": "bytes=0-1023"}) as resp:
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        head = b""
        async for chunk in resp.aiter_bytes():
            head += chunk
            if len(head) >= 1024 or b"X-WR-CALNAME" in head and b"\n" in head.split(b"X-WR-CALNAME", 1)[1]:
                break
    m = _NAME_RE.search(head)
    return m.group(1).decode("utf-8", "replace").strip() if m else None


async def _save(rows: list[tuple[int, int, str]]):
    if not rows:
        return
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        await db.executemany(
            "INSERT OR REPLACE INTO schedule_targets (type, id, title, title_lc) VALUES (?, ?, ?, ?)",
            [(t, i, title, _norm(title)) for t, i, title in rows],
        )
        await db.commit()


async def _scan_type(client: httpx.AsyncClient, target_type: int):
    start = int(await _get_state(f"next_id_{target_type}") or 1)
    misses = int(await _get_state(f"misses_{target_type}") or 0)
    next_id = start
    while misses < STOP_AFTER_MISSES:
        ids = list(range(next_id, next_id + CONCURRENCY * 5))
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(i):
            async with sem:
                for attempt in range(3):
                    try:
                        return i, await fetch_title(client, target_type, i)
                    except Exception as e:
                        if attempt == 2:
                            raise
                        logger.info(f"schedule_index: {target_type}/{i} повтор после ошибки: {e}")
                        await asyncio.sleep(2 * (attempt + 1))

        results = await asyncio.gather(*(one(i) for i in ids))
        found = []
        for i, title in sorted(results):
            if title:
                found.append((target_type, i, title))
                misses = 0
            else:
                misses += 1
        await _save(found)
        next_id = ids[-1] + 1
        await _set_state(f"next_id_{target_type}", str(next_id))
        await _set_state(f"misses_{target_type}", str(misses))


async def build_index(client: httpx.AsyncClient | None = None):
    """Полный (или продолженный) обход всех типов. Идемпотентен, один за раз."""
    if _build_lock.locked():
        return
    async with _build_lock:
        own = client is None
        client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
        try:
            started = time.monotonic()
            for t in TYPES:
                await _scan_type(client, t)
            await _set_state("built_at", str(int(time.time())))
            logger.info(f"schedule_index: справочник собран за {int(time.monotonic() - started)} с, "
                        f"{await count()} записей")
        finally:
            if own:
                await client.aclose()


async def ensure_fresh():
    """Для фоновой задачи: достроить прерванный обход или обновить раз в месяц.
    Ошибки только в лог — бот и поиск по уже собранному работают дальше."""
    try:
        built_at = await _get_state("built_at")
        if built_at and time.time() - int(built_at) > REFRESH_DAYS * 86400:
            for t in TYPES:  # новый круг: сначала, старые записи обновятся по месту
                await _set_state(f"next_id_{t}", "1")
                await _set_state(f"misses_{t}", "0")
            built_at = None
        if not built_at:
            await build_index()
    except Exception as e:
        logger.warning(f"schedule_index: обход прервался, продолжу позже: {e}")


async def is_ready() -> bool:
    return bool(await _get_state("built_at"))


async def count() -> int:
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        cur = await db.execute("SELECT COUNT(*) FROM schedule_targets")
        return (await cur.fetchone())[0]


async def search(query: str, types: tuple[int, ...] = TYPES, limit: int = 20) -> list[dict]:
    """Подстрока без учёта регистра и ё/е; сначала те, что начинаются с
    запроса ("Морозов" раньше "Шморозова"), дальше по алфавиту."""
    q = _norm(query)
    if not q or not types:
        return []
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    marks = ",".join("?" * len(types))
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        cur = await db.execute(
            f"""SELECT type, id, title FROM schedule_targets
                WHERE type IN ({marks}) AND title_lc LIKE ? ESCAPE '\\'
                ORDER BY (title_lc LIKE ? ESCAPE '\\') DESC, length(title), title
                LIMIT ?""",
            (*types, f"%{like}%", f"{like}%", limit),
        )
        return [{"type": t, "id": i, "title": title} for t, i, title in await cur.fetchall()]


async def get_title(target_type: int, target_id: int) -> str | None:
    async with aiosqlite.connect(database.DATABASE_PATH) as db:
        await _ensure_tables(db)
        cur = await db.execute("SELECT title FROM schedule_targets WHERE type=? AND id=?", (target_type, target_id))
        row = await cur.fetchone()
        return row[0] if row else None
