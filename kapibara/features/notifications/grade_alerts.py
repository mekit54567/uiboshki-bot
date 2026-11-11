"""
Новые баллы в СДО — сообщением в личку (тумблер «Новые баллы» в
уведомлениях, notify_prefs: grades). Днём, вместе с проверкой входа (check_soon), бот
открывает журнал БРС каждого, кто подключил свой вход в СДО (sdo_grades.
overview), и сравнивает сумму по предмету с последней точкой истории баллов
(sdo_history). Выросла или упала — одно сообщение со всеми предметами:
«Моделирование: 34 → 39 (+5)». Первый раз (истории нет) — только запоминаем.
Хранится лишь сумма по предмету, как и для графика.
"""

import asyncio
import logging

from kapibara.core.utils import esc
from datetime import UTC
from kapibara.core.errors import aside

logger = logging.getLogger(__name__)
PAUSE_SEC = 20          # между людьми: не открывать журналы всех разом


def _num(x: float) -> str:
    return f"{x:g}"


def changes(last: dict[int, float], courses: list[dict]) -> list[tuple[dict, float, float]]:
    """[(курс, было, стало)] — только где сумма изменилась и было с чем сравнить."""
    out = []
    for c in courses:
        if c.get("id") is None or c.get("score") is None:
            continue
        old = last.get(c["id"])
        new = float(c["score"])
        if old is not None and abs(new - old) >= 0.05:
            out.append((c, old, new))
    return out


def message(diff: list[tuple[dict, float, float]]) -> str:
    lines = ["🎓 <b>Новые баллы в СДО</b>"]
    for c, old, new in sorted(diff, key=lambda x: x[0].get("name") or ""):
        d = round(new - old, 1)
        lines.append(f"• {esc(c.get('name') or c.get('title') or 'Предмет')}: {_num(old)} → <b>{_num(new)}</b> "
                     f"({'+' if d > 0 else ''}{_num(d)})")
    return "\n".join(lines)


def headline(diff: list[tuple[dict, float, float]]) -> tuple[str, str]:
    """Пуш (Никита 25.10): один предмет — «Моделирование: +5» и ниже «было 34,
    стало 39»; несколько — «Новые баллы по 2 предметам» и ниже кратко."""
    from kapibara.features.notifications.push_text import word

    def name(c):
        return _course(c)

    def delta(old, new):
        d = round(new - old, 1)
        return f"{'+' if d > 0 else ''}{_num(d)}"

    if len(diff) == 1:
        c, old, new = diff[0]
        # минус — не новая оценка, а замеченное изменение в журнале (UX-аудит, п. 21)
        was = f"Было {_num(old)}, стало {_num(new)}" if new >= old else \
            f"В СДО изменились баллы: было {_num(old)}, стало {_num(new)}"
        return f"{name(c)}: {delta(old, new)}", was
    n = len(diff)
    items = sorted(diff, key=lambda x: -abs(x[2] - x[1]))
    return (f"Новые баллы по {n} {word(n, 'предмету', 'предметам', 'предметам')}",
            " · ".join(f"{name(c)} {delta(o, w)} ({_num(w)})" for c, o, w in items))


# ── «Работу проверили» (Никита 25.10) ────────────────────────────────────────
# Что из работ текущего контроля уже было оценено — в settings «graded:<id>»
# (JSON «курс:работа» → оценка как написана). Работа стала оценённой или
# оценка у неё поменялась — пуш «Проверили: Практика 2 — 7 из 8». Первый раз
# (ключа нет) — только запоминаем, как и с суммой баллов.

def graded_map(courses: list[dict]) -> dict[str, str]:
    out = {}
    for c in courses:
        for w in c.get("works") or []:
            if w.get("cmid") and w.get("graded"):
                out[f"{c.get('id')}:{w['cmid']}"] = _mark(w)
    return out


def _mark(w: dict) -> str:
    """«7 из 8», «зачтено», «не зачтено»."""
    if w.get("grade") is not None:
        return f"{_num(w['grade'])} из {_num(w['max'])}" if w.get("max") else _num(w["grade"])
    return "зачтено" if w.get("passed") else "не зачтено"


def checked(seen: dict[str, str] | None, courses: list[dict]) -> list[tuple[dict, dict]]:
    """[(курс, работа)] — проверенные с прошлого раза. seen None — первый раз, пусто."""
    if seen is None:
        return []
    return [(c, w) for c in courses for w in c.get("works") or []
            if w.get("cmid") and w.get("graded") and seen.get(f"{c.get('id')}:{w['cmid']}") != _mark(w)]


def _course(c: dict) -> str:
    """Предмет без хвостов СДО: «Архитектура предприятия_Экзамен (часть 1/1)
    [I.26-27]» → «Архитектура предприятия»."""
    from kapibara.features.sdo.courses import clean_course_name
    raw = c.get("name") or c.get("title") or ""
    return clean_course_name(raw) if raw else "Предмет"


def _work(w: dict) -> str:
    """«Практическая работа №2» → «Практика 2» (как у дедлайнов)."""
    from kapibara.features.deadlines.names import clean_event
    return clean_event(w.get("name") or "") if w.get("name") else "Работа"


def checked_text(items: list[tuple[dict, dict]]) -> str:
    lines = ["✅ <b>Проверили работу</b>" if len(items) == 1 else "✅ <b>Проверили работы</b>"]
    for c, w in items:
        lines.append(f"• {esc(_work(w))}: <b>{_mark(w)}</b> — {esc(_course(c))}")
    return "\n".join(lines)


def _plus(points: float) -> str:
    from kapibara.features.notifications.push_text import word
    n = int(points) if float(points).is_integer() else 5   # дробное — «баллов» («2,5 балла» редко)
    return f"+{_num(points)} {word(n, 'балл', 'балла', 'баллов')}"


def checked_head(items: list[tuple[dict, dict]]) -> tuple[str, str]:
    """Пуш (Никита 11.11, вариант Б): предмет и сколько баллов —
    «Архитектура предприятия: +5 баллов», ниже «Практика 2 — 5 из 6».
    Без баллов (зачтено/не зачтено, 0) — оценка вместо «+N баллов»."""
    from kapibara.features.notifications.push_text import word
    if len(items) == 1:
        c, w = items[0]
        mark = _mark(w)
        if w.get("grade"):
            return f"{_course(c)}: {_plus(w['grade'])}", f"{_work(w)} — {mark}"
        return f"{_course(c)}: {mark}", f"Проверили: {_work(w)}"
    n = len(items)
    total = sum(w.get("grade") or 0 for _, w in items)
    courses = {_course(c) for c, _ in items}
    where = next(iter(courses)) if len(courses) == 1 else f"Проверили {n} {word(n, 'работу', 'работы', 'работ')}"
    head = f"{where}: {_plus(total)}" if total else f"Проверили {n} {word(n, 'работу', 'работы', 'работ')}"
    return head, " · ".join(f"{_work(w)}: {_mark(w)}" for _, w in items[:4])


async def _told(user_id: int) -> dict[int, float] | None:
    """Суммы по предметам, о которых уже сообщали (settings «told_scores:<id>»)."""
    import json
    from database import get_setting
    raw = await get_setting(f"told_scores:{user_id}")
    try:
        return {int(k): float(v) for k, v in json.loads(raw).items()} if raw else None
    except (ValueError, TypeError, AttributeError):
        return None


async def _seen(user_id: int) -> dict[str, str] | None:
    import json
    from database import get_setting
    raw = await get_setting(f"graded:{user_id}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


async def check_user(bot, user_id: int, cookie: str, notify: bool = True) -> bool:
    """Сверить баллы одного человека; True — сообщение отправлено. notify=False —
    только записать точку истории (для посещений, attendance.py)."""
    from kapibara.features.sdo import grades as sdo_grades
    from kapibara.features.sdo import history as sdo_history
    from database import get_last_scores
    from kapibara.core.telegram import app_button
    import json
    from database import set_setting
    data = await sdo_grades.overview(user_id, cookie, fresh=True)
    courses = data.get("courses") or []
    # сравниваем с тем, что уже сообщали, а не с историей баллов: историю
    # пишет и приложение, когда человек открывает баллы, и после этого
    # новые баллы «уже были» — пуш не приходил (Никита 02.11)
    told = await _told(user_id)
    diff = changes(told if told is not None else await get_last_scores(user_id), courses)
    await sdo_history.record(user_id, courses)
    scores = {str(c["id"]): float(c["score"]) for c in courses if c.get("id") is not None and c.get("score") is not None}
    if scores:
        await set_setting(f"told_scores:{user_id}", json.dumps({**{str(k): v for k, v in (told or {}).items()},
                                                                **scores}))
    seen = await _seen(user_id)
    done = checked(seen, courses)
    now = graded_map(courses)
    if seen is None or now != seen:
        # работу, которой в журнале больше нет, не забываем: вдруг СДО отдал журнал не целиком
        await set_setting(f"graded:{user_id}", json.dumps({**(seen or {}), **now}, ensure_ascii=False))
    if not (diff or done) or not notify:
        return False
    from kapibara.features.notifications import delivery
    title, short = checked_head(done) if done else headline(diff)
    text = "\n\n".join(x for x in (checked_text(done) if done else "", message(diff) if diff else "") if x)
    await delivery.deliver(bot, user_id, text, kind="grades", tab="sdo", title=title, body=short,
                           reply_markup=app_button("🎓 Открыть баллы", "sdo"))
    return True


# Когда проверять (Никита 02.11): не всех разом по расписанию, а каждого в
# своё время — вместе с проверкой его входа в СДО (sdo_accounts._check_one,
# раз в 50–59 минут, у всех вразнобой), староста с общим входом — вместе с
# проверкой общей куки (scheduler.sdo_keepalive). Ночью не проверяем, чтобы
# не будить пушем.
DAY_HOURS = range(8, 23)          # 8:00–22:59 МСК
_tasks: set = set()


def daytime(now=None) -> bool:
    from datetime import datetime

    from kapibara.core.utils import TZ
    now = now or datetime.now(UTC)
    if now.tzinfo is None:            # sdo_accounts считает время в UTC без пояса
        now = now.replace(tzinfo=UTC)
    return now.astimezone(TZ).hour in DAY_HOURS


async def check_one(bot, user_id: int, cookie: str):
    """Сверить баллы одного человека (тумблер «Новые баллы» — пишем ли ему).
    Сбой СДО — молча, до следующей проверки входа."""
    from kapibara.features.notifications import prefs as notify_prefs
    from database import get_user
    user = await get_user(user_id)
    if not user or not cookie:
        return
    notify = bool(user.get("subscribed")) and bool(notify_prefs.merge(user.get("notify")).get("grades"))
    with aside(logger, f"новые баллы {user_id}", level=logging.INFO):
        await check_user(bot, user_id, cookie, notify=notify)


def check_soon(bot, user_id: int, cookie: str, now=None):
    """Из проверки входа: фоном, чтобы очередь входов не ждала журналы СДО."""
    if not bot or not daytime(now):
        return
    t = asyncio.ensure_future(check_one(bot, user_id, cookie))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def check_all(bot, pause: float = PAUSE_SEC):
    """По расписанию (scheduler.py): все с рабочим входом. Сообщение — тем, у
    кого включён тумблер; остальным только точка истории: по ней видно, какие
    лекции засчитаны (attendance.py), — а она нужна каждому."""
    from kapibara.features.notifications import prefs as notify_prefs
    from kapibara.core.config import SDO_SESSION_COOKIE, STAROSTA_IDS
    from database import get_sdo_session, get_sdo_sessions, get_user
    from kapibara.core.crypto import decrypt
    rows = [(r["user_id"], decrypt(r["cookie_enc"])) for r in await get_sdo_sessions("ok")]
    # староста без своего входа ходит в СДО общей кукой (sdo_accounts.cookie_for) —
    # раньше его тут не было, и новые баллы ему не приходили (Никита 02.11)
    if SDO_SESSION_COOKIE:
        rows += [(uid, SDO_SESSION_COOKIE) for uid in STAROSTA_IDS if uid and not await get_sdo_session(uid)]
    for uid, cookie in rows:
        user = await get_user(uid)
        if not user:
            continue
        notify = bool(user.get("subscribed")) and bool(notify_prefs.merge(user.get("notify")).get("grades"))
        if not cookie:
            continue
        with aside(logger, f"новые баллы {uid}", level=logging.INFO):  # вход устарел, СДО лежит — молча до следующего раза
            await check_user(bot, uid, cookie, notify=notify)
        if pause:
            await asyncio.sleep(pause)
