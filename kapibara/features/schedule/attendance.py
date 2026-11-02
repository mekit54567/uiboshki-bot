"""
Посещения лекций — из баллов СДО, без Пульса МИРЭА (идея владельца, 04.10:
Пульс прикрыт DDoS-Guard и сервер бота не пускает, а баллы за посещаемость
и так лежат в журнале СДО).

Как СДО МИРЭА считает посещаемость (со слов владельца):
  • баллы (обычно 0–20) ставятся только за лекции; плюсик на практике
    баллов не даёт;
  • все баллы делятся поровну на лекции предмета за семестр;
  • уважительный пропуск («У», «ушка») выбывает из деления: 20 баллов на
    8 лекций — по 2,5, а с одной ушкой — на 7, по 2,857.
Отсюда по сумме S, максимуму M и числу лекций N (из расписания группы)
находим посещённые A и ушки U: S = A · M / (N − U), A + U ≤ прошедших.
Дробный «хвост» (12,67 при 4 баллах за лекцию) — как раз след ушек.

Какие именно лекции — по истории (sdo_history: точка в день): прирост после
лекции — отметка за неё. По одному предмету лекции идут минимум через неделю,
так что прирост ложится на свою лекцию, даже если отметку ставят с
опозданием. До начала истории видно только «сколько», а не «какие».
"""

from datetime import date, datetime, timedelta

TOL = 0.051           # СДО показывает баллы и с одним знаком («3,8» за 3 лекции из 16 = 3,75)
SETTLE_DAYS = 10      # столько ждём отметку после лекции, потом — «пропуск»


def solve(score: float, max_pts: float, total: int, past: int) -> list[tuple[int, int]]:
    """Все (посещено, ушек), при которых сумма сходится: A·M/(N−U) = S."""
    out = []
    for u in range(0, past + 1):
        n = total - u
        if n <= 0:
            break
        unit = max_pts / n
        a = round(score / unit)
        if 0 <= a and a + u <= past and abs(a * unit - score) <= TOL:
            out.append((a, u))
    return out


def _pick(cands: list[tuple[int, int]], prev: tuple[int, int] | None) -> tuple[int, int] | None:
    """Из подходящих — с наименьшим числом ушек; если есть прошлый замер —
    не меньше прошлого (баллы за посещение не отнимают) и ближе к нему."""
    if prev:
        cands = [c for c in cands if c[0] >= prev[0] and c[1] >= prev[1]] or cands
        return min(cands, key=lambda c: (c[1] - prev[1], c[0] - prev[0]), default=None)
    return min(cands, key=lambda c: (c[1], c[0]), default=None)


def lecture_dates(raw: bytes, subject: str, today: date | None = None) -> list[date]:
    """Даты лекций (ЛК) предмета за семестр — из календаря группы."""
    from schedule_events import TZ, _calendar_query
    from schedule_format import _split_kind
    today = today or datetime.now(TZ).date()
    start = datetime.combine(today - timedelta(days=200), datetime.min.time(), TZ)
    end = datetime.combine(today + timedelta(days=200), datetime.min.time(), TZ)
    days = set()
    for comp in _calendar_query(raw).between(start, end):
        title, _, short = _split_kind(str(comp.get("SUMMARY", "")))
        if short != "лк" or title != subject:
            continue
        d = comp.get("DTSTART").dt
        days.add(d.astimezone(TZ).date() if isinstance(d, datetime) else d)
    return sorted(days)


def build(score: float | None, max_pts: float, lectures: list[date],
          history: list[tuple[str, float]], today: date, manual: dict[str, str] | None = None) -> dict:
    """Посещения по предмету: сколько, сколько стоит лекция, какие засчитаны.
    history — [(день, баллы за посещаемость)] по возрастанию дня. manual —
    {день: "ok"|"excused"}: свои отметки человека для лекций до начала
    истории, где по баллам видно только «сколько», а не «какие»."""
    total = len(lectures)
    past_on = lambda d: sum(1 for x in lectures if x <= d)  # noqa: E731
    past = past_on(today)
    base = {"score": score or 0, "max": max_pts, "total": total, "past": past, "left": total - past}
    if not total or not max_pts:
        return dict(base, ok=False, why="в расписании нет лекций по этому предмету")
    pts = [(date.fromisoformat(d), s) for d, s in history if s is not None]
    if score is not None and (not pts or pts[-1][0] != today):
        pts.append((today, float(score)))
    pts = [(d, s) for d, s in pts if d <= today]

    status: dict[date, str] = {}
    prev, prev_day = None, None
    baseline = None
    for d, s in pts:
        cur = _pick(solve(s, max_pts, total, past_on(d)), prev)
        if cur is None:
            return dict(base, ok=False, why="баллы не делятся на лекции поровну — "
                        "похоже, у преподавателя свой подсчёт")
        if prev is None:
            baseline = (d, cur)
            p0 = past_on(d)
            for x in lectures:
                if x <= d:
                    if cur == (0, 0) and p0 and (d - x).days <= SETTLE_DAYS:
                        continue        # первый замер — ноль: свежие лекции ещё «ждём отметку», не «Н»
                    status[x] = "ok" if cur == (p0, 0) else "before"
        else:
            da, du = cur[0] - prev[0], cur[1] - prev[1]
            if da > 0 or du > 0:
                # прирост — за ещё не засчитанные лекции до этого дня: сперва
                # прошедшие после прошлого замера (отметку обычно ставят в
                # ближайшие дни), потом более старые — с опозданием, от новых
                open_ = [x for x in lectures if x <= d and status.get(x) is None]
                new_ = [x for x in open_ if x > prev_day]
                order = sorted(new_) + sorted((x for x in open_ if x not in new_), reverse=True)
                # не хватило — значит, отметили лекции ещё до начала истории
                order += sorted((x for x in lectures if status.get(x) == "before"), reverse=True)
                for x in order[:da]:
                    status[x] = "ok"
                for x in order[da:da + du]:
                    status[x] = "excused"
        prev, prev_day = cur, d

    a, u = prev if prev else (0, 0)
    # лекции до начала истории: сколько из них засчитано — знаем, какие — нет.
    # Человек отмечает сам, но не больше, чем видно по баллам; когда все
    # отметки расставлены, остальные — пропуски («Н»).
    left_ok, left_ex = (baseline[1] if baseline else (0, 0))
    marked = set()
    for x in lectures:
        if status.get(x) != "before":
            continue
        m = (manual or {}).get(x.isoformat())
        if m == "ok" and left_ok > 0:
            status[x], left_ok = "ok", left_ok - 1
            marked.add(x)
        elif m == "excused" and left_ex > 0:
            status[x], left_ex = "excused", left_ex - 1
            marked.add(x)
    if not left_ok and not left_ex:
        for x in lectures:
            if status.get(x) == "before":
                status[x] = "miss"
    lect = []
    for i, x in enumerate(lectures):
        st = status.get(x)
        if x > today:
            st = "future"
        elif st is None:
            # баллов ещё нет совсем («-» в журнале) — отметок не ставили, пропусков не знаем
            st = "wait" if (today - x).days <= SETTLE_DAYS or not pts else "miss"
        lect.append({"date": x.isoformat(), "n": i + 1, "status": st, "manual": x in marked})
    unit = max_pts / (total - u) if total > u else 0
    out = dict(base, ok=True, score=round(score or 0, 2), attended=a, excused=u,
               unit=round(unit, 3), waiting=sum(1 for x in lect if x["status"] == "wait"),
               can_get=round(min(max_pts - (score or 0), (total - past) * unit), 2),
               since=pts[0][0].isoformat() if pts else None, lectures=lect)
    if baseline and baseline[1] != (past_on(baseline[0]), 0):
        d0, (a0, u0) = baseline
        out["before"] = {"day": d0.isoformat(), "past": past_on(d0), "attended": a0, "excused": u0,
                         "left_ok": left_ok, "left_excused": left_ex}
    return out


async def for_course(user_id: int, course: dict, manual: dict[str, str] | None = None) -> dict | None:
    """Посещения для экрана предмета: course — ответ /api/sdo/grades/{id}.
    None — у предмета нет строки «Посещаемость» или его нет в расписании."""
    from database import get_attendance_marks, get_attendance_points
    from schedule_events import TZ
    from schedule_parser import fetch_schedule_raw, get_group_subjects
    from sdo_files import match_subject
    from sdo_parser import SEMESTER_WINDOW
    cat = next((k for k in course.get("categories") or [] if "посещ" in (k.get("name") or "").lower()), None)
    if not cat or not cat.get("max"):
        return None
    subjects = await get_group_subjects(**SEMESTER_WINDOW)
    subject = match_subject(course.get("name") or "", subjects)
    if subject not in subjects:
        return None
    today = datetime.now(TZ).date()
    lectures = lecture_dates(await fetch_schedule_raw(), subject, today)
    since = (today - timedelta(days=200)).isoformat()
    history = await get_attendance_points(user_id, course["id"], since)
    if manual is None:
        manual = await get_attendance_marks(user_id, course["id"])
    score = cat.get("score") if cat.get("set", True) else None     # «-» у преподавателя ≠ 0 баллов
    res = dict(build(score, float(cat["max"]), lectures, history, today, manual), subject=subject)
    marks, state = await _pulse(user_id, subject, subjects)
    return with_pulse(res, marks, state, today)


async def _pulse(user_id: int, subject: str, subjects: list[str]) -> tuple[dict[str, str], str]:
    """Отметки Пульса по лекциям предмета и состояние входа (pulse_accounts)."""
    import pulse_accounts
    import pulse_attendance
    from sdo_files import match_subject
    rows = await pulse_attendance.stored(user_id)
    state = (await pulse_accounts.status_for(user_id)).get("state", "off")
    return pulse_attendance.lecture_marks(rows, subject, lambda n: match_subject(n, subjects)), state


def with_pulse(res: dict, marks: dict[str, str], state: str, today: date) -> dict:
    """Пульс поверх баллов СДО (Никита 01.11): что сказал Пульс — то и есть,
    своих отметок там нет. Пульс подключён — свои «?» не нужны вовсе
    (непроверенные лекции ждут Пульс). Отвалился — сказанное Пульсом остаётся,
    остальное — по СДО, как раньше."""
    if not res.get("ok"):
        return dict(res, source="sdo")
    live = state == "ok"
    if not marks and not live:
        return dict(res, source="sdo")
    lect = []
    for x in res["lectures"]:
        st = marks.get(x["date"])
        if st and x["date"] <= today.isoformat():
            x = dict(x, status=st, manual=False, pulse=True)
        elif live and x["status"] == "before":
            x = dict(x, status="wait", manual=False)
        lect.append(x)
    out = dict(res, lectures=lect, source="pulse" if live else "pulse_lost",
               attended=sum(1 for x in lect if x["status"] == "ok"),
               excused=sum(1 for x in lect if x["status"] == "excused"),
               waiting=sum(1 for x in lect if x["status"] == "wait"))
    if live or not any(x["status"] == "before" for x in lect):
        out.pop("before", None)
    return out


def check_mark(blank: dict | None, marks: dict[str, str], day: str, mark: str | None) -> str:
    """Можно ли поставить свою отметку: blank — посещения без своих отметок,
    marks — уже поставленные. «» — можно, иначе — почему нет."""
    if not blank or not blank.get("ok"):
        return "по этому предмету посещения не посчитать"
    if mark not in (None, "ok", "excused"):
        return "неизвестная отметка"
    before = {x["date"] for x in blank["lectures"] if x["status"] == "before"}
    if day not in before:
        return "эту лекцию бот отмечает сам — по баллам"
    if mark is None:
        return ""
    quota = blank["before"]["attended" if mark == "ok" else "excused"]
    used = sum(1 for d, m in marks.items() if m == mark and d in before and d != day)
    if used >= quota:
        return (f"по баллам посещено только {quota} — сначала сними плюсик с другой лекции" if mark == "ok"
                else f"по баллам уважительных пропусков {quota}")
    return ""

