"""Автопилот: план «что сделать и когда» (autopilot.py, autopilot_data.py).

GET  /api/plan            — план на две недели (кэш 15 минут, ?fresh=1 — заново)
POST /api/plan/prefs      — свои настройки: до скольки, сколько в день, цели
POST /api/plan/done       — «сделал» + сколько заняло (план учится)
POST /api/plan/whatif     — «что если пропущу лекцию»

Решатель — CP-SAT, работает до пары секунд и держит процессор, поэтому
зовётся в отдельном потоке (asyncio.to_thread): бот в это время отвечает.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_SECONDS = 15 * 60
_cache: dict[int, tuple[float, dict, dict]] = {}     # user → (когда, входы, ответ)
_locks: dict[int, asyncio.Lock] = {}


def _now() -> datetime:
    from schedule_events import TZ
    return datetime.now(TZ)


def forget(user_id: int):
    _cache.pop(user_id, None)


async def _cookie(user_id: int) -> str | None:
    from sdo_accounts import cookie_for
    try:
        return await cookie_for(user_id)
    except Exception as e:
        logger.info(f"автопилот: вход СДО: {e}")
        return None


def _days(res: dict, prefs: dict, now: datetime) -> list[dict]:
    """Нагрузка на 7 дней вперёд — для столбиков недели."""
    out = []
    for d in range(7):
        day = now.date() + timedelta(days=d)
        light = day.weekday() in prefs.get("light_weekdays", [])
        out.append({"date": day.isoformat(), "minutes": res.get("load", {}).get(day.isoformat(), 0),
                    "cap": prefs["light_max_min"] if light else prefs["max_day_min"], "light": light})
    return out


async def _build(user_id: int, fresh: bool = False) -> tuple[dict, dict]:
    import autopilot as ap
    import autopilot_data
    hit = _cache.get(user_id)
    if hit and not fresh and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1], hit[2]
    lock = _locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        hit = _cache.get(user_id)
        if hit and not fresh and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1], hit[2]
        now = _now()
        inputs = await autopilot_data.gather(user_id, await _cookie(user_id), now)
        wins = ap.windows(inputs["busy"], inputs["prefs"], now)
        inputs = dict(inputs, wins=wins, now=now)
        t0 = time.monotonic()
        res = await asyncio.to_thread(ap.solve, inputs["tasks"], inputs["courses"], wins, inputs["prefs"], now)
        took = round(time.monotonic() - t0, 2)
        if not res.get("ok"):
            logger.warning(f"автопилот: решатель не нашёл план ({res.get('status')})")
        out = dict(res, took=took, updated=int(time.time()), sdo=inputs["sdo"], prefs=inputs["prefs"],
                   days=_days(res, inputs["prefs"], now), lectures=inputs["lectures"],
                   free_minutes=sum((w.end - w.start) * ap.SLOT for w in wins))
        _cache[user_id] = (time.time(), inputs, out)
        return inputs, out


@router.get("/api/plan")
async def api_plan(fresh: bool = False, user: dict = CurrentUser):
    _, out = await _build(user["id"], fresh)
    return out


class Prefs(BaseModel):
    day_start: str | None = None
    day_end: str | None = None
    max_day_min: int | None = None
    light_max_min: int | None = None
    light_weekdays: list[int] | None = None
    goals: dict[str, str] | None = None


def _check_prefs(p: dict) -> str:
    import autopilot as ap
    for k in ("day_start", "day_end"):
        if k in p:
            try:
                h, m = ap._hm(p[k])
            except ValueError:
                return "время — в виде 09:00"
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return "время — в виде 09:00"
    if "day_start" in p and "day_end" in p and p["day_start"] >= p["day_end"]:
        return "конец дня должен быть позже начала"
    for k in ("max_day_min", "light_max_min"):
        if k in p and not (0 <= p[k] <= 12 * 60):
            return "в день — от 0 до 12 часов"
    if "light_weekdays" in p and not all(0 <= d <= 6 for d in p["light_weekdays"]):
        return "дни недели — от 0 (пн) до 6 (вс)"
    return ""


@router.post("/api/plan/prefs")
async def api_plan_prefs(body: Prefs, user: dict = CurrentUser):
    import autopilot_data
    changes = body.model_dump(exclude_none=True)
    prefs = await autopilot_data.get_prefs(user["id"])
    why = _check_prefs({**{k: prefs[k] for k in ("day_start", "day_end")}, **changes})
    if why:
        raise HTTPException(status_code=400, detail=why)
    prefs = await autopilot_data.set_prefs(user["id"], changes)
    forget(user["id"])
    return {"ok": True, "prefs": prefs}


class Done(BaseModel):
    key: str
    kind: str = "deadline"
    planned: int = 0
    minutes: int | None = None       # сколько заняло на самом деле (не ответил — None)


@router.post("/api/plan/done")
async def api_plan_done(body: Done, user: dict = CurrentUser):
    """Сделал: дело уходит из плана, а «сколько заняло» учит оценку времени.
    Дедлайн группы заодно отмечается выполненным (как галочка в «Дедлайнах»)."""
    import autopilot_data
    if not (body.key.startswith("sdo:") or body.key.startswith("dl:")) or len(body.key) > 40:
        raise HTTPException(status_code=400, detail="непонятное дело")
    if body.minutes is not None and not (1 <= body.minutes <= 24 * 60):
        raise HTTPException(status_code=400, detail="сколько заняло — от минуты до суток")
    kind = body.kind if body.kind in ("assign", "quiz", "deadline") else "deadline"
    await autopilot_data.log_done(user["id"], body.key, kind, body.planned, body.minutes)
    if body.key.startswith("dl:") and body.key[3:].isdigit():
        from database import mark_deadline_done
        await mark_deadline_done(int(body.key[3:]), user["id"])
    forget(user["id"])
    return {"ok": True}


class WhatIf(BaseModel):
    course: str
    date: str = ""


@router.post("/api/plan/whatif")
async def api_plan_whatif(body: WhatIf, user: dict = CurrentUser):
    """Что если пропущу лекцию: тот же план без баллов за неё."""
    import autopilot as ap
    inputs, _ = await _build(user["id"])
    lect = inputs["lectures"].get(body.course) or []
    pick = next((x for x in lect if x["date"] == body.date), lect[0] if lect else None)
    if not pick:
        raise HTTPException(status_code=404, detail="впереди нет лекций с баллами за посещаемость")
    res = await asyncio.to_thread(ap.what_if_skip, inputs["tasks"], inputs["courses"], inputs["wins"],
                                  inputs["prefs"], inputs["now"], body.course, pick["value"])
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail="не получилось пересчитать — попробуй ещё раз")
    return dict(res, date=pick["date"])
