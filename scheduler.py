import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import TIMEZONE, SCHEDULE_HOUR, SCHEDULE_MINUTE, DEADLINE_REMINDER_HOUR, DEADLINE_REMINDER_MINUTE
from database import get_all_subscribed_users, get_deadlines_soon, get_user
from schedule_parser import get_today_schedule, fetch_schedule_raw, parse_events_for_date

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

# Храним уже отправленные напоминания чтобы не дублировать
_sent_reminders: set[tuple] = set()


def format_date(date_str: str) -> str:
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%d.%m.%Y")
    except:
        return date_str


def progress_bar(delta: int, max_days: int = 14) -> str:
    if delta <= 0:
        return "━━━━━━━━━━ 100%"
    filled = max(0, 10 - min(int(delta / max_days * 10), 10))
    bar = "━" * filled + "╌" * (10 - filled)
    pct = max(0, min(100, filled * 10))
    return f"{bar} {pct}%"


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

    today = date.today()
    lines = ["⏳ <b>Ближайшие дедлайны группы:</b>\n"]
    for d in deadlines:
        due   = date.fromisoformat(d["due_date"])
        delta = (due - today).days
        badge = "🔴 Сегодня!" if delta == 0 else ("🟠 Завтра" if delta == 1 else f"🟡 Через {delta} дн.")
        tp    = f" в {d['due_time']}" if d.get("due_time") else ""
        desc  = f"\n   📝 {d['description']}" if d.get("description") and d["description"] not in ("", "-") else ""
        lines.append(
            f"• <b>{d['subject']}</b>\n"
            f"  📅 {format_date(d['due_date'])}{tp} — {badge}\n"
            f"  {progress_bar(delta)}{desc}"
        )

    text  = "\n\n".join(lines)
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить {uid}: {e}")


async def check_lesson_reminders(bot: Bot):
    """Каждую минуту проверяем — не пора ли напомнить о паре. Без дублей."""
    global _sent_reminders
    try:
        now   = datetime.now(TZ)
        today = now.date()
        # Сбрасываем кэш в полночь
        if now.hour == 0 and now.minute == 0:
            _sent_reminders.clear()

        raw    = await fetch_schedule_raw()
        events = parse_events_for_date(raw, today)
        users  = await get_all_subscribed_users()

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
                diff = abs((t - remind_time).total_seconds())
                if diff <= 60:
                    # Ключ уникальности: пользователь + время пары + минуты напоминания
                    key = (uid, t.strftime("%H:%M"), remind_mins)
                    if key in _sent_reminders:
                        continue
                    _sent_reminders.add(key)
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
    scheduler.add_job(check_lesson_reminders,  "cron", minute="*",                  args=[bot])
    return scheduler
