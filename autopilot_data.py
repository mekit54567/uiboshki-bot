"""
Входы автопилота (autopilot.py) из того, что бот уже знает о человеке:
пары → занятые часы, работы СДО → задачи со сроками и баллами (у теста —
«Ограничение по времени»), дедлайны группы без СДО, посещения впереди
(attendance.py), цели по предметам и свои настройки. Плюс обучение: сколько
на самом деле заняли сделанные работы — множитель к оценке времени.
"""

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timedelta

import autopilot as ap

logger = logging.getLogger(__name__)

_CMID = re.compile(r"/mod/(assign|quiz)/view\.php\?id=(\d+)")


async def get_prefs(user_id: int) -> dict:
    from database import get_setting
    try:
        mine = json.loads(await get_setting(f"autopilot:{user_id}") or "{}")
    except ValueError:
        mine = {}
    return {**ap.DEFAULT_PREFS, **mine, "goals": {**ap.DEFAULT_PREFS["goals"], **mine.get("goals", {})}}


async def set_prefs(user_id: int, changes: dict) -> dict:
    from database import set_setting
    prefs = await get_prefs(user_id)
    for k in ("day_start", "day_end", "max_day_min", "light_max_min", "light_weekdays"):
        if k in changes:
            prefs[k] = changes[k]
    if "goals" in changes:
        prefs["goals"] = {**prefs["goals"], **{str(k): v for k, v in changes["goals"].items() if v}}
    mine = {k: v for k, v in prefs.items() if v != ap.DEFAULT_PREFS.get(k)}
    await set_setting(f"autopilot:{user_id}", json.dumps(mine, ensure_ascii=False))
    return prefs


async def log_done(user_id: int, key: str, kind: str, planned: int, actual: int | None):
    from database._conn import connect
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO autopilot_log (user_id, key, kind, planned_min, actual_min) "
                         "VALUES (?, ?, ?, ?, ?)", (user_id, key, kind, planned, actual))
        await db.commit()


async def _log(user_id: int) -> list[tuple]:
    from database._conn import connect
    async with connect() as db:
        return await (await db.execute(
            "SELECT key, kind, planned_min, actual_min, at FROM autopilot_log WHERE user_id=?", (user_id,))).fetchall()


def multipliers(log: list[tuple]) -> dict[str, float]:
    """Во сколько раз у человека работы идут дольше/быстрее, чем закладывали:
    медиана фактическое/план по виду работы, от двух ответов, в пределах ×0.5–×3."""
    by: dict[str, list[float]] = {}
    for _, kind, planned, actual, _ in log:
        if planned and actual:
            by.setdefault(kind, []).append(actual / planned)
    out = {}
    for kind, xs in by.items():
        if len(xs) >= 2:
            xs.sort()
            mid = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2
            out[kind] = min(3.0, max(0.5, mid))
    return out


def _goal(course: dict, label: str | None) -> tuple[float, str]:
    marks = course.get("marks") or [{"at": 40, "label": "3"}]
    pick = next((m for m in marks if m["label"] == label), marks[0])
    return float(pick["at"]), pick["label"]


async def gather(user_id: int, cookie: str | None, now: datetime) -> dict:
    """Всё для solve: busy, tasks, courses, prefs (+ ближайшие лекции для «что если»)."""
    import attendance
    import optional_subjects
    from database import get_active_deadlines
    from schedule_parser import fetch_schedule_raw, lessons_for_date
    prefs = await get_prefs(user_id)
    log = await _log(user_id)
    mult = multipliers(log)
    done = {k for k, *_ in log}

    # пары → занятые интервалы (свои предметы по выбору — как у человека)
    busy = {}
    try:
        await optional_subjects.apply_for(user_id)
        raw = await fetch_schedule_raw()
        for d in range(ap.HORIZON_DAYS):
            day = now.date() + timedelta(days=d)
            spans = []
            for les in lessons_for_date(raw, day):
                # «СР» (практика на удалёнке) — без своего времени, окна не занимает
                if les.get("start_iso") and les.get("end_iso") and les.get("kind") != "сам. работа":
                    spans.append((datetime.fromisoformat(les["start_iso"]), datetime.fromisoformat(les["end_iso"])))
            busy[day] = spans
    except Exception as e:
        logger.info(f"автопилот: расписание не загрузилось: {e}")

    tasks: list[ap.Task] = []
    courses: list[ap.Course] = []
    lectures: dict[str, list] = {}
    sdo = "off"
    if cookie:
        import sdo_grades
        from sdo_parser import SdoSessionExpired
        try:
            overview = await sdo_grades.overview(user_id, cookie)
            sdo = "ok"
        except SdoSessionExpired:
            overview, sdo = {}, "expired"
        except Exception as e:
            logger.info(f"автопилот: СДО не ответил: {type(e).__name__}")
            overview, sdo = {}, "down"
        sem = asyncio.Semaphore(3)

        async def detail(c):
            async with sem:
                try:
                    return await sdo_grades.course_detail(user_id, cookie, c["id"])
                except Exception as e:
                    logger.info(f"автопилот: курс {c['id']}: {type(e).__name__}")
                    return None

        for d in await asyncio.gather(*(detail(c) for c in overview.get("courses") or [])):
            if not d:
                continue
            key = str(d["id"])
            goal, label = _goal(d, prefs["goals"].get(key))
            att = None
            try:
                att = await attendance.for_course(user_id, d)
            except Exception as e:
                logger.info(f"автопилот: посещения {key}: {e}")
            att_left = att["can_get"] if att and att.get("ok") else 0.0
            if att and att.get("ok"):
                lectures[key] = [{"date": x["date"], "value": att["unit"]}
                                 for x in att["lectures"] if x["status"] == "future"][:4]
            works = d.get("works") or []
            need = math.ceil(len(works) * d.get("pass_share", 0.75)) - sum(1 for w in works if w.get("status") == "ok")
            courses.append(ap.Course(key, d.get("title") or d.get("name"), float(d.get("score") or 0), goal, label,
                                     attendance_left=float(att_left), tk_need=max(0, need), marks=d.get("marks") or []))
            for w in works:
                if w.get("status") not in ("todo", "soon") or f"sdo:{w['cmid']}" in done:
                    continue
                kind = "quiz" if w.get("module") == "quiz" else "assign"
                base = w.get("time_limit") or ap.DEFAULT_MINUTES[kind]
                tasks.append(ap.Task(
                    f"sdo:{w['cmid']}", w["name"], key, kind, int(round(base * mult.get(kind, 1.0))),
                    points=float(w.get("max") or 0), due=ap.parse_ru_dt(w.get("due", ""), now.tzinfo),
                    opens=ap.parse_ru_dt(w.get("opens", ""), now.tzinfo), tk=True, url=w.get("url", ""),
                    subject=d.get("title") or ""))

    # дедлайны группы: свои и старосты, а из СДО — те, что не попали в работы
    # текущего контроля (или все, если своего входа в СДО нет)
    have = {t.key for t in tasks}
    for dl in await get_active_deadlines(user_id):
        if f"dl:{dl['id']}" in done:
            continue
        desc = (dl.get("description") or "").strip()
        url = desc if desc.startswith("http") else ""      # у СДО и иногда у старосты — ссылка на задание
        cm = _CMID.search(url)
        if cm and (f"sdo:{cm.group(2)}" in have or f"sdo:{cm.group(2)}" in done):
            continue
        try:
            due_day = datetime.fromisoformat(dl["due_date"]).date()
        except (TypeError, ValueError):
            continue
        if not (now.date() <= due_day <= now.date() + timedelta(days=ap.HORIZON_DAYS)):
            continue
        h, mi = ap._hm(dl.get("due_time") or "23:59")
        due = datetime(due_day.year, due_day.month, due_day.day, h, mi, tzinfo=now.tzinfo)
        subj = (dl.get("subject") or "").strip()
        if dl.get("external_id") or url or not desc:
            title, subject = subj or "Дедлайн", ""         # у СДО в subject уже «Практика 2 · Предмет»
        else:
            title, subject = desc, subj
        kind = "quiz" if cm and cm.group(1) == "quiz" else "deadline"
        tasks.append(ap.Task(f"dl:{dl['id']}", title, "", kind,
                             int(round(ap.DEFAULT_MINUTES[kind] * mult.get(kind, 1.0))),
                             due=due, subject=subject, url=url))
    return {"busy": busy, "tasks": tasks, "courses": courses, "prefs": prefs, "lectures": lectures,
            "sdo": sdo}
