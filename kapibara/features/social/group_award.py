"""Группа месяца (5.100.7, Никита 18.10): самой активной группе университета за
прошлый месяц — 7 дней «Капибары+» всем в группе.

Активность — опыт за месяц на человека (xp.py: тот же опыт, что в рейтинге, —
разница на конец и начало месяца по Москве), среди тех, у кого опыт за месяц
есть; таких в группе должно быть не меньше xp.MIN_PEOPLE, иначе это опыт
одного-двух человек. Своя группа (у неё подарок до конца декабря) не
участвует. Кому обрабатывать данные нельзя (privacy.blocked), ни в счёт, ни в
награду не идёт — их уже нет в xp.board.

Дни выдаются тем же billing.grant, что и /grant (#208), с источником
group_award: «/grant @ник off» их не снимает — снимает только ручные. Каждому
в группе бот пишет сам (billing.notify — Telegram и пуш PWA, в приложении на
iPhone о подписке ни слова), Никите — итог. Месяц выдаётся один раз: отметка
award:<ГГГГ-ММ> в settings."""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DAYS = 7
SOURCE = "group_award"
MONTHS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
          "ноябрь", "декабрь")


def _bounds(month: str) -> tuple[datetime, datetime]:
    """Начало месяца и начало следующего по Москве; month — «ГГГГ-ММ»."""
    from xp import MSK
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1, tzinfo=MSK)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=MSK)
    return start, end


def prev_month(now: datetime | None = None) -> str:
    from xp import MSK
    now = (now or datetime.now(MSK)).astimezone(MSK)
    y, m = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return f"{y:04d}-{m:02d}"


async def standings(month: str) -> list[dict]:
    """Группы за месяц, лучшая первой: {"id", "name", "avg", "people", "xp"}.
    Только с опытом у ≥ MIN_PEOPLE человек, без своей группы."""
    import xp
    from database.groups import home
    data = await xp.board()
    raw = await xp._raw()
    start, end = _bounds(month)
    before, after = xp._totals(raw, start), xp._totals(raw, end)
    groups: dict[int, dict] = {}
    for uid, person in data["people"].items():
        gained = after.get(uid, {}).get("total", 0) - before.get(uid, {}).get("total", 0)
        if gained <= 0 or person["group"] == home():
            continue
        g = groups.setdefault(person["group"], {"id": person["group"], "xp": 0, "people": 0})
        g["xp"] += gained
        g["people"] += 1
    names = await xp._group_names(groups)
    out = []
    for g in groups.values():
        g["name"] = names.get(g["id"], "")
        if g["people"] >= xp.MIN_PEOPLE and g["name"]:
            g["avg"] = round(g["xp"] / g["people"])
            out.append(g)
    return sorted(out, key=lambda g: (-g["xp"] / g["people"], -g["xp"], g["name"]))


async def members(group_id: int) -> list[int]:
    """Все в группе, кому можно обрабатывать данные (те же люди, что в рейтинге)."""
    import xp
    data = await xp.board()
    return sorted(uid for uid, p in data["people"].items() if p["group"] == group_id)


def text(name: str, month: str, until: str) -> str:
    import billing
    from utils import esc
    title = MONTHS[int(month[5:]) - 1]
    return (f"<b>{esc(name)} — самая активная группа МИРЭА за {title}!</b>\n\n"
            f"Всем в группе — {DAYS} дней «Капибары+» в подарок, до {billing.fmt_day(until)}. "
            "Опыт считается из баллов СДО, сданных работ и ачивок — спасибо, что учитесь с Капибарой.")


async def award(bot, month: str | None = None) -> dict | None:
    """Выдать награду за month (по умолчанию — прошлый месяц). Уже выдана или
    победителя нет — None (отметка всё равно ставится: месяц не пересчитываем)."""
    import billing
    import locks
    from config import STAROSTA_ID
    from database import get_setting, set_setting
    month = month or prev_month()
    key = f"award:{month}"
    async with locks.lock("group_award"):
        if await get_setting(key):
            return None
        table = await standings(month)
        if not table:
            await set_setting(key, json.dumps({"group": None}))
            logger.info(f"группа месяца {month}: нет группы, где опыт за месяц у ≥ 3 человек")
            return None
        win = table[0]
        people = await members(win["id"])
        given = 0
        sent: list[tuple[int, str]] = []
        for uid in people:
            async with locks.lock("plus_grant", uid):
                until = await billing.grant(uid, DAYS, SOURCE)
            sent.append((uid, until))
            given += 1
        result = {"group": win["id"], "name": win["name"], "avg": win["avg"], "people": win["people"],
                  "granted": given}
        await set_setting(key, json.dumps(result, ensure_ascii=False))
    import scheduler
    for uid, until in sent:
        await billing.notify(bot, uid, text(win["name"], month, until))
        await scheduler.pace()
    if STAROSTA_ID:
        from utils import esc
        runner = ", ".join(f"{esc(g['name'])} ({g['avg']})" for g in table[1:3])
        try:
            await bot.send_message(
                STAROSTA_ID,
                f"Группа месяца за {MONTHS[int(month[5:]) - 1]}: <b>{esc(win['name'])}</b> — {win['avg']} опыта на "
                f"человека ({win['people']} с опытом). +{DAYS} дней «Капибары+»: {given} чел."
                + (f"\nДальше: {runner}." if runner else ""), parse_mode="HTML")
        except Exception as e:
            logger.info(f"группа месяца: не написать Никите: {e}")
    return result
