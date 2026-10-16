"""Бонусные дни «Капибары+»: за закрытый ранг ачивок и «пригласи друга».

Ранги (app/lib/achievements): ачивки пока живут на телефоне, сервер им на
слово не верит — кроме «закрыл ранг» проверяет и настоящие дни с заходами
(события stats.py). Каждый ранг — один раз на аккаунт.

Приглашение: ссылка t.me/<бот>?start=ref_<код> (или /app?ref=<код>).
Засчитывается только новому человеку (пришёл по ссылке впервые) и только
когда друг правда пользуется: FRIEND_DAYS разных дней с заходами за первые
FRIEND_WINDOW дней. Тогда обоим по REF_BONUS дней, пригласившему — не
больше REF_MAX друзей за REF_PERIOD дней. Проверка — раз в день (scheduler).

«Поделиться» (бот, Mini App, PWA, приложение) отправляет не голую ссылку, а
готовое сообщение: картинка, пара строк и кнопка с личной ссылкой."""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ранг → (дней подписки, сколько разных дней с заходами нужно)
RANKS = {"dawn": (3, 1), "noon": (5, 7), "dusk": (7, 14), "midnight": (14, 21)}
RANK_TITLES = {"dawn": "Рассвет", "noon": "Полдень", "dusk": "Сумерки", "midnight": "Полночь"}

REF_BONUS = 7
FRIEND_DAYS = 3
FRIEND_WINDOW = 14
NEW_USER_HOURS = 48             # «новый» — появился в базе не раньше, чем за 2 дня до ссылки
REF_MAX = 8
REF_PERIOD = 182


# Тексты «Поделиться» — тред постов (release/group-message.md, раздел 2);
# NAME поменяется, когда выберут имя приложения.
NAME = "Капибара"
SHARE_TEXT = ("{name} — расписание любой группы МИРЭА, дедлайны и баллы СДО в одном месте. "
              "Сам напомнит о паре и горящем сроке 👇")
SHARE_BUTTON = "Открыть {name}"


def share_text() -> str:
    return SHARE_TEXT.format(name=NAME)


def share_button() -> str:
    return SHARE_BUTTON.format(name=NAME)


def share_image() -> str:
    import billing
    return f"{billing.site()}/site/og.jpg"


class BonusError(Exception):
    pass


async def claim_rank(uid: int, rank: str) -> dict:
    """Закрыл ранг ачивок → дни подписки (один раз). → {days, until}."""
    import billing
    from database.billing import active_days, add_bonus
    if rank not in RANKS:
        raise BonusError("нет такого ранга")
    days, need = RANKS[rank]
    have = await active_days(uid)
    if have < need:
        raise BonusError(f"для ранга «{RANK_TITLES[rank]}» нужно заходить хотя бы {need} разных дней "
                         f"(сейчас {have})")
    if not await add_bonus(uid, "rank", rank, days):
        raise BonusError("бонус за этот ранг уже получен")
    until = await billing.grant(uid, days, f"rank:{rank}")
    return {"days": days, "until": until}


async def link(uid: int) -> str:
    import config
    from database.billing import ref_code
    return f"https://t.me/{config.BOT_USERNAME}?start=ref_{await ref_code(uid)}"


async def bind(friend_id: int, code: str, was_new: bool | None = None) -> bool:
    """Друг пришёл по ссылке с кодом. was_new — бот знает, что человека не было
    в базе до этого /start; иначе (PWA, приложение) — смотрим на joined_at."""
    from database.billing import add_referral, joined_at, user_by_ref
    inviter = await user_by_ref((code or "").strip())
    if not inviter or inviter == friend_id:
        return False
    if was_new is None:
        joined = await joined_at(friend_id)
        if not joined:
            return False
        age = datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(joined)
        was_new = age <= timedelta(hours=NEW_USER_HOURS)
    if not was_new:
        return False
    ok = await add_referral(friend_id, inviter)
    if ok:
        logger.info(f"приглашение: {friend_id} пришёл от {inviter}")
    return ok


async def check(friend_id: int, bot=None) -> bool:
    """Друг уже правда пользуется? Тогда обоим дни. True — наградили сейчас."""
    import billing
    from database.billing import active_days, add_bonus, count_bonuses, get_referral, mark_rewarded
    ref = await get_referral(friend_id)
    if not ref or ref["rewarded_at"]:
        return False
    start = datetime.fromisoformat(ref["at"])
    if datetime.now(timezone.utc).replace(tzinfo=None) - start > timedelta(days=FRIEND_WINDOW):
        return False
    if await active_days(friend_id, ref["at"]) < FRIEND_DAYS:
        return False
    if not await mark_rewarded(friend_id):
        return False
    inviter = ref["inviter_id"]
    await add_bonus(friend_id, "invited", "by_friend", REF_BONUS)
    await billing.grant(friend_id, REF_BONUS, "ref:friend")
    if bot is not None:
        await billing.notify(bot, friend_id, f"Тебя пригласил друг, и ты пользуешься Капибарой: "
                                             f"+{REF_BONUS} дней «Капибары+» в подарок.")
    if await count_bonuses(inviter, "ref", REF_PERIOD) < REF_MAX:
        n = await count_bonuses(inviter, "ref", 100_000)
        await add_bonus(inviter, "ref", f"friend{n + 1}", REF_BONUS)
        until = await billing.grant(inviter, REF_BONUS, "ref:inviter")
        if bot is not None:
            await billing.notify(bot, inviter, f"Друг, которого ты позвал, пользуется Капибарой: "
                                               f"+{REF_BONUS} дней «Капибары+», теперь до {billing.fmt_day(until)}.")
    return True


async def check_all(bot=None) -> int:
    """Раз в день: проверить все свежие приглашения."""
    from database.billing import open_referrals
    n = 0
    for ref in await open_referrals(FRIEND_WINDOW + 1):
        try:
            n += await check(ref["friend_id"], bot)
        except Exception as e:
            logger.warning(f"приглашение {ref['friend_id']}: {e}")
    return n


async def summary(uid: int) -> dict:
    """Для экрана «Капибара+»: ссылка, сколько пришло и засчитано, ранги."""
    from database.billing import get_bonuses, invited_count
    came, rewarded = await invited_count(uid)
    bonuses = await get_bonuses(uid)
    return {"link": await link(uid), "share_text": share_text(), "share_image": share_image(),
            "came": came, "rewarded": rewarded, "bonus_days": REF_BONUS,
            "friend_days": FRIEND_DAYS,
            "ranks": {r: {"days": d, "need_days": need,
                          "claimed": any(b["kind"] == "rank" and b["key"] == r for b in bonuses)}
                      for r, (d, need) in RANKS.items()}}
