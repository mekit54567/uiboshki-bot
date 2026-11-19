"""Оплата звёздами Telegram: счёт в боте, проверка перед списанием и продление подписки.

Курс и наценка: STARS_RUB и STARS_MARKUP. Остальная оплата — в billing и kassa.
"""

import logging
import os
import uuid

from kapibara.features.billing import billing, kassa

logger = logging.getLogger("kapibara.features.billing.billing")  # старое имя: /status

STARS_RUB = float(os.getenv("STARS_RUB", "1.8") or 0)       # сколько ₽ платят за звезду; 0 — без Stars
STARS_MARKUP = float(os.getenv("STARS_MARKUP", "1.55") or 1)  # в звёздах дороже рублей (комиссия Telegram)


def stars_on() -> bool:
    """Оплата звёздами в боте: курс задан и есть реквизиты исполнителя (как у кассы)."""
    return STARS_RUB > 0 and not billing.missing_requisites()


def stars_price(rub: int) -> int:
    """Цена в звёздах: рубли × STARS_MARKUP по курсу STARS_RUB, вверх до целой звезды."""
    import math
    return max(1, math.ceil(round(rub * STARS_MARKUP / STARS_RUB, 6)))


async def stars_invoice(uid: int, plan: str) -> dict:
    """Платёж звёздами: запись в payments (provider stars, amount — цена в
    рублях, по ней же метка Early Supporter) → поля счёта Telegram."""
    from database.billing import add_payment, set_payment_stars
    if not stars_on():
        raise kassa.PayError("оплата звёздами выключена")
    if plan not in billing.PLANS:
        raise kassa.PayError("нет такого тарифа")
    price = next(p["price"] for p in await billing.prices(uid) if p["plan"] == plan)
    days = billing.PLANS[plan]["days"]
    stars = stars_price(price)
    pid = f"stars-{uuid.uuid4().hex}"
    await add_payment(pid, "stars", uid, plan, price, days)
    await set_payment_stars(pid, stars)
    return {"payload": pid, "stars": stars, "days": days,
            "title": f"Капибара+ · {billing.PLANS[plan]['title'].lower()}",
            "description": f"Подписка «Капибара+» на {days} дней (июль и август не считаются). "
                           "Без автосписаний."}


async def stars_check(pid: str, uid: int, total: int, currency: str) -> str:
    """Перед списанием (pre_checkout_query): '' — можно, иначе причина."""
    from database.billing import get_payment
    pay = await get_payment(pid)
    if not pay or pay["provider"] != "stars" or pay["payer_id"] != uid:
        return "Счёт не найден — открой /plus заново."
    if pay["status"] != "pending":
        return "Этот счёт уже оплачен — открой /plus заново."
    if currency != "XTR" or total != pay["stars"]:
        return "Цена изменилась — открой /plus заново."
    return ""


async def stars_paid(pid: str, uid: int, charge_id: str, bot=None) -> bool:
    """Telegram списал звёзды: запомнить номер списания и продлить подписку."""
    from database.billing import get_payment, set_payment_charge
    pay = await get_payment(pid)
    if not pay or pay["provider"] != "stars" or pay["payer_id"] != uid:
        logger.warning(f"Stars: оплата {pid} не найдена или чужая ({uid})")
        return False
    await set_payment_charge(pid, charge_id)
    return await billing.paid(pid, bot)
