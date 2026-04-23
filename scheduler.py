import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import (
    TIMEZONE,
    SCHEDULE_HOUR, SCHEDULE_MINUTE,
    DEADLINE_REMINDER_HOUR, DEADLINE_REMINDER_MINUTE,
)
from database import get_all_subscribed_users, get_deadlines_soon
from schedule_parser import get_today_schedule

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


async def send_morning_schedule(bot: Bot):
    """Рассылает расписание на сегодня всем подписанным."""
    text = await get_today_schedule()
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить расписание {uid}: {e}")


async def send_deadline_reminders(bot: Bot):
    """Рассылает напоминания о дедлайнах в ближайшие 3 дня."""
    deadlines = await get_deadlines_soon(days=3)
    if not deadlines:
        return

    today = datetime.now(TZ).date()
    lines = ["⏳ <b>Ближайшие дедлайны группы:</b>\n"]
    for d in deadlines:
        due = d["due_date"]
        # Считаем дней до дедлайна
        from datetime import date
        delta = (date.fromisoformat(due) - today).days
        if delta == 0:
            badge = "🔴 Сегодня!"
        elif delta == 1:
            badge = "🟠 Завтра"
        else:
            badge = f"🟡 Через {delta} дн."

        time_part = f" {d['due_time']}" if d.get("due_time") else ""
        desc_part = f"\n   📝 {d['description']}" if d.get("description") else ""
        lines.append(
            f"• <b>{d['subject']}</b> — {due}{time_part} {badge}{desc_part}"
        )

    text = "\n".join(lines)
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить дедлайны {uid}: {e}")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        send_morning_schedule,
        trigger="cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        args=[bot],
        id="morning_schedule",
    )

    scheduler.add_job(
        send_deadline_reminders,
        trigger="cron",
        hour=DEADLINE_REMINDER_HOUR,
        minute=DEADLINE_REMINDER_MINUTE,
        args=[bot],
        id="deadline_reminders",
    )

    return scheduler
