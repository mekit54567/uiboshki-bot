"""
Публичный (без авторизации) поиск/бэкенд расписания РТУ МИРЭА.

Найден не разведкой, а от самого владельца: он скинул реальные webcal-ссылки
своей группы и одного препода, а потом руками через DevTools на lk.mirea.ru
поймал сетевой запрос, который делает поиск препода/группы/аудитории по имени
на странице расписания личного кабинета. Внутри он бьёт не в сам lk.mirea.ru
(это Bitrix, авторизация нужна только для самого кабинета), а в отдельный
публичный бэкенд:

    https://schedule-of.mirea.ru/schedule/api/search?limit=N&match=<текст>

Без кук, без токена — просто открытый эндпоинт. Возвращает вперемешку все типы
целей (группа/препод/аудитория), различаются полем scheduleTarget. Плюс:

    /schedule/api/baseinfo?id=<id>&type=<type>   — получить карточку по id
    /schedule/api/ical/<type>/<id>               — ical конкретной цели

Ровно тот же движок, что уже используется в config.ICAL_URL для расписания
своей группы (там просто зеркало на english.mirea.ru, здесь — прямой хост).

Важно: schedule-of.mirea.ru из-за рубежа (Railway US West) не отвечает — поиск
висел ~40 с и отвечал «не нашёл». Поэтому искать — по своему справочнику
(schedule_index.py, собран с зеркала), а официальный поиск — только запасной,
с коротким таймаутом. ical тоже сначала с зеркала: там только он и есть.
"""

import logging
import httpx

logger = logging.getLogger(__name__)

BASE = "https://schedule-of.mirea.ru/schedule/api"

TARGET_GROUP   = 1
TARGET_TEACHER = 2
TARGET_ROOM    = 3


MIRROR = "https://english.mirea.ru/schedule/api"


class SearchUnavailable(Exception):
    """Справочник ещё не собран, а официальный поиск недоступен — это не
    «ничего не нашлось», и пользователю надо сказать именно это."""


async def _official_search(query: str, target_type: int, limit: int) -> list[dict]:
    """Официальный поиск ищет по всем типам сразу — отфильтровываем нужный
    target_type у себя (limit*3 — с запасом на фильтрацию)."""
    async with httpx.AsyncClient(timeout=4) as client:
        resp = await client.get(f"{BASE}/search", params={"limit": limit * 3, "match": query})
        resp.raise_for_status()
        data = resp.json().get("data", [])
    return [d for d in data if d.get("scheduleTarget") == target_type][:limit]


async def search_targets(query: str, target_type: int, limit: int = 8) -> list[dict]:
    """[{"id", "fullTitle", "scheduleTarget"}]. Сначала свой справочник, если
    в нём пусто — официальный поиск. SearchUnavailable — если справочник ещё
    не собран и официальный поиск не ответил."""
    import schedule_index
    query = query.strip()
    if not query:
        return []
    found = await schedule_index.search(query, (target_type,), limit)
    if found:
        return [{"id": f["id"], "fullTitle": f["title"], "scheduleTarget": f["type"]} for f in found]
    try:
        return await _official_search(query, target_type, limit)
    except Exception as e:
        logger.info(f"official mirea search unavailable: {e}")
        if not await schedule_index.is_ready():
            raise SearchUnavailable() from e
        return []


async def add_hints_for_namesakes(results: list[dict], limit: int = 10) -> list[dict]:
    """Для одинаковых названий в выдаче («Морозов В. А.» ×3 — в справочнике
    только инициалы) подтягивает их расписание и добавляет "hint": главный
    предмет на 2 недели или «нет пар». Те, у кого есть пары, — выше.
    results — [{"id", "fullTitle", "scheduleTarget"}]; остальные не трогаются."""
    import asyncio
    from collections import Counter
    from schedule_parser import summarize_target
    counts = Counter(r["fullTitle"] for r in results)
    dupes = [r for r in results if counts[r["fullTitle"]] > 1][:limit]
    if not dupes:
        return results

    async def hint(r):
        raw = await fetch_ical(r["id"], r["scheduleTarget"])
        if raw is None:
            return
        try:
            subject, pairs = summarize_target(raw)
        except Exception:
            return
        r["pairs"] = pairs
        r["hint"] = subject if pairs else "нет пар в ближайшие 2 недели"

    await asyncio.gather(*(hint(r) for r in dupes))
    # Порядок выдачи (совпадения с начала, свежие группы выше) сохраняем —
    # переставляем только однофамильцев между собой: с парами — первыми.
    order = {id(r): i for i, r in enumerate(results)}
    first_pos: dict[str, int] = {}
    for i, r in enumerate(results):
        first_pos.setdefault(r["fullTitle"], i)
    return sorted(results, key=lambda r: (first_pos[r["fullTitle"]], -(r.get("pairs") or 0), order[id(r)]))


async def get_baseinfo(target_id: int, target_type: int) -> dict | None:
    import schedule_index
    title = await schedule_index.get_title(target_type, target_id)
    if title:
        return {"id": target_id, "fullTitle": title}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BASE}/baseinfo", params={"id": target_id, "type": target_type})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"mirea baseinfo failed: {e}")
        return None


async def fetch_ical(target_id: int, target_type: int) -> bytes | None:
    for base in (MIRROR, BASE):
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(f"{base}/ical/{target_type}/{target_id}")
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning(f"mirea ical fetch failed ({base}): {e}")
    return None
