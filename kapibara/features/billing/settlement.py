"""Уведомления касс: чей платёж, засчитать, отменить."""

import json
import logging

from kapibara.core import config
from kapibara.core.errors import NETWORK
from kapibara.features.billing import billing, donate, kassa

logger = logging.getLogger("kapibara.features.billing.billing")  # старое имя: /status

async def yookassa_check(pid: str) -> str | None:
    """Статус платежа у самой ЮKassa (уведомлению на слово не верим)."""
    try:
        async with kassa.yk_client() as c:
            r = await c.get(f"{kassa.YOOKASSA_API}/payments/{pid}")
        r.raise_for_status()
        data = r.json()
    except (*NETWORK, ValueError) as e:
        logger.warning(f"ЮKassa: статус {pid} не узнать: {e}")
        return None
    pay = await billing.find_payment(pid)
    if pay and data.get("status") == "succeeded" and data.get("test") and not config.is_starosta(pay["payer_id"] or 0):
        # тестовый платёж (денег нет) засчитывается только Никите — как у Robokassa, 21.10
        logger.warning(f"ЮKassa: тестовый платёж {pid} не от Никиты — не засчитан")
        return "test"
    if pay and data.get("status") == "succeeded":
        amount = data.get("amount") or {}
        if amount.get("currency") != "RUB" or float(amount.get("value", 0)) + 0.001 < pay["amount"]:
            logger.warning(f"ЮKassa: сумма {pid} не та: {json.dumps(amount)}")
            return "mismatch"
    return data.get("status")


async def is_ours(pid: str) -> bool:
    return await billing.find_payment(pid) is not None


async def settle(pid: str, bot=None) -> bool:
    """Касса подтвердила оплату: донат — спасибо, без дней подписки; платёж
    подписки — продлить (paid). Различаем по таблице, а не по телу
    уведомления: ему не верим. True — засчитали сейчас (не повтор)."""
    from database.billing import get_donation
    if await get_donation(pid):
        return await donate.donation_paid(pid, bot)
    return await billing.paid(pid, bot)


async def cancel(pid: str):
    from database.billing import mark_donation, mark_payment
    await mark_payment(pid, "canceled")
    await mark_donation(pid, "canceled")
