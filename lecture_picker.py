"""
Подбор лекций под вопрос. После выгрузки СДО (сотни файлов) текст лекций
одного предмета — это сотни тысяч символов, и отдавать его Gemini целиком
на каждый вопрос в чате медленно и упирается в лимит токенов. Поэтому в
модель идут лекции, в которых есть слова вопроса (сначала совпадения в
названии), в пределах бюджета. Без выбранного предмета — то же по всем
предметам, но только при явном совпадении: на «привет» лекции не нужны.

Ничего не индексируем заранее: слова каждой лекции считаются один раз и
кэшируются, пока текст лекций не поменяется.
"""

import re

SUBJECT_BUDGET = 200_000   # ~60К токенов — отвечает быстро и не упирается в лимиты
AUTO_BUDGET = 60_000       # без выбранного предмета — только самое подходящее
AUTO_MIN_SCORE = 2         # два слова вопроса в тексте лекции (или одно — в названии); с 4 короткий
                           # точный вопрос («дебет и кредит — что это?») лекций не получал

_WORD = re.compile(r"[а-яёa-z]{4,}|\d{1,3}", re.I)
_STOP = {
    "что", "это", "как", "такое", "почему", "зачем", "когда", "какой", "какая", "какие", "каких", "есть",
    "объясни", "расскажи", "помоги", "реши", "решить", "задача", "задачу", "пожалуйста", "нужно", "надо",
    "можно", "будет", "если", "чтобы", "очень", "тема", "теме", "темы", "лекция", "лекции", "лекцию",
    "этой", "этот", "этого", "этом", "меня", "тебя", "себя", "всех", "всего", "только", "сейчас",
    "сегодня", "завтра", "неделе", "неделю", "недели", "пара", "пары", "сдавать", "сдать", "дедлайн",
}
_cache: dict[tuple, list[tuple]] = {}
# Текст из PDF бывает с управляющими символами и «половинками» суррогатных
# пар — модели такое лучше не отдавать.
_JUNK = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]")


# Сокращения и синонимы в вопросе → полные слова, которые встречаются в
# лекциях. Слова короче 4 букв раньше выбрасывались целиком — «ООП», «SQL»,
# «БД» в вопросе не помогали найти лекцию вовсе.
SYNONYMS = {
    "ооп": "объектно ориентированное программирование",
    "ооаип": "объектно ориентированный анализ программирование",
    "оаип": "объектно ориентированный анализ программирование",
    "матан": "математический анализ",
    "линал": "линейная алгебра матрица",
    "линейка": "линейная алгебра",
    "тервер": "теория вероятностей",
    "твимс": "теория вероятностей математическая статистика",
    "матстат": "математическая статистика",
    "диффуры": "дифференциальные уравнения",
    "диффур": "дифференциальные уравнения",
    "бд": "база данных",
    "субд": "система управления базами данных",
    "ис": "информационная система",
    "аис": "автоматизированная информационная система",
    "ит": "информационные технологии",
    "ии": "искусственный интеллект",
    "мо": "машинное обучение",
    "бп": "бизнес процесс",
    "бизнес-процесс": "бизнес процесс",
    "бизнеспроцесс": "бизнес процесс",
    "эконом": "экономика",
    "фин": "финансовый",
    "бухучет": "бухгалтерский учет",
    "бух": "бухгалтерский",
    "пр": "практическая",
    "кр": "контрольная",
    "лаба": "лабораторная",
    "лабу": "лабораторная",
    "фирма": "предприятие организация компания",
    "фирмы": "предприятие организация компания",
    "компания": "предприятие организация",
    "выручка": "выручка доход",
    "зарплата": "заработная оплата труда",
    "зп": "заработная оплата труда",
    "сотрудники": "персонал работники",
}
# Короткие латинские аббревиатуры, которые стоит искать как есть.
ACRONYMS = {"sql", "erp", "crm", "uml", "kpi", "bpm", "api", "itil", "swot", "pest", "idef", "bpmn", "epc",
            "aris", "scm", "mrp", "olap", "etl", "ооп"}
_SHORT = re.compile(r"(?<![а-яёa-z])[а-яёa-z]{2,4}(?![а-яёa-z])", re.I)


def expand(query: str) -> str:
    """Вопрос + расшифровка сокращений/синонимов из SYNONYMS."""
    low = (query or "").lower().replace("ё", "е")
    # у слов от 4 букв — любые окончания («матаном», «лабу»), короткие — только целиком
    extra = [full for short, full in SYNONYMS.items()
             if re.search(r"(?<![а-яёa-z])" + re.escape(short) + (r"[а-яё]{0,3}" if len(short) >= 4 else "")
                          + r"(?![а-яёa-z])", low)]
    return query + (" " + " ".join(extra) if extra else "")


# Окончания: «база», «базы», «базами» → «баз» (раньше считались разными
# словами — совпадение ловилось, только если вопрос в том же падеже).
_ENDING = re.compile(r"(?:иями|ями|ами|ого|его|ому|ему|ыми|ими|ией|ия|ие|ий|ый|ой|ая|яя|ое|ее|ые|ых|их|"
                     r"ов|ев|ей|ам|ям|ах|ях|ом|ем|ую|юю|ы|и|а|я|е|у|ю|о|ь)$")


def _stem(w: str) -> str:
    if w.isdigit() or not re.match(r"[а-я]", w):
        return w[:6]
    cut = _ENDING.sub("", w)
    return (cut if len(cut) >= 3 else w)[:6]


def _stems(text: str) -> set[str]:
    out = set()
    low = text.lower().replace("ё", "е")
    for w in _WORD.findall(low):
        if w in _STOP:
            continue
        out.add(_stem(w))
    out |= {w for w in _SHORT.findall(low) if w in ACRONYMS}
    return out


def _blocks(context: str) -> list[tuple[str, str, set, set]]:
    """[(заголовок, блок, слова заголовка, слова текста)] — блоки в формате
    database.get_subject_lecture_context: "=== Название ===\\nтекст"."""
    key = (len(context), context[:200], context[-200:])
    if key not in _cache:
        parts = context.split("\n\n=== ")
        blocks = []
        for i, part in enumerate(parts):
            block = part if i == 0 else "=== " + part
            title = block.split("\n", 1)[0].strip("= ").strip()
            blocks.append((title, block, _stems(title), _stems(block)))
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = blocks
    return _cache[key]


_typo_index: dict[tuple, dict[str, set[str]]] = {}


def _deletes(stem: str) -> set[str]:
    return {stem} | {stem[:i] + stem[i + 1:] for i in range(len(stem))}


def _fix_typos(query: set[str], blocks: list, key: tuple) -> set[str]:
    """Слова вопроса, которых нет в лекциях, заменяем на похожие из лекций
    (одна буква отличается / лишняя / пропущена): живой тест — «Дебит и
    кредит» не находил лекцию про «дебет». Индекс «слово без одной буквы» →
    слова строится лениво и только когда в вопросе есть незнакомое слово."""
    vocab = set().union(*(t | b for _, _, t, b in blocks)) if blocks else set()
    unknown = {q for q in query if len(q) >= 5 and not q.isdigit() and q not in vocab}
    if not unknown:
        return query
    if key not in _typo_index:
        index: dict[str, set[str]] = {}
        for word in vocab:
            if len(word) >= 4 and not word.isdigit():
                for d in _deletes(word):
                    index.setdefault(d, set()).add(word)
        if len(_typo_index) > 8:
            _typo_index.clear()
        _typo_index[key] = index
    index = _typo_index[key]
    fixed = set(query) - unknown
    for q in unknown:
        near = set().union(*(index.get(d, set()) for d in _deletes(q)))
        fixed |= near or {q}
    return fixed


def _score(query: set, title: set, body: set) -> int:
    return 3 * len(query & title) + len(query & body)


def pick(context: str, query: str, budget: int = SUBJECT_BUDGET, min_score: int = 0,
         one_subject: bool = False) -> str:
    """Лекции под вопрос в пределах budget, в исходном порядке. Короткий
    контекст — как есть (при min_score=0). Без слов в вопросе — первые
    лекции по бюджету, как раньше."""
    if not context.strip():
        return ""
    if min_score == 0 and len(context) <= budget:
        return _JUNK.sub("", context)
    blocks = _blocks(context)
    q = _fix_typos(_stems(expand(query or "")), blocks, (len(context), context[:200], context[-200:]))
    scored = [(_score(q, t, b), i) for i, (_, _, t, b) in enumerate(blocks)] if q else []
    order = [i for s, i in sorted(scored, key=lambda x: (-x[0], x[1])) if s > 0 and s >= min_score]
    if one_subject and order:
        # чат без выбранного предмета (заголовки «предмет: файл»): лекции только
        # того предмета, где совпадение сильнее всего. Живой тест: на вопрос про
        # оценку бизнеса ушли «Практика 1» анализа данных, ПР по ООАиП и лекция
        # ещё одного предмета — по паре общих слов.
        top = blocks[order[0]][0].split(": ", 1)[0]
        order = [i for i in order if blocks[i][0].split(": ", 1)[0] == top]
    if not order and min_score == 0:
        order = list(range(len(blocks)))      # ничего не совпало — первые лекции, как раньше
    chosen, used = [], 0
    for i in order:
        size = len(blocks[i][1]) + 2
        if used + size > budget:
            if not chosen and min_score == 0:  # даже одна лекция не влезает — её начало
                return blocks[i][1][:budget]
            continue
        chosen.append(i)
        used += size
    return _JUNK.sub("", "\n\n".join(blocks[i][1] for i in sorted(chosen)))


# «по лекции», «на практике», «что препод говорил» — вопрос явно про
# материалы конкретного предмета, а не общий.
_WANTS_COURSE = re.compile(r"лекци|(?<![а-яё])лк(?![а-яё])|практи|семинар|методич|препод|на пар[еау]|по предмет|"
                           r"(?<![а-яё])тем[аеуы]\s*№?\s*\d|по курсу|в курсе", re.I)


def wants_course(query: str) -> bool:
    return bool(_WANTS_COURSE.search(query or ""))


# Быстрые ответы чата («Короче», «Подробнее», «Пример», «Проверь меня» —
# QUICK_REPLIES в js/chat.js) и короткие «а почему?»: темы в них нет, и
# поиск по ним приносил случайные куски лекций. Тема — в прошлых вопросах.
_FOLLOW_UP = re.compile(r"^\s*(объясни то же самое|разбери подробнее|приведи (простой )?пример|задай мне|"
                        r"короче|подробнее|пример|продолжи|дальше|ещ[её]\b|не понял|непонятно|поясни)", re.I)
# Заглушки вложения без текста (chat.js): искать лекции не по чему.
ATTACHMENT_STUBS = ("Разбери этот файл.", "Реши задание на фото.")


def search_query(history: list[dict]) -> str:
    """По чему искать лекции для ответа: последний вопрос, а если он короткий
    или это быстрый ответ — вместе с 1–2 предыдущими вопросами студента."""
    users = [(m.get("content") or "").strip() for m in history if m.get("role") == "user"]
    users = [u for u in users if u]
    if not users or users[-1] in ATTACHMENT_STUBS:
        return ""
    last = users[-1]
    if not _FOLLOW_UP.match(last) and len(_stems(last)) >= 2:
        return last
    return "\n".join(users[-3:])


def subject_scores(context: str, query: str, min_score: int = AUTO_MIN_SCORE) -> list[tuple[str, int]]:
    """[(предмет, лучший балл лекции)] по убыванию — для контекста с
    заголовками «предмет: файл». Чат без предмета спрашивает, какой имелся в
    виду, если двое близки, а вопрос явно про лекции."""
    if not context.strip():
        return []
    blocks = _blocks(context)
    q = _fix_typos(_stems(expand(query or "")), blocks, (len(context), context[:200], context[-200:]))
    if not q:
        return []
    best: dict[str, int] = {}
    for title, _, t, b in blocks:
        score = _score(q, t, b)
        if score >= min_score and ": " in title:
            subj = title.split(": ", 1)[0]
            best[subj] = max(best.get(subj, 0), score)
    return sorted(best.items(), key=lambda x: -x[1])


# «МБП», «ООАП», «ФХД» — предмет по первым буквам слов названия (Никита
# 21.10: «завтра МБП, что на лекции» — помощник не понял и вывалил весь
# список предметов). Мелкие слова («и», «в», «по») не в счёт; слово через
# дефис — либо две буквы («бизнес-процессов» → БП), либо одна.
_ABBR = re.compile(r"(?<![а-яёa-z])[а-яё]{2,7}(?![а-яёa-z])", re.I)
_SMALL = {"и", "в", "во", "на", "по", "к", "с", "со", "для", "о", "об", "от", "из"}


def _initials(subject: str) -> set[str]:
    words = [w for w in re.split(r"\s+", subject.lower().replace("ё", "е")) if w and w not in _SMALL]
    out = {""}
    for w in words:
        parts = [p for p in w.split("-") if p]
        if not parts:
            continue
        variants = {"".join(p[0] for p in parts), parts[0][0]}
        out = {o + v for o in out for v in variants}
    return {o for o in out if len(o) >= 2}


def subject_by_abbrev(text: str, subjects: list[str]) -> str | None:
    """Предмет, сокращение которого есть в тексте; два подходящих — None.
    Строчными («мбп») — только от трёх букв: «пр», «лк» — не предметы."""
    found = set()
    for m in _ABBR.finditer(text or ""):
        tok = m.group(0)
        if not tok.isupper() and len(tok) < 3:
            continue
        low = tok.lower().replace("ё", "е")
        if low in _STOP or low in {"лк", "пр", "лаб", "кр", "экз", "зач"}:
            continue
        for s in subjects:
            if low in _initials(s):
                found.add(s)
    return found.pop() if len(found) == 1 else None
