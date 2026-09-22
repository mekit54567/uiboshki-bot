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
"""

import logging
import httpx

logger = logging.getLogger(__name__)

BASE = "https://schedule-of.mirea.ru/schedule/api"

TARGET_GROUP   = 1
TARGET_TEACHER = 2
TARGET_ROOM    = 3


async def search_targets(query: str, target_type: int, limit: int = 8) -> list[dict]:
    """Ищет по всем типам сразу (так работает сам API) и отфильтровывает
    только нужный target_type на своей стороне. limit*3 в запросе — с
    запасом, чтобы после фильтрации по типу не остаться с пустым списком
    из-за того, что верхние N результатов оказались не того типа."""
    query = query.strip()
    if not query:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BASE}/search", params={"limit": limit * 3, "match": query})
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"mirea schedule search failed: {e}")
        return []
    return [d for d in data if d.get("scheduleTarget") == target_type][:limit]


async def get_baseinfo(target_id: int, target_type: int) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BASE}/baseinfo", params={"id": target_id, "type": target_type})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"mirea baseinfo failed: {e}")
        return None


async def fetch_ical(target_id: int, target_type: int) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{BASE}/ical/{target_type}/{target_id}")
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"mirea ical fetch failed: {e}")
        return None
