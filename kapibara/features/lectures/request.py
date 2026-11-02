"""
Файл по запросу в чате: «скинь практику 3 по основам предпр деят», «нужна
лекция 2 по анализу данных», «дай файлы по учетной деятельности».

Запрос узнаём по слову-просьбе (скинь, дай, нужна…) вместе с типом файла
(лекция, практика, лаба, КР, методичка, файл…). Предмет ищем среди папок
«Файлов» по началам слов, чтобы сокращения вроде «предпр деят» находили
«Основы предпринимательской деятельности». Номер — первое число в запросе.
Не похоже на просьбу или предмет не нашёлся — текст идёт дальше к ИИ.
"""

import re

from file_categories import category_of, natural_key, sort_files

_ASK = re.compile(r"(?<![а-яё])(скин|кин|дай|дайте|пришли|пришлите|отправ|нуж[нe]|найди|ищу|где\s+(?:лежит|найти)|скачать)",
                  re.I)
_KIND = re.compile(r"лекц|(?<![а-яё])лк(?![а-яё])|практ|(?<![а-яё])пр(?![а-яё])|лаб|методич|(?<![а-яё])кр(?![а-яё])|"
                   r"контрольн|файл|презентац|билет|конспект", re.I)
_NOISE = {
    "скинь", "скиньте", "кинь", "киньте", "дай", "дайте", "пришли", "пришлите", "отправь", "отправьте",
    "нужна", "нужен", "нужно", "нужны", "найди", "ищу", "где", "лежит", "найти", "скачать", "мне",
    "пожалуйста", "плиз", "пж", "по", "для", "все", "всё", "файл", "файлы", "файлик", "номер",
    "лекция", "лекцию", "лекции", "лекций", "лк", "практика", "практику", "практики", "практическая",
    "практическую", "пр", "лаба", "лабу", "лабы", "лабораторная", "лабораторную", "методичка", "методичку",
    "методички", "кр", "контрольная", "контрольную", "презентация", "презентацию", "билеты", "задание",
    "задания", "конспект", "работа", "работу", "предмет", "предмету", "из", "в", "на", "и", "а", "ну",
    # служебные слова: «лекцию про NPV» — «про» как основа находила «программирование»
    "про", "о", "об", "обо", "от", "с", "со", "к", "ко", "у", "за", "до", "под", "над", "при", "без",
    "это", "эту", "этот", "эти", "тот", "ту", "те", "там", "тут", "его", "её", "ее", "их", "что", "как",
    "можно", "есть", "кто", "нибудь", "какую", "какой", "какие", "тему", "теме", "тема",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z]+", text.lower().replace("ё", "е"))


_KIND_CAT = [("лекц", "lecture"), ("лк", "lecture"), ("презентац", "lecture"), ("конспект", "lecture"),
             ("практ", "practice"), ("пр", "practice"), ("лаб", "practice"),
             ("методич", "method"), ("кр", "control"), ("контрольн", "control"), ("билет", "exam")]


def _kind_of(text: str) -> str | None:
    """Тип файла по слову из запроса (только по нему — не по предмету)."""
    for m in _KIND.finditer(text.lower()):
        word = m.group(0)
        for prefix, cat in _KIND_CAT:
            if word.startswith(prefix):
                return cat
    return None


def is_request(text: str) -> bool:
    t = text.lower()
    return bool(_ASK.search(t) and _KIND.search(t)) and len(text) <= 200


def match_subjects(text: str, subjects: list[str]) -> list[str]:
    """Предметы, лучше всех покрытые словами запроса (по началам слов:
    «предпр» → «предпринимательской», «основам» → «основы»). Пусто —
    ни одно слово не подошло."""
    query = [w for w in _words(text) if len(w) >= 2 and w not in _NOISE]   # «уч деят» — и «уч» в деле
    if not query:
        return []
    scored = []
    for subject in subjects:
        subj = [w for w in _words(subject) if len(w) >= 3]
        hits = short = 0
        for q in query:
            stem = q[:max(3, min(len(q), 5))]
            if any(s.startswith(stem) or (len(s) >= 4 and q.startswith(s[:5])) for s in subj):
                if len(q) >= 4:
                    hits += 1
                else:
                    short += 1
        # Короткое слово («уч», «про») совпадает началом почти с чем угодно —
        # оно только разбивает ничью, но само предмет не находит.
        if hits:
            scored.append((hits + short, 0, subject))
    if not scored:
        return []
    best = max(h for h, _, _ in scored)
    return [s for h, _, s in scored if h == best]       # ничья — переспросим, а не угадаем


def find(text: str, files: list[dict]) -> tuple[list[str], list[dict]]:
    """(подходящие предметы, файлы). Файлы — только если предмет один."""
    subjects = sorted({f["subject"] for f in files if f.get("subject")})
    found = match_subjects(text, subjects)
    if len(found) != 1:
        return found, []
    items = [f for f in files if f.get("subject") == found[0]]
    cat = _kind_of(text)
    if cat:
        items = [f for f in items if category_of(f) == cat] or items
    num = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text)
    if num:
        n = int(num.group(1))
        exact = [f for f in items if n in [p for p in natural_key(f.get("title", "")) if isinstance(p, int)]]
        first = [f for f in exact if next((p for p in natural_key(f["title"]) if isinstance(p, int)), None) == n]
        items = first or exact
    return found, sort_files(items)
