"""Предложение показаться в рейтинге (Никита 18.11, варианты А + В из ревью 152-ФЗ).

Рамка закона: согласие свободное и однозначное (ст. 9), молчание согласием
не считается (ч. 8 ст. 10.1). Поэтому здесь только напоминания; сам тумблер
человек включает сам, обе галочки выключены, отказ так же прост, как согласие.

Вариант А (клиент спрашивает, мы считаем):
  • карточка на экране «Рейтинг», пока человека не видно ни группе, ни всем;
    «Не сейчас» прячет её на CARD_SNOOZE_DAYS;
  • лист при входе: первый раз через SHEET_FIRST_HOURS после первого входа,
    потом не чаще раза в SHEET_GAP_DAYS, не больше SHEET_MAX раз;
  • «Больше не предлагать» — никогда: ни карточки, ни листа, ни пуша.
Вариант В: предложение по поводу (группа поднялась в рейтинге вуза или человек
набрал за неделю XP_WEEK_MIN опыта) — не чаще раза в EVENT_GAP_DAYS, мимо
тихих часов, не тем, кто выбрал «Только важное», и не сразу после листа.

Нельзя (тёмные паттерны): галочка заранее, спрашивать на каждом входе,
«чтобы видеть других, покажи себя», одна кнопка сразу на «группе» и «всем»,
включать молча. Ничего из этого здесь нет: состояние только считает, когда
можно напомнить, и ничего не включает.
"""

import logging
from datetime import UTC, datetime, timedelta

from database._conn import connect
from kapibara.core.errors import aside

logger = logging.getLogger(__name__)

SHEET_FIRST_HOURS = 2
SHEET_GAP_DAYS = 14
SHEET_MAX = 3
CARD_SNOOZE_DAYS = 14
EVENT_GAP_DAYS = 30
EVENT_AFTER_SHEET_DAYS = 3
EVENT_MIN_AGE_DAYS = 3
XP_WEEK_MIN = 30
ACTIONS = ("shown", "later", "stop", "accepted")
SOURCES = ("card", "sheet", "event")
_FMT = "%Y-%m-%d %H:%M:%S"


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_FMT)


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], _FMT).replace(tzinfo=UTC)
    except ValueError:
        return None


async def _row(user_id: int) -> dict:
    async with connect() as db:
        row = await (await db.execute(
            "SELECT shown, last_at, stopped, card_until, event_at, accepted_via FROM rating_offers "
            "WHERE user_id = ?", (user_id,))).fetchone()
        joined = await (await db.execute("SELECT joined_at FROM users WHERE user_id = ?", (user_id,))).fetchone()
    return {"shown": row[0] if row else 0, "last_at": _parse(row[1]) if row else None,
            "stopped": bool(row[2]) if row else False, "card_until": _parse(row[3]) if row else None,
            "event_at": _parse(row[4]) if row else None, "accepted_via": row[5] if row else None,
            "joined_at": _parse(joined[0]) if joined else None}


async def hidden(user_id: int) -> bool:
    """Человека не видно ни группе, ни всем — только тогда есть что предлагать."""
    from kapibara.features.social import xp
    p = await xp.profile(user_id)
    return not p["show"] and not p["show_all"]


def _sheet_due(r: dict, now: datetime) -> bool:
    if r["shown"] >= SHEET_MAX:
        return False
    if r["last_at"] is not None:
        return now >= r["last_at"] + timedelta(days=SHEET_GAP_DAYS)
    first = r["joined_at"]
    return first is not None and now >= first + timedelta(hours=SHEET_FIRST_HOURS)


async def state(user_id: int, now: datetime | None = None) -> dict:
    """{'card': показать карточку в «Рейтинге», 'sheet': показать лист при входе}."""
    from kapibara.features.privacy import privacy
    now = now or datetime.now(UTC)
    off = {"card": False, "sheet": False}
    if await privacy.blocked(user_id) or not await hidden(user_id):
        return off
    r = await _row(user_id)
    if r["stopped"]:
        return off
    return {"card": r["card_until"] is None or now >= r["card_until"], "sheet": _sheet_due(r, now)}


async def act(user_id: int, action: str, source: str | None = None, now: datetime | None = None) -> dict:
    """shown — лист показан (считается), later — «Не сейчас» у карточки,
    stop — «Больше не предлагать», accepted — человек сам включил тумблер
    (source: card / sheet / event — для статистики)."""
    if action not in ACTIONS:
        raise ValueError("неизвестное действие")
    if source is not None and source not in SOURCES:
        raise ValueError("неизвестный источник")
    now = now or datetime.now(UTC)
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO rating_offers (user_id) VALUES (?)", (user_id,))
        if action == "shown":
            await db.execute("UPDATE rating_offers SET shown = shown + 1, last_at = ? WHERE user_id = ?",
                             (_stamp(now), user_id))
        elif action == "later":
            await db.execute("UPDATE rating_offers SET card_until = ? WHERE user_id = ?",
                             (_stamp(now + timedelta(days=CARD_SNOOZE_DAYS)), user_id))
        elif action == "stop":
            await db.execute("UPDATE rating_offers SET stopped = 1 WHERE user_id = ?", (user_id,))
        else:
            await db.execute("UPDATE rating_offers SET accepted_via = COALESCE(accepted_via, ?) WHERE user_id = ?",
                             (source or "card", user_id))
        await db.commit()
    return await state(user_id, now)


async def counts() -> dict[str, int]:
    """Для /stats: сколько людей согласились после карточки, листа, пуша."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT accepted_via, COUNT(*) FROM rating_offers WHERE accepted_via IS NOT NULL "
            "GROUP BY accepted_via")).fetchall()
        shown = await (await db.execute("SELECT COUNT(*) FROM rating_offers WHERE shown > 0")).fetchone()
        stopped = await (await db.execute("SELECT COUNT(*) FROM rating_offers WHERE stopped = 1")).fetchone()
    return {**dict.fromkeys(SOURCES, 0), **dict(rows), "shown": shown[0], "stopped": stopped[0]}


# ── Вариант В: по поводу ─────────────────────────────────────────────────────

def reason(b: dict, user_id: int) -> dict | None:
    """Повод из доски опыта (xp.board): группа поднялась в вузе или своя неделя.
    → {'kind': 'group' | 'xp', ...} или None."""
    person = b["people"].get(user_id)
    if not person:
        return None
    gid = person["group"]
    hist = b["history"].get(gid) or []
    if len(hist) >= 2:
        was, now = hist[-2].get("place"), hist[-1].get("place")
        if was is not None and now is not None and now < was:
            name = (b["groups"].get(gid) or {}).get("name") or ""
            return {"kind": "group", "group": name, "place": now, "up": was - now}
    mine = b["xp"].get(user_id) or {"total": 0}
    week = mine["total"] - b["week_start"].get(user_id, {}).get("total", 0)
    if week >= XP_WEEK_MIN:
        return {"kind": "xp", "week": week}
    return None


def text(why: dict) -> tuple[str, str, str]:
    """(заголовок, текст для ленты и пуша, HTML для Telegram). Без нажима:
    сразу сказано, что решать человеку и что по умолчанию его не видно."""
    tail = "Хочешь — покажись группе, тумблеры выключены, решать тебе."
    if why["kind"] == "group":
        up = why["up"]
        title = "Группа поднялась в рейтинге"
        body = f"Группа {why['group']} поднялась на {why['place']} место в вузе (+{up}). {tail}"
    else:
        title = "Ты набрал опыт"
        body = f"За эту неделю у тебя +{why['week']} опыта. {tail}"
    return title, body, f"<b>{title}</b>\n{body}"


async def send_events(bot, now: datetime | None = None) -> int:
    """Раз в день: кому есть повод и можно писать — одно предложение в ленту и
    пуш. → сколько отправлено."""
    from database import get_reminder_users
    from kapibara.core.telegram import app_button
    from kapibara.core.utils import TZ
    from kapibara.features.notifications import delivery
    from kapibara.features.notifications import prefs as notify_prefs
    from kapibara.features.notifications.broadcast import pace
    from kapibara.features.social import xp
    now = now or datetime.now(UTC)
    b = await xp.board()
    sent = 0
    for user in await get_reminder_users():
        uid = user["user_id"]
        prefs = notify_prefs.merge(user.get("notify"))
        if notify_prefs.profile(prefs) == "important" or notify_prefs.quiet_now(prefs, now.astimezone(TZ)):
            continue
        if uid not in b["people"]:          # нет согласия на обработку или ждёт удаления — в доске нет
            continue
        why = reason(b, uid)
        if why is None or not await hidden(uid):
            continue
        r = await _row(uid)
        if r["stopped"] or r["accepted_via"]:
            continue
        if r["joined_at"] is None or now < r["joined_at"] + timedelta(days=EVENT_MIN_AGE_DAYS):
            continue
        if r["event_at"] and now < r["event_at"] + timedelta(days=EVENT_GAP_DAYS):
            continue
        if r["last_at"] and now < r["last_at"] + timedelta(days=EVENT_AFTER_SHEET_DAYS):
            continue
        title, body, html = text(why)
        with aside(logger, f"предложение рейтинга {uid}", level=logging.INFO):
            async with connect() as db:         # отметка до отправки: сбой не должен повторять предложение
                await db.execute("INSERT OR IGNORE INTO rating_offers (user_id) VALUES (?)", (uid,))
                await db.execute("UPDATE rating_offers SET event_at = ? WHERE user_id = ?", (_stamp(now), uid))
                await db.commit()
            await delivery.deliver(bot, uid, html, kind="rating", tab="more", title=title, body=body,
                                   reply_markup=app_button("🚀 Открыть «Ещё»", "more"))
            sent += 1
            await pace()
    return sent
