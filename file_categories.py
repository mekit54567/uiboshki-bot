"""
Типы файлов внутри предмета: лекции, практики, КР и тесты, методички,
экзамен/зачёт, другое. Просьба владельца: «файлы собрать по предметам, а
внутри них — по лекциям, практикам, КР и т.д.».

Тип можно задать при загрузке (/upload) или поправить в WebApp; если не
задан — определяется по названию/имени файла (detect_category). Для старых
файлов без типа — тоже на лету, без миграции данных.
"""

import re

CATEGORIES: list[tuple[str, str]] = [
    ("lecture",  "📓 Лекции"),
    ("practice", "🛠 Практики и лабы"),
    ("control",  "📝 КР и тесты"),
    ("method",   "📘 Методички"),
    ("exam",     "🎓 Экзамен и зачёт"),
    ("other",    "📂 Другое"),
]
LABELS = dict(CATEGORIES)
ORDER = {key: i for i, (key, _) in enumerate(CATEGORIES)}

# Порядок проверки важен: «Вопросы к экзамену по лекциям» — экзамен, а не
# лекция; «Методические указания к практике» — методичка, а не практика.
_RULES: list[tuple[str, re.Pattern]] = [
    ("exam",     re.compile(r"экзам|зач[её]т|билет|вопросы\s+к|итогов", re.I)),
    ("method",   re.compile(r"методич|указани|пособи|учебник|рекомендац|руководств", re.I)),
    ("control",  re.compile(r"контрольн|(?<![а-яё])кр(?![а-яё])|тест|самостоятельн|(?<![а-яё])ср[\s_№-]*\d", re.I)),
    ("practice", re.compile(r"практ|(?<![а-яё])пр[\s_№-]*\d|лаб|семинар|задани|кейс|курсов", re.I)),
    ("lecture",  re.compile(r"лекц|(?<![а-яё])лк(?![а-яё])|презентац|конспект|(?<![а-яё])тема(?![а-яё])", re.I)),
]


def detect_category(*texts: str) -> str:
    """Тип файла по названию/имени файла; "other", если ничего не подошло."""
    text = " ".join(t for t in texts if t).replace("_", " ")
    for key, pattern in _RULES:
        if pattern.search(text):
            return key
    return "other"


def natural_key(title: str) -> list:
    """«Практика 2» раньше «Практики 10»: числа сравниваются как числа.
    re.split с группой чередует текст и числа — типы на позициях совпадают."""
    parts = re.split(r"(\d+)", (title or "").lower().replace("ё", "е"))
    return [int(p) if i % 2 else p.strip() for i, p in enumerate(parts)]


def sort_files(files: list[dict]) -> list[dict]:
    """По типам (лекции, практики, …), внутри — по названию с числами.
    Раньше шли в порядке загрузки: после выгрузки СДО «Практика 2» стояла
    выше «Практики 1», а «Практическая работа 15» — между ними."""
    return sorted(files, key=lambda f: (ORDER[category_of(f)], natural_key(f.get("title", ""))))


def category_of(f: dict) -> str:
    """Тип файла из базы: явно заданный или определённый по названию."""
    cat = f.get("category")
    return cat if cat in LABELS else detect_category(f.get("title", ""), f.get("file_name", ""))
