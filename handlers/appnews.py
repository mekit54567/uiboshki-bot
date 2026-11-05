"""Рассылка «у Капибары теперь своё приложение» (/appnews, Никита 05.11):
старосте — превью ровно как увидят все и кнопка «Разослать». Один раз:
повторное нажатие (или второй /appnews после рассылки) ничего не шлёт."""

from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from kapibara.core import config
from kapibara.core.errors import NETWORK

router = Router()

# Ссылка по id приложения — на случай, если APPSTORE_URL на сервере ещё не задан
APPSTORE_FALLBACK = "https://apps.apple.com/app/id6828117584"
DONE_KEY = "appnews:sent"

TEXT = (
    "📱 <b>У Капибары теперь есть своё приложение</b>\n\n"
    "Не сайт в обёртке, а настоящее приложение для iPhone и Android. "
    "Открывается быстрее, листается плавнее, а в СДО входит обычной страницей МИРЭА — "
    "без копирования непонятных строчек.\n\n"
    "Входи через тот же Telegram: всё на месте — сроки, отметки, настройки.\n\n"
    "Бот никуда не уходит и остаётся рядом. Просто теперь Капибара живёт ещё и у тебя на экране 🦫"
)


def appstore_url() -> str:
    return config.APPSTORE_URL or APPSTORE_FALLBACK


def news_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🍏 App Store", url=appstore_url()),
        InlineKeyboardButton(text="🤖 RuStore", url=config.RUSTORE_URL)]])


@router.message(Command("appnews"))
async def cmd_appnews(message: Message):
    from database import get_setting
    if not message.from_user or not config.is_starosta(message.from_user.id):
        return
    done = await get_setting(DONE_KEY)
    await message.answer(TEXT, parse_mode="HTML", reply_markup=news_kb())
    if done:
        await message.answer(f"👆 Так выглядела рассылка. Уже разослал {done} — второй раз не шлю.")
        return
    await message.answer(
        "👆 Так увидят все, у кого включены уведомления. Разослать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Разослать всем", callback_data="appnews:go")]]))


@router.callback_query(F.data == "appnews:go")
async def appnews_go(callback: CallbackQuery):
    from database import get_all_subscribed_users, get_setting, set_setting
    from kapibara.core.locks import lock
    from kapibara.core.utils import TZ
    from kapibara.features.notifications import delivery
    from kapibara.features.notifications.broadcast import pace
    if not config.is_starosta(callback.from_user.id):
        await callback.answer()
        return
    async with lock("appnews"):          # двойное нажатие — одна рассылка
        if await get_setting(DONE_KEY):
            await callback.answer("Уже разослано", show_alert=True)
            return
        await set_setting(DONE_KEY, datetime.now(TZ).strftime("%d.%m %H:%M"))
    await callback.answer("Рассылаю…")
    msg = callback.message if isinstance(callback.message, Message) else None
    if msg:
        await msg.edit_reply_markup(reply_markup=None)
    sent = failed = 0
    for uid in await get_all_subscribed_users():
        try:
            await delivery.deliver(callback.bot, uid, TEXT, kind="news", tab="more", reply_markup=news_kb(),
                                   title="Капибара — своё приложение",
                                   body="Теперь в App Store и RuStore")
            sent += 1
        except (TelegramAPIError, *NETWORK):   # бот заблокирован, пуш не ушёл — считаем и дальше
            failed += 1
        await pace()
    if msg:
        await msg.answer(f"✅ Разослал: {sent}, не дошло: {failed}.")
