"""
Тесты СДО в уведомлениях (Никита 12.10): «Уведомления → Тесты СДО».

• Напоминания до закрытия теста — за 1 день, 3 ч, 1 ч, 30 мин, 10 мин,
  сколько угодно сразу (notify_prefs: quiz_remind, список минут; по
  умолчанию — ни одного, есть утренние «Дедлайны»).
• «Тест открылся» (quiz_open, по умолчанию включено): когда открывается —
  из календаря СДО (событие «… открывается» у mod_quiz, sdo_parser
  прикладывает его к закрытию теста как opens); преподаватель открыл раньше
  (событие пропало или переехало в прошлое) — время открытия = время синка;
  новый тест, уже открытый, — в рассылке после синка (new_tasks.py) строкой
  «Открыли тест», а не «новое задание».

Проверка — раз в минуту (scheduler.py, как свои напоминания о дедлайне):
сначала по тестам без людей; если сейчас ничего не пора — база людей не
нужна. Срок — тот, что в СДО (свою правку срока тест в СДО не двигает);
кому — только тем, кто видит тест у себя (группа, не сдан, не скрыт, не
предмет по выбору, куда не ходит), как в new_tasks. Что ушло — в
quiz_alerts, одна отметка на (человек, дедлайн, вид, время): после
перезапуска и переноса срока ничего не придёт дважды.

Задержка «открыли»: у теста со временем открытия в календаре — до минуты.
Внезапное открытие видно по календарю СДО: полный синк раз в
SDO_SYNC_INTERVAL_HOURS, а между ними — peek на проверке куки (раз в 55 мин
один лишний запрос — календарь текущего месяца; изменилось что-то у тестов
— сразу полный синк), то есть до часа у своей группы, у других групп — до
синка их СДО.
"""

import json
import logging
import re
from datetime import datetime, timedelta

from notify_prefs import QUIZ_REMIND_CHOICES as CHOICES     # минут до закрытия — плашки в «Уведомлениях»
from utils import TZ

logger = logging.getLogger(__name__)

FMT = "%Y-%m-%d %H:%M"
LATE = 15                                # мин: опоздали (перезапуск) — ещё шлём, позже — нет
OPEN_LATE = 120                          # мин: «открыли тест» после открытия — не позже
PEEK_KEY = "sdo:quiz_sig"                # что о тестах видел последний полный синк (peek)


def _parse(at: str | None) -> datetime | None:
    try:
        return datetime.strptime((at or "")[:16], FMT).replace(tzinfo=TZ)
    except ValueError:
        return None


def close_at(d: dict) -> datetime:
    t = (d.get("due_time") or "23:59").strip()[:5]
    return datetime.strptime(f"{d['due_date']} {t}", FMT).replace(tzinfo=TZ)


def next_open(prev: str | None, new: str | None, now: datetime) -> str:
    """Что запомнить об открытии теста после синка. prev — что знали (None —
    тест видим впервые), new — событие «открывается» из календаря (None —
    нет: открыт без ограничения или открылся до окна календаря)."""
    n = now.strftime(FMT)
    if new and new > n:
        return new                           # откроется потом — по расписанию
    if prev and prev > n:
        return n                             # ждали позже, а он уже открыт: открыли сейчас
    if prev is not None:
        return prev                          # уже открыт и мы это знаем
    return new or ""                         # впервые: открыт с new или «когда — не знаем»


async def note_opens(items: list[dict], now: datetime | None = None):
    """После синка (sdo_parser.apply_items): открытия тестов из календаря."""
    import quiz_time
    from database.sdo import get_quiz_opens, save_quiz_opens
    now = now or datetime.now(TZ)
    new = {c: i.get("opens") for i in items if i.get("calendar") and (c := quiz_time.quiz_cmid(i.get("description")))}
    if not new:
        return
    known = await get_quiz_opens(new)
    fresh = {c: next_open(known.get(c), o, now) for c, o in new.items()}
    await save_quiz_opens({c: v for c, v in fresh.items() if known.get(c) != v})


def is_open(open_at: str | None, now: datetime) -> bool:
    """Тест уже открыт: открытие было или его нет в календаре."""
    return not open_at or open_at <= now.strftime(FMT)


def limit_text(minutes: int | None) -> str:
    from notify_prefs import minutes_text
    return f" ({minutes_text(minutes)} на попытку)" if minutes else ""


def remind_head(minutes: int, close: datetime, now: datetime) -> str:
    """«Через 10 мин закрывается тест», «Завтра в 23:59 закрывается тест»."""
    from notify_prefs import minutes_text
    if minutes >= 1440:
        day = {0: "Сегодня", 1: "Завтра"}.get((close.date() - now.date()).days, close.strftime("%d.%m"))
        return f"{day} в {close:%H:%M} закрывается тест"
    left = max(1, round((close - now).total_seconds() / 60))
    left = minutes if abs(left - minutes) <= 1 else left      # пришло в свою минуту — ровное число
    return f"Через {minutes_text(left)} закрывается тест"


def remind_text(d: dict, minutes: int, limit: int | None, now: datetime) -> str:
    from utils import esc
    return f"⏰ <b>{remind_head(minutes, close_at(d), now)}</b> · {esc(d['subject'])}{limit_text(limit)}"


def open_line(d: dict, limit: int | None) -> str:
    from new_tasks import when
    from utils import esc
    return f"• <b>{esc(d['subject'])}</b>{limit_text(limit)} — сдать {when(d['due_date'], d.get('due_time'))}"


def open_text(d: dict, limit: int | None) -> str:
    return "🔓 <b>Открыли тест</b>\n" + open_line(d, limit)


def push_head(d: dict, kind: str, minutes: int, limit: int | None, now: datetime) -> tuple[str, str]:
    """Пуш (Никита 25.10): «Через 30 мин закрывается тест» и ниже название;
    «Открыли тест: Тест 2» и ниже предмет, лимит и срок."""
    from notify_prefs import minutes_text
    from push_text import split_subject, when
    name, course = split_subject(d["subject"])
    lim = f"{minutes_text(limit)} на попытку" if limit else ""
    if kind == "open":
        due = "сдать " + when(d["due_date"], d.get("due_time"), now.date())
        return f"Открыли тест: {name}", " · ".join(x for x in (course, lim, due) if x)
    return remind_head(minutes, close_at(d), now), " · ".join(x for x in (d["subject"], lim) if x)


def due_now(quizzes: list[dict], opens: dict[int, str], now: datetime) -> list[tuple[dict, str, str, int]]:
    """Что пора прислать сейчас: (дедлайн, вид, время-ключ, минуты).
    Вид — «r<минуты>» (до закрытия) или «open»."""
    import quiz_time
    out = []
    for d in quizzes:
        close = close_at(d)
        if close <= now:
            continue
        for m in CHOICES:
            at = close - timedelta(minutes=m)
            if at <= now < at + timedelta(minutes=min(LATE, max(1, m // 2))):
                out.append((d, f"r{m}", at.strftime(FMT), m))
        o = _parse(opens.get(quiz_time.quiz_cmid(d.get("description"))))
        if o and o <= now < o + timedelta(minutes=OPEN_LATE):
            out.append((d, "open", "", 0))
    return out


async def visible_to(uid: int, skip_optional: dict | None = None) -> dict[int, dict]:
    """Дедлайны, которые человек видит у себя и не сдал (как new_tasks)."""
    from config import OPTIONAL_SUBJECTS
    from database import get_active_deadlines
    answers = skip_optional or {}
    skip = [s.lower() for s in OPTIONAL_SUBJECTS if not answers.get(s)]
    return {d["id"]: d for d in await get_active_deadlines(uid) if not d.get("done")
            and not any(s in (d.get("subject") or "").lower() for s in skip)}


async def send_due(bot, now: datetime | None = None) -> int:
    """Раз в минуту: напоминания до закрытия и «открыли тест». → сколько ушло."""
    import notify_prefs
    import quiz_time
    from database import get_all_optional_answers, get_quiz_limits, get_reminder_users
    from database.sdo import get_quiz_deadlines, get_quiz_opens, mark_quiz_alert
    now = now or datetime.now(TZ)
    quizzes = await get_quiz_deadlines(now.date().isoformat())
    if not quizzes:
        return 0
    cmids = [quiz_time.quiz_cmid(d["description"]) for d in quizzes]
    due = due_now(quizzes, await get_quiz_opens(cmids), now)
    if not due:
        return 0
    limits = await get_quiz_limits([c for c in cmids if c])
    answers = await get_all_optional_answers()
    from keyboards import app_button
    sent = 0
    for user in await get_reminder_users():
        uid = user["user_id"]
        prefs = notify_prefs.merge(user.get("notify"))
        wanted = [x for x in due if (x[1] == "open" and prefs["quiz_open"])
                  or (x[1] != "open" and x[3] in prefs["quiz_remind"])]
        if not wanted:
            continue
        mine = await visible_to(uid, answers.get(uid))
        for d, kind, at, m in wanted:
            if d["id"] not in mine or not await mark_quiz_alert(uid, d["id"], kind, at):
                continue
            limit = limits.get(quiz_time.quiz_cmid(d["description"]))
            text = open_text(d, limit) if kind == "open" else remind_text(d, m, limit, now)
            title, short = push_head(d, kind, m, limit, now)
            try:
                import delivery
                await delivery.deliver(bot, uid, text, kind="quiz", tab="deadlines", title=title, body=short,
                                       reply_markup=app_button("📋 Открыть дедлайны", "deadlines"))
                sent += 1
            except Exception as e:
                logger.info(f"тест СДО {uid}: {e}")    # обычно — бот заблокирован
    return sent


# ── Peek: внезапно открытый тест — не ждать полного синка ────────────────────

def signature(items: list[dict]) -> list[str]:
    """Тесты из календаря: «id события|когда открывается»."""
    return sorted({f"{i['external_id']}|{i.get('opens') or ''}" for i in items
                   if i.get("calendar") and "/mod/quiz/" in (i.get("description") or "")})


async def remember(items: list[dict]):
    """Полный синк своей группы: что он видел о тестах — для peek."""
    from database import set_setting
    await set_setting(PEEK_KEY, json.dumps(signature(items)))


async def peek(client, html: str) -> bool:
    """На проверке куки (sdo_parser.keepalive, раз в 55 мин): календарь
    текущего месяца (с 20-го — и следующего) одним запросом на месяц. Есть
    тест, которого полный синк не видел, или у теста другое время открытия —
    True: пора полный синк. Сбой — False (синк и так придёт по расписанию)."""
    import sdo_parser
    from database import get_setting
    m = re.search(r'"sesskey":"([^"]+)"', html or "")
    seen = await get_setting(PEEK_KEY)
    if not m or seen is None:
        return False
    try:
        months = 2 if datetime.now(TZ).day >= 20 else 1
        events = await sdo_parser.calendar_months(client, m.group(1), months)
    except Exception as e:
        logger.info(f"тесты СДО: peek не вышел ({type(e).__name__})")
        return False
    if events is None:
        return False
    fresh = set(signature(sdo_parser.parse_calendar_events(events))) - set(json.loads(seen))
    if fresh:
        logger.info(f"тесты СДО: в календаре изменились тесты ({len(fresh)}) — синк сейчас")
    return bool(fresh)
