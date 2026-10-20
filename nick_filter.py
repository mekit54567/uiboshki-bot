"""Ник в рейтинге (5.100.3, Никита 18.10: «главное, чтобы не маты и не
оскорбления»): проверка до сохранения. Ловит мат и оскорбления и в обходах —
латиница вместо кириллицы, цифры вместо букв, точки и повторы между буквами.
Чего фильтр не поймал — на это жалоба и ручная модерация (/nicks у Никиты).
"""

import re

MIN_LEN, MAX_LEN = 2, 24

# Похожие знаки → русская буква: «xу1» ловится как «хуй».
_LOOK = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о", "p": "р",
    "t": "т", "x": "х", "y": "у", "u": "и", "n": "п", "r": "г", "i": "и", "l": "л", "d": "д",
    "z": "з", "s": "с", "f": "ф", "g": "г", "v": "в", "w": "ш", "j": "й",
    "0": "о", "1": "и", "3": "з", "4": "ч", "6": "б", "8": "в", "@": "а", "$": "с",
    "ё": "е", "й": "и",
})

# Латиница по звуку: «ebanko» → «ебанко».
_SOUND = (("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("ya", "я"), ("yu", "ю"),
          ("yo", "е"), ("ts", "ц"))
_SOUND1 = str.maketrans({
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "z": "з", "i": "и", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "h": "х",
    "c": "к", "y": "и", "x": "х", "j": "и", "w": "в", "q": "к",
})

# Корни мата и оскорблений (после замены похожих букв, без знаков и повторов):
# где угодно в нике — только те, что не прячутся внутри обычных слов.
_ROOTS = (
    "хуи", "хуе", "хуя", "пизд", "пезд", "бляд", "блят", "мудак", "мудил", "пидор", "пидар", "педераст",
    "гандон", "гондон", "залуп", "шлюх", "дроч", "долбоеб", "ебан", "ебат", "еблан", "ебло", "выеб", "заеб",
    "уеб",
    "дегенерат", "ублюд", "проститут", "нигер", "нигга", "фашист", "нацист", "гитлер",
)
# Целым словом: внутри других слов они бывают безобидными («мандарин», «требую»).
_WORDS = {
    "бля", "еба", "ебу", "сука", "суки", "сучка", "манда", "жопа", "жопу", "говно", "срака", "дебил",
    "идиот", "даун", "чмо", "мразь", "тварь", "скотина", "урод", "лох", "хохол", "хохлы", "жид", "жиды",
    "чурка", "хач", "негр", "педик", "дура", "дурак",
}
_ROOTS_EN = ("fuck", "shit", "bitch", "cunt", "nigg", "whore", "slut")
_WORDS_EN = {"dick", "fag", "nazi", "hitler", "ass"}
# Не выдавать себя за сервис, МИРЭА или старост (робот 18.10: «Капибара на
# паре» — обычный ник, его пропускаем). Где угодно в нике — роли и «официальный»:
_RESERVED = ("админ", "модер", "поддержк", "староста", "ректор", "деканат", "официальн")
_RESERVED_EN = ("admin", "moder", "support", "rector", "official")
# Ник целиком из имён сервиса — «Капибара», «Капибара МИРЭА», «Капибара бот»,
# «МИРЭА», «РТУ МИРЭА»: так выглядит сам сервис. Со своими словами — можно.
_SERVICE = {"мирэа", "миреа", "рту", "бот", "приложение", "сервис", "команда", "оф", "uiboshki"}
_SERVICE_STEMS = ("капибар", "уибошк")

_ALLOWED = re.compile(r"^[A-Za-zА-Яа-яЁё0-9 ._\-]+$")


def _squash(text: str, sound: bool = False) -> str:
    low = text.lower()
    if sound:
        for a, b in _SOUND:
            low = low.replace(a, b)
        low = low.translate(_SOUND1)
    low = low.translate(_LOOK)
    letters = re.sub(r"[^а-я]", "", low)
    return re.sub(r"(.)\1+", r"\1", letters)


def _looks_like_service(parts: list[str]) -> bool:
    """Все слова ника — имена сервиса (капибара, МИРЭА, бот…): ник выдаёт себя за сервис."""
    def service(word: str) -> bool:
        forms = {_squash(word), _squash(word, sound=True)}
        return any(f in _SERVICE or f.startswith(_SERVICE_STEMS) for f in forms)
    words = [w for w in parts if w]
    return bool(words) and all(service(w) for w in words)


def problem(nick: str) -> str | None:
    """Почему ник не подходит (текст для человека) или None — подходит."""
    nick = " ".join((nick or "").split())
    if len(nick) < MIN_LEN:
        return f"ник — хотя бы {MIN_LEN} знака"
    if len(nick) > MAX_LEN:
        return f"ник — не длиннее {MAX_LEN} знаков"
    if not _ALLOWED.match(nick):
        return "в нике — только буквы, цифры, пробел, точка, дефис и _"
    if not re.search(r"[A-Za-zА-Яа-яЁё]", nick):
        return "в нике нужна хотя бы одна буква"
    parts = re.split(r"[ ._\-]+", nick)
    flats = {_squash(nick), _squash(nick, sound=True)}
    words = {_squash(w, k) for w in parts for k in (False, True)} | flats
    raw = nick.lower()
    raw_words = set(re.split(r"[^a-z]+", raw)) | {re.sub(r"[^a-z]", "", raw)}
    if (any(_squash(w) in f for f in flats for w in _RESERVED) or any(w in raw for w in _RESERVED_EN)
            or _looks_like_service(parts)):
        return "такой ник похож на официальный — придумай другой"
    if (any(r in f for f in flats for r in _ROOTS) or words & _WORDS
            or any(r in re.sub(r"[^a-z]", "", raw) for r in _ROOTS_EN) or raw_words & _WORDS_EN):
        return "такой ник не подойдёт — без мата и оскорблений"
    return None


def default(full_name: str) -> str:
    """Ник по умолчанию: имя и первая буква фамилии — «Никита К.»."""
    parts = [p for p in (full_name or "").split() if p]
    if not parts:
        return "Студент"
    nick = parts[0][:MAX_LEN - 3]
    if len(parts) > 1 and parts[1][:1].isalpha():
        nick += f" {parts[1][0].upper()}."
    return nick


def rude(text: str) -> bool:
    """Мат или оскорбление в свободном тексте (комментарии под парой,
    lesson_comments.py): те же корни и слова, что у ников, по каждому слову."""
    raw = (text or "").lower()
    parts = [w for w in re.split(r"[^A-Za-zА-Яа-яЁё0-9@$]+", text or "") if w]
    words = {_squash(w, k) for w in parts for k in (False, True)}
    if any(r in w for w in words for r in _ROOTS) or words & _WORDS:
        return True
    latin = set(re.split(r"[^a-z]+", raw))
    return any(r in w for w in latin for r in _ROOTS_EN) or bool(latin & _WORDS_EN)
