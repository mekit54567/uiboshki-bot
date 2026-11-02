"""Оформление расписания для бота (HTML Telegram): пара, день, номера пар
кнопками-цифрами, типы занятий. Без сети и без разбора ical — на входе уже
разобранные события (schedule_events)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import TIMEZONE
from utils import esc

TZ = ZoneInfo(TIMEZONE)

DAY_NAMES = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]


MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
_KEYCAPS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
DAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
# Номер пары — по времени звонка, а не по месту в списке дня: у преподавателя
# (или у группы в день с «окном» с утра) первая пара дня бывает третьей.
PAIR_SLOTS = {"09:00": 1, "10:40": 2, "12:40": 3, "14:20": 4, "16:20": 5, "18:00": 6, "19:40": 7}

# Тип занятия — первым словом в SUMMARY ical МИРЭА ("ЛК Матан", "ПР ...").
_KINDS = {
    "ЛК": ("лекция", "лк"), "ПР": ("практика", "пр"), "ЛАБ": ("лабораторная", "лаб"),
    "ЛР": ("лабораторная", "лаб"), "СР": ("сам. работа", "ср"), "ДОП": ("доп. занятие", "доп"),
    "ЭКЗ": ("экзамен", "экз"), "ЗАЧ": ("зачёт", "зач"), "КОНС": ("консультация", "конс"),
    "КП": ("курсовой проект", "кп"), "КР": ("курсовая работа", "кр"),
}


def _human_date(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def _keycap(n: int) -> str:
    return _KEYCAPS[n] if 0 <= n < len(_KEYCAPS) else f"{n}."


def _pairs_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} пара"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} пары"
    return f"{n} пар"


def _split_kind(summary: str) -> tuple[str, str, str]:
    """"ЛК Основы бизнес-анализа" -> ("Основы бизнес-анализа", "лекция", "лк")."""
    head, _, rest = summary.strip().partition(" ")
    kind = _KINDS.get(head.upper())
    if kind and rest.strip():
        return rest.strip(), kind[0], kind[1]
    return summary.strip(), "", ""


def is_self_study(summary: str) -> bool:
    """«СР …» — самостоятельная работа (производственная практика на
    удалёнке): фиксированного времени нет, напоминать о ней не нужно."""
    return _split_kind(summary)[1] == "сам. работа"


def _short_teacher(name: str) -> str:
    """"Иванов Иван Иванович" -> "Иванов И. И."."""
    parts = (name or "").split()
    if len(parts) < 2:
        return name or ""
    return parts[0] + " " + " ".join(p[0] + "." for p in parts[1:3] if p)


# Между соседними парами МИРЭА — 10 или 30 минут (после 2-й и 4-й пары).
# Больше — уже «окно»: такие пары одним блоком не склеиваем.
MAX_RUN_GAP = timedelta(minutes=30)


def _adjacent(prev: dict, e: dict, i: int) -> bool:
    """Пара e идёт сразу за блоком prev, без окна. Время есть — по нему,
    нет — по номеру пары."""
    end, start = prev.get("time_end"), e.get("time_start")
    if end and start:
        return timedelta(0) <= start - end <= MAX_RUN_GAP
    return i == prev["last"] + 1


def _merge_runs(events: list[dict]) -> list[dict]:
    """Подряд идущие одинаковые пары (5 пар практики, 4 пары военки) —
    одним блоком «1️⃣–4️⃣ 09:00–15:50», а не четырьмя копиями подряд.
    Только соседние: «ПР Матан» на 1-й и 4-й паре — два блока, иначе окно
    между ними считалось бы парой (статус «сейчас», лишние точки)."""
    runs: list[dict] = []
    for pos, e in enumerate(events, 1):
        i = PAIR_SLOTS.get((e.get("time") or "").split("–")[0], pos)
        prev = runs[-1] if runs else None
        same = ("summary", "location", "teacher", "groups")
        if prev and all(prev.get(k) == e.get(k) for k in same) and _adjacent(prev, e, i):
            prev["last"] = i
            prev["time_end"] = e.get("time_end")
            prev["end_str"] = (e.get("time") or "").split("–")[-1]
            prev["parts"].append((e.get("time_start"), e.get("time_end")))
            continue
        runs.append({**e, "first": i, "last": i,
                     # каждая пара блока отдельно: «до конца пары» в 4 парах
                     # военки — до конца текущей, а не всего блока (виджет, 14.10)
                     "parts": [(e.get("time_start"), e.get("time_end"))],
                     "start_str": (e.get("time") or "").split("–")[0],
                     "end_str": (e.get("time") or "").split("–")[-1]})
    return runs


def _run_time(r: dict) -> str:
    if not r["start_str"]:
        return ""
    return r["start_str"] if r["start_str"] == r["end_str"] else f"{r['start_str']}–{r['end_str']}"


def _run_num(r: dict) -> str:
    return _keycap(r["first"]) if r["first"] == r["last"] else f"{_keycap(r['first'])}–{_keycap(r['last'])}"


def format_lesson(e: dict, num: str = "", now: datetime | None = None) -> str:
    """Одна пара (или блок подряд идущих) — три строки: время и аудитория,
    название, тип и преподаватель. Без рамок ┌│└: в Telegram шрифт не
    моноширинный, и они съезжали."""
    r = e if "start_str" in e else {**e, "start_str": (e.get("time") or "").split("–")[0],
                                     "end_str": (e.get("time") or "").split("–")[-1]}
    title, kind, _ = _split_kind(e["summary"])
    time_str = _run_time(r)
    status, past = "", False
    if now and e.get("time_start"):
        end = r.get("time_end") or e["time_start"]
        if e["time_start"] <= now < end:
            status = " · 🟢 <b>сейчас</b>"
        elif end <= now:
            past = True
    if time_str:
        time_str = f"<s>{time_str}</s>" if past else f"<b>{time_str}</b>"
    head = " ".join(x for x in (num, time_str) if x)
    loc = esc(e.get("location") or "")
    line1 = head + (f"  📍 {loc}" if loc else "") + status
    extra = [kind] if kind else []
    if e.get("teacher"):
        extra.append(esc(_short_teacher(e["teacher"])))
    if "first" in r and r["last"] > r["first"]:
        extra.append(f"{_pairs_word(r['last'] - r['first'] + 1)} подряд")
    lines = [line1, esc(title)]
    if extra:
        lines.append(f"<i>{' · '.join(extra)}</i>")
    return "\n".join(lines)


def format_day(events: list[dict], target: date, show_date=True,
               now: datetime | None = None, compact: bool = False, extra: str = "") -> str:
    weekday = DAY_NAMES[target.weekday()]
    title = f"{weekday}, {_human_date(target)}" if show_date else weekday

    if compact:
        if not events:
            return f"<b>{title}</b> — пар нет 🎉"
        lines = [f"<b>{title}</b>"]
        for r in _merge_runs(events):
            name, _, short = _split_kind(r["summary"])
            name = esc(name) + (f" ({short})" if short else "")
            loc = f" · {esc(r['location'])}" if r.get("location") else ""
            who = ""
            if extra == "groups" and r.get("groups"):
                who = f" · 👥 {esc(r['groups'])}"
            elif extra == "teacher" and r.get("teacher"):
                who = f" · 👤 {esc(_short_teacher(r['teacher']))}"
            lines.append(f"{_run_num(r)} {_run_time(r)} · {name}{loc}{who}")
        return "\n".join(lines)

    if not events:
        return f"📅 <b>{title}</b>\n🎉 Пар нет!"
    runs = _merge_runs(events)
    first = runs[0]["start_str"]
    last = runs[-1]["end_str"]
    span = f" · {first}–{last}" if first and last else ""
    blocks = [f"📅 <b>{title}</b>\n{_pairs_word(len(events))}{span}"]
    blocks += [format_lesson(r, _run_num(r), now) for r in runs]
    return "\n\n".join(blocks)
