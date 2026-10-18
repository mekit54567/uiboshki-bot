"""
Контекст группы для ИИ-чата WebApp: сегодняшняя дата, пары на сегодня и
завтра, ближайшие дедлайны (как их видит этот студент — общие + его личные)
и свежие ДЗ. Короткий обычный текст (без HTML) в конец системного промпта —
чтобы на «что сдавать на неделе?» или «когда у нас анализ данных?» чат
отвечал по делу, а не «я не знаю вашего расписания».
"""

import logging
import re
from datetime import date, datetime, timedelta

import aiosqlite

import database
from database import _conn
from config import GROUP_NAME
from utils import TZ, today_msk

logger = logging.getLogger(__name__)

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_TAG_RE = re.compile(r"<[^>]+>")


def _plain(html: str) -> str:
    return _TAG_RE.sub("", html).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


async def list_homework(limit: int = 30, group_id: int | None = None) -> list[dict]:
    """ДЗ с доски (/addhw), свежие сверху. Таблица создаётся лениво
    (database/homework.init_hw_table) — на пустой базе её может не быть."""
    try:
        from database.homework import init_hw_table
        await init_hw_table()            # колонка group_id (этап 1 (б)) — и у таблиц старого вида
        async with _conn.connect() as db:
            db.row_factory = aiosqlite.Row
            from database.groups import g_or_home, scope_sql
            cur = await db.execute(
                "SELECT id, subject, content, lesson_date, created_at, file_id, file_type, created_by FROM homework "
                f"WHERE {scope_sql()} "
                "ORDER BY COALESCE(lesson_date, substr(created_at, 1, 10)) DESC, id DESC LIMIT ?",
                (g_or_home(group_id), limit),
            )
            return [dict(r) for r in await cur.fetchall()]
    except aiosqlite.OperationalError:
        return []


async def _schedule_lines(days: int = 2, user_id: int | None = None) -> list[str]:
    from schedule_parser import format_day, parse_events_for_date, raw_for_user
    try:
        raw = await raw_for_user(user_id or 0)
    except Exception as e:
        logger.info(f"group_context: расписание недоступно: {e}")
        return []
    today = today_msk()
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        label = "Сегодня" if i == 0 else "Завтра"
        out.append(f"{label}: " + _plain(format_day(parse_events_for_date(raw, d), d, compact=True, extra="teacher")))
    return out


async def build_group_context(user_id: int, deadline_days: int = 21) -> str:
    import groups
    from database.groups import viewer_group
    gid = await viewer_group(user_id)
    name = (await groups.name_of(gid)) or GROUP_NAME
    today = today_msk()
    lines = [
        f"Контекст группы {name} (используй, если вопрос про учёбу группы; не пересказывай без нужды).",
        f"Сегодня {today.strftime('%d.%m.%Y')}, {WEEKDAYS[today.weekday()]}, "
        f"{datetime.now(TZ).strftime('%H:%M')} по Москве.",
    ]
    lines += await _schedule_lines(user_id=user_id)

    try:
        deadlines = await database.get_active_deadlines(user_id)
    except Exception as e:
        logger.warning(f"контекст ИИ без дедлайнов: {e!r}")
        deadlines = []
    horizon = today + timedelta(days=deadline_days)
    upcoming = [d for d in deadlines if date.fromisoformat(d["due_date"]) <= horizon]
    if upcoming:
        lines.append("Ближайшие дедлайны:")
        for d in upcoming[:15]:
            when = date.fromisoformat(d["due_date"]).strftime("%d.%m") + (f" {d['due_time']}" if d.get("due_time") else "")
            lines.append(f"- {when} — {d['subject']}")
    else:
        lines.append("Активных дедлайнов на ближайшие три недели нет.")

    hw = await list_homework(10, gid)
    if hw:
        lines.append("Домашние задания (свежие):")
        for h in hw:
            when = f" (к {date.fromisoformat(h['lesson_date']).strftime('%d.%m')})" if h.get("lesson_date") else ""
            lines.append(f"- {h['subject']}{when}: {(h.get('content') or '[файл]')[:200]}")
    return "\n".join(lines)
