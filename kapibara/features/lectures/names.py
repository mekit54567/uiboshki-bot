"""
Понятные названия файлов внутри предмета (просьба владельца: «чтобы было
понятно — Лекция 1, Лекция 2, Лекция 3…»). Из СДО файлы приходят с какими
угодно названиями: «Презентация_тема_2», «ЛК3 Бизнес-процессы.pdf»,
«Практическое занятие №5. Анализ», «Тема 1. Введение».

tidy_titles(files) → {id: новое название}: тип (file_categories) + номер +
тема, если она есть: «Лекция 3. Бизнес-процессы», «Практика 5. Анализ».
Номер берётся из названия; если ни у одного файла этого типа в предмете
номера нет — нумеруем по порядку выгрузки (он идёт по курсу в СДО).
Методички, экзаменационное и «другое» не нумеруются — только чистится
мусор (подчёркивания, расширение). Применяет староста командой /tidyfiles
(сначала показывает, что поменяется); старое название хранится в
files.orig_title — «/tidyfiles undo» возвращает всё как было.

text_titles(files, names, texts) — лекциям без темы («Лекция 8», «Лекция 1.
Презентация») тема из текста файла (lecture_topic): «Лекция 8. Тема». Одна
лекция в PDF и PPTX получает одну тему — в приложении это одна строка.
split_title — «Лекция 8» и тема отдельно: приложение пишет тему под номером.
"""

import re

from file_categories import category_of, natural_key
from lecture_topic import topic_from_text
from translit import from_translit

NUMBERED = ("lecture", "practice", "control")

# Служебное слово + номер: «Лекция 3», «ЛК03», «Тема №2», «ПР_4», «Пр.з. 5»,
# «Практическое занятие № 5», «Семинар 1». Без «часть», «задание», «модуль»:
# «часть 1.1», «Задание 3 курс» — не номера занятий.
_KEY = (r"лекци[а-яё]*|лк|тем[аы]?|практ[а-яё]*|пр(?:\.\s*з\.?)?|лаб[а-яё]*|лр|семинар[а-яё]*|занят[а-яё]*|"
        r"работ[а-яё]*|кр|контрольн[а-яё]*|тест[а-яё]*")
# два номера подряд — два занятия в одном файле: «5 6», «5-6», «5 и 6», «Практика11 12»
_RANGE = r"(\d{1,2})(?:\s*(?:[-–—,]|и)\s*|\s+)(\d{1,2})(?![\da-z]|[.,]\d)"
_ONE = r"(\d{1,2})(?![\d]|[.,]\d)"          # «1.1» — не номер
_NUM = re.compile(r"(?<![а-яёa-z])(" + _KEY + r")(?:\s+[а-яё]+)?\s*[№#]?\s*0?(?:" + _RANGE + "|" + _ONE + ")", re.I)
_EXT = re.compile(r"\.(pdf|docx?|pptx?|xlsx?|odt|odp|rtf|txt|zip|rar|7z|png|jpe?g)$", re.I)
_LEAD = re.compile(r"^(?:\d{1,2}[.)]\s+|слайд[а-яё]*\s+)", re.I)        # «2. Лекция 2 …», «Слайд Тема 2 …»
_TEMA = re.compile(r"^тема\s*№?\s*(\d{1,2})[.,]?\s+лекци[яи]\s*№?\s*(\d{1,2})(?!\d)\s*(.*)$", re.I)
_ACRONYM = re.compile(r"^(?=[^\s]*[А-ЯЁA-Z][^\s]*[А-ЯЁA-Z])[А-ЯЁA-Zа-яё]{2,7}(?=$|[\s(\-–—:,.])")
_GENERIC = re.compile(r"^(?:лекци[а-яё]*|практическ[а-яё]*(?:\s+заняти[а-яё]*)?|заняти[а-яё]*|материал[а-яё]*|"
                      r"слайд[а-яё]*|конспект[а-яё]*|файл|к\s+лекци[а-яё]*|к\s+практик[а-яё]*)$", re.I)
_PRESENT = re.compile(r"^презентаци[а-яё]*(?:\s+(?:к|по|для)\s+(?:лекци|практик|заняти|тем)[а-яё]*)?$", re.I)
_FMT = re.compile(r"\s*\((?:pdf|pptx?|docx?|xlsx?|odt|odp|rtf|txt)\)$", re.I)   # старое «Лекция 3 (PDF)»
# «Лекция 8», «Практика 5–6», «Тема 2, лекция 1» и тема после точки
_HEAD = re.compile(r"^((?:Лекция|Практика|Семинар|Лабораторная|Контрольная|Тест) \d{1,2}(?:[–-]\d{1,2})?|"
                   r"Тема \d{1,2}, лекция \d{1,2})(?:\. (.+))?$")
TOPIC_MAX = 100


def clean(title: str) -> str:
    """Подчёркивания → пробелы, без расширения и лишних пробелов/знаков по краям;
    название транслитом — по-русски («Lektsiya 05 …» → «Лекция 05 …»)."""
    t = from_translit(_EXT.sub("", (title or "").strip()).replace("_", " "))
    t = re.sub(r"[_]+", " ", t)
    t = _FMT.sub("", re.sub(r"\s+", " ", t)).strip(" -–—:")
    return t[:1].upper() + t[1:] if t else t


def _label(m) -> str:
    a, b, one = m.group(2), m.group(3), m.group(4)
    if one:
        return str(int(one))
    return f"{int(a)}–{int(b)}" if int(b) == int(a) + 1 else str(int(a))


def _best(text: str):
    """Номер занятия: полная форма («Практическая работа 7») важнее сокращения
    («ПР1 часть 1 (Практическая работа 1)» — это работа 1 из 14)."""
    ms = list(_NUM.finditer(text.replace("_", " ")))
    if not ms:
        return None
    full = [m for m in ms if len(re.sub(r"[^а-яё]", "", m.group(1).lower())) >= 4]
    return (full or ms)[0]


def number_of(title: str) -> str | None:
    """Номер из названия: «3», а для двух подряд — «5–6» («Практика 5 6»)."""
    m = _best(title or "")
    return _label(m) if m else None


def word_for(cat: str, title: str) -> str:
    low = (title or "").lower()
    if cat == "lecture":
        return "Лекция"
    if cat == "practice":
        if re.search(r"лаб|(?<![а-яё])лр(?![а-яё])", low):
            return "Лабораторная"
        return "Семинар" if "семинар" in low else "Практика"
    return "Тест" if "тест" in low else "Контрольная"


def _topic(rest: str) -> str:
    """Тема из хвоста после «Лекция 3»: без служебных слов, сокращения предмета
    в начале («ООАиП - …», «МБП …») и пояснения в скобках в начале
    («(к лекции 1) – …», «(доп) – …» — уходит в конец)."""
    t = rest.lstrip(" .:-–—)").rstrip(" .:-–—")
    for _ in range(4):
        before = t
        t = re.sub(r"^\((?:к|по)\s+[^)]*\)\s*[-–—:.]*\s*", "", t, flags=re.I)          # «(к лекции 1)»
        m = re.match(r"^\(([^)]{1,30})\)\s*[-–—:.]*\s*(.+)$", t)                      # «(доп) - Тема»
        if m:
            t = f"{m.group(2)} ({m.group(1)})"
        a = _ACRONYM.match(t)
        if a and len(t) > a.end():
            t = t[a.end():]
        elif a:
            t = ""
        t = re.sub(r"^(?:тема|по теме)\s*[:.]?\s+", "", t, flags=re.I)
        t = t.strip(" .:-–—")
        if t == before:
            break
    if not t or _GENERIC.match(t) or t.isdigit():
        return ""
    if _PRESENT.match(t):
        return "Презентация"
    t = t[:1].upper() + t[1:]
    return t if len(t) <= TOPIC_MAX else t[:TOPIC_MAX - 1].rstrip() + "…"


def topic_of(title: str) -> str:
    """Тема без «Лекция 3.» в начале; пусто, если там только общее слово."""
    t = _LEAD.sub("", clean(title))
    t = re.sub(r"^(?:презентаци[а-яё]*|конспект[а-яё]*|слайд[а-яё]*)\s+", "", t, flags=re.I)
    m = _best(t)
    if m and m.start() == 0:
        t = t[m.end():]
    return _topic(t)


def rename_one(title: str, cat: str, file_name: str = "") -> str | None:
    """Новое название занятия или None — номер не найден или из названия
    нельзя сделать понятное без потери смысла (тогда только чистка)."""
    t = _LEAD.sub("", clean(title))
    tema = _TEMA.match(t)
    if tema:
        topic = _topic(tema.group(3))
        return f"Тема {int(tema.group(1))}, лекция {int(tema.group(2))}" + (f". {topic}" if topic else "")
    m = _best(t)
    if not m:
        return None
    rest = t[m.end():]
    if m.start() == 0 or re.match(r"^(?:презентаци[а-яё]*|конспект[а-яё]*)\s+$", t[:m.start()], re.I):
        topic = _topic(rest)
    else:
        # номер в середине: «Моделирование БП ЛК01 Лекции», «… Кудрявцева И.Г. ПР01».
        # Переименовываем, только если после номера ничего важного нет.
        topic = _topic(rest)
        if topic and topic != "Презентация":
            return None
    return f"{word_for(cat, title + ' ' + (file_name or ''))} {_label(m)}" + (f". {topic}" if topic else "")


def tidy_titles(files: list[dict]) -> dict[int, str]:
    """{id: новое название} для файлов, у которых название меняется.
    files — все файлы (dict из базы: id, title, subject, category, file_name)."""
    groups: dict[tuple, list[dict]] = {}
    for f in files:
        groups.setdefault((f.get("subject") or "", category_of(f)), []).append(f)
    out: dict[int, str] = {}
    for (_, cat), items in groups.items():
        named = {}
        if cat in NUMBERED:
            named = {f["id"]: rename_one(f["title"], cat, f.get("file_name") or "") for f in items}
            nums = [f for f in items if named[f["id"]]]
            if not nums and cat == "lecture" and len(items) >= 2:
                # лекции без номеров вовсе — по порядку выгрузки (он идёт по курсу в СДО)
                for i, f in enumerate(sorted(items, key=lambda f: f["id"]), 1):
                    topic = topic_of(f["title"])
                    named[f["id"]] = f"Лекция {i}" + (f". {topic}" if topic else "")
        for f in items:
            new = named.get(f["id"]) or clean(f["title"])
            if new and new != f["title"]:
                out[f["id"]] = new
    # одинаковые названия (PDF и презентация одной лекции) остаются одинаковыми:
    # приложение показывает их одной строкой с кнопкой второго формата
    return out


def split_title(title: str) -> tuple[str, str]:
    """«Лекция 8. Управление рисками» → («Лекция 8», «Управление рисками»);
    название не по шаблону — («», «»)."""
    m = _HEAD.match((title or "").strip())
    return (m.group(1), m.group(2) or "") if m else ("", "")


def _no_topic(topic: str) -> bool:
    return not topic or topic == "Презентация"


def text_titles(files: list[dict], names: dict[int, str], texts: dict[int, str]) -> dict[int, str]:
    """{id: «Лекция 8. Тема»} — лекциям, у которых и после tidy_titles нет темы,
    тема из начала текста (texts: id → текст файла). names — что дал tidy_titles.

    У одной лекции (тот же предмет и номер — PDF и презентация) тема одна:
    из названия соседнего файла, если там есть, иначе первая найденная в тексте.
    Одна и та же «тема» у трёх и больше лекций предмета — это название курса
    со всех титульных слайдов, не берём."""
    lectures = [f for f in sorted(files, key=lambda f: f["id"]) if category_of(f) == "lecture"]
    need: dict[int, tuple[str, str]] = {}                  # id → (предмет, «Лекция 8»)
    known: dict[tuple, str] = {}                           # (предмет, «лекция 8») → тема
    found: dict[int, str] = {}
    for f in lectures:
        subj = f.get("subject") or ""
        head, topic = split_title(names.get(f["id"], f["title"]))
        if not head:
            continue
        if not _no_topic(topic):
            known.setdefault((subj, head.lower()), topic)       # тема из названия — надёжнее текста
            continue
        need[f["id"]] = (subj, head)
        t = topic_from_text(texts.get(f["id"]) or "", subj, int(re.findall(r"\d+", head)[-1]))
        if t:
            found[f["id"]] = t
    heads_by_topic: dict[tuple, set] = {}
    for fid, t in found.items():
        heads_by_topic.setdefault((need[fid][0], t.lower()), set()).add(need[fid][1].lower())
    for fid, t in found.items():
        subj, head = need[fid]
        if len(heads_by_topic[(subj, t.lower())]) < 3:
            known.setdefault((subj, head.lower()), t)
    out = {}
    for fid, (subj, head) in need.items():
        topic = known.get((subj, head.lower()))
        if topic:
            out[fid] = f"{head}. {topic}"
    return out


def preview(files: list[dict], changes: dict[int, str], limit: int = 25, marked: set | None = None) -> list[str]:
    """Строки «было → стало» по предметам, для сообщения старосте; marked —
    темы из текста лекций (их проверить глазами), со значком 📄."""
    from utils import esc
    by_id = {f["id"]: f for f in files}
    rows = sorted(changes.items(), key=lambda kv: (by_id[kv[0]].get("subject") or "", natural_key(kv[1])))
    lines, last = [], None
    for fid, new in rows[:limit]:
        subj = by_id[fid].get("subject") or "Без предмета"
        if subj != last:
            lines.append(f"\n<b>{esc(subj)}</b>")
            last = subj
        mark = "📄 " if marked and fid in marked else "• "
        lines.append(f"{mark}{esc(by_id[fid]['title'])} → <b>{esc(new)}</b>")
    return lines


def full_list(files: list[dict], changes: dict[int, str], marked: set | None = None) -> str:
    """Все переименования текстом для файла: по предметам, «было → стало»;
    тема из текста лекции — с пометкой."""
    by_id = {f["id"]: f for f in files}
    rows = sorted(changes.items(), key=lambda kv: (by_id[kv[0]].get("subject") or "", natural_key(kv[1])))
    out, last = [], None
    for fid, new in rows:
        subj = by_id[fid].get("subject") or "Без предмета"
        if subj != last:
            out.append(("\n" if out else "") + f"== {subj} ==")
            last = subj
        note = "   (тема из текста)" if marked and fid in marked else ""
        out.append(f"{by_id[fid]['title']}  →  {new}{note}")
    return "\n".join(out) + "\n"
