"""
Понятные названия дедлайнов из СДО. Moodle даёт событие и курс так:
«Практическая работа №2 - срок сдачи» + «Анализ данных_Экзамен (часть 1/1)
[I.26-27]». Бот показывает «Практика 2 · Анализ данных (Экз)»:
- из события убирается «- срок сдачи», «закрывается», «должно быть
  выполнено», «№»; «Практическая работа / Практическое задание N» →
  «Практика N», «Тестирование 1» → «Тест 1»; если событие начинается с
  названия курса («Производственная практика. Итоговые отчеты…») — оно
  убирается, курс и так написан;
- из курса — метка семестра «[I.26-27]», «_Зачет/_Экзамен» (уходит в конец
  как «(Зач)» / «(Экз)», просьба владельца), «(часть 1/2)», подчёркивания;
  если курс есть в расписании группы — его имя оттуда.
Метку семестра синк проверяет до переименования (sdo_parser.sync_deadlines).
"""

import re

SEP = " · "
_EVENT_TAIL = re.compile(r"\s*(?:[-–—:]\s*)?(?:срок сдачи|закрывается|открывается|должно быть выполнено|"
                         r"is due|closes|opens)\s*$", re.I)
_PRACTICE = re.compile(r"^практическ[а-яё]*\s+(?:работ[а-яё]*|задани[а-яё]*|заняти[а-яё]*)\s*(\d{1,2}(?:\s*[-–]\s*\d{1,2})?)\b",
                       re.I)
_LAB = re.compile(r"^лабораторн[а-яё]*\s+(?:работ[а-яё]*\s*)?(\d{1,2})\b", re.I)
_TESTING = re.compile(r"^тестировани[ея]\b", re.I)
_SEM_TAG = re.compile(r"\s*\[(?:I{1,2})\.\d{2}-\d{2}\]")
_PART = re.compile(r"\s*\(\s*часть\s*\d+\s*/\s*\d+\s*\)", re.I)
_EXAM = re.compile(r"_(?:(дифф?[.\s]*зач[её]т|зач[её]т)|(экзамен)|курсов[а-яё]*)\b.*$", re.I)


def exam_kind(course: str) -> str:
    """«(Зач)» / «(Экз)» — по метке в названии курса СДО, иначе пусто."""
    m = _EXAM.search(course or "")
    if not m:
        return ""
    return "Зач" if m.group(1) else ("Экз" if m.group(2) else "")


def clean_course(course: str, subjects: list[str] | None = None) -> str:
    c = _SEM_TAG.sub("", course or "")
    c = _PART.sub("", c)
    c = _EXAM.sub("", c)
    c = re.sub(r"[_]+", " ", c)
    c = re.sub(r"\s+", " ", c).strip(" -–—.")
    if subjects and c:
        from sdo_files import match_subject
        m = match_subject(c, subjects)
        if m in subjects:
            return m
    return c


def clean_event(title: str, course: str = "") -> str:
    t = (title or "").strip()
    t = _EVENT_TAIL.sub("", t)
    t = re.sub(r"№\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—.:")
    if course:
        low, c = t.lower(), course.lower()
        if low.startswith(c) and len(t) > len(c) + 3:
            t = t[len(course):].lstrip(" .:-–—")
    m = _PRACTICE.match(t)
    if m:
        rest = t[m.end():].strip(" .:-–—")
        num = re.sub(r"\s*[-–]\s*", "–", m.group(1))
        t = f"Практика {num}" + (f". {rest}" if rest else "")
    elif (m := _LAB.match(t)):
        rest = t[m.end():].strip(" .:-–—")
        t = f"Лабораторная {m.group(1)}" + (f". {rest}" if rest else "")
    else:
        t = _TESTING.sub("Тест", t)
    return t[:1].upper() + t[1:] if t else "Без названия"


def pretty(title: str, course: str, subjects: list[str] | None = None) -> str:
    """«Практика 2 · Анализ данных (Экз)»; без курса — только событие."""
    c = clean_course(course, subjects)
    t = clean_event(title, c)
    kind = exam_kind(course)
    return (f"{t}{SEP}{c}" if c else t) + (f" ({kind})" if kind and c else "")



_KIND_TAIL = re.compile(r"\s*\((?:Зач|Экз)\)$")


def _looks_sdo(course: str) -> bool:
    """Курс СДО в сыром виде: метка семестра, «_Зачет», «(часть 1/2)»."""
    return bool(_SEM_TAG.search(course) or _PART.search(course) or _EXAM.search(course))


def pretty_subject(subject: str) -> str:
    """Готовое название дедлайна; сырое из СДО (записи до понятных названий,
    запасной путь «Предстоящие») — понятным: «Практическое задание 1 - срок
    сдачи (Моделирование бизнес-процессов_Зачет (часть 1/2) [I.26-27])» →
    «Практика 1 · Моделирование бизнес-процессов (Зач)». Своё название без
    курса СДО в скобках — как есть."""
    s = (subject or "").strip()
    if SEP in s:
        return s
    from sdo_parser import course_of
    course = course_of(s)
    at = s.rfind("(" + course) if course else -1
    if at > 0 and _looks_sdo(course) and s[:at].strip():
        return pretty(s[:at].strip(), course)
    return s


def split_subject(subject: str) -> tuple[str, str]:
    """Название дедлайна → (работа, предмет без «(Зач)»), для показа по частям:
    «Практика 2 · Анализ данных (Экз)» → («Практика 2», «Анализ данных»);
    без предмета — (название, "")."""
    s = pretty_subject(subject)
    if SEP not in s:
        return s, ""
    task, course = s.rsplit(SEP, 1)
    return task.strip(), _KIND_TAIL.sub("", course).strip()
