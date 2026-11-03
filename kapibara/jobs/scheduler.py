import asyncio
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from kapibara.core.config import (
    TIMEZONE, SCHEDULE_HOUR, SCHEDULE_MINUTE, DEADLINE_REMINDER_HOUR, DEADLINE_REMINDER_MINUTE,
    SDO_SYNC_INTERVAL_HOURS, STAROSTA_ID, SCHEDULE_DIFF_CHECK_MINUTES, GROUP_CHAT_ID,
)
from database import get_all_subscribed_users, get_deadlines_soon
from kapibara.features.schedule.parser import get_today_schedule, fetch_schedule_raw, parse_events_for_date, format_lesson
from kapibara.core.utils import esc, today_msk, esc_attr
from kapibara.core.errors import aside
from kapibara.core.telegram import app_button
from kapibara.features.notifications.broadcast import pace

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
    except (TypeError, ValueError):      # не дата — показать как есть
        return date_str


def progress_bar(delta: int, max_days: int = 14) -> str:
    if delta <= 0:
        return "━━━━━━━━━━ 100%"
    filled = max(0, 10 - min(int(delta / max_days * 10), 10))
    bar = "━" * filled + "╌" * (10 - filled)
    pct = max(0, min(100, filled * 10))
    return f"{bar} {pct}%"


async def _group_raws(fetch_home=None):
    """Календари групп для рассылки — kapibara.features.notifications.broadcast;
    своя группа — fetch_schedule_raw этого модуля (тесты его подменяют)."""
    from kapibara.features.notifications import broadcast
    return await broadcast.group_raws(fetch_home or fetch_schedule_raw)


async def deliver(bot, user_id: int, html: str, **kw):
    """Рассылка через слой доставки (delivery.py): Telegram + пуш PWA."""
    from kapibara.features.notifications import delivery
    return await delivery.deliver(bot, user_id, html, **kw)


INDEX_FIRST_DELAY = 10          # мин после запуска до первого прохода индекса лекций


async def send_morning_schedule(bot: Bot):
    from kapibara.features.notifications import prefs as notify_prefs
    from database import get_user_group
    from kapibara.features.groups.optional_subjects import apply_for
    from kapibara.features.schedule.parser import format_day

    now = datetime.now(TZ)
    weather_text = None          # погоду берём один раз и только если кому-то нужна
    raw_of = await _group_raws()

    users = await get_all_subscribed_users()
    for uid in users:
        with aside(logger, f"рассылка: не смог отправить {uid}"):
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
                    weather_text = ""            # не вышло — утро без погоды
                    with aside(logger, "утро: погода"):
                        from kapibara.features.weather.forecast import get_weather_for_morning
                        weather_text = await get_weather_for_morning() or ""
                if weather_text:
                    head += f"\n{weather_text}"
            if prefs["campus"] and events:
                note = notify_prefs.campus_note(events, home)
                if note:
                    head += f"\n{note}"
            body = format_day(events, now.date(), now=now) if events is not None else await get_today_schedule(gid)
            title, short = morning_push(events, home, prefs, weather_text) if events is not None else (None, None)
            await deliver(bot, uid, f"{head}\n\n{body}", kind="morning", tab="today", title=title, body=short,
                          reply_markup=app_button("📅 Открыть расписание", "today"))
            await pace()


def morning_push(events: list[dict], home: str | None, prefs: dict, weather: str | None):
    """Пуш утра (Никита 25.10): «Сегодня: 5 пар с 09:00, В-78» и «Первая — …
    · ☁️ +3°, пасмурно». events — пары дня (parse_events_for_date, без
    предметов по выбору, куда человек не ходит)."""
    from kapibara.features.notifications.evening_digest import day_title, first_pair
    from kapibara.features.schedule.format import _split_kind
    lessons = []
    for e in sorted((e for e in events if e.get("time_start")), key=lambda e: e["time_start"]):
        name, kind, _ = _split_kind(e.get("summary") or "")
        if kind != "сам. работа":
            lessons.append({"start": e["time_start"].strftime("%H:%M"), "pairs": 1, "title": name,
                            "kind": kind, "room": e.get("location") or ""})
    sky = (weather or "").split(" · ")[0] if prefs.get("weather") else ""
    if not lessons:
        return "Сегодня пар нет", sky or "Отдыхай"
    title = day_title(lessons, "Сегодня", home, prefs.get("campus", True))
    return title, " · ".join(x for x in (first_pair(lessons), sky) if x)


async def group_chat() -> int:
    """Чат своей группы: GROUP_CHAT_ID или запомненный, когда староста
    добавил бота в чат (handlers/members_chat.py). 0 — не задан."""
    from kapibara.features.groups import members
    return GROUP_CHAT_ID or await members.chat_id()


def morning_caption(lessons: list[dict], notes: str) -> str:
    """Подпись к утренней карточке в чате группы (до 1024 знаков — лимит Telegram)."""
    from kapibara.features.schedule.card import _pairs_word
    n = sum(l.get("pairs", 1) for l in lessons)
    first = lessons[0]
    where = f" · {esc(first['room'])}" if first.get("room") else ""
    text = (f"☀️ <b>Доброе утро!</b> Сегодня {n} {_pairs_word(n)}, "
            f"с {first['start']} до {lessons[-1]['end']}.\nПервая — {esc(first['title'])}{where}")
    return text + notes if len(text + notes) <= 1000 else text


def group_app_kb() -> InlineKeyboardMarkup:
    """Кнопка-ссылка (в группе кнопки web_app не работают)."""
    from kapibara.core.config import BOT_USERNAME
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="📱 Открыть Капибару", url=f"https://t.me/{BOT_USERNAME}?startapp")]])


async def send_group_morning(bot: Bot, chat_id: int | None = None) -> str:
    """Утром в чат группы — карточка дня «Мел» (как в @боте) с подписью и
    заметками к парам. Без предметов по выбору. Пар нет — молчим. Отключить —
    /groupmorning off у старосты. chat_id — куда (превью старосте).
    Возвращает, что вышло: sent / no_chat / off / no_lessons."""
    from aiogram.types import BufferedInputFile
    from database import get_setting
    from kapibara.core.config import BOT_USERNAME, GROUP_NAME, OPTIONAL_SUBJECTS
    from kapibara.features.groups.optional_subjects import HIDE
    from kapibara.features.schedule import card
    from kapibara.features.schedule.parser import lessons_for_date
    from handlers.schedule import _notes_block
    if chat_id is None:                                  # не превью старосте — в чат группы
        if await get_setting("group_morning") == "off":
            return "off"
        if not (chat_id := await group_chat()):
            return "no_chat"
    HIDE.set(frozenset(OPTIONAL_SUBJECTS))       # в общем чате — без предметов по выбору
    raw = await fetch_schedule_raw()
    now = datetime.now(TZ)
    lessons = lessons_for_date(raw, now.date())
    if not lessons:
        return "no_lessons"
    data = await asyncio.to_thread(card.build_own, raw, "today", now, GROUP_NAME, BOT_USERNAME)
    caption = morning_caption(lessons, await _notes_block(now.date().isoformat()))
    await bot.send_photo(chat_id, BufferedInputFile(data, "today.jpg"), caption=caption,
                         parse_mode="HTML", reply_markup=group_app_kb())
    return "sent"


async def send_group_morning_digest(bot: Bot):
    """Задание по расписанию: сбой не роняет планировщик, но виден в логах."""
    with aside(logger, "Не смог отправить утреннюю карточку в группу"):
        await send_group_morning(bot)


def _format_deadline_reminders(deadlines: list[dict]) -> str:
    from kapibara.features.deadlines.labels import due_label
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


def deadlines_push(deadlines: list[dict], today: date | None = None) -> tuple[str, str]:
    """Пуш о сроках (Никита 25.10): один — «Завтра до 23:59: Практика 2»,
    несколько — «3 срока за 3 дня, ближайший завтра»; ниже — что и когда."""
    from kapibara.features.notifications.push_text import cap, split_subject, when, word
    today = today or today_msk()
    items = sorted(deadlines, key=lambda d: (d["due_date"], d.get("due_time") or "99"))
    first = items[0]
    name, course = split_subject(first["subject"])
    if len(items) == 1:
        return f"{cap(when(first['due_date'], first.get('due_time'), today))}: {name}", course or "Срок близко"
    n = len(items)
    title = f"{n} {word(n, 'срок', 'срока', 'сроков')} за 3 дня, ближайший {when(first['due_date'], None, today)}"
    body = "; ".join(f"{split_subject(d['subject'])[0]} — {when(d['due_date'], d.get('due_time'), today)}"
                     for d in items[:4])
    return title, body + (f" и ещё {n - 4}" if n > 4 else "")


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
    from kapibara.features.notifications import prefs as notify_prefs
    weekday = today_msk().weekday()
    users = await get_all_subscribed_users()
    for uid in users:
        with aside(logger, f"рассылка: не смог отправить {uid}"):
            if not notify_prefs.allowed(await notify_prefs.get(uid), "deadlines", weekday):
                continue
            deadlines = await get_deadlines_soon(days=3, viewer_id=uid)
            if not deadlines:
                continue
            title, short = deadlines_push(deadlines)
            await deliver(bot, uid, _format_deadline_reminders(deadlines), kind="deadlines", tab="deadlines",
                          title=title, body=short,
                          reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
            await pace()

    # В общий чат группы имеет смысл предлагать публиковать только общие
    # дедлайны (старосты/автосинка СДО), никогда — чью-то личную запись.
    if STAROSTA_ID and await group_chat():
        with aside(logger, "Не смог отправить старосте запрос на публикацию дедлайнов"):
            shared = await get_deadlines_soon(days=3, shared_only=True)
            if shared:
                text = _format_deadline_reminders(shared)
                await bot.send_message(
                    STAROSTA_ID,
                    text + DEADLINE_POST_QUESTION,
                    parse_mode="HTML",
                    reply_markup=DEADLINE_POST_KB,
                )


async def _any_other_group() -> bool:
    """Есть ли люди из других групп (этап 1) — тогда напоминания смотрят и их календари."""
    from kapibara.features.groups import groups
    from database import group_counts
    return any(g["id"] and g["id"] != groups.home_id() for g in await group_counts())


async def check_lesson_reminders(bot: Bot):
    """Раз в минуту: кому пора напомнить о паре. Если в ближайшие часы пар нет
    — выходим, не трогая базу; иначе пользователи и их ответы про предметы
    по выбору — двумя запросами на всех, а расписание разбирается один раз на
    каждый набор скрытых предметов, а не на каждого человека."""
    global _sent_reminders
    with aside(logger, "напоминания о парах"):
        from kapibara.features.notifications import prefs as notify_prefs
        from kapibara.core.config import OPTIONAL_SUBJECTS
        from database import get_all_optional_answers, get_reminder_users
        from kapibara.features.groups.optional_subjects import HIDE, no_filter
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

            # У каждой пары свой сценарий: первая за день, после короткой
            # перемены или после большого перерыва — и своё «за сколько».
            for e, remind_mins, kind in notify_prefs.plan_reminders(by_hide[key_h], prefs):
                t = e["time_start"]
                diff = abs((t - (now + timedelta(minutes=remind_mins))).total_seconds())
                if diff > 60:
                    continue
                key = (today, uid, t.strftime("%H:%M"), remind_mins)
                if key in _sent_reminders:
                    continue
                _sent_reminders.add(key)
                # Память стирается перезапуском (деплой посреди минуты
                # напоминания) — отметка в базе ловит второй процесс.
                with aside(logger, "отметка напоминания о паре"):
                    from database.schedule import mark_lesson_reminder
                    if not await mark_lesson_reminder(uid, today.isoformat(), key[2], remind_mins):
                        continue
                label = "первая пара" if kind == "remind_first" else "пара"
                title, short = lesson_push(e, remind_mins)
                with aside(logger, f"напоминание о паре {uid}"):
                    await deliver(
                        bot, uid,
                        f"⏰ <b>Через {notify_prefs.minutes_text(remind_mins)} {label}</b>\n\n"
                        + format_lesson(e),
                        kind="lesson", tab="today", title=title, body=short,
                        reply_markup=app_button("📅 Расписание", "today"),
                    )


def lesson_push(e: dict, minutes: int) -> tuple[str, str]:
    """Пуш перед парой (Никита 25.10): «Через 15 мин: Анализ данных»,
    ниже «А-1 (В-78) · лекция · Иванов И. И.»."""
    from kapibara.features.notifications import prefs as notify_prefs
    from kapibara.features.schedule.format import _short_teacher, _split_kind
    name, kind, _ = _split_kind(e.get("summary") or "")
    title = f"Через {notify_prefs.minutes_text(minutes)}: {name or 'пара'}"
    parts = [e.get("location") or "", kind, _short_teacher(e.get("teacher") or "")]
    return title, " · ".join(p for p in parts if p) or "Пара по расписанию"


# ── Автосинк дедлайнов из СДО ────────────────────────────────────────────────

_sdo_expired_notified = False  # не спамим старосте одним и тем же каждые N часов
_sdo_error_notified = False    # то же для сетевой недоступности СДО


async def _note_sync(result: dict):
    """Чем кончился синк — для /status (health.py) и вкладки «Сдать» (sdo_check.py)."""
    from kapibara.ops import health
    from kapibara.features.sdo import check as sdo_check
    await sdo_check.note_home(result)
    if result.get("missing"):
        return
    if "error" in result:
        await health.note("sdo_sync", False, "СДО не ответил")
    elif result.get("expired"):
        await health.note("sdo_sync", False, "кука протухла")
        await health.note("sdo_cookie", False, "протухла — обнови SDO_SESSION_COOKIE")
    else:
        await health.note("sdo_sync", True, f"новых {result.get('added', 0)}, изменено {result.get('updated', 0)}")


async def sdo_keepalive(bot: Bot | None = None):
    """Лёгкий запрос в СДО раз в час (сессия не гаснет) + отметка для /status.
    Заодно той же сессией — календарь текущего месяца (quiz_alerts.peek):
    тест внезапно открыли — полный синк сейчас, а не через 6 часов."""
    from kapibara.ops import health
    from kapibara.features.sdo.parser import keepalive
    from kapibara.core.config import SDO_SESSION_COOKIE
    if not SDO_SESSION_COOKIE:
        return
    changed = []

    async def peek(client, html):
        from kapibara.features.notifications import quiz_alerts
        changed.append(await quiz_alerts.peek(client, html))
    ok = await keepalive(peek=peek if bot else None)
    await health.note("sdo_cookie", bool(ok), "" if ok else
                      "СДО не ответил — про куку не знаю" if ok is None else "СДО не пустил — кука протухла")
    from kapibara.features.sdo import parser as sdo_parser
    if ok and sdo_parser.IDLE_TIMEOUT:
        from database import set_setting
        await set_setting("sdo:idle_timeout", str(sdo_parser.IDLE_TIMEOUT))
    if ok and bot and any(changed):                     # changed копит только peek, а он — с ботом
        await sync_sdo_deadlines(bot)
    from kapibara.features.notifications import grade_alerts
    if ok and bot and grade_alerts.daytime():
        # староста без своего входа ходит этой кукой — его новые баллы проверяем здесь
        from kapibara.core.config import STAROSTA_IDS
        from database import get_sdo_session
        with aside(logger, "новые баллы старосты"):
            for uid in STAROSTA_IDS:
                if uid and not await get_sdo_session(uid):
                    grade_alerts.check_soon(bot, uid, SDO_SESSION_COOKIE)


async def sync_sdo_deadlines(bot: Bot):
    global _sdo_expired_notified
    from kapibara.features.sdo.parser import sync_deadlines

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
            with aside(logger, "Не смог уведомить старосту о недоступности СДО"):
                await bot.send_message(
                    STAROSTA_ID,
                    "⚠️ СДО недоступен с сервера бота — автосинк дедлайнов не работает.\n\n"
                    f"Ошибка: {result['error'][:300]}\n\n"
                    "Если так будет и дальше, скорее всего online-edu.mirea.ru не пускает "
                    "зарубежные адреса (сервер бота — в США).",
                )
                _sdo_error_notified = True
        return
    _sdo_error_notified = False

    if result.get("expired"):
        if not _sdo_expired_notified and STAROSTA_ID:
            with aside(logger, "Не смог уведомить старосту о протухшей куке СДО"):
                await bot.send_message(
                    STAROSTA_ID,
                    "⚠️ Сессия СДО протухла — автосинк дедлайнов не работает.\n\n"
                    "Зайди в online-edu.mirea.ru в браузере (с опцией «запомнить меня»), "
                    "возьми свежее значение куки MoodleSession (DevTools → Application → "
                    "Cookies) и обнови переменную окружения SDO_SESSION_COOKIE.",
                )
                _sdo_expired_notified = True
        return

    _sdo_expired_notified = False  # сессия снова живая — сбрасываем флаг

    with aside(logger, "время тестов: не вышло узнать"):
        from kapibara.features.deadlines import quiz_time
        await quiz_time.learn_missing()

    if (result["added"] or result.get("updated") or result.get("gone")) and STAROSTA_ID:
        parts = []
        if result["added"]:
            parts.append(f"добавлено новых дедлайнов — {result['added']}")
        if result.get("updated"):
            parts.append(f"перенесено/изменено — {result['updated']}")
        if result.get("gone"):
            parts.append(f"пропало из СДО и убрано — {len(result['gone'])} ({'; '.join(result['gone'][:5])})")
        with aside(logger, "Не смог уведомить старосту об автосинке СДО"):
            await bot.send_message(
                STAROSTA_ID,
                f"🔄 Автосинк СДО: {', '.join(parts)}",
            )
    # каждому — что появилось нового (у кого включено «Новые задания»)
    with aside(logger, "новые задания: рассылка не вышла"):
        from kapibara.features.notifications import new_tasks
        await new_tasks.announce(bot, result.get("new_ids") or [], result.get("moved") or {})


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    from kapibara.features.schedule.diff import check_schedule_changes

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(send_morning_schedule,       "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_group_morning_digest,   "cron", hour=SCHEDULE_HOUR,          minute=SCHEDULE_MINUTE,          args=[bot])
    scheduler.add_job(send_deadline_reminders, "cron", hour=DEADLINE_REMINDER_HOUR, minute=DEADLINE_REMINDER_MINUTE, args=[bot])
    scheduler.add_job(check_lesson_reminders,  "cron", minute="*",                  args=[bot])
    from kapibara.features.notifications.weekly_digest import send_all as send_weekly_digest      # обзор недели — воскресенье, 19:00
    scheduler.add_job(send_weekly_digest,      "cron", day_of_week="sun", hour=19, minute=0, args=[bot])
    from kapibara.features.notifications.evening_digest import send_all as send_evening_digest    # сводка на завтра — во время, выбранное человеком
    scheduler.add_job(send_evening_digest,     "cron", minute="0,30", args=[bot])
    # новые баллы СДО — не отдельным расписанием, а у каждого вместе с проверкой
    # его входа (sdo_accounts._check_one, grade_alerts.check_soon; Никита 02.11)
    from kapibara.features.deadlines.reminders import send_due as send_deadline_custom_reminders   # свои напоминания о дедлайне
    scheduler.add_job(send_deadline_custom_reminders, "cron", minute="*",        args=[bot])
    from kapibara.features.notifications import quiz_alerts                    # тесты СДО: до закрытия и «открыли тест» (Уведомления → Тесты СДО)
    scheduler.add_job(quiz_alerts.send_due,    "cron", minute="*",             args=[bot])
    from kapibara.features.deadlines import soon as deadline_soon                  # «срок скоро, а ты не сдал» (Уведомления → Срок скоро)
    scheduler.add_job(deadline_soon.send_due,  "cron", minute="*/5",           args=[bot])
    from database.sdo import purge_quiz_alerts
    scheduler.add_job(purge_quiz_alerts,       "cron", hour=4, minute=22)
    from database.schedule import purge_lesson_reminders   # отметки «напомнил о паре» старше вчера

    async def purge_reminders():
        await purge_lesson_reminders((datetime.now(TZ).date() - timedelta(days=1)).isoformat())
    scheduler.add_job(purge_reminders,         "cron", hour=4, minute=23)
    # Первый синк — через минуту после запуска: после деплоя СДО иначе молчал
    # до 6 часов, и сессия Moodle успевала истечь. Плюс лёгкий запрос в СДО
    # каждый час, чтобы сессия не гасла без обращений (sdo_parser.keepalive).
    scheduler.add_job(sync_sdo_deadlines,      "interval", hours=SDO_SYNC_INTERVAL_HOURS, args=[bot],
                      next_run_time=datetime.now(ZoneInfo(TIMEZONE)) + timedelta(minutes=1))
    from kapibara.features.groups import sync as group_sync                     # СДО других групп по входам, которыми поделились (этап 1 (в))
    scheduler.add_job(group_sync.sync_all,     "interval", hours=SDO_SYNC_INTERVAL_HOURS, args=[bot],
                      next_run_time=datetime.now(TZ) + timedelta(minutes=5))
    scheduler.add_job(sdo_keepalive,           "interval", minutes=55, args=[bot])
    # Входы студентов в СДО — вразнобой: раз в минуту проверяются те, чья
    # очередь (50–59 мин случайно, потом 55), а не все разом (sdo_accounts.py)
    from kapibara.features.sdo.accounts import keepalive_due
    scheduler.add_job(keepalive_due,           "interval", minutes=1, args=[bot])
    from kapibara.features.pulse import service as pulse_service                        # вход в Пульс — так же, как СДО (pulse/accounts.py)
    scheduler.add_job(pulse_service.keepalive_due, "interval", minutes=1)
    from database import purge_events          # статистика старше 180 дней не нужна
    scheduler.add_job(purge_events,            "cron", hour=4, minute=20)
    from kapibara.features.privacy import privacy                             # 152-ФЗ: год без заходов — данные стираются
    from kapibara.features.identity import apple as apple_signin                        # отзыв входа Apple, если Apple не ответил при удалении
    scheduler.add_job(privacy.purge,           "cron", hour=4, minute=25)
    scheduler.add_job(apple_signin.retry_revokes, "cron", minute=37)      # отзыв входа Apple, который не прошёл
    from kapibara.features.billing import referrals                           # «пригласи друга»: друг пользуется — обоим дни подписки
    scheduler.add_job(referrals.check_all,     "cron", hour=12, minute=17, args=[bot])
    from kapibara.features.social import group_award                         # группа месяца: 1-го числа — 7 дней «Капибары+» (5.100.7)
    scheduler.add_job(group_award.award,       "cron", day=1, hour=12, minute=5, args=[bot])
    from kapibara.ops import health
    scheduler.add_job(health.alert_errors,     "interval", minutes=15, args=[bot])   # всплеск ошибок — старосте
    from kapibara.ops import stats
    scheduler.add_job(stats.send_evening,      "cron", hour=21, minute=3, args=[bot])  # +N новых за день — старосте
    scheduler.add_job(check_schedule_changes,  "interval", minutes=SCHEDULE_DIFF_CHECK_MINUTES, args=[bot])
    # Справочник для поиска преподавателей/групп/аудиторий: достроить, если
    # обход прервался (редеплой), и обновлять раз в месяц (см. schedule_index).
    from kapibara.features.schedule import index as schedule_index
    scheduler.add_job(schedule_index.ensure_fresh, "cron", hour=4, minute=10)
    # Поиск по смыслу: нарезать лекции по страницам и досчитать векторы —
    # понемногу, в пределах бесплатных лимитов Gemini (semantic_index.py).
    from kapibara.features.ai import semantic_index

    async def index_lectures():
        with aside(logger, "индекс поиска"):
            st = await semantic_index.index_pending(bot)
            from kapibara.ops import health
            await health.note("semantic", True, f"{st['chunks']} фрагментов из {st['files']} файлов, "
                                                f"с векторами {st['embedded']}")
    # первый проход — не сразу: после выкладки все разом открывают приложение,
    # а на Amvera пол-ядра (17.10: в первые минуты ответы по 35 с)
    scheduler.add_job(index_lectures, "interval", minutes=20, next_run_time=datetime.now(TZ) + timedelta(minutes=INDEX_FIRST_DELAY))
    from kapibara.features.ai import local_embed
    scheduler.add_job(local_embed.unload_idle, "interval", minutes=5)    # своя модель векторов — из памяти после простоя
    # Копия базы старосте каждую ночь, без звука (backup.py).
    if STAROSTA_ID:
        from kapibara.ops.backup import send_backup
        scheduler.add_job(send_backup, "cron", hour=4, minute=40, args=[bot, STAROSTA_ID])
    return scheduler
