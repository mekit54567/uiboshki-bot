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

md_to_tg_html_chunks() — ответ модели (Markdown) -> куски HTML для Telegram.
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
        part = esc(part)
        part = _BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", part)
        part = _ITALIC_RE.sub(r"<i>\1</i>", part)
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
