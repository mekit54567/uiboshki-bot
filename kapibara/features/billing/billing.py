"""Подписка «Капибара+»: цены, оплата, срок (PLAN.md «Подписка»).

Покупка — только на сайте: бот, Mini App, PWA и Android-приложение
открывают /plus по личной ссылке (подписана, вход не нужен); в iOS-сборке
подписки не видно вовсе (правила App Store вне США, 3.1.1 и 3.1.3). В самом
боте — ещё и счёт в звёздах Telegram (Stars: цифровое внутри Telegram — только
они), дороже рублей на STARS_MARKUP (Никита 21.10: +55 % — комиссия Telegram).

Цена первых (Никита 17.10): пока не сказано иначе, все платят «early»-цену
(месяц 149 ₽), и кто оплатил по ней — метка Early Supporter, платит так навсегда.
Новым — полная цена с `/plus stage full` (settings plus:stage). Своей группе
— подарок до GIFT_UNTIL (`/plus gift`, settings plus:gift): с ним она в
лимитах подписки (plans.py). Ручные продления и безлимит — `/grant`
(plus_grant.py); все продления пишутся в журнал plus_grants. Июль и август в
срок не считаются (пауза на лето): оплаченные дни переносятся на сентябрь.
"""

import hashlib
import hmac
import logging
import secrets
import time
from typing import TypedDict
from datetime import date, timedelta

from kapibara.core import config
from kapibara.core.errors import aside
from kapibara.features.billing import kassa
from kapibara.features.billing.kassa import PayError  # общая ошибка оплаты, её ловят как billing.PayError

logger = logging.getLogger(__name__)

class Plan(TypedDict):
    days: int
    price: int
    early: int
    title: str


PLANS: dict[str, Plan] = {           # price — полная, early — цена первых (метка Early Supporter)
    "month": {"days": 30, "price": 249, "early": 149, "title": "Месяц"},
    "semester": {"days": 150, "price": 790, "early": 649, "title": "Семестр"},
}
GIFT_UNTIL = "2026-12-31"             # подарок своей группе (Никита 17.10: «месяц или два»)
SUMMER = (7, 8)                       # месяцы паузы: оплаченные дни в них не идут
LINK_TTL = 24 * 3600                  # личная ссылка на /plus живёт сутки


def provider(configured_only: bool = False, uid: int | None = None) -> str:
    """Какая касса подключена: 'yookassa', 'robokassa' или ''. Пока нет
    реквизитов исполнителя (PD_FIO, PD_INN, PD_EMAIL) — оферта без них, для
    самозанятого так нельзя: оплата закрыта (configured_only — какая задана).
    uid — для кого: в тестовом режиме Robokassa касса открыта только Никите."""
    kind = (kassa.configured() or [""])[0]
    if configured_only or not kind:
        return kind
    if missing_requisites() or (uid is not None and test_only(uid)):
        return ""
    return kind


def test_only(uid: int | None) -> bool:
    """Тестовая оплата — только Никите (21.10: иначе любой набрал бы «Капибару+»
    бесплатно); остальным пока «оплата скоро»."""
    return kassa.test_mode() and not (uid and config.is_starosta(uid))


def missing_requisites() -> list[str]:
    from kapibara.features.privacy import privacy
    return [k for k in privacy.operator_missing() if k != "PD_CITY"]


def site() -> str:
    return (config.WEBAPP_URL or "https://www.uiboshki.ru").rstrip("/")


# ── Личная ссылка на страницу оплаты ─────────────────────────────────────────

def _sig(uid: int, exp: int) -> str:
    if not config.BOT_TOKEN:          # пустой ключ подписи подделывается — лучше упасть
        raise RuntimeError("BOT_TOKEN не задан — личную ссылку на оплату не подписать")
    return hmac.new(config.BOT_TOKEN.encode(), f"plus:{uid}:{exp}".encode(), hashlib.sha256).hexdigest()[:24]


def make_key(uid: int, now: float | None = None) -> str:
    exp = int((now or time.time()) + LINK_TTL)
    return f"{uid}.{exp}.{_sig(uid, exp)}"


def read_key(key: str, now: float | None = None) -> int | None:
    """uid из ключа ссылки или None (чужой, битый, просроченный)."""
    try:
        uid_s, exp_s, sig = key.split(".")
        uid, exp = int(uid_s), int(exp_s)
    except (ValueError, AttributeError):
        return None
    if exp < (now or time.time()) or not hmac.compare_digest(sig, _sig(uid, exp)):
        return None
    return uid


def pay_link(uid: int) -> str:
    return f"{site()}/plus?k={make_key(uid)}"


def donate_link(uid: int) -> str:
    """Личная ссылка на «Поддержать проект» — тот же ключ, что у /plus."""
    return f"{site()}/donate?k={make_key(uid)}"


def new_claim() -> str:
    """Код доната без входа: 22 знака [A-Za-z0-9_-] — влезает в /start (до 64)."""
    return secrets.token_urlsafe(16)


def claim_link(claim: str) -> str:
    """Ссылка в бота: привязать донат без входа к Telegram и открыть роадмап."""
    return f"https://t.me/{config.BOT_USERNAME}?start=dn_{claim}"


# ── Срок ─────────────────────────────────────────────────────────────────────

def add_days(start: date, days: int) -> date:
    """Последний оплаченный день, если считать days дней с start включительно
    и не считать июль и август."""
    d, left = start, days
    while True:
        if d.month not in SUMMER:
            left -= 1
            if left == 0:
                return d
        d += timedelta(days=1)


async def early() -> bool:
    """Действует ли цена первых для новых (пока Никита не скажет «249»)."""
    from database import get_setting
    return (await get_setting("plus:stage")) != "full"


async def gift_until() -> str | None:
    """До какого дня подарок своей группе (включительно) или None — выключен."""
    from database import get_setting
    v = await get_setting("plus:gift")
    return None if v == "off" else (v or GIFT_UNTIL)


async def gift_for(uid: int) -> str | None:
    """Подарок действует для него (своя группа и срок не прошёл) → последний день."""
    from kapibara.features.groups import groups
    from kapibara.core.utils import today_msk
    until = await gift_until()
    if not until or until < today_msk().isoformat():
        return None
    return until if await groups.in_home_group(uid) else None


async def unlimited_for(uid: int) -> dict | None:
    """Безлимит, выданный Никитой (/grant), действует → {"until": день или
    None — навсегда}; иначе None."""
    from database.billing import get_unlimited
    from kapibara.core.utils import today_msk
    un = await get_unlimited(uid)
    if not un or (un["until"] and un["until"] < today_msk().isoformat()):
        return None
    return {"until": un["until"]}


async def status(uid: int) -> dict:
    """Подписка человека: active, until (оплата, подарок или безлимит до даты —
    что дольше; безлимит навсегда — until может быть None), paid_until, gift,
    unlimited (bool) и unlimited_until, founder, цены для него."""
    from database.billing import get_sub
    from kapibara.core.utils import today_msk
    today = today_msk().isoformat()
    sub = await get_sub(uid)
    paid_until = sub["until"] if sub and sub["until"] >= today else None
    gift = await gift_for(uid)
    unl = await unlimited_for(uid)
    until = max(filter(None, (paid_until, gift, unl and unl["until"])), default=None)
    return {"active": bool(until) or bool(unl), "until": until, "paid_until": paid_until, "gift": gift,
            "unlimited": bool(unl), "unlimited_until": unl and unl["until"],
            "founder": bool(sub and sub["founder"]), "early": await early(),
            "prices": await prices(uid), "provider": provider(uid=uid)}


async def founder_price_for(uid: int) -> bool:
    """Платит ли он по цене первых: она ещё действует для новых или он уже
    Early Supporter (оплатил по ней — навсегда, перерывы не важны)."""
    from database.billing import get_sub
    sub = await get_sub(uid)
    return bool(sub and sub["founder"]) or await early()


async def prices(uid: int) -> list[dict]:
    founder = await founder_price_for(uid)
    return [{"plan": key, "title": p["title"], "days": p["days"],
             "price": p["early"] if founder else p["price"], "full": p["price"], "founder": founder}
            for key, p in PLANS.items()]


async def extend_from(uid: int, last: str | None, days: int) -> str:
    """Последний день, если прибавить days дней (без лета) к сроку last —
    после него и после подарка группе, если они ещё идут, иначе с сегодня."""
    from kapibara.core.utils import today_msk
    start = today_msk()
    for end in (last, await gift_for(uid)):
        if end and end >= start.isoformat():
            start = date.fromisoformat(end) + timedelta(days=1)
    return add_days(start, days).isoformat()


async def grant(uid: int, days: int, source: str, founder: bool | None = None, by: int | None = None,
                note: str | None = None) -> str:
    """Продлить подписку на days дней (без лета) — после оплаченного срока и
    после подарка группе, если он ещё идёт. → новый последний день. Каждое
    продление — в журнал plus_grants (source manual — вручную, /grant)."""
    from database.billing import get_sub, log_grant, put_sub
    sub = await get_sub(uid)
    prev = sub["until"] if sub else None
    until = await extend_from(uid, prev, days)
    await put_sub(uid, until, source, founder)
    await log_grant(uid, "sub", source, days, prev, until, by, note=note)
    return until


# ── Платёж ───────────────────────────────────────────────────────────────────


async def create(uid: int, plan: str, return_url: str) -> str:
    """Создать платёж и вернуть адрес страницы кассы."""
    from database.billing import add_payment
    kind = provider(uid=uid)
    if not kind:
        raise PayError("оплата ещё не подключена")
    if plan not in PLANS:
        raise PayError("нет такого тарифа")
    price = next(p["price"] for p in await prices(uid) if p["plan"] == plan)
    days = PLANS[plan]["days"]
    title = f"Подписка «Капибара+» на {days} дней"
    if kind == "yookassa":
        try:
            return await kassa.yookassa_create(uid, plan, price, days, title, return_url)
        except PayError:
            if "robokassa" not in kassa.configured():
                raise
            logger.warning("ЮKassa не ответила — платёж через Robokassa")
    inv = await kassa.new_inv_id()
    await add_payment(str(inv), "robokassa", uid, plan, price, days)
    return kassa.robokassa_url(inv, price, title, return_url)


async def find_payment(pid: str) -> dict | None:
    """Платёж подписки или донат — у обоих есть amount и payer_id."""
    from database.billing import get_donation, get_payment
    return await get_payment(pid) or await get_donation(pid)


async def paid(pid: str, bot=None) -> bool:
    """Касса подтвердила оплату: продлить подписку (один раз на платёж) и
    написать человеку. True — продлили сейчас."""
    from database.billing import add_bonus, mark_paid
    pay = await find_payment(pid)
    if not pay or not await mark_paid(pid) or not pay["payer_id"]:
        return False
    uid = pay["payer_id"]
    founder = None
    plan = PLANS.get(pay["plan"])
    if plan and pay["amount"] < plan["price"]:          # оплачено по цене первых — Early Supporter навсегда
        await add_bonus(uid, "founder", "slot", 0)
        founder = True
    until = await grant(uid, pay["days"], "pay", founder)
    logger.info(f"подписка: оплата {pid} — {uid} до {until}")
    if bot is not None:
        await notify(bot, uid, f"Оплата прошла, спасибо! «Капибара+» до {fmt_day(until)}.")
    return True


async def notify(bot, uid: int, text: str):
    from kapibara.features.notifications import delivery
    with aside(logger, f"подписка: не написать {uid}", level=logging.INFO):
        await delivery.deliver(bot, uid, text, kind="plus", tab="more", always_tg=True)


def fmt_day(iso: str) -> str:
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
    d = date.fromisoformat(iso)
    return f"{d.day} {months[d.month - 1]} {d.year}"
