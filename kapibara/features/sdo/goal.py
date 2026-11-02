"""
Цель по предмету: что нужно, чтобы дойти до зачёта, «3», «4» или «5».

Не расписание и не план по дням — когда делать, человек решает сам
(владелец: «люди делают в тот день, когда есть настроение»). Бот только
считает:
  • сколько баллов не хватает до выбранной оценки и откуда их взять —
    открытые работы текущего контроля (их максимум), посещения лекций
    впереди (attendance.py) и экзамен — «Семестровый контроль», до 40
    (владелец 09.10: без него на «5» «не хватало», хотя пороги — по сумме
    с экзаменом);
  • правило БРС: зачтено не меньше 75 % работ ТК. Зачтена — оценка не ниже
    проходного порога со страницы работы в СДО. Меньше 75 % — экзамена по
    БРС не будет, и баллы почти ничего не решают;
  • итог: «есть», «дойдёшь», «впритык» или «не хватит, даже если сдать всё».

Автомат и экзамен (владелец 09.10, окончательно): итог — баллы за семестр
плюс баллы за экзамен, пороги — отметки курса (40/60/80). Без экзамена —
автомат, но только «3» и «4» («5» автоматом не бывает) и только при 75 %
зачтённых работ ТК. Минимума на экзамене нет: 59 + 1 балл на экзамене — «4».
Максимум за экзамен — max категории «Семестровый контроль» журнала. У зачёта
экзамена нет.

Работы ниже порога («low») и с давно прошедшим сроком («miss», больше
15 дней без оценки) считаем потерянными: пересдачу открывает преподаватель, на неё не рассчитываем.
Своя цель хранится в settings («goals:<id>» → {курс: оценка}); без неё —
первая отметка курса (зачёт или «3»).

Два счёта (владелец 14.10: «дойдёшь до 5/4/3 считать без учёта экзамена»):
пока экзамен впереди, карточка считает «автомат» — только баллы семестра,
отметки без последней («5» автоматом нет), — или «с экзаменом» — сумма с
экзаменом, все отметки. По умолчанию — автомат; выбор — settings
«goal_modes:<id>» → {курс: "auto"|"exam"}.
"""

import json
import math

OPEN = ("todo", "soon", "offline", "wait", "late")   # ещё могут дать баллы и зачёт
# late — срок прошёл, оценки нет, но не больше 15 дней: могли сдать на паре (sdo_grades.GRACE_DAYS)
LOST = ("low", "miss")
TIGHT_MARGIN = 5.0                            # запас меньше — «впритык»
EXAM_POINTS = 40.0                            # «Семестровый контроль 0–40», если в журнале его нет
MODES = ("auto", "exam")                      # счёт цели: автомат или с экзаменом


def exam_info(course: dict) -> tuple[float, float]:
    """(максимум за экзамен, уже получено на нём): категория «Семестровый
    контроль» (или «экзамен») журнала; у экзамена без такой категории — 40.
    У зачёта экзамена нет — (0, 0)."""
    if len(course.get("marks") or []) < 2:
        return 0.0, 0.0
    cats = [c for c in course.get("categories") or []
            if "семестр" in (c.get("name") or "").lower() or "экзам" in (c.get("name") or "").lower()]
    if not cats:
        return EXAM_POINTS, 0.0
    return (sum(float(c.get("max") or 0) for c in cats),
            sum(min(float(c.get("max") or 0), float(c.get("score") or 0)) for c in cats))


def exam_left(course: dict) -> float:
    """Сколько ещё можно получить на экзамене (у зачёта — 0)."""
    top, got = exam_info(course)
    return max(0.0, top - got)


def final_mark(marks: list[dict], semester: float, exam: float | None = None, tk_ok: bool = True) -> str | None:
    """Отметка по правилам БРС. exam — баллы за сданный экзамен: тогда по
    сумме, минимума нет (59 + 1 → «4»). exam None — автомат: только при 75 %
    зачтённых работ и не выше предпоследней отметки («5» автоматом нет).
    None — отметки нет."""
    if exam is None:
        if not tk_ok:
            return None
        marks = marks[:-1] if len(marks) > 1 else marks
    total = semester + (exam or 0)
    got = [m for m in marks if total >= float(m["at"])]
    return got[-1]["label"] if got else None


async def get_goals(user_id: int, key: str = "goals") -> dict[str, str]:
    from database import get_setting
    try:
        data = json.loads(await get_setting(f"{key}:{user_id}") or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


async def get_modes(user_id: int) -> dict[str, str]:
    """Счёт цели по курсам: "auto" — автомат, "exam" — с экзаменом."""
    return await get_goals(user_id, "goal_modes")


async def set_goal(user_id: int, course_id: int, label: str | None, key: str = "goals") -> dict[str, str]:
    from database import set_setting
    from locks import lock
    async with lock(key, user_id):           # две цели подряд по разным предметам — сохраняются обе
        goals = await get_goals(user_id, key)
        if label:
            goals[str(course_id)] = label
        else:
            goals.pop(str(course_id), None)
        await set_setting(f"{key}:{user_id}", json.dumps(goals, ensure_ascii=False))
    return goals


async def set_mode(user_id: int, course_id: int, mode: str) -> dict[str, str]:
    return await set_goal(user_id, course_id, mode if mode in MODES else None, "goal_modes")


def _status(score: float, at: float, best: float, tk: dict, auto: bool = True) -> str:
    """auto — цель можно получить без экзамена (зачёт, «3», «4», экзамен уже
    сдан); «5» до экзамена «есть» не бывает."""
    if score >= at and tk["ok"] and auto:
        return "done"
    if best < at or not tk["reachable"]:
        return "no"
    if best - at < TIGHT_MARGIN or (tk["left"] and tk["left"] >= tk["open"]):
        return "tight"          # мало запаса по баллам или зачесть нужно все открытые
    return "ok"


def plan(course: dict, attendance: dict | None = None, label: str | None = None,
         mode: str | None = None) -> dict:
    """course — ответ sdo_grades.course_detail (работы со статусами),
    attendance — attendance.for_course или None, mode — "auto" или "exam"
    (пока экзамен впереди; без него — автомат)."""
    all_marks = course.get("marks") or [{"at": 40, "label": "3"}]
    score = float(course.get("score") or 0)
    exam_max, exam_got = exam_info(course)
    exam = max(0.0, exam_max - exam_got)
    # экзамен ещё впереди — автомат и экзамен считаем отдельно
    pending = len(all_marks) >= 2 and exam > 0 and not exam_got
    mode = (mode if mode in MODES else "auto") if pending else None
    marks = all_marks[:-1] if mode == "auto" else all_marks
    mark = next((m for m in marks if m["label"] == label), None)
    if mark is None and mode == "auto" and label == all_marks[-1]["label"]:
        mark = marks[-1]                 # цель «5» в счёте автомата — лучшая автоматом
    mark = mark or marks[0]
    at = float(mark["at"])
    works = course.get("works") or []
    open_ = [w for w in works if w.get("status") in OPEN]
    lost = [w for w in works if w.get("status") in LOST]
    open_points = sum(float(w.get("max") or 0) for w in open_)
    att_ok = bool(attendance and attendance.get("ok"))
    att_left = float(attendance.get("can_get") or 0) if att_ok else 0.0
    semester_best = score + open_points + att_left
    exam_in = 0.0 if mode == "auto" else exam
    best = semester_best + exam_in

    total = len(works)
    passed = sum(1 for w in works if w.get("status") == "ok")
    need = math.ceil(total * float(course.get("pass_share") or 0.75)) if total else 0
    left = max(0, need - passed)
    tk = {"total": total, "passed": passed, "need": need, "left": left, "open": len(open_),
          "ok": passed >= need, "reachable": len(open_) >= left}

    auto_ok = not pending or mark is not all_marks[-1]
    with_exam = mode == "exam"

    out = {
        "label": mark["label"], "at": at, "own": bool(label) and mark["label"] == label,
        "marks": [m["label"] for m in marks], "mode": mode,
        "score": round(score, 2), "need": round(max(0.0, at - score), 2),
        "open_points": round(open_points, 2), "open_count": len(open_),
        "attendance_left": round(att_left, 2), "exam_left": round(exam_in, 2), "best": round(best, 2),
        "lost_count": len(lost), "lost_points": round(sum(float(w.get("max") or 0) for w in lost), 2),
        "tk": tk, "status": _status(score, at, best, tk, auto_ok),
        "exam_pending": pending, "exam_max": round(exam_max, 2),
        # какая отметка автоматом: уже есть / можно добрать работами и лекциями
        "auto": final_mark(all_marks, score, None, tk["ok"]) if pending else None,
        "auto_best": final_mark(all_marks, semester_best, None, tk["reachable"]) if pending else None,
        "auto_ok": auto_ok,
        # с экзаменом: сколько нужно на экзамене для цели при нынешних баллах
        # (минимума нет, больше максимума экзамена не бывает); exam_short —
        # сколько не хватит даже с полным экзаменом: добирать работами и лекциями
        "need_exam": round(min(exam, max(0.0, at - score)), 2) if with_exam else 0,
        "exam_short": round(max(0.0, at - score - exam), 2) if with_exam else 0,
    }
    # прогноз без процентов (14.10): какие открытые работы нельзя пропустить —
    # без любой из них цель уже не набрать (баллами или правилом 75 %)
    if out["status"] in ("ok", "tight"):
        must = [w for w in open_
                if best - float(w.get("max") or 0) < at or len(open_) - 1 < left]
        out["must"] = [str(w.get("name") or "") for w in must]
    # «что если пропущу лекцию»: минус одна лекция из того, что дают посещения
    future = [x for x in (attendance or {}).get("lectures") or [] if x.get("status") == "future"]
    if att_ok and future and attendance.get("unit"):
        unit = min(float(attendance["unit"]), att_left)
        out["skip"] = {"value": round(unit, 2), "date": future[0]["date"],
                       "status": _status(score, at, best - unit, tk, auto_ok)}
    return out
