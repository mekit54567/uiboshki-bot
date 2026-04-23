import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import TIMEZONE, SCHEDULE_HOUR, SCHEDULE_MINUTE, DEADLINE_REMINDER_HOUR, DEADLINE_REMINDER_MINUTE
from database import get_all_subscribed_users, get_deadlines_soon, get_user
from schedule_parser import get_today_schedule, get_first_lesson_today, fetch_schedule_raw, parse_events_for_date

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


async def send_morning_schedule(bot: Bot):
    text  = await get_today_schedule()
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить {uid}: {e}")


async def send_deadline_reminders(bot: Bot):
    deadlines = await get_deadlines_soon(days=3)
    if not deadlines:
        return

    from datetime import date
    today = date.today()
    lines = ["⏳ <b>Ближайшие дедлайны группы:</b>\n"]
    for d in deadlines:
        due   = date.fromisoformat(d["due_date"])
        delta = (due - today).days
        badge = "🔴 Сегодня!" if delta == 0 else ("🟠 Завтра" if delta == 1 else f"🟡 Через {delta} дн.")
        tp    = f" {d['due_time']}" if d.get("due_time") else ""
        dp    = f"\n   📝 {d['description']}" if d.get("description") else ""

        # Прогресс-бар (10 делений)
        if delta <= 0:
            bar = "🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴"
        else:
            filled = max(0, 10 - min(delta, 10))
            bar = "▓" * filled + "░" * (10 - filled)

        lines.append(f"• <b>{d['subject']}</b> — {d['due_date']}{tp} {badge}\n  [{bar}]{dp}")

    text  = "\n\n".join(lines)
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить {uid}: {e}")


async def check_lesson_reminders(bot: Bot):
    """Каждую минуту проверяем — не пора ли напомнить о паре."""
    try:
        now   = datetime.now(TZ)
        today = now.date()
        raw   = await fetch_schedule_raw()
        events = parse_events_for_date(raw, today)

        users = await get_all_subscribed_users()
        for uid in users:
            user = await get_user(uid)
            if not user:
                continue
            remind_mins = user.get("reminder_minutes", 15)
            remind_time = now + timedelta(minutes=remind_mins)

            for e in events:
                if not e["time_start"]:
                    continue
                t = e["time_start"]
                # Если пара начнётся ровно через remind_mins (±1 мин)
                diff = abs((t - remind_time).total_seconds())
                if diff <= 60:
                    try:
                        await bot.send_message(
                            uid,
                            f"⏰ <b>Через {remind_mins} минут пара!</b>\n\n"
                            f"┌ 📖 {e['summary']}\n"
                            f"└ 📍 {e['location'] or '—'}\n\n"
                            f"Начало в <b>{e['time'].split('–')[0]}</b>",
                            parse_mode="HTML"
                        )
                    except Exception as ex:
                        logger.warning(f"Reminder error {uid}: {ex}")
    except Exception as e:
        logger.error(f"check_lesson_reminders: {e}")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(send_morning_schedule,   "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_deadline_reminders, "cron", hour=DEADLINE_REMINDER_HOUR, minute=DEADLINE_REMINDER_MINUTE, args=[bot])
    scheduler.add_job(check_lesson_reminders,  "cron", minute="*",                  args=[bot])  # каждую минуту

    return scheduler
