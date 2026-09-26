"""
Мелкие общие помощники, нужные сразу во многих хендлерах.

esc() — экранирование текста перед вставкой в сообщение с parse_mode="HTML".
Всё, что пришло от пользователя (предмет/описание дедлайна, заметка, ДЗ,
вопрос голосования, пост в ленту, имя в профиле) или из внешнего источника
(название пары из ical, название задания из СДО), может содержать "<", ">"
или "&" — например "x < 5" в задаче из истории решалки или "R&D" в названии
курса. Без экранирования Telegram отвечает "can't parse entities" и не
отправляет сообщение ВООБЩЕ — один такой общий дедлайн ломал /deadlines и
утреннюю рассылку всей группе. А в WebApp тот же HTML вставляется через
innerHTML — там неэкранированная заметка к паре была уже XSS.

today_msk() — "сегодня" по Москве, а не по часам сервера: Railway и
большинство хостингов живут в UTC, и с 00:00 до 03:00 МСК date.today() —
ещё вчерашний день (заметки "на сегодня" уезжали на вчера, дедлайн на
сегодня считался "завтрашним").

parse_day_month() — общий разбор даты ДД.ММ[.ГГГГ] для дедлайнов (/add) и
привязки ДЗ к паре (/addhw).

md_to_tg_html_chunks() — ответ модели (Markdown) -> куски HTML для Telegram,
с читаемой математикой (pretty_math: x^2 -> x², sqrt -> √, <= -> ≤ …).
"""

import re
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def today_msk() -> date:
    return datetime.now(TZ).date()


def esc(value) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=False)


_DAY_MONTH_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$")

# Насколько далеко в прошлое может быть дата без года, чтобы остаться в
# текущем году (см. parse_day_month).
_PAST_WINDOW = timedelta(days=183)


def parse_day_month(raw: str, today: date) -> date | None:
    """ДД.ММ или ДД.ММ.ГГГГ -> date; None — неверный формат или такой даты нет.

    Без года берётся ближайшая к today дата: "15.01", набранное в декабре, —
    это январь СЛЕДУЮЩЕГО года. Раньше подставлялся всегда текущий год, и
    такой дедлайн сразу становился "💀 просрочен" (не попадал ни в одно
    напоминание), а ДЗ — привязывалось к паре годичной давности и не
    появлялось в календаре. Недавнее прошлое (до полугода назад) остаётся в
    текущем году — дедлайн, записанный задним числом, честно показывается
    просроченным, а не уезжает на год вперёд."""
    match = _DAY_MONTH_RE.match((raw or "").strip())
    if not match:
        return None
    day, month, year = (int(g) if g else None for g in match.groups())
    if year:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    # Текущий год, потом следующий: "29.02" в невисокосном году — это 29
    # февраля следующего (високосного) года, а не "несуществующая дата".
    for y in (today.year, today.year + 1):
        try:
            parsed = date(y, month, day)
        except ValueError:
            continue
        if y == today.year and today - parsed > _PAST_WINDOW:
            continue
        return parsed
    return None


def utc_to_msk_date(sqlite_ts: str) -> str:
    """created_at из SQLite (datetime('now') — это UTC без таймзоны) ->
    дата "YYYY-MM-DD" по Москве, для показа пользователю. Иначе запись,
    добавленная с 00:00 до 03:00 МСК, показывалась вчерашним числом."""
    try:
        dt = datetime.fromisoformat(sqlite_ts).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return (sqlite_ts or "")[:10]
    return dt.astimezone(TZ).date().isoformat()


def split_by_lines(text: str, limit: int = 3500) -> list[str]:
    """Режет длинное HTML-сообщение на куски не длиннее limit по границам
    строк. Раньше резали ровно каждые 4000 символов — разрез мог попасть
    внутрь <b>…</b> или "&amp;", и такой кусок Telegram отклонял целиком
    ("can't parse entities"), а остаток недели не доходил. Теги в
    расписании не переносятся через строку, так что граница строки всегда
    безопасна. Лимит с запасом до 4096: Telegram считает длину в UTF-16, и
    эмодзи (📖, 📍) там занимают по две единицы."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if current and len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


# ── Читаемая математика в ответах модели ───────────────────────────────────
# Студент читает ответ в Telegram, а не в LaTeX-редакторе: "6^7", "sqrt(x)",
# "x_1", "<=" и "\frac{a}{b}" — это разметка, а не формулы. Переводим в то,
# что пишут от руки: 6⁷, √x, x₁, ≤, a/b. Только вне `кода`.

_SUP = dict(zip("0123456789+-−=()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRTUVW",
                "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ"))
_SUB = dict(zip("0123456789+-−=()aehijklmnoprstuvx",
                "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))

_LATEX_SYMBOLS = {
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "equiv": "≡", "sim": "~", "infty": "∞", "to": "→",
    "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftrightarrow": "⇔",
    "iff": "⇔", "implies": "⇒", "in": "∈", "notin": "∉", "subset": "⊂",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "sum": "Σ", "prod": "Π", "int": "∫", "partial": "∂", "nabla": "∇",
    "circ": "°", "degree": "°", "angle": "∠", "perp": "⊥", "parallel": "∥",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "lambda": "λ",
    "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "ln": "ln", "log": "log", "lg": "lg", "sin": "sin", "cos": "cos",
    "tan": "tg", "tg": "tg", "cot": "ctg", "ctg": "ctg", "arcsin": "arcsin",
    "arccos": "arccos", "arctan": "arctg", "lim": "lim", "max": "max",
    "min": "min", "exp": "exp", "det": "det",
    "left": "", "right": "", "quad": " ", "qquad": " ", "displaystyle": "",
    "%": "%", ",": " ", ";": " ", ":": " ", "!": "",
}

_FRAC_RE      = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_LSQRT_RE     = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_TEXT_RE      = re.compile(r"\\(?:text|mathrm|mathbf|operatorname)\s*\{([^{}]*)\}")
_LATEX_CMD_RE = re.compile(r"\\([a-zA-Z]+|[%,;:!])")
_DOLLAR_RE    = re.compile(r"\$\$?([^$\n]+?)\$\$?")
_PARENS_RE    = re.compile(r"\\[(\[]\s*(.*?)\s*\\[)\]]")
_PYPOW_RE     = re.compile(r"(?<=[\w)])\*\*(?=[\d(\w-])")
_SQRT_RE      = re.compile(r"\bsqrt\s*\(")
_SQRT_SIMPLE  = re.compile(r"√\((\w+)\)")
_POW_RE       = re.compile(r"(?<=[\w)\]])\^(\{[^{}]+\}|\([^()]+\)|[-−]?\d+|[-−]?[a-zA-Z])")
_SUBIDX_RE    = re.compile(r"(?<=[a-zA-Zα-ωΑ-Ω])_(\{[^{}]+\}|\d+|[aehijklmnoprstuvx](?![a-zA-Z]))")
_OPS = [("<=>", "⇔"), ("<=", "≤"), (">=", "≥"), ("!=", "≠"), ("=>", "⇒"),
        ("->", "→"), ("+/-", "±"), ("+-", "±"), ("~=", "≈")]


def _script(group: str, table: dict) -> str | None:
    """Содержимое степени/индекса -> надстрочные/подстрочные символы;
    None — если хоть один символ так не пишется (тогда оставляем как было)."""
    body = group[1:-1] if group[:1] in "{(" else group
    body = body.replace(" ", "")
    if not body or any(ch not in table for ch in body):
        return None
    return "".join(table[ch] for ch in body)


def _frac(m: re.Match) -> str:
    a, b = m.group(1).strip(), m.group(2).strip()
    wrap = lambda x: x if re.fullmatch(r"[\w.,^√]+", x) else f"({x})"
    return f"{wrap(a)}/{wrap(b)}"


def pretty_math(text: str) -> str:
    """Формулы из ответа модели -> как пишут от руки (6^7 -> 6⁷, sqrt(x) -> √x,
    x_1 -> x₁, <= -> ≤, \\frac{a}{b} -> a/b, \\pi -> π). Нераспознанное не
    трогается: лучше "2^(1/3)", чем потерянная степень."""
    if not text:
        return text
    if "\\" in text or "$" in text:
        text = _PARENS_RE.sub(r"\1", text)
        text = _DOLLAR_RE.sub(lambda m: m.group(1) if re.search(r"[\\^_{}=]", m.group(1)) else m.group(0), text)
        for _ in range(3):  # вложенные \frac{\sqrt{..}}{..}
            text = _FRAC_RE.sub(_frac, text)
            text = _LSQRT_RE.sub(r"√(\1)", text)
            text = _TEXT_RE.sub(r"\1", text)
        text = _LATEX_CMD_RE.sub(lambda m: _LATEX_SYMBOLS.get(m.group(1), m.group(0)), text)
    text = _PYPOW_RE.sub("^", text)
    text = _SQRT_RE.sub("√(", text)
    text = _SQRT_SIMPLE.sub(r"√\1", text)
    text = _POW_RE.sub(lambda m: _script(m.group(1), _SUP) or m.group(0), text)
    text = _SUBIDX_RE.sub(lambda m: _script(m.group(1), _SUB) or m.group(0), text)
    for src, dst in _OPS:
        text = text.replace(src, dst)
    return text


# ── Ответ модели: Markdown -> HTML Telegram ─────────────────────────────────

_FENCE_RE   = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_RULE_RE    = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_BULLET_RE  = re.compile(r"^(\s*)[*+-]\s+")
_BOLD_RE    = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
# Одиночные *…* — курсив, только если звёздочка не прилипла к слову/цифре
# с внешней стороны и не отбита пробелом изнутри: "3 * x^2 * ln(x)" и
# "2*3" остаются умножением, "*важно*" становится курсивом. Внутрь курсива
# не пускаем теги (уже расставленный <b>), чтобы они не пересеклись.
_ITALIC_RE  = re.compile(r"(?<![\w*])\*(?=[^\s*<])([^*\n<]+?)(?<=[^\s*>])\*(?![\w*])")
# Оставшаяся после курсива одиночная * между множителями — умножение: "3 * x" -> "3 · x",
# "2*3" -> "2·3"; несимметричная "a *b" — не умножение, не трогаем.
_MUL_RE     = re.compile(r"(?<=[\w)\]'′⁰¹²³⁴⁵⁶⁷⁸⁹])( \*(?= )|\*(?=[\w(√-]))")


def _md_inline(line: str) -> str:
    """Одна строка вне блока кода: экранирование + `код`, **жирный**, *курсив*."""
    parts = line.split("`")
    if len(parts) % 2 == 0:            # непарный бэктик — оставляем как текст
        parts = [line]
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(f"<code>{esc(part)}</code>")
            continue
        part = esc(pretty_math(part))
        part = _BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", part)
        part = _ITALIC_RE.sub(r"<i>\1</i>", part)
        part = _MUL_RE.sub(lambda m: m.group(1).replace("*", "·"), part)
        out.append(part)
    return "".join(out)


def _md_to_tg_html(text: str) -> str:
    lines, code, in_code = [], [], False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            if in_code:
                lines.append(f"<pre>{esc(chr(10).join(code))}</pre>")
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            lines.append(f"<b>{_md_inline(heading.group(1))}</b>")
        elif _RULE_RE.match(line):
            lines.append("──────────")
        else:
            lines.append(_md_inline(_BULLET_RE.sub(r"\1• ", line)))
    if in_code:                        # модель не закрыла блок кода
        lines.append(f"<pre>{esc(chr(10).join(code))}</pre>")
    return "\n".join(lines)


def md_to_tg_html_chunks(text: str, limit: int = 3500) -> list[str]:
    """Ответ модели (обычный Markdown: **жирный**, ### заголовки, ```код```)
    -> куски HTML для parse_mode="HTML".

    Раньше ответ уходил с parse_mode="Markdown" — это старый Markdown
    Telegram, где одиночная * — жирный, а заголовков нет вовсе. Gemini
    пишет умножение звёздочкой ("3 * x^2 * ln(x)"), поэтому знаки умножения
    исчезали, жирный растекался на пол-ответа, а "### 3. Итог" выводились
    как есть (поймано живым тестом в Telegram). Здесь всё, что не разметка,
    экранируется, так что Telegram не отклонит кусок. Режем по строкам
    исходного текста; если разрез попал внутрь ```-блока, блок закрывается
    в конце куска и открывается заново в следующем."""
    chunks = split_by_lines(text or "", limit)
    in_code = False
    fixed = []
    for chunk in chunks:
        if in_code:
            chunk = "```\n" + chunk
        fences = sum(1 for line in chunk.split("\n") if _FENCE_RE.match(line))
        in_code = fences % 2 == 1
        if in_code:
            chunk += "\n```"
        fixed.append(chunk)
    return [_md_to_tg_html(chunk) for chunk in fixed]
