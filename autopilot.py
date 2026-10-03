"""
Автопилот семестра: что сделать и когда, чтобы закрыть сессию.

Бот и так знает почти всё: пары (свободные окна между ними), работы
текущего контроля со сроками и баллами (СДО), дедлайны группы, сколько ещё
лекций и почём каждая (attendance.py), пороги «зачёт / 3 / 4 / 5». Не хватало
одного — сложить это в план. Это задача составления расписания, и решает её
не перебор руками, а CP-SAT из Google OR-Tools — решатель ограничений, тот же
класс, что расписывает станки на заводах и самолёты в аэропортах.

Модель (solve):
  • время — слоты по 15 минут на HORIZON_DAYS вперёд;
  • каждая работа × каждое окно, куда она влезает до срока, — необязательный
    интервал (optional interval) со своим «флажком»; у работы не больше
    одного флажка — либо она в плане ровно в одном окне, либо её нет;
  • NoOverlap — дела не налезают друг на друга и между ними 15 минут
    передышки (пары уже вырезаны из окон);
  • на день — не больше max_day_min минут, в «лёгкие» дни — light_max_min;
  • по каждому предмету: недобор до цели = цель − баллы − посещения впереди −
    баллы запланированных работ (не меньше нуля); плюс правило БРС: зачтено
    ≥ 75 % работ текущего контроля.
Цель — лексикографическая, в две фазы:
  1) минимум недоборов (сначала — правило 75 %, потом баллы, потом дедлайны
     без баллов);
  2) при этом же минимуме — побольше полезных работ, пораньше (запас до
     срока) и ровнее по дням (минимум самого тяжёлого дня).
Вторая фаза стартует с подсказок (AddHint) из первой — решатель не ищет
заново то, что уже нашёл.

Здесь — только математика (без сети и базы), сбор данных и API — в
webapp/routes/plan.py, «что если» — тот же solve с изменёнными входами.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

SLOT = 15                 # минут в слоте
HORIZON_DAYS = 14
MIN_WINDOW = 30           # окна короче — не окна
SAFETY_H = 48             # закончить за двое суток до срока — запас на «что-то пошло не так»
BREAK = 1                 # слот передышки после каждого дела: два дела подряд — не впритык
DEFAULT_MINUTES = {"assign": 90, "quiz": 30, "deadline": 60}
DEFAULT_PREFS = {"day_start": "09:00", "day_end": "23:00", "max_day_min": 180,
                 "light_weekdays": [6], "light_max_min": 90, "buffer_min": 10, "goals": {}}


@dataclass
class Task:
    key: str                       # «sdo:<cmid>» или «dl:<id>»
    title: str
    course: str                    # ключ предмета (id курса СДО) или «» для дедлайнов
    kind: str                      # assign | quiz | deadline
    minutes: int
    points: float = 0.0
    due: datetime | None = None
    opens: datetime | None = None
    tk: bool = False               # считается в правиле 75 %
    url: str = ""
    subject: str = ""


@dataclass
class Course:
    key: str
    title: str
    score: float                   # уже набрано
    goal: float                    # порог цели (40, 60, 80…)
    goal_label: str                # «зачёт», «3», «4», «5»
    attendance_left: float = 0.0   # можно ещё получить, если ходить на лекции
    tk_need: int = 0               # сколько ещё работ ТК нужно зачесть
    marks: list = field(default_factory=list)


@dataclass
class Window:
    start: int                     # слоты от полуночи первого дня
    end: int
    day: int


# ── время ─────────────────────────────────────────────────────────────────────

def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def origin_of(today: date, tz) -> datetime:
    return datetime(today.year, today.month, today.day, tzinfo=tz)


def to_slot(dt: datetime, origin: datetime, up: bool = False) -> int:
    mins = (dt - origin).total_seconds() / 60
    return math.ceil(mins / SLOT) if up else math.floor(mins / SLOT)


def from_slot(s: int, origin: datetime) -> datetime:
    return origin + timedelta(minutes=s * SLOT)


_RU_DT = re.compile(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})(?:\D+(\d{1,2}):(\d{2}))?", re.I)


def parse_ru_dt(text: str, tz) -> datetime | None:
    """«среда, 15 октября 2026, 23:59» → datetime (как пишет СДО)."""
    from schedule_format import MONTHS_GEN
    m = _RU_DT.search(text or "")
    if not m or m.group(2).lower() not in MONTHS_GEN:
        return None
    h, mi = (int(m.group(4)), int(m.group(5))) if m.group(4) else (23, 59)
    return datetime(int(m.group(3)), MONTHS_GEN.index(m.group(2).lower()) + 1, int(m.group(1)), h, mi, tzinfo=tz)


def windows(busy_by_day: dict[date, list[tuple[datetime, datetime]]], prefs: dict, now: datetime,
            days: int = HORIZON_DAYS) -> list[Window]:
    """Свободные окна: [начало дня, конец дня] минус пары (с запасом
    buffer_min на дорогу/перемену); сегодня — не раньше «сейчас + 10 мин»."""
    origin = origin_of(now.date(), now.tzinfo)
    buf = timedelta(minutes=prefs.get("buffer_min", 10))
    out = []
    for d in range(days):
        day = now.date() + timedelta(days=d)
        sh, sm = _hm(prefs["day_start"])
        eh, em = _hm(prefs["day_end"])
        ds = datetime(day.year, day.month, day.day, sh, sm, tzinfo=now.tzinfo)
        de = datetime(day.year, day.month, day.day, eh, em, tzinfo=now.tzinfo)
        if d == 0:
            ds = max(ds, now + timedelta(minutes=10))
        cur = ds
        free = []
        for bs, be in sorted(busy_by_day.get(day, [])):
            if bs - buf > cur:
                free.append((cur, min(bs - buf, de)))
            cur = max(cur, be + buf)
        free.append((cur, de))
        for a, b in free:
            s, e = to_slot(a, origin, up=True), to_slot(b, origin)
            if (e - s) * SLOT >= MIN_WINDOW:
                out.append(Window(s, e, d))
    return out


# ── решатель ──────────────────────────────────────────────────────────────────

def _p10(x: float) -> int:
    return int(round((x or 0) * 10))       # баллы — в десятых: CP-SAT работает с целыми


def solve(tasks: list[Task], courses: list[Course], wins: list[Window], prefs: dict, now: datetime,
          time_limit: float = 2.0) -> dict:
    """План: какие работы, в какое окно и когда; недоборы по предметам."""
    from ortools.sat.python import cp_model
    origin = origin_of(now.date(), now.tzinfo)
    horizon = HORIZON_DAYS * 24 * 60 // SLOT
    m = cp_model.CpModel()
    present: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    places = []                         # (task, window, флажок, начало, длина)
    intervals = []
    for t in tasks:
        d = max(1, math.ceil(t.minutes / SLOT))
        due = min(horizon, to_slot(t.due, origin)) if t.due else horizon
        opens = max(0, to_slot(t.opens, origin, up=True)) if t.opens else 0
        lits = []
        end = m.NewIntVar(0, horizon, f"end_{t.key}")
        for w in wins:
            lo, hi = max(w.start, opens), min(w.end, due) - d
            if hi < lo:
                continue
            lit = m.NewBoolVar(f"at_{t.key}_{w.start}")
            s = m.NewIntVar(lo, hi, f"s_{t.key}_{w.start}")
            # интервал для NoOverlap — с передышкой после дела (BREAK), сроки и
            # лимит дня — по самому делу
            intervals.append(m.NewOptionalIntervalVar(s, d + BREAK, s + d + BREAK, lit, f"iv_{t.key}_{w.start}"))
            m.Add(end == s + d).OnlyEnforceIf(lit)
            places.append((t, w, lit, s, d))
            lits.append(lit)
        x = m.NewBoolVar(f"x_{t.key}")
        if lits:
            m.Add(sum(lits) == x)
        else:
            m.Add(x == 0)                 # не влезает ни в одно окно до срока
        m.Add(end == 0).OnlyEnforceIf(x.Not())
        present[t.key], ends[t.key] = x, end
    m.AddNoOverlap(intervals)

    # нагрузка по дням: не больше лимита; сверх «комфортных» двух третей
    # лимита — штраф за каждый слот (одного «самого тяжёлого дня» мало:
    # срочные дела и так забивают сегодня, и решателю становится всё равно,
    # что остальные дни тоже под завязку)
    overs = []
    for day in range(HORIZON_DAYS):
        terms = [d * lit for (_, w, lit, _, d) in places if w.day == day]
        if not terms:
            continue
        weekday = (now.date() + timedelta(days=day)).weekday()
        cap = prefs["light_max_min"] if weekday in prefs.get("light_weekdays", []) else prefs["max_day_min"]
        m.Add(sum(terms) <= cap // SLOT)
        over = m.NewIntVar(0, cap // SLOT, f"over_{day}")
        m.Add(over >= sum(terms) - (cap * 2 // 3) // SLOT)
        overs.append(over)

    # недоборы по предметам
    shorts, tk_shorts = {}, {}
    for c in courses:
        mine = [t for t in tasks if t.course == c.key]
        gained = sum(_p10(t.points) * present[t.key] for t in mine)
        gap = _p10(c.goal) - _p10(c.score) - _p10(c.attendance_left)
        s = m.NewIntVar(0, max(0, gap), f"short_{c.key}")
        m.Add(s >= gap - gained)
        shorts[c.key] = s
        if c.tk_need > 0:
            tks = [present[t.key] for t in mine if t.tk]
            k = m.NewIntVar(0, c.tk_need, f"tk_{c.key}")
            m.Add(k >= c.tk_need - sum(tks))
            tk_shorts[c.key] = k
    plain = [present[t.key] for t in tasks if not t.points]       # дедлайны без баллов
    zero = m.NewIntVar(0, 0, "zero")      # чтобы цель была выражением даже без предметов и дедлайнов
    phase1 = zero + 1000 * sum(tk_shorts.values()) + 10 * sum(shorts.values()) + 300 * sum(1 - x for x in plain)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 4
    m.Minimize(phase1)
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"ok": False, "status": solver.StatusName(st)}
    best1 = int(round(solver.ObjectiveValue()))
    for v in [*present.values(), *(p[2] for p in places), *(p[3] for p in places)]:
        m.AddHint(v, solver.Value(v))

    # фаза 2: тот же минимум недоборов, а сверх него — польза, запас до срока
    # (закончить за SAFETY_H часов до срока), ровность по дням и только потом
    # «пораньше» — иначе решатель забивает первые дни под завязку
    m.Add(phase1 <= best1)
    value = sum((_p10(t.points) + 5) * present[t.key] for t in tasks)
    late = []
    for t in tasks:
        if t.due:
            soft = to_slot(t.due, origin) - SAFETY_H * 60 // SLOT
            lt = m.NewIntVar(0, horizon, f"late_{t.key}")
            m.Add(lt >= ends[t.key] - soft).OnlyEnforceIf(present[t.key])
            late.append(lt)
    m.Minimize(-100_000 * value + 100 * sum(late) + 300 * sum(overs) + sum(ends.values()))
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"ok": False, "status": solver.StatusName(st)}

    items = []
    for t, w, lit, s, d in places:
        if solver.Value(lit):
            a = from_slot(solver.Value(s), origin)
            items.append({"key": t.key, "title": t.title, "course": t.course, "subject": t.subject,
                          "kind": t.kind, "points": t.points, "minutes": d * SLOT, "url": t.url,
                          "start": a.isoformat(), "end": (a + timedelta(minutes=d * SLOT)).isoformat(),
                          "due": t.due.isoformat() if t.due else None})
    items.sort(key=lambda i: i["start"])
    planned = {c.key: sum(t.points for t in tasks if t.course == c.key and solver.Value(present[t.key])) for c in courses}
    out_courses = []
    for c in courses:
        short = solver.Value(shorts[c.key]) / 10
        tk_short = solver.Value(tk_shorts[c.key]) if c.key in tk_shorts else 0
        projected = round(c.score + c.attendance_left + planned[c.key], 1)
        # done — цель уже набрана; risk — даже по плану не хватает; tight —
        # хватает впритык (запас меньше 5) или только если ходить на лекции
        status = ("done" if c.score >= c.goal and not c.tk_need else
                  "risk" if short > 0 or tk_short > 0 else
                  "tight" if projected - c.goal < 5 or projected - c.attendance_left < c.goal else "ok")
        out_courses.append({"key": c.key, "title": c.title, "score": c.score, "goal": c.goal,
                            "goal_label": c.goal_label, "attendance_left": round(c.attendance_left, 1),
                            "planned": round(planned[c.key], 1), "projected": projected,
                            "short": short, "tk_need": c.tk_need, "tk_short": tk_short, "status": status,
                            "marks": [m["label"] for m in c.marks]})
    load = {}
    for i in items:
        day = i["start"][:10]
        load[day] = load.get(day, 0) + i["minutes"]
    planned_keys = {i["key"] for i in items}
    return {"ok": True, "items": items, "courses": out_courses, "load": load,
            "unplanned": [{"key": t.key, "title": t.title, "course": t.course, "subject": t.subject,
                           "due": t.due.isoformat() if t.due else None, "points": t.points}
                          for t in tasks if t.key not in planned_keys],
            "status": solver.StatusName(st)}


def what_if_skip(tasks, courses, wins, prefs, now, course_key: str, lecture_value: float, **kw) -> dict:
    """«Что если пропущу лекцию»: тот же план, но посещения впереди меньше на
    цену лекции. → разница: какие предметы ухудшатся и что добавится в план."""
    import copy
    base = solve(tasks, courses, wins, prefs, now, **kw)
    alt_courses = copy.deepcopy(courses)
    for c in alt_courses:
        if c.key == course_key:
            c.attendance_left = max(0.0, c.attendance_left - lecture_value)
    alt = solve(tasks, alt_courses, wins, prefs, now, **kw)
    if not (base.get("ok") and alt.get("ok")):
        return {"ok": False}
    b = {c["key"]: c for c in base["courses"]}
    a = {c["key"]: c for c in alt["courses"]}
    before = {i["key"] for i in base["items"]}
    return {"ok": True, "lost": round(lecture_value, 2),
            "course": a.get(course_key),
            "was": b.get(course_key),
            "added": [i for i in alt["items"] if i["key"] not in before],
            "minutes_more": sum(i["minutes"] for i in alt["items"]) - sum(i["minutes"] for i in base["items"])}
