"""
Конструктор уведомлений (WebApp → ☰ Ещё → Уведомления): что присылать и в
какие дни. Хранится JSON в users.notify; чего там нет — берётся из DEFAULTS
(они повторяют старое поведение: всё включено, каждый день). Общий выключатель
— по-прежнему users.subscribed, время напоминания о паре — reminder_minutes.

Корпус: у пар МИРЭА место вида «В-328 (В-78)» — корпус в скобках. «Свой»
корпус группы — самый частый в её календаре; если сегодня пары в другом,
утренняя рассылка подсвечивает это («сегодня пары на МП-1, не на В-78»).
"""

import json
import re
from collections import Counter

ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
REMINDER_CHOICES = (5, 10, 15, 30)      # /settings в чате: одно время на все сценарии

# Напоминание перед парой — по сценарию (минут до начала, 0 — не напоминать):
# первая пара дня, после короткой перемены (10 мин между парами МИРЭА) и
# после большого перерыва (30 мин и больше). Пресеты — кнопки, «своё» — поле.
REMIND = {
    "remind_first": {"title": "Первая пара дня", "presets": [30, 60, 180], "max": 300, "default": 60},
    "remind_short": {"title": "После короткой перемены", "presets": [5], "max": 30, "default": 5},
    "remind_long": {"title": "После большого перерыва", "presets": [5, 10, 15], "max": 120, "default": 10},
}
SHORT_BREAK_MAX = 20   # минут между парами: до стольки — «короткая перемена»

# Вечерняя сводка на завтра (evening_digest.py, Никита 12.10): время — с 17:00
# до 23:30 через полчаса (задача проверяет раз в 30 минут). Выключена у всех,
# пока человек сам не включит; при DESIGN2=0 её нет совсем.
EVENING_TIMES = [f"{h:02d}:{m:02d}" for h in range(17, 24) for m in (0, 30)]

DEFAULTS = {
    "morning": True, "morning_days": ALL_DAYS, "weather": True, "campus": True, "skip_empty": False,
    "lessons": True, "lesson_days": ALL_DAYS,
    **{k: v["default"] for k, v in REMIND.items()},
    "deadlines": True, "deadline_days": ALL_DAYS,
    "weekly": True,          # обзор недели в воскресенье вечером (weekly_digest.py)
    "grades": True,          # новые баллы в СДО (grade_alerts.py)
    "new_tasks": True,       # новые задания из СДО после синка (new_tasks.py)
    "evening": False,        # вечерняя сводка на завтра (evening_digest.py)
    "evening_time": "20:00",
    "quiz_remind": [],       # тесты СДО: за сколько минут до закрытия (quiz_alerts.py), несколько
    "quiz_open": True,       # тесты СДО: «Открыли тест»
    "deadline_soon": True,   # «срок скоро, а ты не сдал» (deadline_soon.py, Никита 25.10)
    "deadline_soon_hours": 3,
    "tg_copy": True,         # пуш дошёл — дублировать ли ещё в Telegram (delivery.deliver, Никита 14.10)
}
# Тесты СДО (quiz_alerts.CHOICES): за 1 день, 3 ч, 1 ч, 30 мин, 10 мин до закрытия
QUIZ_REMIND_CHOICES = (1440, 180, 60, 30, 10)
# «Срок скоро»: за сколько часов до срока, одно время (Никита 25.10: по умолчанию 3)
DEADLINE_SOON_CHOICES = (1, 3, 6, 12, 24)
DAYS_KEY = {"morning": "morning_days", "lessons": "lesson_days", "deadlines": "deadline_days"}
_BOOLS = [k for k, v in DEFAULTS.items() if isinstance(v, bool)]
_DAYS = [k for k in DEFAULTS if k.endswith("_days")]


def merge(raw: str | dict | None) -> dict:
    """Сохранённое поверх умолчаний; мусор и лишние ключи отбрасываются."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    raw = raw if isinstance(raw, dict) else {}
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    for k in _BOOLS:
        if isinstance(raw.get(k), bool):
            out[k] = raw[k]
    for k, spec in REMIND.items():
        v = raw.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= spec["max"]:
            out[k] = v
    v = raw.get("quiz_remind")
    if isinstance(v, list):
        out["quiz_remind"] = sorted({m for m in v if isinstance(m, int) and not isinstance(m, bool)
                                     and m in QUIZ_REMIND_CHOICES}, reverse=True)
    v = raw.get("deadline_soon_hours")
    if isinstance(v, int) and not isinstance(v, bool) and v in DEADLINE_SOON_CHOICES:
        out["deadline_soon_hours"] = v
    if raw.get("evening_time") in EVENING_TIMES:
        out["evening_time"] = raw["evening_time"]
    for k in _DAYS:
        v = raw.get(k)
        if isinstance(v, list):
            out[k] = sorted({d for d in v if isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6})
    return out


def allowed(prefs: dict, kind: str, weekday: int) -> bool:
    """kind: morning / lessons / deadlines — включено и сегодня его день."""
    return bool(prefs.get(kind)) and weekday in prefs.get(DAYS_KEY[kind], [])


async def get(user_id: int) -> dict:
    from database import get_user
    user = await get_user(user_id) or {}
    return merge(user.get("notify"))


def scenario(prev_end, start) -> str:
    """Какой сценарий у пары: первая за день или после перемены (какой)."""
    if prev_end is None:
        return "remind_first"
    gap = (start - prev_end).total_seconds() / 60
    return "remind_short" if gap <= SHORT_BREAK_MAX else "remind_long"


def _join(a: str, b: str) -> str:
    parts = [p for p in (a or "").split(" / ") if p]
    return " / ".join(parts + [b]) if b and b not in parts else (a or b or "")


def _combine_parallel(timed: list[dict]) -> list[dict]:
    """Пары в одно время (подгруппы в разных аудиториях) — одной парой со
    всеми аудиториями: какая подгруппа у человека, бот не знает, а раньше в
    напоминание попадала аудитория первой из них — часто чужая."""
    out: list[dict] = []
    for e in timed:
        prev = out[-1] if out else None
        if prev and e["time_start"] == prev["time_start"] and e.get("time_end") == prev.get("time_end"):
            for k in ("summary", "location", "teacher"):
                prev[k] = _join(prev.get(k, ""), e.get(k, ""))
            continue
        out.append(dict(e))
    return out


def plan_reminders(events: list[dict], prefs: dict) -> list[tuple[dict, int, str]]:
    """(пара, за сколько минут, сценарий) — пары по порядку, без сам. работы
    и без времени; сценарий со значением 0 — без напоминания. Одинаковые
    пары подряд — одним блоком (как в расписании): одно напоминание перед
    первой, а не «через 5 мин пара» после каждой перемены внутри блока."""
    from schedule_format import _merge_runs
    from schedule_parser import is_self_study
    timed = sorted((e for e in events if e.get("time_start") and not is_self_study(e.get("summary", ""))),
                   key=lambda e: e["time_start"])
    out, prev_end = [], None
    for e in _merge_runs(_combine_parallel(timed)):
        if prev_end is not None and e["time_start"] < prev_end:
            continue                      # дубль/наложение — уже напомнили о первой
        kind = scenario(prev_end, e["time_start"])
        if prefs.get(kind):
            out.append((e, prefs[kind], kind))
        prev_end = e.get("time_end") or e["time_start"]
    return out


async def set_all_reminders(user_id: int, minutes: int):
    """Из чата (/settings, /setreminder) — одно время на все сценарии
    (в пределах каждого); тонко — в приложении."""
    from database import get_user, set_notify, set_reminder_minutes
    from locks import lock
    await set_reminder_minutes(user_id, minutes)
    async with lock("notify", user_id):
        prefs = merge((await get_user(user_id) or {}).get("notify"))
        for k, spec in REMIND.items():
            prefs[k] = min(minutes, spec["max"])
        await set_notify(user_id, prefs)


def summary(prefs: dict) -> str:
    """«первая — за 1 ч, после перемены — за 5 мин, …» для /settings."""
    parts = []
    for k, label in (("remind_first", "первая пара"), ("remind_short", "после короткой перемены"),
                     ("remind_long", "после большого перерыва")):
        parts.append(f"{label} — " + (f"за {minutes_text(prefs[k])}" if prefs[k] else "не напоминать"))
    return "; ".join(parts)


def minutes_text(m: int) -> str:
    h, mm = divmod(m, 60)
    return " ".join(p for p in ((f"{h} ч" if h else ""), (f"{mm} мин" if mm else "")) if p) or "0 мин"


# ── корпус ───────────────────────────────────────────────────────────────────

_CAMPUS = re.compile(r"\(([^()]{1,12})\)\s*$")


def campus_of(location: str | None) -> str | None:
    m = _CAMPUS.search((location or "").strip())
    return m.group(1).strip() if m else None


def home_campus(raw: bytes | str) -> str | None:
    """Самый частый корпус в календаре группы."""
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    text = re.sub(r"\r?\n[ \t]", "", text)            # развернуть перенесённые строки ical
    counts = Counter(c for c in (campus_of(loc.replace("\\,", ",")) for loc in
                                 re.findall(r"^LOCATION[^:]*:(.*)$", text, re.M)) if c)
    return counts.most_common(1)[0][0] if counts else None


def campus_note(events: list[dict], home: str | None) -> str:
    """Строка для утренней рассылки, если сегодня пары не в своём корпусе."""
    if not home:
        return ""
    other = [(e.get("time_start"), campus_of(e.get("location"))) for e in events]
    other = [(t, c) for t, c in other if c and c != home]
    if not other:
        return ""
    names = sorted({c for _, c in other})
    known = [c for c in (campus_of(e.get("location")) for e in events) if c]
    if len(other) == len(known):
        return f"📍 <b>Сегодня пары на {', '.join(names)}</b> — не на {home}"
    first = min((t for t, _ in other if t), default=None)
    when = f" с {first:%H:%M}" if first else ""
    return f"📍 <b>Сегодня часть пар на {', '.join(names)}</b>{when} — не только на {home}"
