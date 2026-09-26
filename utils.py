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
