"""
Новые баллы в СДО — сообщением в личку (тумблер «Новые баллы» в
уведомлениях, notify_prefs: grades). Раз в 3 часа днём бот по очереди
открывает журнал БРС каждого, кто подключил свой вход в СДО (sdo_grades.
overview), и сравнивает сумму по предмету с последней точкой истории баллов
(sdo_history). Выросла или упала — одно сообщение со всеми предметами:
«Моделирование: 34 → 39 (+5)». Первый раз (истории нет) — только запоминаем.
Хранится лишь сумма по предмету, как и для графика.
"""

import asyncio
import logging

from utils import esc

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
    from push_text import word

    def name(c):
        return c.get("name") or c.get("title") or "Предмет"

    def delta(old, new):
        d = round(new - old, 1)
        return f"{'+' if d > 0 else ''}{_num(d)}"

    if len(diff) == 1:
        c, old, new = diff[0]
        return f"{name(c)}: {delta(old, new)}", f"Было {_num(old)}, стало {_num(new)}"
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


def checked_text(items: list[tuple[dict, dict]]) -> str:
    lines = ["✅ <b>Проверили работу</b>" if len(items) == 1 else "✅ <b>Проверили работы</b>"]
    for c, w in items:
        lines.append(f"• {esc(c.get('name') or c.get('title') or 'Предмет')} — {esc(w.get('name') or '')}: "
                     f"<b>{_mark(w)}</b>")
    return "\n".join(lines)


def checked_head(items: list[tuple[dict, dict]]) -> tuple[str, str]:
    from push_text import word
    if len(items) == 1:
        c, w = items[0]
        return f"Проверили: {w.get('name') or 'работу'} — {_mark(w)}", c.get("name") or c.get("title") or ""
    n = len(items)
    return (f"Проверили {n} {word(n, 'работу', 'работы', 'работ')}",
            " · ".join(f"{w.get('name')} — {_mark(w)}" for _, w in items[:4]))


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
    import sdo_grades
    import sdo_history
    from database import get_last_scores
    from keyboards import app_button
    import json
    from database import set_setting
    data = await sdo_grades.overview(user_id, cookie, fresh=True)
    courses = data.get("courses") or []
    diff = changes(await get_last_scores(user_id), courses)
    await sdo_history.record(user_id, courses)
    seen = await _seen(user_id)
    done = checked(seen, courses)
    now = graded_map(courses)
    if seen is None or now != seen:
        # работу, которой в журнале больше нет, не забываем: вдруг СДО отдал журнал не целиком
        await set_setting(f"graded:{user_id}", json.dumps({**(seen or {}), **now}, ensure_ascii=False))
    if not (diff or done) or not notify:
        return False
    import delivery
    title, short = checked_head(done) if done else headline(diff)
    text = "\n\n".join(x for x in (checked_text(done) if done else "", message(diff) if diff else "") if x)
    await delivery.deliver(bot, user_id, text, kind="grades", tab="sdo", title=title, body=short,
                           reply_markup=app_button("🎓 Открыть баллы", "sdo"))
    return True


async def check_all(bot, pause: float = PAUSE_SEC):
    """По расписанию (scheduler.py): все с рабочим входом. Сообщение — тем, у
    кого включён тумблер; остальным только точка истории: по ней видно, какие
    лекции засчитаны (attendance.py), — а она нужна каждому."""
    import notify_prefs
    from database import get_sdo_sessions, get_user
    from sdo_accounts import decrypt
    for row in await get_sdo_sessions("ok"):
        uid = row["user_id"]
        user = await get_user(uid)
        if not user:
            continue
        notify = bool(user.get("subscribed")) and bool(notify_prefs.merge(user.get("notify")).get("grades"))
        cookie = decrypt(row["cookie_enc"])
        if not cookie:
            continue
        try:
            await check_user(bot, uid, cookie, notify=notify)
        except Exception as e:          # вход устарел, СДО лежит — молча до следующего раза
            logger.info(f"новые баллы {uid}: {type(e).__name__}")
        if pause:
            await asyncio.sleep(pause)
