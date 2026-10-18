"""Карта корпусов (campus_map.py, 5.100.4): список, план корпуса, поиск
аудитории, маршрут. Выключено (MAP=0 или нет данных) — список пуст, планов нет."""

from fastapi import APIRouter, HTTPException

from webapp.deps import CurrentUser

router = APIRouter()


def _on():
    import campus_map
    if not campus_map.enabled():
        raise HTTPException(status_code=404, detail="карты пока нет")
    return campus_map


@router.get("/api/map")
async def api_map(user: dict = CurrentUser):
    import campus_map
    return {"campuses": campus_map.campuses() if campus_map.enabled() else []}


@router.get("/api/map/find")
async def api_map_find(q: str = "", user: dict = CurrentUser):
    return {"rooms": _on().find(q[:40])}


@router.get("/api/map/route")
async def api_map_route(campus: str, src: str, dst: str, lift: bool = False, user: dict = CurrentUser):
    found = _on().route(campus, src, dst, lift=lift)
    if not found:
        raise HTTPException(status_code=404, detail="маршрут не найден")
    return found


@router.get("/api/map/{cid}")
async def api_map_campus(cid: str, user: dict = CurrentUser):
    data = _on().campus(cid)
    if not data:
        raise HTTPException(status_code=404, detail="нет такого корпуса")
    return data
