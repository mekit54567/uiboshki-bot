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
from database import get_all_subscribed_users, get_deadlines_soon
from schedule_parser import get_today_schedule, fetch_schedule_raw, parse_events_for_date, format_lesson
from utils import esc, today_msk, esc_attr
from keyboards import app_button

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


async def _group_raws(fetch_home=None):
    """Календари групп для рассылки: {группа: (raw, свой корпус)} — каждый
    качается один раз на рассылку; своя группа — прежним вызовом (с кэшем и
    запасной копией), чужие — через общий кэш календарей МИРЭА."""
    import notify_prefs
    cache: dict = {}

    async def get(gid):
        import groups
        key = None if not gid or gid == groups.home_id() else gid
        if key not in cache:
            try:
                if key is None:
                    raw = await (fetch_home or fetch_schedule_raw)()
                else:
                    import schedule_parser
                    raw = await schedule_parser.fetch_schedule_raw(group_id=key)
                cache[key] = (raw, notify_prefs.home_campus(raw))
            except Exception as e:
                logger.error(f"Рассылка: расписание группы {key or 'своей'} не загрузилось: {e}")
                cache[key] = (None, None)
        return cache[key]
    return get


async def deliver(bot, user_id: int, html: str, **kw):
    """Рассылка через слой доставки (delivery.py): Telegram + пуш PWA."""
    import delivery
    return await delivery.deliver(bot, user_id, html, **kw)


async def pace():
    """Пауза между сообщениями рассылки: Telegram пускает ~30 в секунду, а
    групп и людей станет много (этап 1 (г))."""
    import asyncio
    await asyncio.sleep(PACE_SECONDS)


PACE_SECONDS = 0.05


async def send_morning_schedule(bot: Bot):
    import notify_prefs
    from database import get_user_group
    from optional_subjects import apply_for
    from schedule_parser import format_day

    now = datetime.now(TZ)
    weather_text = None          # погоду берём один раз и только если кому-то нужна
    raw_of = await _group_raws()

    users = await get_all_subscribed_users()
    for uid in users:
        try:
            prefs = await notify_prefs.get(uid)
            if not notify_prefs.allowed(prefs, "morning", now.weekday()):
                continue
            gid = await get_user_group(uid)
            raw, home = await raw_of(gid)            # у каждого — расписание его группы
            await apply_for(uid)   # у каждого своё: предметы по выбору
            events = parse_events_for_date(raw, now.date()) if raw is not None else None
            if prefs["skip_empty"] and events is not None and not events:
                continue
            head = "☀️ <b>Доброе утро!</b>"
            if prefs["weather"]:
                if weather_text is None:
                    try:
                        from handlers.weather import get_weather_for_morning
                        weather_text = await get_weather_for_morning() or ""
                    except Exception as e:
                        logger.error(f"Weather error: {e}")
                        weather_text = ""
                if weather_text:
                    head += f"\n{weather_text}"
            if prefs["campus"] and events:
                note = notify_prefs.campus_note(events, home)
                if note:
                    head += f"\n{note}"
            body = format_day(events, now.date(), now=now) if events is not None else await get_today_schedule(gid)
            await deliver(bot, uid, f"{head}\n\n{body}", kind="morning", tab="today",
                          reply_markup=app_button("📅 Открыть расписание", "today"))
            await pace()
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
        from config import OPTIONAL_SUBJECTS
        from handlers.schedule import _notes_block
        from optional_subjects import HIDE
        HIDE.set(frozenset(OPTIONAL_SUBJECTS))   # в общем чате — без предметов по выбору
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
    import notify_prefs
    weekday = today_msk().weekday()
    users = await get_all_subscribed_users()
    for uid in users:
        try:
            if not notify_prefs.allowed(await notify_prefs.get(uid), "deadlines", weekday):
                continue
            deadlines = await get_deadlines_soon(days=3, viewer_id=uid)
            if not deadlines:
                continue
            await deliver(bot, uid, _format_deadline_reminders(deadlines), kind="deadlines", tab="deadlines",
                          reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
            await pace()
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


async def _any_other_group() -> bool:
    """Есть ли люди из других групп (этап 1) — тогда напоминания смотрят и их календари."""
    import groups
    from database import group_counts
    return any(g["id"] and g["id"] != groups.home_id() for g in await group_counts())


async def check_lesson_reminders(bot: Bot):
    """Раз в минуту: кому пора напомнить о паре. Если в ближайшие часы пар нет
    — выходим, не трогая базу; иначе пользователи и их ответы про предметы
    по выбору — двумя запросами на всех, а расписание разбирается один раз на
    каждый набор скрытых предметов, а не на каждого человека."""
    global _sent_reminders
    try:
        import notify_prefs
        from config import OPTIONAL_SUBJECTS
        from database import get_all_optional_answers, get_reminder_users
        from optional_subjects import HIDE, no_filter
        now   = datetime.now(TZ)
        today = now.date()
        _sent_reminders = {k for k in _sent_reminders if k[0] == today}

        horizon = max(spec["max"] for spec in notify_prefs.REMIND.values()) * 60 + 120
        raw_of = await _group_raws()
        upcoming_of: dict = {}

        async def upcoming_for(gid):
            """Есть ли у группы пары в ближайшие часы (иначе её людей не трогаем)."""
            if gid not in upcoming_of:
                raw, _ = await raw_of(gid)
                with no_filter():
                    upcoming_of[gid] = raw is not None and any(
                        e["time_start"] and 0 <= (e["time_start"] - now).total_seconds() <= horizon
                        for e in parse_events_for_date(raw, today))
            return upcoming_of[gid]

        if not await upcoming_for(None) and not await _any_other_group():
            return                       # своя группа без пар и других групп нет — база не нужна

        answers = await get_all_optional_answers()
        by_hide: dict[tuple, list] = {}
        for user in await get_reminder_users():
            uid = user["user_id"]
            prefs = notify_prefs.merge(user.get("notify"))
            if not notify_prefs.allowed(prefs, "lessons", today.weekday()):
                continue
            gid = user.get("group_id")
            if not await upcoming_for(gid):
                continue
            raw, _ = await raw_of(gid)
            mine = answers.get(uid, {})
            hide = frozenset(s for s in OPTIONAL_SUBJECTS if not mine.get(s))
            key_h = (gid, hide)
            if key_h not in by_hide:
                token = HIDE.set(hide)
                try:
                    by_hide[key_h] = parse_events_for_date(raw, today)
                finally:
                    HIDE.reset(token)
            hide = key_h

            # У каждой пары свой сценарий: первая за день, после короткой
            # перемены или после большого перерыва — и своё «за сколько».
            for e, remind_mins, kind in notify_prefs.plan_reminders(by_hide[hide], prefs):
                t = e["time_start"]
                diff = abs((t - (now + timedelta(minutes=remind_mins))).total_seconds())
                if diff > 60:
                    continue
                key = (today, uid, t.strftime("%H:%M"), remind_mins)
                if key in _sent_reminders:
                    continue
                _sent_reminders.add(key)
                label = "первая пара" if kind == "remind_first" else "пара"
                try:
                    await deliver(
                        bot, uid,
                        f"⏰ <b>Через {notify_prefs.minutes_text(remind_mins)} {label}</b>\n\n"
                        + format_lesson(e),
                        kind="lesson", tab="today",
                        reply_markup=app_button("📅 Расписание", "today"),
                    )
                except Exception as ex:
                    logger.warning(f"Reminder error {uid}: {ex}")
    except Exception as e:
        logger.error(f"check_lesson_reminders: {e}")


# ── Автосинк дедлайнов из СДО ────────────────────────────────────────────────

_sdo_expired_notified = False  # не спамим старосте одним и тем же каждые N часов
_sdo_error_notified = False    # то же для сетевой недоступности СДО


async def _note_sync(result: dict):
    """Чем кончился синк — для /status (health.py)."""
    import health
    if result.get("missing"):
        return
    if "error" in result:
        await health.note("sdo_sync", False, "СДО не ответил")
    elif result.get("expired"):
        await health.note("sdo_sync", False, "кука протухла")
        await health.note("sdo_cookie", False, "протухла — обнови SDO_SESSION_COOKIE")
    else:
        await health.note("sdo_sync", True, f"новых {result.get('added', 0)}, изменено {result.get('updated', 0)}")


async def sdo_keepalive():
    """Лёгкий запрос в СДО раз в час (сессия не гаснет) + отметка для /status."""
    import health
    from sdo_parser import keepalive
    from config import SDO_SESSION_COOKIE
    if not SDO_SESSION_COOKIE:
        return
    ok = await keepalive()
    await health.note("sdo_cookie", ok, "" if ok else "СДО не пустил — возможно, кука протухла")
    import sdo_parser
    if ok and sdo_parser.IDLE_TIMEOUT:
        from database import set_setting
        await set_setting("sdo:idle_timeout", str(sdo_parser.IDLE_TIMEOUT))


async def sync_sdo_deadlines(bot: Bot):
    global _sdo_expired_notified
    from sdo_parser import sync_deadlines

    result = await sync_deadlines()
    await _note_sync(result)

    if result.get("missing"):
        return  # СДО не подключали (нет SDO_SESSION_COOKIE) — не о чем напоминать

    if "error" in result:
        # Сетевой сбой, а не протухшая кука: например, online-edu.mirea.ru не
        # пускает зарубежные IP (сервер Railway в US West). Раньше это молча
        # глоталось, и никто не знал, что автосинк не работает вовсе.
        global _sdo_error_notified
        if not _sdo_error_notified and STAROSTA_ID:
            try:
                await bot.send_message(
                    STAROSTA_ID,
                    "⚠️ СДО недоступен с сервера бота — автосинк дедлайнов не работает.\n\n"
                    f"Ошибка: {result['error'][:300]}\n\n"
                    "Если так будет и дальше, скорее всего online-edu.mirea.ru не пускает "
                    "зарубежные адреса (сервер бота — в США).",
                )
                _sdo_error_notified = True
            except Exception as e:
                logger.warning(f"Не смог уведомить старосту о недоступности СДО: {e}")
        return
    _sdo_error_notified = False

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

    if (result["added"] or result.get("updated") or result.get("gone")) and STAROSTA_ID:
        parts = []
        if result["added"]:
            parts.append(f"добавлено новых дедлайнов — {result['added']}")
        if result.get("updated"):
            parts.append(f"перенесено/изменено — {result['updated']}")
        if result.get("gone"):
            parts.append(f"пропало из СДО и убрано — {len(result['gone'])} ({'; '.join(result['gone'][:5])})")
        try:
            await bot.send_message(
                STAROSTA_ID,
                f"🔄 Автосинк СДО: {', '.join(parts)}",
            )
        except Exception as e:
            logger.warning(f"Не смог уведомить старосту об автосинке СДО: {e}")
    # каждому — что появилось нового (у кого включено «Новые задания»)
    try:
        import new_tasks
        await new_tasks.announce(bot, result.get("new_ids") or [], result.get("moved") or {})
    except Exception as e:
        logger.warning(f"новые задания: рассылка не вышла: {e}")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    from schedule_diff import check_schedule_changes

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(send_morning_schedule,       "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_group_morning_digest,   "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_deadline_reminders, "cron", hour=DEADLINE_REMINDER_HOUR, minute=DEADLINE_REMINDER_MINUTE, args=[bot])
    scheduler.add_job(check_lesson_reminders,  "cron", minute="*",                  args=[bot])
    from weekly_digest import send_all as send_weekly_digest      # обзор недели — воскресенье, 19:00
    scheduler.add_job(send_weekly_digest,      "cron", day_of_week="sun", hour=19, minute=0, args=[bot])
    from grade_alerts import check_all as check_new_grades     # новые баллы СДО — днём раз в 3 часа
    scheduler.add_job(check_new_grades,        "cron", hour="10,13,16,19,22", minute=7, args=[bot])
    from deadline_reminders import send_due as send_deadline_custom_reminders   # свои напоминания о дедлайне
    scheduler.add_job(send_deadline_custom_reminders, "cron", minute="*",        args=[bot])
    # Первый синк — через минуту после запуска: после деплоя СДО иначе молчал
    # до 6 часов, и сессия Moodle успевала истечь. Плюс лёгкий запрос в СДО
    # каждый час, чтобы сессия не гасла без обращений (sdo_parser.keepalive).
    scheduler.add_job(sync_sdo_deadlines,      "interval", hours=SDO_SYNC_INTERVAL_HOURS, args=[bot],
                      next_run_time=datetime.now(ZoneInfo(TIMEZONE)) + timedelta(minutes=1))
    import group_sync                     # СДО других групп по входам, которыми поделились (этап 1 (в))
    scheduler.add_job(group_sync.sync_all,     "interval", hours=SDO_SYNC_INTERVAL_HOURS, args=[bot],
                      next_run_time=datetime.now(TZ) + timedelta(minutes=5))
    scheduler.add_job(sdo_keepalive,           "interval", minutes=55)
    # Входы студентов в СДО — вразнобой: раз в минуту проверяются те, чья
    # очередь (50–59 мин случайно, потом 55), а не все разом (sdo_accounts.py)
    from sdo_accounts import keepalive_due
    scheduler.add_job(keepalive_due,           "interval", minutes=1, args=[bot])
    from database import purge_events          # статистика старше 180 дней не нужна
    scheduler.add_job(purge_events,            "cron", hour=4, minute=20)
    import health
    scheduler.add_job(health.alert_errors,     "interval", minutes=15, args=[bot])   # всплеск ошибок — старосте
    import stats
    scheduler.add_job(stats.send_evening,      "cron", hour=21, minute=3, args=[bot])  # +N новых за день — старосте
    scheduler.add_job(check_schedule_changes,  "interval", minutes=SCHEDULE_DIFF_CHECK_MINUTES, args=[bot])
    # Справочник для поиска преподавателей/групп/аудиторий: достроить, если
    # обход прервался (редеплой), и обновлять раз в месяц (см. schedule_index).
    import schedule_index
    scheduler.add_job(schedule_index.ensure_fresh, "cron", hour=4, minute=10)
    # Поиск по смыслу: нарезать лекции по страницам и досчитать векторы —
    # понемногу, в пределах бесплатных лимитов Gemini (semantic_index.py).
    import semantic_index

    async def index_lectures():
        try:
            await semantic_index.index_pending(bot)
        except Exception as e:
            logger.warning(f"индекс поиска: {type(e).__name__}: {e}")
    scheduler.add_job(index_lectures, "interval", minutes=20, next_run_time=datetime.now(TZ) + timedelta(minutes=2))
    import local_embed
    scheduler.add_job(local_embed.unload_idle, "interval", minutes=5)    # своя модель векторов — из памяти после простоя
    # Копия базы старосте каждую ночь, без звука (backup.py).
    if STAROSTA_ID:
        from backup import send_backup
        scheduler.add_job(send_backup, "cron", hour=4, minute=40, args=[bot, STAROSTA_ID])
    return scheduler
