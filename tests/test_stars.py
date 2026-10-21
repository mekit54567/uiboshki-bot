"""Оплата «Капибары+» звёздами Telegram (billing.stars_…, handlers/plus.py):
цена дороже рублей на STARS_MARKUP, счёт XTR, проверка перед списанием,
продление один раз на платёж и номер списания для возврата."""
import pytest
from aiogram.types import Chat, Message, PreCheckoutQuery, SuccessfulPayment, Update, User

import billing
from tests.test_plus import ME, robokassa  # noqa: F401 — фикстура (реквизиты исполнителя)
from tests.test_review_bot import _uid, bot, dp, press  # noqa: F401 — фикстуры


def test_stars_price_is_rubles_plus_markup(monkeypatch):
    monkeypatch.setattr(billing, "STARS_RUB", 1.8)
    monkeypatch.setattr(billing, "STARS_MARKUP", 1.55)
    assert billing.stars_price(149) == 129          # 149 × 1,55 / 1,8 = 128,3 → вверх
    assert billing.stars_price(90) == 78            # 77,5 → 78
    monkeypatch.setattr(billing, "STARS_RUB", 0)
    assert not billing.stars_on()


async def _pre_checkout(dp, bot, payload, total, uid=ME):  # noqa: F811
    q = PreCheckoutQuery(id=str(_uid()), from_user=User(id=uid, is_bot=False, first_name="X"),
                         currency="XTR", total_amount=total, invoice_payload=payload)
    await dp.feed_update(bot, Update(update_id=_uid(), pre_checkout_query=q))
    return bot.session.named("AnswerPreCheckoutQuery")[-1]


async def _paid(dp, bot, payload, total, uid=ME, charge="ch-1"):  # noqa: F811
    sp = SuccessfulPayment(currency="XTR", total_amount=total, invoice_payload=payload,
                           telegram_payment_charge_id=charge, provider_payment_charge_id="")
    msg = Message(message_id=_uid() % 10**6, date=0, chat=Chat(id=uid, type="private"),
                  from_user=User(id=uid, is_bot=False, first_name="X"), successful_payment=sp)
    await dp.feed_update(bot, Update(update_id=_uid(), message=msg))


@pytest.mark.asyncio
async def test_stars_invoice_check_and_paid_once(db, bot, dp, robokassa):  # noqa: F811
    from database.billing import get_payment, get_sub
    await db.upsert_user(ME, "", "u")
    from handlers.plus import plus_text
    text, kb = await plus_text(ME)
    buttons = [b for row in kb.inline_keyboard for b in row if (b.callback_data or "").startswith("plus:stars:")]
    assert "звёздами Telegram" in text and [b.callback_data for b in buttons] == ["plus:stars:month",
                                                                                  "plus:stars:semester"]

    await press(dp, bot, "plus:stars:month", uid=ME)
    inv = bot.session.named("SendInvoice")[-1]
    stars = billing.stars_price(149)
    assert inv.currency == "XTR" and inv.prices[0].amount == stars and not inv.provider_token

    assert (await _pre_checkout(dp, bot, inv.payload, stars - 1)).ok is False     # подменили цену
    assert (await _pre_checkout(dp, bot, inv.payload, stars, uid=ME + 1)).ok is False   # чужой счёт
    assert (await _pre_checkout(dp, bot, inv.payload, stars)).ok is True

    await _paid(dp, bot, inv.payload, stars)
    await _paid(dp, bot, inv.payload, stars)                                       # повтор — не продлевает
    pay = await get_payment(inv.payload)
    assert pay["status"] == "succeeded" and pay["charge_id"] == "ch-1" and pay["stars"] == stars
    assert (await get_sub(ME))["founder"]                                          # по цене первых
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_PATH) as c:
        n = (await (await c.execute("SELECT COUNT(*) FROM plus_grants WHERE user_id=? AND source='pay'",
                                     (ME,))).fetchone())[0]
    assert n == 1
    assert (await _pre_checkout(dp, bot, inv.payload, stars)).ok is False         # оплаченный — второй раз нет


@pytest.mark.asyncio
async def test_no_stars_without_requisites(db, monkeypatch):
    import privacy
    monkeypatch.setattr(privacy, "INN", "")
    with pytest.raises(billing.PayError):
        await billing.stars_invoice(ME, "month")
