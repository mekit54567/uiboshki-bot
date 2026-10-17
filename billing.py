"""Подписка «Капибара+»: цены, оплата, срок (PLAN.md «Подписка»).

Покупка — только на сайте: бот, Mini App, PWA и Android-приложение
открывают /plus по личной ссылке (подписана, вход не нужен); в iOS-сборке
подписки не видно вовсе (правила App Store вне США, 3.1.1 и 3.1.3). В Telegram счёт не выставляем: цифровое
внутри бота — только Stars (правила Telegram), а Stars Никита не хочет.

Касса — та, ключи которой заданы: ЮKassa (YOOKASSA_SHOP_ID +
YOOKASSA_SECRET_KEY) или Robokassa (ROBOKASSA_LOGIN + ROBOKASSA_PASS1 +
ROBOKASSA_PASS2); заданы обе — ЮKassa, а если она не ответила, Robokassa.
Нет ключей — «оплата скоро», статус и бонусы работают. Автосписаний нет:
каждый срок оплачивается отдельно, срок складывается.

Цена первых (Никита 17.10): пока не сказано иначе, все платят «early»-цену
(месяц 149 ₽), и кто оплатил по ней — «Основатель», платит так навсегда.
Новым — полная цена с `/plus stage full` (settings plus:stage). Своей группе
— подарок до GIFT_UNTIL (`/plus gift`, settings plus:gift). Июль и август в
срок не считаются (пауза на лето): оплаченные дни переносятся на сентябрь."""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from datetime import date, timedelta

import config

logger = logging.getLogger(__name__)

PLANS = {                             # price — полная, early — цена первых («Основатель»)
    "month": {"days": 30, "price": 249, "early": 149, "title": "Месяц"},
    "semester": {"days": 150, "price": 790, "early": 649, "title": "Семестр"},
}
GIFT_UNTIL = "2026-12-31"             # подарок своей группе (Никита 17.10: «месяц или два»)
SUMMER = (7, 8)                       # месяцы паузы: оплаченные дни в них не идут

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN", "").strip()
ROBOKASSA_PASS1 = os.getenv("ROBOKASSA_PASS1", "").strip()
ROBOKASSA_PASS2 = os.getenv("ROBOKASSA_PASS2", "").strip()
ROBOKASSA_TEST = os.getenv("ROBOKASSA_TEST", "") == "1"

LINK_TTL = 24 * 3600                  # личная ссылка на /plus живёт сутки
YOOKASSA_API = "https://api.yookassa.ru/v3"
ROBOKASSA_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _kassas() -> list[str]:
    return ((["yookassa"] if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY else []) +
            (["robokassa"] if ROBOKASSA_LOGIN and ROBOKASSA_PASS1 and ROBOKASSA_PASS2 else []))


def provider(configured_only: bool = False) -> str:
    """Какая касса подключена: 'yookassa', 'robokassa' или ''. Пока нет
    реквизитов исполнителя (PD_FIO, PD_INN, PD_EMAIL) — оферта без них, для
    самозанятого так нельзя: оплата закрыта (configured_only — какая задана)."""
    kind = (_kassas() or [""])[0]
    if configured_only or not kind:
        return kind
    return "" if missing_requisites() else kind


def missing_requisites() -> list[str]:
    import privacy
    return [k for k in privacy.operator_missing() if k != "PD_CITY"]


def site() -> str:
    return (config.WEBAPP_URL or "https://www.uiboshki.ru").rstrip("/")


# ── Личная ссылка на страницу оплаты ─────────────────────────────────────────

def _sig(uid: int, exp: int) -> str:
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
    import plans
    from utils import today_msk
    until = await gift_until()
    if not until or until < today_msk().isoformat():
        return None
    return until if await plans._own(uid) else None


async def status(uid: int) -> dict:
    """Подписка человека: active, until (оплата или подарок — что дольше),
    paid_until, gift, founder, цены для него."""
    from database.billing import get_sub
    from utils import today_msk
    today = today_msk().isoformat()
    sub = await get_sub(uid)
    paid_until = sub["until"] if sub and sub["until"] >= today else None
    gift = await gift_for(uid)
    until = max(filter(None, (paid_until, gift)), default=None)
    return {"active": bool(until), "until": until, "paid_until": paid_until, "gift": gift,
            "founder": bool(sub and sub["founder"]), "early": await early(),
            "prices": await prices(uid), "provider": provider()}


async def founder_price_for(uid: int) -> bool:
    """Платит ли он по цене первых: она ещё действует для новых или он уже
    «Основатель» (оплатил по ней — навсегда, перерывы не важны)."""
    from database.billing import get_sub
    sub = await get_sub(uid)
    return bool(sub and sub["founder"]) or await early()


async def prices(uid: int) -> list[dict]:
    founder = await founder_price_for(uid)
    return [{"plan": key, "title": p["title"], "days": p["days"],
             "price": p["early"] if founder else p["price"], "full": p["price"], "founder": founder}
            for key, p in PLANS.items()]


async def grant(uid: int, days: int, source: str, founder: bool | None = None) -> str:
    """Продлить подписку на days дней (без лета) — после оплаченного срока и
    после подарка группе, если он ещё идёт. → новый последний день."""
    from database.billing import get_sub, put_sub
    from utils import today_msk
    today = today_msk()
    sub = await get_sub(uid)
    start = today
    for last in (sub["until"] if sub else None, await gift_for(uid)):
        if last and last >= start.isoformat():
            start = date.fromisoformat(last) + timedelta(days=1)
    until = add_days(start, days).isoformat()
    await put_sub(uid, until, source, founder)
    return until


# ── Платёж ───────────────────────────────────────────────────────────────────

class PayError(Exception):
    pass


async def create(uid: int, plan: str, return_url: str) -> str:
    """Создать платёж и вернуть адрес страницы кассы."""
    from database.billing import add_payment
    kind = provider()
    if not kind:
        raise PayError("оплата ещё не подключена")
    if plan not in PLANS:
        raise PayError("нет такого тарифа")
    price = next(p["price"] for p in await prices(uid) if p["plan"] == plan)
    days = PLANS[plan]["days"]
    title = f"Подписка «Капибара+» на {days} дней"
    if kind == "yookassa":
        try:
            return await _yookassa_create(uid, plan, price, days, title, return_url)
        except PayError:
            if "robokassa" not in _kassas():
                raise
            logger.warning("ЮKassa не ответила — платёж через Robokassa")
    inv = await _new_inv_id()
    await add_payment(str(inv), "robokassa", uid, plan, price, days)
    return robokassa_url(inv, price, title)


async def _yookassa_create(uid: int, plan: str, price: int, days: int, title: str, return_url: str) -> str:
    from database.billing import add_payment, mark_payment, set_payment_id
    local = f"local-{uuid.uuid4()}"
    await add_payment(local, "yookassa", uid, plan, price, days)
    body = {"amount": {"value": f"{price}.00", "currency": "RUB"}, "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": title, "metadata": {"plan": plan}}    # без id человека (152-ФЗ): связь — в payments
    try:
        async with _yk_client() as c:
            r = await c.post(f"{YOOKASSA_API}/payments", json=body, headers={"Idempotence-Key": local})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(f"ЮKassa: платёж не создан: {e}")
        await mark_payment(local, "canceled")
        raise PayError("касса не отвечает — попробуй через минуту")
    await set_payment_id(local, data["id"])
    return data["confirmation"]["confirmation_url"]


async def _new_inv_id() -> int:
    from database.billing import get_payment
    while True:
        inv = secrets.randbelow(2_000_000_000) + 1
        if not await get_payment(str(inv)):
            return inv


def _yk_client():
    import httpx
    import net
    return net.client(timeout=20, auth=httpx.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY))


def robokassa_url(inv: int, price: int, title: str) -> str:
    from urllib.parse import urlencode
    out_sum = f"{price}.00"
    sig = hashlib.md5(f"{ROBOKASSA_LOGIN}:{out_sum}:{inv}:{ROBOKASSA_PASS1}".encode()).hexdigest()
    q = {"MerchantLogin": ROBOKASSA_LOGIN, "OutSum": out_sum, "InvId": inv, "Description": title,
         "SignatureValue": sig, "Culture": "ru", "Encoding": "utf-8"}
    if ROBOKASSA_TEST:
        q["IsTest"] = 1
    return f"{ROBOKASSA_URL}?{urlencode(q)}"


def robokassa_ok(out_sum: str, inv: str, sig: str) -> bool:
    """Подпись уведомления Robokassa (ResultURL): md5(OutSum:InvId:Pass2)."""
    want = hashlib.md5(f"{out_sum}:{inv}:{ROBOKASSA_PASS2}".encode()).hexdigest()
    return bool(ROBOKASSA_PASS2) and hmac.compare_digest(want.lower(), (sig or "").lower())


async def yookassa_check(pid: str) -> str | None:
    """Статус платежа у самой ЮKassa (уведомлению на слово не верим)."""
    try:
        async with _yk_client() as c:
            r = await c.get(f"{YOOKASSA_API}/payments/{pid}")
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning(f"ЮKassa: статус {pid} не узнать: {e}")
        return None
    pay = await _payment(pid)
    if pay and data.get("status") == "succeeded":
        amount = data.get("amount") or {}
        if amount.get("currency") != "RUB" or float(amount.get("value", 0)) + 0.001 < pay["amount"]:
            logger.warning(f"ЮKassa: сумма {pid} не та: {json.dumps(amount)}")
            return "mismatch"
    return data.get("status")


async def _payment(pid: str) -> dict | None:
    from database.billing import get_payment
    return await get_payment(pid)


async def paid(pid: str, bot=None) -> bool:
    """Касса подтвердила оплату: продлить подписку (один раз на платёж) и
    написать человеку. True — продлили сейчас."""
    from database.billing import add_bonus, mark_paid
    pay = await _payment(pid)
    if not pay or not await mark_paid(pid) or not pay["payer_id"]:
        return False
    uid = pay["payer_id"]
    founder = None
    plan = PLANS.get(pay["plan"])
    if plan and pay["amount"] < plan["price"]:          # оплачено по цене первых — «Основатель» навсегда
        await add_bonus(uid, "founder", "slot", 0)
        founder = True
    until = await grant(uid, pay["days"], "pay", founder)
    logger.info(f"подписка: оплата {pid} — {uid} до {until}")
    if bot is not None:
        await notify(bot, uid, f"Оплата прошла, спасибо! «Капибара+» до {fmt_day(until)}.")
    return True


async def notify(bot, uid: int, text: str):
    import delivery
    try:
        await delivery.deliver(bot, uid, text, kind="plus", tab="more")
    except Exception as e:
        logger.info(f"подписка: не написать {uid}: {e}")


def fmt_day(iso: str) -> str:
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
    d = date.fromisoformat(iso)
    return f"{d.day} {months[d.month - 1]} {d.year}"
