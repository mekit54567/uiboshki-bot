"""Курсы СДО ↔ предметы расписания: какой курс к какому предмету и этого
ли он семестра (03.11, клубок импортов). Чистые функции без сети и базы —
ими пользуются синк дедлайнов (parser), файлы курсов (files), баллы
(grades) и понятные названия (deadlines.names); раньше они брали это друг у
друга по кругу. Снаружи по-старому можно и из sdo.parser / sdo.files."""
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from kapibara.core.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)
SEP = " · "       # «Практика 2 · Анализ данных (Экз)» — понятное название (deadlines.names)

# первый (осенний) семестр 2026/27, «[II.25-26]» — весенний 2025/26.
# Владелец: дедлайны курсов прошлого семестра не нужны.
_SEM_TAG = re.compile(r"\[\s*(I{1,2})\s*\.\s*(\d{2})\s*-\s*(\d{2})\s*\]")


def current_semester_tag(today=None) -> str:
    """Сентябрь–январь (с сессией) — «I.26-27», февраль–июль — «II.25-26».
    С августа — уже осенний: курсы на новый год открывают заранее."""
    d = today or datetime.now(TZ).date()
    if d.month >= 8:
        return f"I.{d.year % 100:02d}-{(d.year + 1) % 100:02d}"
    if d.month == 1:
        return f"I.{(d.year - 1) % 100:02d}-{d.year % 100:02d}"
    return f"II.{(d.year - 1) % 100:02d}-{d.year % 100:02d}"


def is_old_semester(text: str, today=None) -> bool:
    """Есть метка семестра, и она не нынешняя. Без метки — не знаем, не трогаем."""
    tags = [f"{a}.{b}-{c}" for a, b, c in _SEM_TAG.findall(text or "")]
    return bool(tags) and current_semester_tag(today) not in tags


def course_of(subject: str) -> str:
    """Курс из названия дедлайна: последняя скобка верхнего уровня —
    «ПР 1 (Анализ данных (УИБО-03-24))» → «Анализ данных (УИБО-03-24)»."""
    s = (subject or "").rstrip()
    if SEP in s:          # уже понятное название: «Практика 2 · Анализ данных (Экз)»
        return re.sub(r"\s*\((?:Зач|Экз)\)$", "", s.rsplit(SEP, 1)[1]).strip()
    if not s.endswith(")"):
        return ""
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                return s[i + 1:-1].strip()
    return ""


# Курсы не из расписания, которые всё равно нужны (владелец: «оставь
# Учебный отдел»): приказы, объявления, документы института. Через запятую,
# по вхождению без учёта регистра; переопределяется SDO_KEEP_COURSES.
KEEP_COURSES = [c.strip().lower() for c in os.getenv("SDO_KEEP_COURSES", "Учебный отдел").split(",") if c.strip()]

# Предметы для сверки с курсами СДО — за весь семестр, а не за ±пару недель:
# предмет, у которого пары через раз или ещё не начались, иначе не попадал в
# список, и его курс уходил к похожему по словам («Учетная деятельность на
# предприятии» → «Основы предпринимательской деятельности»).
SEMESTER_WINDOW = {"days_back": 60, "days_ahead": 120}


def off_schedule(course: str, subjects: list[str]) -> bool:
    """Курса нет среди предметов нынешнего расписания группы. Живой тест:
    «Методы принятия управленческих решений», «Физкультура 3/3» и т.п.
    прошлых семестров были без метки «[II.25-26]». Нет расписания или
    курса — не выбрасываем (лучше лишний дедлайн, чем пропущенный)."""
    if not course or not subjects:
        return False
    if any(k in course.lower() for k in KEEP_COURSES):
        return False
    return match_subject(course, subjects) not in subjects


def not_this_semester(item: dict, subjects: list[str]) -> bool:
    return is_old_semester(item["subject"]) or off_schedule(item.get("course") or course_of(item["subject"]), subjects)


_COURSE_NOISE = re.compile(
    r"\[[^\]]*\]|\([^)]*\)|\b(?:экзамен|зач[её]т|диф\w*|курсов\w+|кп|кр|семестр|осень|весна)\b|\d{2,4}[-/.]\d{2,4}",
    re.I,
)


def clean_course_name(name: str) -> str:
    """«Архитектура_Экзамен [I.26-27]» → «Архитектура»."""
    text = _COURSE_NOISE.sub(" ", name.replace("_", " "))
    return re.sub(r"\s+", " ", text).strip(" .,-—:") or name.strip()


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яёa-z]{3,}", text.lower().replace("ё", "е"))
            if w not in {"для", "and", "the", "при", "основы"}}


def match_subject(course_name: str, subjects: list[str]) -> str:
    """Предмет из расписания группы, похожий на курс СДО (чтобы файлы и
    решалка жили под одним названием), иначе — очищенное имя курса.

    Главное — доля слов меньшего названия, найденных в большем
    («Архитектура» → «Архитектура вычислительных машин…»). При равенстве
    решает доля общих слов от всех: «Учетная деятельность на предприятии» и
    «Основы предпринимательской деятельности» делят «деятельность» и
    «предпр…», раньше побеждал первый по списку. Полная ничья — не угадываем."""
    clean = clean_course_name(course_name)
    course_stems = _stems(clean)
    scored = []
    for subject in subjects:
        subj_stems = _stems(subject)
        if not subj_stems or not course_stems:
            continue
        common = len(course_stems & subj_stems)
        if common:
            scored.append((common / min(len(course_stems), len(subj_stems)),
                           common / len(course_stems | subj_stems), subject))
    scored.sort(key=lambda t: t[:2], reverse=True)
    if not scored or scored[0][0] < 0.6:
        return clean
    if len(scored) > 1 and scored[1][:2] == scored[0][:2]:
        return clean
    return scored[0][2]


# ── материалы курса ──────────────────────────────────────────────────────────
