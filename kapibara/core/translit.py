"""
Названия файлов латиницей обратно по-русски (владелец, 09.10: в одном предмете
лекции из СДО пришли как «Lektsiya 05 Protsessnaya arhitektura»).

from_translit(title) трогает только названия, которые начинаются со слова
занятия латиницей («Lektsiya», «Praktika», «Tema» …), и в них — только слова
с приметами русского транслита (ts, ya, kh, окончания -aya, -iya …).
Английские слова и сокращения остаются: «Roadmap Governance», «ArchiMate»,
«TOGAF», «Baseline Target Gap».
"""

import re

# слово занятия в начале названия — значит, всё название набрано транслитом
_MODE = re.compile(r"^\W*(?:\d{1,2}\W+)?(?:lekts|lekc|praktik|praktich|laborator|kontroln|seminar|zanyat|tema(?![a-z]))",
                   re.I)
# приметы транслита и английского
_RU = re.compile(r"zh|kh|ts|ch|sh|ya|yu|yo|iy|yy|(?:a|i|ie|ii|ov|ev|ogo|ego|ykh|ikh|ost|om|ami)$")
_EN = re.compile(r"w|q|x|th|oa|ee|oo|ea|ou|ck|c(?!h|iya|ii)|[^aeiouy]e$")
_KNOWN = {"biznes", "tema", "analiz"}         # без примет, но русские
_PAIRS = [("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
          ("yu", "ю"), ("ya", "я"), ("yo", "ё"), ("ye", "е")]
_ONE = dict(zip("abvgdezijklmnoprstufhcy", "абвгдезийклмнопрстуфхцы"))
_VOWELS = "aeiouy"


def _word(w: str) -> str:
    low = w.lower()
    out, i = [], 0
    while i < len(low):
        for lat, cyr in _PAIRS:
            if low.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            ch = low[i]
            if ch == "e" and i == 0:
                out.append("э")
            elif ch == "y" and i > 0 and low[i - 1] in _VOWELS:
                out.append("й")                          # «-iy», «-oy», «-yy»: ий, ой, ый
            else:
                out.append(_ONE.get(ch, ch))
            i += 1
    s = "".join(out)
    return s[:1].upper() + s[1:] if w[:1].isupper() else s


def _russian(w: str) -> bool:
    low = w.lower()
    if sum(c.isupper() for c in w) > 1:                # TOGAF, ArchiMate, ARIS
        return False
    if low in _KNOWN:
        return True
    return bool(_RU.search(low)) and not _EN.search(low.replace("ch", ""))


def from_translit(title: str) -> str:
    """«Lektsiya 01 Arhitektura predpriyatiya» → «Лекция 01 Архитектура предприятия»;
    обычные названия — как были."""
    if not title or not _MODE.match(title):
        return title
    return re.sub(r"[A-Za-z]+", lambda m: _word(m.group()) if _russian(m.group()) else m.group(), title)
