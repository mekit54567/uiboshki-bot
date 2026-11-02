"""
Свои напоминания о дедлайне: у дедлайна в приложении — «Напомнить» → за день,
за 3 часа, за час или своё время. Приходит в личку с кнопкой «Открыть
дедлайны». Если человек уже отметил дедлайн сделанным или дедлайн удалили —
не приходит. Время — МСК, «ГГГГ-ММ-ДД ЧЧ:ММ» (сравнивается строкой).
Проверка — раз в минуту (scheduler.py: send_deadline_custom_reminders).
"""

import logging
from datetime import datetime, timedelta

from utils import TZ

logger = logging.getLogger(__name__)

PRESETS = {"1d": timedelta(days=1), "3h": timedelta(hours=3), "1h": timedelta(hours=1)}
FMT = "%Y-%m-%d %H:%M"


def due_at(d: dict) -> datetime:
    """Срок дедлайна: дата + время (нет времени — конец дня)."""
    t = (d.get("due_time") or "23:59").strip()[:5]
    return datetime.strptime(f"{d['due_date']} {t}", FMT).replace(tzinfo=TZ)


def resolve(d: dict, preset: str | None, at: str | None, now: datetime | None = None) -> str:
    """Время напоминания строкой; ValueError с понятным текстом, если нельзя."""
    now = now or datetime.now(TZ)
    if preset:
        if preset not in PRESETS:
            raise ValueError("нет такого варианта")
        when = due_at(d) - PRESETS[preset]
    else:
        try:
            when = datetime.strptime((at or "").replace("T", " ")[:16], FMT).replace(tzinfo=TZ)
        except ValueError:
            raise ValueError("время в формате ГГГГ-ММ-ДД ЧЧ:ММ")
    if when <= now:
        raise ValueError("это время уже прошло")
    if when > due_at(d) + timedelta(days=1):
        raise ValueError("позже срока — смысла нет")
    return when.strftime(FMT)


def label(at: str, now: datetime | None = None) -> str:
    """«завтра в 18:00», «сегодня в 21:00», «5 окт в 9:00»."""
    from schedule_parser import MONTHS_GEN
    now = now or datetime.now(TZ)
    t = datetime.strptime(at, FMT)
    days = (t.date() - now.date()).days
    hm = f"{t.hour}:{t.minute:02d}"
    if days == 0:
        return f"сегодня в {hm}"
    if days == 1:
        return f"завтра в {hm}"
    return f"{t.day} {MONTHS_GEN[t.month - 1]} в {hm}"


async def send_due(bot, now: datetime | None = None):
    from database import due_deadline_reminders, mark_deadline_reminder_sent
    from handlers.deadlines import due_label
    from keyboards import app_button
    from utils import esc
    now = now or datetime.now(TZ)
    for r in await due_deadline_reminders(now.strftime(FMT)):
        await mark_deadline_reminder_sent(r["user_id"], r["deadline_id"], r["remind_at"])
        if r["done"]:
            continue
        due = datetime.strptime(r["due_date"], "%Y-%m-%d").date()
        desc = (r.get("description") or "").strip()
        text = (f"⏰ <b>Напоминание: {esc(r['subject'])}</b>\n{due_label(due, now.date(), r.get('due_time'))}"
                + (f"\n📝 {esc(desc[:300])}" if desc and not desc.startswith("http") else ""))
        from push_text import split_subject, when
        name, course = split_subject(r["subject"])
        try:
            # через слой доставки: раньше — только Telegram, и в приложении
            # (вход через VK/Яндекс) своё напоминание не приходило совсем
            import delivery
            await delivery.deliver(bot, r["user_id"], text, kind="deadlines", tab="deadlines",
                                   title=f"Напоминание: {name}",
                                   body=" · ".join(x for x in (course, "срок " + when(r["due_date"], r.get("due_time"), now.date())) if x),
                                   reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
        except Exception as e:
            logger.info(f"напоминание о дедлайне не дошло до {r['user_id']}: {e!r}")  # обычно — бот заблокирован
