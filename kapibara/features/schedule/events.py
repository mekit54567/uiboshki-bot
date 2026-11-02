"""Разбор ical: события дня, пары структурой (для WebApp), номер недели,
обзор недель, сводка по найденному преподавателю/группе/аудитории. Без сети:
на входе — байты календаря."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events

from optional_subjects import unfiltered
from schedule_format import TZ, _merge_runs, _short_teacher, _split_kind


TEACHER_RE = re.compile(r"Преподаватель:\s*([^\n\\]+)")


def _extract_teacher(component) -> str:
    """Имя преподавателя зашито в DESCRIPTION у пар типа ЛК/ПР
    ("Преподаватель: Фамилия Имя Отчество\n..."). У "СР"/доп. занятий
    его может не быть вовсе — тогда просто пустая строка."""
    desc = str(component.get("DESCRIPTION", ""))
    m = TEACHER_RE.search(desc)
    return m.group(1).strip() if m else ""


def _extract_groups(component) -> str:
    """У ical преподавателя/аудитории в DESCRIPTION — группы ("КСБО-11-26
    1 п/г"), а не "Преподаватель: …" как у ical группы."""
    desc = str(component.get("DESCRIPTION", ""))
    if TEACHER_RE.search(desc):
        return ""
    parts = [p.strip() for p in re.split(r"\\n|\n", desc) if p.strip()]
    return ", ".join(parts)


# Код группы МИРЭА: «УИБО-03-24», «КСБО-11-26» (подгруппа «1 п/г» — отдельно)
GROUP_CODE_RE = re.compile(r"[А-ЯЁA-Z]{2,6}-\d{2}-\d{2}")


def groups_at(ical_data: bytes, when: datetime) -> list[str]:
    """Чьи пары идут в момент when по календарю аудитории или преподавателя:
    коды групп из DESCRIPTION, по порядку и без повторов. Так экран пары
    показывает, с кем она общая (поток на лекции), — в календаре своей
    группы других групп нет."""
    out: list[str] = []
    for comp in _calendar_query(ical_data).at(when.astimezone(TZ).date()):
        start, end = comp.get("DTSTART"), comp.get("DTEND")
        if not start or not end or not isinstance(start.dt, datetime) or not isinstance(end.dt, datetime):
            continue
        s, e = start.dt, end.dt
        if s.tzinfo is None:
            s = s.replace(tzinfo=ZoneInfo("Europe/Moscow"))
        if e.tzinfo is None:
            e = e.replace(tzinfo=ZoneInfo("Europe/Moscow"))
        if not s <= when < e:
            continue
        for code in GROUP_CODE_RE.findall(str(comp.get("DESCRIPTION", ""))):
            if code not in out:
                out.append(code)
    return out


# Разобранный календарь последних ical-байт: Calendar.from_ical + разворот
# повторов — чистый CPU в event loop. get_group_subjects дёргал разбор 42 раза
# подряд (1,6 с блокировки всего бота на каждый /solve и /upload), главная
# WebApp — ещё дважды на запрос. Кэш по самим байтам (кэш fetch_schedule_raw
# отдаёт тот же объект, пока не протухнет) — чужие ical (поиск препода)
# просто вытесняют его, ничего не ломая.
_parsed_cal: tuple[bytes, object] | None = None


def _calendar_query(ical_data: bytes):
    global _parsed_cal
    if _parsed_cal is None or _parsed_cal[0] is not ical_data and _parsed_cal[0] != ical_data:
        _parsed_cal = (ical_data, recurring_ical_events.of(Calendar.from_ical(ical_data)))
    return _parsed_cal[1]


def parse_events_for_date(ical_data: bytes, target: date) -> list[dict]:
    events_raw = _calendar_query(ical_data).at(target)
    events = []

    from optional_subjects import HIDE
    hide = HIDE.get()
    for component in events_raw:
        summary = str(component.get("SUMMARY", "Без названия"))
        if summary.strip().endswith("неделя"):
            continue
        if hide and _split_kind(summary)[0] in hide:
            continue   # предмет по выбору, на который человек не ходит

        location = str(component.get("LOCATION", ""))
        teacher  = _extract_teacher(component)
        groups   = _extract_groups(component)
        dtstart  = component.get("DTSTART")
        dtend    = component.get("DTEND")

        time_str = ""
        time_start = None
        time_end = None
        if dtstart:
            t = dtstart.dt
            if isinstance(t, datetime):
                if t.tzinfo is None:
                    t = t.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                t_msk = t.astimezone(TZ)
                time_start = t_msk
                time_str = t_msk.strftime("%H:%M")
                if dtend:
                    te = dtend.dt
                    if isinstance(te, datetime):
                        if te.tzinfo is None:
                            te = te.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                        te_msk = te.astimezone(TZ)
                        time_end = te_msk
                        time_str += "–" + te_msk.strftime("%H:%M")

        events.append({
            "summary":    summary,
            "time":       time_str,
            "time_start": time_start,
            "time_end":   time_end,
            "location":   location,
            "teacher":    teacher,
            "groups":     groups,
        })

    events.sort(key=lambda e: e["time"] or "99:99")
    return events


def lessons_for_date(raw: bytes, target: date, now: datetime | None = None) -> list[dict]:
    """Пары дня структурой (для WebApp, который рисует их сам, а не
    вставляет готовый HTML бота): номер по звонку, время, название, тип,
    аудитория, преподаватель, статус past/now/later (при заданном now)."""
    out = []
    for r in _merge_runs(parse_events_for_date(raw, target)):
        title, kind, _ = _split_kind(r["summary"])
        status = ""
        if now and r.get("time_start"):
            end = r.get("time_end") or r["time_start"]
            status = "now" if r["time_start"] <= now < end else ("past" if end <= now else "later")
        out.append({
            "num": r["first"] if r["first"] == r["last"] else f"{r['first']}–{r['last']}",
            "pairs": r["last"] - r["first"] + 1,
            "start": r["start_str"], "end": r["end_str"],
            "title": title, "kind": kind,
            "room": r.get("location") or "", "teacher": _short_teacher(r.get("teacher") or ""),
            "groups": r.get("groups") or "",   # у преподавателя и аудитории — чьи это пары
            "status": status,
            "start_iso": r["time_start"].isoformat() if r.get("time_start") else None,
            "end_iso": r["time_end"].isoformat() if r.get("time_end") else None,
            **({"parts": [[a.isoformat(), b.isoformat()] for a, b in r["parts"] if a and b]}
               if r["last"] > r["first"] and all(a and b for a, b in r["parts"]) else {}),
        })
    return out


_WEEK_RE = re.compile(r"^\s*(\d{1,2})\s*неделя\s*$", re.I)


def week_number(raw: bytes, target: date) -> int | None:
    """Номер учебной недели: в ical МИРЭА есть события на весь день
    «4 неделя» (в расписание пар они не попадают — см. parse_events_for_date)."""
    for component in _calendar_query(raw).at(target):
        m = _WEEK_RE.match(str(component.get("SUMMARY", "")))
        if m:
            return int(m.group(1))
    return None


def week_overview(raw: bytes, monday: date, days: int = 6) -> dict:
    """Для полоски дней в WebApp: номер недели и по точке на каждую пару
    дня (тип пары — для цвета), как в официальном приложении МИРЭА."""
    out, num = [], None
    for i in range(days):
        d = monday + timedelta(days=i)
        num = num or week_number(raw, d)
        dots = []
        for lesson in lessons_for_date(raw, d):
            dots += [lesson["kind"]] * lesson["pairs"]
        out.append({"date": d.isoformat(), "dots": dots})
    return {"week": num, "days": out}


@unfiltered
def target_weeks(raw: bytes, first_monday: date, weeks: int = 8, now: datetime | None = None) -> list[dict]:
    """Расписание найденной группы/преподавателя/аудитории по неделям для
    WebApp — сразу на weeks недель одним ответом (разбор ~0,1 с), чтобы
    листать недели без запросов. Как у главной: номер недели и пары по дням."""
    out = []
    for w in range(weeks):
        monday = first_monday + timedelta(weeks=w)
        days, num = [], None
        for i in range(7):   # воскресенье тоже: бывают и в этот день (WebApp покажет его, только если есть пары)
            d = monday + timedelta(days=i)
            num = num or week_number(raw, d)
            days.append({"date": d.isoformat(),
                         "lessons": lessons_for_date(raw, d, now=now if now and d == now.date() else None)})
        out.append({"monday": monday.isoformat(), "week": num, "days": days})
    return out


@unfiltered
def summarize_target(raw: bytes, days: int = 14) -> tuple[str, int]:
    """(главный предмет, сколько пар) за days дней вперёд — подпись, чтобы
    отличить однофамильцев: в справочнике МИРЭА у преподавателей только
    инициалы, и «Морозов В. А.» бывает трижды."""
    from collections import Counter
    today = datetime.now(TZ).date()
    subjects: Counter = Counter()
    pairs = 0
    for i in range(days):
        for e in parse_events_for_date(raw, today + timedelta(days=i)):
            title, _, _ = _split_kind(e["summary"])
            subjects[title] += 1
            pairs += 1
    return (subjects.most_common(1)[0][0] if subjects else ""), pairs


def list_upcoming_events(raw: bytes, days_ahead: int = 14) -> list[dict]:
    """Плоский список всех пар на ближайшие days_ahead дней из произвольного
    ical (не обязательно своей группы — годится и для чужого препода/
    аудитории, полученных через mirea_schedule_api.fetch_ical)."""
    today = datetime.now(TZ).date()
    results = []
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        for e in parse_events_for_date(raw, d):
            results.append({**e, "date": d})
    return results
