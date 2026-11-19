"""«Поддержать проект» (Никита 18.10) — донат той же кассой на сайте (/donate по
такой же личной ссылке): сумма на выбор, своя таблица donations, дней
подписки не даёт — просто спасибо; в ответ открывается роадмап (roadmap.py). Уведомления касс
отличают его от подписки по таблице, где лежит платёж (settle). На iPhone —
скрыт, как и подписка (донат не через Apple — против правил App Store).
"""

import logging

from kapibara.core import config
from kapibara.features.billing import billing, kassa

logger = logging.getLogger("kapibara.features.billing.billing")  # старое имя: /status

DONATE_AMOUNTS = (100, 300, 500)      # «Поддержать проект»: кнопки сумм, и своя — от MIN до MAX
DONATE_MIN = 50
DONATE_MAX = 15000
DONATE_TITLE = "Добровольная поддержка проекта «Капибара»"   # позиция в кассе и в чеке «Мой налог»


def donate_amount(value) -> int:
    """Сумма доната из формы: целые рубли от DONATE_MIN до DONATE_MAX."""
    try:
        amount = int(str(value).strip().replace(" ", "").replace("₽", ""))
    except (TypeError, ValueError):
        raise kassa.PayError(f"сумма — целым числом рублей, от {DONATE_MIN} ₽") from None
    if amount < DONATE_MIN or amount > DONATE_MAX:
        raise kassa.PayError(f"сумма — от {DONATE_MIN} до {DONATE_MAX} ₽")
    return amount


async def create_donation(uid: int | None, amount, return_url: str, claim: str | None = None) -> str:
    """Донат «Поддержать проект»: платёж в кассе → адрес её страницы. Та же
    касса и те же условия, что у подписки (без реквизитов — закрыто).
    uid None — донат без входа с открытой страницы /donate, claim — код,
    по которому его потом привязывают к Telegram (claim_link)."""
    from database.billing import add_donation
    kind = billing.provider(uid=uid or 0)          # 0: без входа в тестовом режиме касса закрыта
    if not kind:
        raise kassa.PayError("оплата ещё не подключена")
    amount = donate_amount(amount)
    if kind == "yookassa":
        try:
            return await kassa.yookassa_create(uid, "donation", amount, 0, DONATE_TITLE, return_url,
                                          donation=True, claim=claim)
        except kassa.PayError:
            if "robokassa" not in kassa.configured():
                raise
            logger.warning("ЮKassa не ответила — донат через Robokassa")
    inv = await kassa.new_inv_id()
    await add_donation(str(inv), "robokassa", uid, amount, claim)
    return kassa.robokassa_url(inv, amount, DONATE_TITLE, return_url)


def donate_thanks(amount: int) -> str:
    return (f"💛 Спасибо за поддержку! {amount} ₽ дошли до Капибары — на сервер, ИИ и новые функции.\n\n"
            "Это не подписка: ничего не спишется — просто твоё спасибо. В ответ тебе открыт роадмап — "
            "что я делаю сейчас и что дальше: /roadmap. Мне правда приятно. — Никита")


async def donation_paid(pid: str, bot=None) -> bool:
    """Донат оплачен: отметить (один раз), поблагодарить человека, коротко
    сказать Никите. Подписку не трогает."""
    from database.billing import donation_totals, get_donation, mark_donation_paid
    pay = await get_donation(pid)
    if not pay or not await mark_donation_paid(pid):
        return False
    uid, amount = pay["payer_id"], pay["amount"]
    logger.info(f"поддержка проекта: {pid} — {amount} ₽")
    if bot is not None:
        if uid:
            await billing.notify(bot, uid, donate_thanks(amount))
        if config.STAROSTA_ID and uid != config.STAROSTA_ID:
            n, total = await donation_totals()
            await billing.notify(bot, config.STAROSTA_ID,
                         f"💛 Поддержка проекта: {amount} ₽ от {await _who(uid)}. Всего: {n} · {total} ₽.")
    return True


def who_text(u: dict) -> str:
    from kapibara.core.utils import esc
    name = esc(u.get("full_name") or "")
    nick = f"@{esc(u['username'])}" if u.get("username") else ""
    parts = [p for p in (name, nick) if p]
    return " ".join(parts + [f"(<code>{u['user_id']}</code>)"])


async def _who(uid: int | None) -> str:
    from database import get_user
    u = await get_user(uid) if uid else None
    return who_text(u) if u else "кого-то без аккаунта"


async def donate_status_line() -> str:
    """Строка для /status: сколько донатов и на какую сумму."""
    from database.billing import donation_totals
    n, total = await donation_totals()
    if not n:
        return "Поддержка проекта (/donate): донатов пока нет"
    m, month = await donation_totals(30)
    return f"Поддержка проекта (/donate): {n} · {total} ₽, за 30 дней — {m} · {month} ₽"
