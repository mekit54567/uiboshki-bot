"""
Новые задания из СДО и перенесённые сроки — всем, у кого включено
(уведомления → «Новые задания»).

Синк СДО (scheduler.sync_sdo_deadlines, раз в 6 ч) раньше писал только
старосте «добавлено N». Теперь каждому — одно сообщение на синк со списком:
что появилось и до когда. Показываем только то, что человек видит у себя в
дедлайнах (get_active_deadlines, свои отметки) и без предметов по выбору,
куда человек не ходит (OPTIONAL_SUBJECTS без ответа «хожу»), а
массовый завал — начало семестра, первый синк, СДО отдал всё разом — не
рассылаем: это не «новое», а «всё».
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)

MASS = 8            # больше за один синк — это не новые задания, а выгрузка всего
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def when(due_date: str, due_time: str | None) -> str:
    """«чт, 8 октября до 23:59»."""
    from schedule_parser import MONTHS_GEN
    d = date.fromisoformat(due_date)
    text = f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    return text + (f" до {due_time}" if due_time else "")


def _was(iso: str) -> str:
    from schedule_parser import MONTHS_GEN
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS_GEN[d.month - 1]}"


def _lines(items: list[dict]) -> list[str]:
    from utils import esc
    return [f"• <b>{esc(i['subject'])}</b> — " + ("теперь " if i.get("was") else "")
            + when(i["due_date"], i.get("due_time"))
            + (f" (было {_was(i['was'])})" if i.get("was") and i["was"] != i["due_date"] else "")
            for i in sorted(items, key=lambda i: (i["due_date"], i.get("due_time") or ""))]


def build(items: list[dict], moved: list[dict] | None = None, opened: list[str] | None = None) -> str:
    """Новые задания, перенесённые сроки и открытые тесты (строки
    quiz_alerts.open_line) — одним сообщением."""
    parts = []
    if opened:
        parts.append(("🔓 <b>Открыли тест</b>" if len(opened) == 1 else "🔓 <b>Открыли тесты</b>")
                     + "\n" + "\n".join(opened))
    if items:
        head = "🆕 В СДО новое задание:" if len(items) == 1 else "🆕 В СДО новые задания:"
        parts.append(head + "\n" + "\n".join(_lines(items)))
    if moved:
        head = "📅 Срок перенесли:" if len(moved) == 1 else "📅 Сроки перенесли:"
        parts.append(head + "\n" + "\n".join(_lines(moved)))
    return "\n\n".join(parts)


def headline(items: list[dict], moved: list[dict] | None = None, opened: list[dict] | None = None,
             today: date | None = None) -> tuple[str, str]:
    """Пуш (Никита 25.10): одно событие — «Новое задание: Практика 3» и ниже
    «Анализ данных · сдать в чт до 23:59»; несколько — «В СДО новое: 2
    задания, 1 перенос» и ниже названия."""
    from push_text import split_subject, when as when_s, word
    from utils import today_msk
    today = today or today_msk()
    moved, opened = moved or [], opened or []

    def due(d):
        return when_s(d["due_date"], d.get("due_time"), today)

    events = ([("Открыли тест", d) for d in opened] + [("Новое задание", d) for d in items]
              + [("Перенесли срок", d) for d in moved])
    if len(events) == 1:
        head, d = events[0]
        name, course = split_subject(d["subject"])
        if d.get("was"):
            tail = f"теперь {due(d)}" + (f", было {_was(d['was'])}" if d["was"] != d["due_date"] else "")
        else:
            tail = f"сдать {due(d)}"
        return f"{head}: {name}", " · ".join(x for x in (course, tail) if x)
    bits = []
    if opened:
        bits.append(f"{len(opened)} {word(len(opened), 'тест открыт', 'теста открыты', 'тестов открыто')}")
    if items:
        bits.append(f"{len(items)} {word(len(items), 'задание', 'задания', 'заданий')}")
    if moved:
        bits.append(f"{len(moved)} {word(len(moved), 'перенос', 'переноса', 'переносов')}")
    body = "; ".join(f"{split_subject(d['subject'])[0]} — {due(d)}" for _, d in events[:4])
    return "В СДО новое: " + ", ".join(bits), body


async def announce(bot, new_ids: list[int], moved: dict[int, str] | None = None) -> int:
    """Разослать про новые дедлайны и перенесённые сроки (из синка). → скольким ушло."""
    import notify_prefs
    from database import get_active_deadlines, get_reminder_users
    from keyboards import app_button
    moved = moved or {}
    if len(new_ids) > MASS:
        logger.info(f"новые задания: {len(new_ids)} за раз — не рассылаю (выгрузка, а не новое)")
        new_ids = []
    if len(moved) > MASS:
        logger.info(f"перенесённые сроки: {len(moved)} за раз — не рассылаю")
        moved = {}
    if not new_ids and not moved:
        return 0
    from config import OPTIONAL_SUBJECTS
    from database import get_all_optional_answers
    answers = await get_all_optional_answers()
    ids, sent = set(new_ids), 0
    opened_now = await _opened(new_ids)
    for user in await get_reminder_users():
        uid = user["user_id"]
        prefs = notify_prefs.merge(user.get("notify"))
        if not prefs.get("new_tasks") and not (prefs.get("quiz_open") and opened_now):
            continue
        # предметы по выбору, куда человек не ходит («хожу» не отвечал), — мимо
        skip = [s.lower() for s in OPTIONAL_SUBJECTS if not answers.get(uid, {}).get(s)]
        visible = [d for d in await get_active_deadlines(uid) if not d.get("done")
                   and not any(s in (d.get("subject") or "").lower() for s in skip)]
        mine = [d for d in visible if d["id"] in ids]
        # новый тест, который уже открыт, — «Открыли тест» (Тесты СДО → «Тест
        # открылся»), а не строкой нового задания; отметка — та же, что у
        # quiz_alerts, чтобы минутная проверка не прислала его ещё раз
        opened, opened_d = [], []
        if prefs.get("quiz_open"):
            from database.sdo import mark_quiz_alert
            for d in [d for d in mine if d["id"] in opened_now]:
                mine.remove(d)
                if await mark_quiz_alert(uid, d["id"], "open", ""):
                    opened.append(opened_now[d["id"]])
                    opened_d.append(d)
        if not prefs.get("new_tasks"):
            mine, shifted = [], []
        else:
            shifted = [dict(d, was=moved[d["id"]]) for d in visible if d["id"] in moved]
        if not mine and not shifted and not opened:
            continue
        try:
            import delivery
            title, short = headline(mine, shifted, opened_d)
            await delivery.deliver(bot, uid, build(mine, shifted, opened), kind="new_tasks", tab="deadlines",
                                   title=title, body=short,
                                   reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
            sent += 1
        except Exception as e:
            logger.info(f"новые задания {uid}: {e}")
    return sent


async def _opened(new_ids: list[int]) -> dict[int, str]:
    """Новые дедлайны-тесты, которые уже открыты: {id: строка для «Открыли тест»}."""
    if not new_ids:
        return {}
    import quiz_alerts
    import quiz_time
    from database import get_deadline, get_quiz_limits
    from database.sdo import get_quiz_opens
    from datetime import datetime
    from utils import TZ
    now = datetime.now(TZ)
    quizzes = [d for i in new_ids if (d := await get_deadline(i)) and quiz_time.quiz_cmid(d.get("description"))]
    if not quizzes:
        return {}
    cmids = [quiz_time.quiz_cmid(d["description"]) for d in quizzes]
    opens, limits = await get_quiz_opens(cmids), await get_quiz_limits(cmids)
    return {d["id"]: quiz_alerts.open_line(d, limits.get(c)) for d, c in zip(quizzes, cmids)
            if quiz_alerts.is_open(opens.get(c), now) and quiz_alerts.close_at(d) > now}
