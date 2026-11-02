"""
Тема лекции из её текста (владелец, 09.10: «тема лекции в файлах точно есть,
её бы писать под „Лекция 1“»). В половине предметов файлы называются просто
«Лекция 8» или «Лекция 1. Презентация» — а на первом слайде или первой
странице тема написана.

topic_from_text(text, subject) → тема или «». Смотрим только начало текста
(титульный слайд / первая страница), по порядку:
1. «Тема: …», «Тема лекции: …», «Тема 3. …»;
2. «Лекция 8. …» или строка сразу после «Лекция 8»;
3. первая строка, похожая на заголовок, — после шапки вуза, кафедры,
   названия предмета, преподавателя и года.
Шапку (МИРЭА, институт, кафедра, «Москва 2025», ФИО, должности) и название
самого предмета темой не считаем. Ничего похожего — «» (лучше без темы, чем
с чужой строкой). Применяет староста через /tidyfiles — сначала видит
«было → стало».
"""

import re

HEAD_CHARS = 2500        # титульный слайд / первая страница
HEAD_LINES = 40
TOPIC_MAX = 100

_SPACE = re.compile(r"[\s ​]+")
# шапка вуза и титульного листа — не тема
_BOILER = re.compile(
    r"мирэа|университет|министерств[а-яё]*\s+(?:науки|образован)|федеральн[а-яё]*\s+государствен|"
    r"государствен[а-яё]*\s+бюджетн|образовательн[а-яё]*\s+учреждени|высшего\s+образован|"
    r"(?<![а-яё])институт(?:а|е|у|ом)?(?![а-яё])|(?<![а-яё])кафедр|(?<![а-яё])рту(?![а-яё])|"
    r"[А-ЯЁ]{2,6}-\d{2}-\d{2}|"                                       # шифр группы «УИБО-03-24»
    r"^(?:г\.\s*)?москва\b|^\d{4}\s*(?:г\.?|год)?$|"
    r"^(?:дисциплин|учебн[а-яё]+\s+дисциплин|по\s+дисциплин|направлени[ея]\s|профиль|специальност|"
    r"преподавател|лектор|автор|составител|разработчик|выполнил|подготовил|ст\.\s*преп|старш[а-яё]+\s+преп|"
    r"доцент|профессор|ассистент|зав\.|заведующ|к\.\s*[тэфпю]\.\s*н|д\.\s*[тэфпю]\.\s*н|кандидат\s|"
    r"семестр|учебный\s+год|бакалавриат|магистратур|форма\s+обучения|для\s+студент|"
    r"презентаци[яи](?![а-яё])|слайд|конспект\s+лекци|курс\s+лекций|оглавлени|"
    r"содержание\s*:?$|план(?:\s+лекции|\s+занятия)?\s*:?$|вопрос[а-яё]*\s*(?:лекции|для|к\s|:|$)|"
    r"(?:список\s+|рекомендуем[а-яё]+\s+)?литератур[а-яё]*\s*:?$|"
    r"цел[иь](?:\s+и\s+задачи)?\s*(?:лекции|занятия|:|$)|задачи\s*(?:лекции|занятия|:|$)|"
    r"(?:лекци[а-яё]*|тема|занятие|материал[а-яё]*)\s*№?\s*\d*\s*[.:]?$)",
    re.I)
# ФИО: «Кудрявцева И.Г.», «И.Г. Кудрявцева», «Иванов Иван Иванович»
_PERSON = re.compile(
    r"^(?:[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.?|[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё-]+|"
    r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|чна|ична|ьич))$")
_URL = re.compile(r"https?://|www\.|@[a-z]|\.(?:ru|com|org)\b", re.I)
# служебное «Лекция 8», «Лекция № 8.», «ЛЕКЦИЯ 8:», «Тема 3»
_LECTURE = re.compile(r"^(?:лекци[яи]|лк|занятие)(?![а-яё])\s*№?\s*(\d{1,2})(?![\d.]\d)\s*[.:)\-–—]?\s*(.*)$", re.I)
_TEMA = re.compile(r"^тема(?![а-яё])(?:\s+лекции)?(?:\s*№?\s*\d{1,2}(?![\d.]\d))?\s*[.:\-–—]?\s*(.*)$", re.I)
# строка-продолжение: заголовок перенёсся («Управление проектами в» / «информационных системах»)
_TAIL_WORD = re.compile(r"(?:^|\s)(?:в|во|и|на|по|для|из|к|с|со|о|об|от|до|за|при|без|или|как|их|её|его)$", re.I)
_SMALL = {"в", "во", "и", "на", "по", "для", "из", "к", "с", "со", "о", "об", "от", "до", "за", "при", "без",
          "или", "как", "не", "а", "но"}


# PDF отдаёт «бизнес -анализа», «Б -А» — дефис прилипает к следующему слову
_HYPHEN = re.compile(r"(?<=[А-ЯЁа-яёA-Za-z]) -(?=[А-ЯЁа-яёA-Za-z])")


def _norm(line: str) -> str:
    line = _HYPHEN.sub("-", _SPACE.sub(" ", line or "")).strip()
    return line.strip(" \t•·▪►–—-*|")


def _key(s: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]", "", (s or "").lower().replace("ё", "е"))


# лишнее вокруг названия предмета: «Дисциплина „…“», «Курс: …»
_SUBJ_EXTRA = {"", "дисциплина", "учебнаядисциплина", "подисциплине", "курс", "покурсу"}


def _is_subject(line: str, subject: str) -> bool:
    """Строка — название самого предмета («Архитектура предприятия», «Дисциплина
    „Архитектура предприятия“»), а не тема."""
    a, b = _key(line), _key(subject)
    return bool(a and b) and len(b) >= 4 and b in a and a.replace(b, "", 1) in _SUBJ_EXTRA


def _marker(line: str) -> bool:
    return bool(_TEMA.match(line) or _LECTURE.match(line))


def _boiler(line: str, subject: str) -> bool:
    letters = re.sub(r"[^а-яёa-z]", "", line.lower())
    return (len(letters) < 3 or bool(_BOILER.search(line)) or bool(_PERSON.match(line))
            or bool(_URL.search(line)) or _is_subject(line, subject))


def _titleish(line: str) -> bool:
    """Похоже на заголовок, а не на предложение из текста лекции."""
    words = line.split()
    if not 1 <= len(words) <= 12 or not 4 <= len(line) <= TOPIC_MAX + 10:
        return False
    if not re.match(r"[«\"„(]?[А-ЯЁA-Z0-9]", line):          # с маленькой — середина фразы
        return False
    if line.endswith((":", ",", ";")) or line.count(".") > 2:
        return False
    if len(words) > 6 and (line.endswith(".") or re.search(r"[.!?] [А-ЯЁA-Z]", line)):
        return False                                           # предложение, а не заголовок
    if len(words) == 1 and len(line) < 6:
        return False
    return bool(re.search(r"[а-яёa-z]{3}", line.lower()))


def _join(lines: list[str], i: int, first: str) -> str:
    """Заголовок с переносами: следующая строка с маленькой буквы или текущая
    кончается предлогом — склеиваем."""
    out = first
    for nxt in lines[i + 1:i + 4]:
        if len(out) + len(nxt) + 1 > TOPIC_MAX + 10:
            break
        if re.match(r"[а-яё]", nxt) or _TAIL_WORD.search(out) or out.endswith(("-", "–", "—")):
            if _BOILER.search(nxt) or _PERSON.match(nxt) or _marker(nxt):
                break
            out = (out[:-1] if out.endswith("-") and not out.endswith(" -") else out + " ") + nxt
            continue
        break
    return out


def _lower_word(w: str) -> str:
    """Слово из капса: длинное — строчными, короткое (ИТ, БД, ERP) — как есть,
    предлоги — строчными; через дефис — по частям («ИТ-ПРОЕКТАХ» → «ИТ-проектах»)."""
    parts = []
    for part in w.split("-"):
        core = re.sub(r"[^А-ЯЁа-яё]", "", part)
        parts.append(part.lower() if core and (len(core) > 3 or core.lower() in _SMALL) else part)
    return "-".join(parts)


def _caps(t: str) -> str:
    """«УПРАВЛЕНИЕ РИСКАМИ В ИТ» → «Управление рисками в ИТ»: капсом набранный
    заголовок — обычными буквами."""
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 8 or sum(c.isupper() for c in letters) < 0.8 * len(letters):
        return t
    return " ".join(_lower_word(w) for w in t.split())


def tidy_topic(t: str) -> str:
    t = _norm(t)
    t = re.sub(r"^[«\"„](.+)[»\"“]$", r"\1", t)                 # тема целиком в кавычках
    t = t.strip(" .:;,-–—")
    t = _caps(t)
    if not t:
        return ""
    t = t[:1].upper() + t[1:]
    return t if len(t) <= TOPIC_MAX else t[:TOPIC_MAX - 1].rstrip() + "…"


def _candidate(raw: str, subject: str) -> str:
    """Тема из строки или «», если строка не похожа на заголовок или это шапка."""
    raw = _norm(raw).strip(" :;,-–—")
    if not _titleish(raw) or _boiler(raw, subject) or _marker(raw):
        return ""
    return tidy_topic(raw)


def head_lines(text: str) -> list[str]:
    lines = [_norm(x) for x in (text or "")[:HEAD_CHARS].splitlines()]
    return [x for x in lines if x][:HEAD_LINES]


def _after(lines: list[str], i: int, rest: str, subject: str) -> str:
    """Тема у маркера в строке i: после него в той же строке или, если там
    пусто, в одной из следующих строк (после шапки)."""
    inner = _TEMA.match(rest)                                  # «Лекция 3. Тема: …»
    if inner:
        rest = inner.group(1).strip()
    if rest:
        return _candidate(_join(lines, i, rest), subject)
    for j in range(i + 1, min(i + 4, len(lines))):
        if _marker(lines[j]):
            return ""                                          # у неё свой разбор
        if _boiler(lines[j], subject):
            continue
        return _candidate(_join(lines, j, lines[j]), subject)
    return ""


def topic_from_text(text: str, subject: str = "", number: int | None = None) -> str:
    """Тема лекции по началу её текста или «». number — номер лекции из
    названия файла: на слайде «План курса» перечислены все лекции, берём свою."""
    lines = head_lines(text)
    own, tema, other = "", "", {}                              # other: номер → тема
    for i, line in enumerate(lines):
        m = _LECTURE.match(line)
        if m:
            topic = _after(lines, i, m.group(2).strip(), subject)
            n = int(m.group(1))
            if topic and n == number and not own:
                own = topic
            elif topic:
                other.setdefault(n, topic)
            else:
                other.setdefault(n, "")
            continue
        m = _TEMA.match(line)
        if m and not tema:
            tema = _after(lines, i, m.group(1).strip(), subject)
    if own or tema:
        return own or tema
    # «Лекция 7» на титульном, а файл пронумерован по порядку выгрузки — номер
    # в тексте один, значит, это она; несколько разных (план курса) — не гадаем
    if other:
        found = [t for t in other.values() if t]
        return found[0] if len(other) == 1 and found else ""
    # без «Лекция N» и «Тема» — первая строка-заголовок после шапки (титульный)
    for i, line in enumerate(lines[:12]):
        if _boiler(line, subject):
            continue
        return _candidate(_join(lines, i, line), subject)  # первая же не-шапка: заголовок или ничего
    return ""
