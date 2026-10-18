"""«Капибара+» в боте: /plus — статус и кнопка «Оплатить на сайте» (счёт в
Telegram не выставляем: цифровое внутри бота — только Stars), /invite —
готовое сообщение для друга с личной ссылкой, /grant — ручные выдачи
Никиты (plus_grant.py). В инлайне «@бот share» —
то же сообщение в любой чат (handlers/inline.py)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()


async def plus_text(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    import billing
    import config
    import referrals
    st = await billing.status(uid)
    inv = await referrals.summary(uid)
    if st["unlimited"]:
        head = ("✨ <b>У тебя безлимит</b> «Капибары+» "
                + (f"до {billing.fmt_day(st['unlimited_until'])}" if st["unlimited_until"] else "навсегда")
                + ": ИИ без дневных лимитов. Платить ничего не нужно.")
    elif st["paid_until"]:
        head = f"✨ <b>Капибара+</b> до {billing.fmt_day(st['until'])}."
    elif st["gift"]:
        head = (f"✨ <b>Капибара+</b> — подарок твоей группе до {billing.fmt_day(st['gift'])}. "
                "Платить ничего не нужно.")
    else:
        head = "✨ <b>Капибара+</b> — подписка на Капибару. Сейчас её нет."
    if st["founder"]:
        head += "\nТы «Основатель»: цена первых пользователей остаётся за тобой навсегда."
    prices = " · ".join(f"{p['title'].lower()} {p['price']} ₽" for p in st["prices"])
    price_line = (f"Цены первых пользователей: {prices}. Кто оплатит по ним, так и платит всегда."
                  if st["prices"][0]["founder"] else f"Цены: {prices}.")
    lines = [head, ""]
    if not st["unlimited"]:      # безлимиту цены и оплата ни к чему (робот 18.10)
        lines += [f"Что даёт: ИИ — до {config.AI_SUB_DAILY} вопросов в день для любой группы, "
                  "иконки и наряды капибары «по подписке», значок «друг Капибары».",
                  price_line + " Без автосписаний, июль и август не считаются.",
                  "Оплата — на сайте uiboshki.ru по кнопке ниже (или «Ещё → Капибара+» в приложении: "
                  "здесь, на Android и на uiboshki.ru/app). Подписка работает везде, и на iPhone.", ""]
    lines += [f"🎁 Позови друга: когда он попользуется {inv['friend_days']} дня, вам обоим "
              f"+{inv['bonus_days']} дней. Пришло по твоей ссылке: {inv['came']}, засчитано: {inv['rewarded']}.",
              "🏅 Закрыл ранг ачивок в приложении — тоже дни подписки (Ещё → Ачивки)."]
    rows = []
    if st["provider"] and not st["unlimited"]:
        rows.append([InlineKeyboardButton(text="💳 Оплатить на сайте", url=billing.pay_link(uid))])
    elif not st["unlimited"]:
        lines.append("\nОплата скоро заработает.")
    rows.append([InlineKeyboardButton(text="🎁 Позвать друга", callback_data="plus:invite")])
    if config.is_starosta(uid):
        lines.append("\n" + await admin_text())
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def admin_text() -> str:
    import billing
    gift = await billing.gift_until()
    stage = ("цена первых (месяц 149 ₽) — <code>/plus stage full</code> переключит новых на полную"
             if await billing.early() else
             "новым — полная цена; <code>/plus stage early</code> вернёт цену первых")
    gift_line = (f"подарок своей группе до {billing.fmt_day(gift)} — <code>/plus gift 15.01.2027</code> "
                 f"или <code>/plus gift off</code>" if gift else
                 "подарка своей группе нет — <code>/plus gift 31.12.2026</code>")
    return (f"<b>Для старосты:</b>\n• {stage}\n• {gift_line}\n"
            "• <code>/grant @ник 3m</code> — продлить вручную, <code>/grant @ник unlimited</code> — безлимит, "
            "<code>/grant</code> — подробнее")


async def admin_cmd(uid: int, args: list[str]) -> str | None:
    """/plus stage full|early, /plus gift ДД.ММ.ГГГГ|off — только староста.
    None — это не команда старосты."""
    import config
    from datetime import datetime

    from database import set_setting
    if not args or args[0] not in ("stage", "gift") or not config.is_starosta(uid):
        return None
    val = args[1].lower() if len(args) > 1 else ""
    if args[0] == "stage":
        if val not in ("full", "early"):
            return "Так: <code>/plus stage full</code> или <code>/plus stage early</code>."
        await set_setting("plus:stage", val)
    else:
        if val != "off":
            try:
                val = datetime.strptime(val, "%d.%m.%Y").date().isoformat()
            except ValueError:
                return "Так: <code>/plus gift 31.12.2026</code> или <code>/plus gift off</code>."
        await set_setting("plus:gift", val)
    return "Готово.\n" + await admin_text()


@router.message(Command("plus"))
async def cmd_plus(message: Message):
    args = (message.text or "").split()[1:]
    done = await admin_cmd(message.from_user.id, args)
    if done is not None:
        await message.answer(done, parse_mode="HTML")
        return
    text, kb = await plus_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@router.message(Command("grant"))
async def cmd_grant(message: Message):
    """/grant — ручные выдачи «Капибары+» и безлимита (plus_grant.py). Только
    Никита (config.is_starosta), старостам групп и замам — нет."""
    import config
    import plus_grant
    if not config.is_starosta(message.from_user.id):
        await message.answer("Эта команда только для владельца бота.")
        return
    args = (message.text or "").split()[1:]
    await message.answer(await plus_grant.command(message.bot, message.from_user.id, args), parse_mode="HTML")


# ── Рассылка о запуске «Капибары+» (только по кнопке старосты) ─────────────

async def launch_text(uid: int) -> str:
    """Сообщение всем при запуске: своей группе — про подарок, остальным —
    что бесплатное остаётся бесплатным. Где платить — сайт; на iPhone внутри
    приложения об оплате ни слова (App Store 3.1.1), поэтому говорим здесь."""
    import billing
    import referrals
    st = await billing.status(uid)
    inv = await referrals.summary(uid)
    m = next(p for p in st["prices"] if p["plan"] == "month")
    lines = ["✨ <b>Появилась «Капибара+»</b> — подписка на Капибару.", ""]
    if st["gift"]:
        lines += [f"Твоей группе — в подарок до {billing.fmt_day(st['gift'])}: всё уже включено, "
                  "платить ничего не нужно.", ""]
    else:
        lines += ["Расписание, дедлайны, баллы СДО, файлы и напоминания остаются бесплатными.", ""]
    import config
    lines += [f"Что даёт: ИИ — до {config.AI_SUB_DAILY} вопросов в день для любой группы, иконки и наряды "
              "капибары «по подписке», значок «друг Капибары».",
              (f"Цена первых пользователей — {m['price']} ₽ в месяц, и кто оплатит по ней, так и платит "
               "всегда." if m["founder"] else f"Месяц — {m['price']} ₽."),
              "Оплата — на сайте uiboshki.ru: /plus здесь или «Ещё → Капибара+» в приложении. "
              "Подписка работает везде, и на iPhone." if st["provider"] else
              "Оплата заработает совсем скоро — на сайте uiboshki.ru, напишу.", "",
              f"🎁 Позови друга — /invite: когда он попользуется {inv['friend_days']} дня, "
              f"вам обоим +{inv['bonus_days']} дней."]
    return "\n".join(lines)


def _launch_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✨ Подробнее", callback_data="plus:show"),
        InlineKeyboardButton(text="🎁 Позвать друга", callback_data="plus:invite")]])


@router.message(Command("plusnews"))
async def cmd_plusnews(message: Message):
    """Староста: показать рассылку о запуске (как её увидит он сам) и кнопку «Разослать»."""
    import config
    from database import get_setting
    if not config.is_starosta(message.from_user.id):
        return
    done = await get_setting("plus:announced")
    await message.answer(await launch_text(message.from_user.id), parse_mode="HTML", reply_markup=_launch_kb())
    await message.answer(
        "👆 Так увидят все: своей группе — с подарком, остальным — без. "
        + (f"Уже рассылал {done}. " if done else "") + "Разослать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Разослать всем", callback_data="plus:news:go")]]))


@router.callback_query(F.data == "plus:news:go")
async def plusnews_go(callback: CallbackQuery):
    import config
    import delivery
    import scheduler
    from database import get_all_subscribed_users, set_setting
    from datetime import datetime

    from utils import TZ
    if not config.is_starosta(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer("Рассылаю…")
    await callback.message.edit_reply_markup(reply_markup=None)
    await set_setting("plus:announced", datetime.now(TZ).strftime("%d.%m %H:%M"))
    sent = failed = 0
    for uid in await get_all_subscribed_users():
        try:
            await delivery.deliver(callback.bot, uid, await launch_text(uid), kind="plus", tab="more",
                                   reply_markup=_launch_kb())
            sent += 1
        except Exception:
            failed += 1
        await scheduler.pace()
    await callback.message.answer(f"✅ Разослал: {sent}, не дошло: {failed}.")


@router.callback_query(F.data == "plus:show")
async def plus_show(callback: CallbackQuery):
    await callback.answer()
    text, kb = await plus_text(callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


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
