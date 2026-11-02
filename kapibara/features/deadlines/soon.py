"""
«Срок скоро, а ты не сдал» (Никита 25.10): за N часов до срока — пуш, если
работа у человека не отмечена сданной. N — в «Уведомлениях» (notify_prefs:
deadline_soon, deadline_soon_hours, по умолчанию 3 ч; 1, 3, 6, 12 или 24).

Срок без времени — до 23:59, как у тестов (quiz_alerts.close_at). Кому — как
в quiz_alerts.visible_to: видит у себя, не сдал, не предмет по выбору, куда
не ходит. Тест, про который человек уже просил напоминать в «Тестах СДО»
(quiz_remind), здесь не повторяем. Что ушло — отметка в quiz_alerts (вид
«soon<часы>», время — срок): после перезапуска и переноса срока ничего не
придёт дважды, перенесли — придёт к новому сроку.

Проверка раз в 5 минут (scheduler.py); опоздали (перезапуск) — шлём ещё
LATE минут, позже — нет.
"""

import logging
from datetime import datetime, timedelta

from utils import TZ

logger = logging.getLogger(__name__)
LATE = 30           # мин


def due_at(d: dict) -> datetime:
    from quiz_alerts import close_at
    return close_at(d)


def is_due(d: dict, hours: int, now: datetime) -> bool:
    """Сейчас — то самое «за hours ч до срока» (с запасом LATE минут), и срок не прошёл."""
    due = due_at(d)
    at = due - timedelta(hours=hours)
    return at <= now < min(at + timedelta(minutes=LATE), due)


def text(d: dict, hours: int, now: datetime) -> tuple[str, str, str]:
    """(заголовок пуша, текст пуша, HTML для Telegram)."""
    from notify_prefs import minutes_text
    from push_text import split_subject, when
    from utils import esc
    due = due_at(d)
    left = max(1, round((due - now).total_seconds() / 60))
    left = hours * 60 if abs(left - hours * 60) <= LATE else left
    name, course = split_subject(d["subject"])
    title = f"Через {minutes_text(left)} срок: {name}"
    deadline = when(d["due_date"], d.get("due_time") or "23:59", now.date())
    body = " · ".join(x for x in (course, deadline, "ещё не сдано") if x)
    html = (f"⏰ <b>{esc(title)}</b>\n" + (f"{esc(course)} · " if course else "") + f"срок {esc(deadline)}\n"
            "Работа ещё не отмечена сданной.")
    return title, body, html


async def send_due(bot, now: datetime | None = None) -> int:
    """Раз в 5 минут: кому пора напомнить. → сколько ушло."""
    import notify_prefs
    import quiz_time
    from database import get_all_optional_answers, get_reminder_users
    from database.sdo import mark_quiz_alert
    from keyboards import app_button
    from quiz_alerts import visible_to
    now = now or datetime.now(TZ)
    users = [(u, p) for u in await get_reminder_users()
             if (p := notify_prefs.merge(u.get("notify"))).get("deadline_soon")]
    if not users:
        return 0
    answers = await get_all_optional_answers()
    sent = 0
    for user, prefs in users:
        uid, hours = user["user_id"], prefs["deadline_soon_hours"]
        for d in (await visible_to(uid, answers.get(uid))).values():
            if not is_due(d, hours, now):
                continue
            if prefs["quiz_remind"] and quiz_time.quiz_cmid(d.get("description")):
                continue                     # тест — уже напоминают «Тесты СДО»
            if not await mark_quiz_alert(uid, d["id"], f"soon{hours}", due_at(d).strftime("%Y-%m-%d %H:%M")):
                continue
            title, body, html = text(d, hours, now)
            try:
                import delivery
                await delivery.deliver(bot, uid, html, kind="deadlines", tab="deadlines", title=title, body=body,
                                       reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
                sent += 1
            except Exception as e:
                logger.info(f"срок скоро {uid}: {e}")      # обычно — бот заблокирован
    return sent
