"""Кассы оплаты: ключи ЮKassa и Robokassa, запросы к ним и подписи Robokassa.

Касса — та, ключи которой заданы: ЮKassa (YOOKASSA_SHOP_ID +
YOOKASSA_SECRET_KEY) или Robokassa (ROBOKASSA_LOGIN + ROBOKASSA_PASS1 +
ROBOKASSA_PASS2); заданы обе — ЮKassa, а если она не ответила, Robokassa.
Нет ключей — «оплата скоро», статус и бонусы работают. Автосписаний нет:
каждый срок оплачивается отдельно, срок складывается.
"""

import hashlib
import hmac
import logging
import os
import secrets
import uuid

from kapibara.core.errors import NETWORK

logger = logging.getLogger("kapibara.features.billing.billing")  # старое имя: /status

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN", "").strip()
ROBOKASSA_PASS1 = os.getenv("ROBOKASSA_PASS1", "").strip()
ROBOKASSA_PASS2 = os.getenv("ROBOKASSA_PASS2", "").strip()
ROBOKASSA_TEST = os.getenv("ROBOKASSA_TEST", "") == "1"
YOOKASSA_API = "https://api.yookassa.ru/v3"
ROBOKASSA_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def configured() -> list[str]:
    return ((["yookassa"] if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY else []) +
            (["robokassa"] if ROBOKASSA_LOGIN and ROBOKASSA_PASS1 and ROBOKASSA_PASS2 else []))


def test_mode() -> bool:
    """Касса в тестовом режиме — деньги не списываются: Robokassa с
    ROBOKASSA_TEST=1 или тестовый магазин ЮKassa (секретный ключ test_…)."""
    kind = (configured() or [""])[0]
    if kind == "yookassa":
        return YOOKASSA_SECRET_KEY.startswith("test_")
    return ROBOKASSA_TEST and kind == "robokassa"


class PayError(Exception):
    pass


async def yookassa_create(uid: int | None, plan: str, price: int, days: int, title: str, return_url: str,
                          donation: bool = False, claim: str | None = None) -> str:
    from database import billing as store
    local = f"local-{uuid.uuid4()}"
    if donation:
        await store.add_donation(local, "yookassa", uid, price, claim)
    else:
        await store.add_payment(local, "yookassa", uid or 0, plan, price, days)   # подписка — всегда с uid
    body = {"amount": {"value": f"{price}.00", "currency": "RUB"}, "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": title,        # без id человека (152-ФЗ): связь — в payments/donations
            "metadata": {"kind": "donation"} if donation else {"plan": plan}}
    try:
        async with yk_client() as c:
            r = await c.post(f"{YOOKASSA_API}/payments", json=body, headers={"Idempotence-Key": local})
        r.raise_for_status()
        data = r.json()
    except (*NETWORK, ValueError) as e:
        logger.warning(f"ЮKassa: платёж не создан: {e}")
        await (store.mark_donation if donation else store.mark_payment)(local, "canceled")
        raise PayError("касса не отвечает — попробуй через минуту") from e
    await (store.set_donation_id if donation else store.set_payment_id)(local, data["id"])
    return data["confirmation"]["confirmation_url"]


async def new_inv_id() -> int:
    """Номер счёта Robokassa — один на подписки и донаты (уведомление
    находит платёж по номеру)."""
    from database.billing import get_donation, get_payment
    while True:
        inv = secrets.randbelow(2_000_000_000) + 1
        if not await get_payment(str(inv)) and not await get_donation(str(inv)):
            return inv


def yk_client():
    import httpx
    from kapibara.core import net
    return net.client(timeout=20, auth=httpx.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY))


def robokassa_url(inv: int, price: int, title: str, back: str = "") -> str:
    """Ссылка на оплату. back — куда вернуть после оплаты (/plus/done или
    /donate/done с личным ключом): в кабинете Robokassa Success URL один на
    всё, поэтому свой адрес — SuccessUrl2, отказ — та же страница без /done
    (FailUrl2). Оба входят в подпись после InvId."""
    from urllib.parse import urlencode
    out_sum = f"{price}.00"
    extra = []
    if back:
        extra = [("SuccessUrl2", back), ("SuccessUrl2Method", "GET"),
                 ("FailUrl2", back.replace("/done", "", 1)), ("FailUrl2Method", "GET")]
    base = ":".join([ROBOKASSA_LOGIN, out_sum, str(inv)] + [v for _, v in extra] + [ROBOKASSA_PASS1])
    sig = hashlib.md5(base.encode()).hexdigest()
    q = {"MerchantLogin": ROBOKASSA_LOGIN, "OutSum": out_sum, "InvId": inv, "Description": title,
         "SignatureValue": sig, "Culture": "ru", "Encoding": "utf-8", **dict(extra)}
    if ROBOKASSA_TEST:
        q["IsTest"] = 1
    return f"{ROBOKASSA_URL}?{urlencode(q)}"


def robokassa_ok(out_sum: str, inv: str, sig: str) -> bool:
    """Подпись уведомления Robokassa (ResultURL): md5(OutSum:InvId:Pass2)."""
    want = hashlib.md5(f"{out_sum}:{inv}:{ROBOKASSA_PASS2}".encode()).hexdigest()
    return bool(ROBOKASSA_PASS2) and hmac.compare_digest(want.lower(), (sig or "").lower())
