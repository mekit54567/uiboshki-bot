"""
История баллов СДО: при каждом просмотре баллов сумма по каждому предмету
записывается на сегодняшний день (одна точка в день — последняя за день).
На экране предмета — график за семестр и прирост за неделю. Хранится только
сумма баллов, без названий работ и оценок за них.
"""

from datetime import timedelta

from utils import today_msk

KEEP_DAYS = 160          # семестр с запасом


async def record(user_id: int, courses: list[dict]):
    from database import save_score_points
    scores = {c["id"]: float(c["score"]) for c in courses if c.get("id") is not None and c.get("score") is not None}
    if scores:
        await save_score_points(user_id, today_msk().isoformat(), scores)
    # баллы за посещаемость отдельно — по их приросту attendance.py видит,
    # какие лекции засчитаны
    from database import save_attendance_points
    att = {}
    for c in courses:
        cat = next((k for k in c.get("categories") or [] if "посещ" in (k.get("name") or "").lower()), None)
        if c.get("id") is not None and cat and cat.get("max") and cat.get("score") is not None:
            att[c["id"]] = (float(cat["score"]), float(cat["max"]))
    if att:
        await save_attendance_points(user_id, today_msk().isoformat(), att)
    # названия курсов — общим словарём: «Итоги дня» пишут «Анализ данных: +6»
    import day_summary
    await day_summary.remember_courses(courses)


async def series(user_id: int, course_id: int, current: float | None = None) -> dict:
    """{"points": [[день, баллы], …], "week_delta": прирост за 7 дней или None}."""
    from database import get_score_points
    today = today_msk()
    pts = await get_score_points(user_id, course_id, (today - timedelta(days=KEEP_DAYS)).isoformat())
    if current is not None and (not pts or pts[-1][0] != today.isoformat()):
        pts.append((today.isoformat(), float(current)))
    week_ago = (today - timedelta(days=7)).isoformat()
    before = [s for d, s in pts if d <= week_ago]
    base = before[-1] if before else (pts[0][1] if pts and pts[0][0] < today.isoformat() else None)
    delta = round(pts[-1][1] - base, 1) if pts and base is not None else None
    return {"points": [[d, s] for d, s in pts], "week_delta": delta}
