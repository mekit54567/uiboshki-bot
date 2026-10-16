"""«Капибара+» в боте: /plus — статус и кнопка «Оплатить на сайте» (счёт в
Telegram не выставляем: цифровое внутри бота — только Stars), /invite —
готовое сообщение для друга с личной ссылкой. В инлайне «@бот share» —
то же сообщение в любой чат (handlers/inline.py)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()


async def plus_text(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    import billing
    import referrals
    st = await billing.status(uid)
    inv = await referrals.summary(uid)
    if st["active"]:
        head = f"✨ <b>Капибара+</b> до {billing.fmt_day(st['until'])}."
    else:
        head = "✨ <b>Капибара+</b> — подписка на Капибару. Сейчас её нет."
    if st["founder"]:
        head += "\nТы «Основатель»: месяц для тебя — 149 ₽, пока продлеваешь без долгих перерывов."
    prices = " · ".join(f"{p['title'].lower()} {p['price']} ₽" for p in st["prices"])
    lines = [head, "",
             "Что даёт: ИИ сверх пробы для любой группы (твоей группе он и так бесплатный), "
             "иконки и наряды капибары «по подписке», значок «друг Капибары».",
             f"Цены: {prices}. Без автосписаний, июль и август не считаются.", "",
             f"🎁 Позови друга: когда он попользуется {inv['friend_days']} дня, вам обоим "
             f"+{inv['bonus_days']} дней. Пришло по твоей ссылке: {inv['came']}, засчитано: {inv['rewarded']}.",
             "🏅 Закрыл ранг ачивок в приложении — тоже дни подписки (Ещё → Ачивки)."]
    rows = []
    if st["provider"]:
        rows.append([InlineKeyboardButton(text="💳 Оплатить на сайте", url=billing.pay_link(uid))])
    else:
        lines.append("\nОплата скоро заработает.")
    rows.append([InlineKeyboardButton(text="🎁 Позвать друга", callback_data="plus:invite")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("plus"))
async def cmd_plus(message: Message):
    text, kb = await plus_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


async def share_kb(uid: int) -> InlineKeyboardMarkup:
    import referrals
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=referrals.share_button(), url=await referrals.link(uid))]])


async def send_invite(message: Message, uid: int):
    """Готовое сообщение — переслать другу; и кнопка выбрать чат (инлайн)."""
    import referrals
    kb = await share_kb(uid)
    try:
        await message.answer_photo(referrals.share_image(), caption=referrals.share_text(), reply_markup=kb)
    except Exception:
        await message.answer(referrals.share_text(), reply_markup=kb)
    await message.answer(
        "👆 Перешли это сообщение другу или нажми кнопку ниже и выбери чат. Ссылка твоя: когда друг "
        "начнёт пользоваться, вам обоим подарим дни «Капибары+».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📤 Отправить в чат", switch_inline_query="share")]]))


@router.message(Command("invite"))
async def cmd_invite(message: Message):
    await send_invite(message, message.from_user.id)


@router.callback_query(F.data == "plus:invite")
async def invite_button(callback: CallbackQuery):
    await callback.answer()
    await send_invite(callback.message, callback.from_user.id)
