import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    TIMEZONE, SCHEDULE_HOUR, SCHEDULE_MINUTE, DEADLINE_REMINDER_HOUR, DEADLINE_REMINDER_MINUTE,
    SDO_SYNC_INTERVAL_HOURS, STAROSTA_ID, SCHEDULE_DIFF_CHECK_MINUTES, GROUP_CHAT_ID,
)
from database import get_all_subscribed_users, get_deadlines_soon, get_user
from schedule_parser import get_today_schedule, fetch_schedule_raw, parse_events_for_date, format_lesson
from utils import esc, today_msk, esc_attr

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

# Ключ — (дата, user_id, время пары, за сколько минут). Дата обязательна:
# раньше её не было, а набор чистился только ровно в 00:00 — если джоба в
# эту минуту не запустилась (APScheduler пропускает запуск, пока ещё
# крутится предыдущий, или бот перезапускался), набор не чистился никогда,
# и напоминание о паре в то же время на следующий день молча не приходило.
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
    schedule_text = await get_today_schedule()

    # Приветствие + погода одной строкой (если не получили — без неё)
    try:
        from handlers.weather import get_weather_for_morning
        weather_text = await get_weather_for_morning()
    except Exception as e:
        logger.error(f"Weather error: {e}")
        weather_text = ""
    head = "☀️ <b>Доброе утро!</b>" + (f"\n{weather_text}" if weather_text else "")
    full_text = f"{head}\n\n{schedule_text}"

    users = await get_all_subscribed_users()
    for uid in users:
        try:
            await bot.send_message(uid, full_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить {uid}: {e}")


async def send_group_morning_digest(bot: Bot):
    """Короткий утренний дайджест в общий чат группы (не в личку): расписание
    на сегодня + пометки к парам, если есть. Без погоды — в группе это лишнее,
    оставляем это личным рассылкам. Молчит, если GROUP_CHAT_ID не настроен —
    это не критическая функция, чтобы падать при её отсутствии."""
    if not GROUP_CHAT_ID:
        return
    try:
        from handlers.schedule import _notes_block
        text = await get_today_schedule()
        text += await _notes_block(today_msk().isoformat())
        await bot.send_message(GROUP_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не смог отправить утренний дайджест в группу: {e}")


def _format_deadline_reminders(deadlines: list[dict]) -> str:
    from handlers.deadlines import due_label
    today = today_msk()
    lines = ["⏳ <b>Ближайшие дедлайны группы</b>"]
    for d in deadlines:
        due = date.fromisoformat(d["due_date"])
        desc = (d.get("description") or "").strip()
        extra = ""
        if desc.startswith(("http://", "https://")):
            extra = f' · <a href="{esc_attr(desc)}">задание</a>'
        elif desc and desc not in ("-", "–"):
            extra = f"\n   📝 {esc(desc[:200])}"
        lines.append(f"• <b>{esc(d['subject'])}</b>\n   {due_label(due, today, d.get('due_time'))}{extra}")
    return "\n\n".join(lines)


# Вопрос старосте дописывается в конец того же текста — хендлер кнопки
# (handlers/deadlines.py: deadline_post_confirm) отрезает его перед отправкой
# в группу, иначе группа видела бы "Опубликовать этот список?" в самом посте.
DEADLINE_POST_QUESTION = "\n\n👆 Опубликовать этот список в общий чат группы?"

DEADLINE_POST_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Опубликовать в группу", callback_data="dlpost:yes"),
    InlineKeyboardButton(text="🚫 Не публиковать", callback_data="dlpost:no"),
]])


async def send_deadline_reminders(bot: Bot):
    # Дедлайны теперь бывают личные (видны только автору) — рассылка каждому
    # подписчику собирается персонально (общие + его личные, не отмеченные им
    # самим), а не одним и тем же текстом всем подряд.
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            deadlines = await get_deadlines_soon(days=3, viewer_id=uid)
            if not deadlines:
                continue
            await bot.send_message(uid, _format_deadline_reminders(deadlines), parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить {uid}: {e}")

    # В общий чат группы имеет смысл предлагать публиковать только общие
    # дедлайны (старосты/автосинка СДО), никогда — чью-то личную запись.
    if STAROSTA_ID and GROUP_CHAT_ID:
        try:
            shared = await get_deadlines_soon(days=3, shared_only=True)
            if shared:
                text = _format_deadline_reminders(shared)
                await bot.send_message(
                    STAROSTA_ID,
                    text + DEADLINE_POST_QUESTION,
                    parse_mode="HTML",
                    reply_markup=DEADLINE_POST_KB,
                )
        except Exception as e:
            logger.warning(f"Не смог отправить старосте запрос на публикацию дедлайнов: {e}")


async def check_lesson_reminders(bot: Bot):
    global _sent_reminders
    try:
        now   = datetime.now(TZ)
        today = now.date()
        _sent_reminders = {k for k in _sent_reminders if k[0] == today}

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
                    key = (today, uid, t.strftime("%H:%M"), remind_mins)
                    if key in _sent_reminders:
                        continue
                    _sent_reminders.add(key)
                    try:
                        await bot.send_message(
                            uid,
                            f"⏰ <b>Через {remind_mins} мин пара</b>\n\n"
                            + format_lesson(e),
                            parse_mode="HTML"
                        )
                    except Exception as ex:
                        logger.warning(f"Reminder error {uid}: {ex}")
    except Exception as e:
        logger.error(f"check_lesson_reminders: {e}")


# ── Автосинк дедлайнов из СДО ────────────────────────────────────────────────

_sdo_expired_notified = False  # не спамим старосте одним и тем же каждые N часов


async def sync_sdo_deadlines(bot: Bot):
    global _sdo_expired_notified
    from sdo_parser import sync_deadlines

    result = await sync_deadlines()

    if result.get("expired"):
        if not _sdo_expired_notified and STAROSTA_ID:
            try:
                await bot.send_message(
                    STAROSTA_ID,
                    "⚠️ Сессия СДО протухла — автосинк дедлайнов не работает.\n\n"
                    "Зайди в online-edu.mirea.ru в браузере (с опцией «запомнить меня»), "
                    "возьми свежее значение куки MoodleSession (DevTools → Application → "
                    "Cookies) и обнови переменную окружения SDO_SESSION_COOKIE.",
                )
                _sdo_expired_notified = True
            except Exception as e:
                logger.warning(f"Не смог уведомить старосту о протухшей куке СДО: {e}")
        return

    _sdo_expired_notified = False  # сессия снова живая — сбрасываем флаг

    if (result["added"] or result.get("updated")) and STAROSTA_ID:
        parts = []
        if result["added"]:
            parts.append(f"добавлено новых дедлайнов — {result['added']}")
        if result.get("updated"):
            parts.append(f"перенесено/изменено — {result['updated']}")
        try:
            await bot.send_message(
                STAROSTA_ID,
                f"🔄 Автосинк СДО: {', '.join(parts)}",
            )
        except Exception as e:
            logger.warning(f"Не смог уведомить старосту об автосинке СДО: {e}")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    from schedule_diff import check_schedule_changes

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(send_morning_schedule,       "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_group_morning_digest,   "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_deadline_reminders, "cron", hour=DEADLINE_REMINDER_HOUR, minute=DEADLINE_REMINDER_MINUTE, args=[bot])
    scheduler.add_job(check_lesson_reminders,  "cron", minute="*",                  args=[bot])
    scheduler.add_job(sync_sdo_deadlines,      "interval", hours=SDO_SYNC_INTERVAL_HOURS, args=[bot])
    scheduler.add_job(check_schedule_changes,  "interval", minutes=SCHEDULE_DIFF_CHECK_MINUTES, args=[bot])
    # Справочник для поиска преподавателей/групп/аудиторий: достроить, если
    # обход прервался (редеплой), и обновлять раз в месяц (см. schedule_index).
    import schedule_index
    scheduler.add_job(schedule_index.ensure_fresh, "cron", hour=4, minute=10)
    return scheduler
