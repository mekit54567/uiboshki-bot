"""Бонусные дни «Капибары+»: за закрытый ранг ачивок и «пригласи друга».

Ранги (app/lib/achievements): сервер приложению на слово не верит —
проверяет настоящие дни с заходами (события stats.py), а когда ачивки
хранятся на сервере (achievements.py, 5.91), — и что все ачивки ранга
открыты. Каждый ранг — один раз на аккаунт.

Приглашение: ссылка t.me/<бот>?start=ref_<код> (или /app?ref=<код>).
Засчитывается только новому человеку (пришёл по ссылке впервые) и только
когда друг правда пользуется: FRIEND_DAYS разных дней с заходами за первые
FRIEND_WINDOW дней. Тогда другу REF_BONUS дней всегда, пригласившему — тоже,
но не больше чем за REF_MAX друзей за всё время (Никита 18.10: «максимум 3
человека по приглашению дают подписку»). Проверка — раз в день (scheduler).

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
REF_MAX = 3                     # пригласившему — дни максимум за 3 друзей, за всё время


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


def tg_share_url(link: str) -> str:
    """t.me/share/url: Telegram сам предложит выбрать чат, сообщение уже готово."""
    from urllib.parse import urlencode
    return "https://t.me/share/url?" + urlencode({"url": link, "text": share_text()})


def share_image() -> str:
    """Картинка приглашения — своя, приложение в светлой теме (Никита 18.10):
    tools/site_og.py --invite; превью сайта og.jpg — отдельно."""
    import billing
    return f"{billing.site()}/site/invite.jpg"


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
    if not await _rank_closed(uid, rank):
        # без «уже»: приложение спросит ещё раз, когда отправит ачивки
        raise BonusError(f"сервер пока не видит закрытый ранг «{RANK_TITLES[rank]}» — проверим позже")
    if not await add_bonus(uid, "rank", rank, days):
        raise BonusError("бонус за этот ранг уже получен")
    until = await billing.grant(uid, days, f"rank:{rank}")
    return {"days": days, "until": until}


async def _rank_closed(uid: int, rank: str) -> bool:
    """Ачивки на сервере (5.91) — все ачивки ранга открыты; без них — верим дням."""
    try:
        import achievements
    except ImportError:
        return True
    return await achievements.rank_closed(uid, rank)


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
    from database.billing import active_days, add_bonus, get_referral, mark_rewarded
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
    n = await counted(inviter)
    if n < REF_MAX:
        await add_bonus(inviter, "ref", f"friend{n + 1}", REF_BONUS)
        until = await billing.grant(inviter, REF_BONUS, "ref:inviter")
        if bot is not None:
            await billing.notify(bot, inviter, f"Друг, которого ты позвал, пользуется Капибарой: "
                                               f"+{REF_BONUS} дней «Капибары+», теперь до {billing.fmt_day(until)}."
                                               + (f" Это {REF_MAX}-й друг — бонус за приглашения на этом всё, "
                                                  f"друзьям дни по-прежнему дают." if n + 1 >= REF_MAX else ""))
    elif bot is not None:
        await billing.notify(bot, inviter, f"Друг, которого ты позвал, пользуется Капибарой — ему "
                                           f"+{REF_BONUS} дней «Капибары+». {limit_done()}")
    return True


async def counted(uid: int) -> int:
    """Скольких друзей уже засчитали пригласившему (дали ему дни) — за всё время."""
    from database.billing import count_bonuses
    return await count_bonuses(uid, "ref", 100_000)


def limit_done() -> str:
    return (f"Ты уже позвал {REF_MAX} {_friends(REF_MAX)} — бонус за приглашения закончился, "
            f"друзьям дни по-прежнему дают.")


def _friends(n: int) -> str:
    """3 друзей, 1 друга (родительный: «позвал 3 друзей», «за 1 друга»)."""
    return "друга" if n % 10 == 1 and n % 100 != 11 else "друзей"


def invite_line(inv: dict) -> str:
    """Про приглашения для бота и сайта (/plus, /invite, рассылка): кому сколько
    дней и сколько друзей ещё засчитают пригласившему — или честно, что всё."""
    when = f"Когда друг попользуется Капибарой {FRIEND_DAYS} дня"
    if inv["ref_counted"] >= inv["ref_max"]:
        return f"{when}, ему +{REF_BONUS} дней «Капибары+». {limit_done()}"
    return (f"{when}, вам обоим +{REF_BONUS} дней «Капибары+». Тебе — максимум за "
            f"{inv['ref_max']} {_friends(inv['ref_max'])}, засчитано {inv['ref_counted']} из {inv['ref_max']}.")


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
            "friend_days": FRIEND_DAYS, "ref_max": REF_MAX, "ref_counted": await counted(uid),
            "ranks": {r: {"days": d, "need_days": need,
                          "claimed": any(b["kind"] == "rank" and b["key"] == r for b in bonuses)}
                      for r, (d, need) in RANKS.items()}}
