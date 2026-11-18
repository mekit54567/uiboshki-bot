"""Вход в приложение без Telegram через бота (webapp/routes/auth.py):
«/start login_<код>» → «Войти на <устройство>? Да, это я» → число с экрана
устройства из трёх (как у Google). Новому человеку перед этим — канал
(login_channel.py, кнопки «chan:…» — в handlers/start.py)."""

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from kapibara.core.utils import esc
from kapibara.bot.tg import data_of, msg

router = Router()


async def ask_login(message: Message, code: str):
    """«Войти в приложение на Chrome · Android?» — подтверждение входа по коду."""
    from database.sessions import get_login
    login = await get_login(code)
    if not login or login["status"] != "wait":
        await message.answer("Ссылка для входа устарела — нажми «Войти через Telegram» в приложении ещё раз.")
        return
    from kapibara.features.identity import login_channel
    if await login_channel.needed(message.bot, message.chat.id):     # новый — сначала канал
        store = login_channel.store_app(login["device"])
        await message.answer(login_channel.text(store), reply_markup=login_channel.keyboard(f"login:{code}", store))
        return
    text, kb = login_prompt(code, login)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


def login_prompt(code: str, login: dict) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, это я", callback_data=f"login:ok:{code}"),
        InlineKeyboardButton(text="Нет", callback_data=f"login:no:{code}"),
    ]])
    return (f"🔐 Войти в приложение Капибары на устройстве <b>{esc(login['device'] or 'браузер')}</b>?\n\n"
            "Если это не ты нажал «Войти» — жми «Нет». Дальше попрошу нажать число с экрана устройства."), kb


@router.callback_query(F.data.startswith("login:"))
async def login_decision(callback: CallbackQuery):
    """«Да, это я» → три числа (как у Google): нажать то, что на экране
    устройства; другое число — вход отклонён. Иначе вход по чужой ссылке
    подтверждался одним нажатием (ревью безопасности 09.10)."""
    from database.sessions import decide_login, get_login, pick_options
    _, verdict, rest = data_of(callback).split(":", 2)
    if verdict == "ok":                       # шаг 1 → выбрать число
        login = await get_login(rest)
        await callback.answer()
        if not login or login["status"] != "wait":
            await msg(callback).edit_text("Ссылка для входа устарела.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=str(n), callback_data=f"login:n:{n}:{rest}")
             for n in pick_options(login["pick"] or 0)],
            [InlineKeyboardButton(text="Это не я", callback_data=f"login:no:{rest}")],
        ])
        await msg(callback).edit_text("🔢 Какое число на экране устройства? Нажми его.", reply_markup=kb)
        return
    if verdict == "n":                        # шаг 2 — выбранное число
        num, code = rest.split(":", 1)
        login = await get_login(code)
        right = bool(login and str(login.get("pick")) == num)
        ok = await decide_login(code, callback.from_user.id, right)
        await callback.answer()
        text = ("✅ Готово — возвращайся в приложение." if right else
                "Число не то — вход отклонён. Если это был ты, начни вход заново.") if ok \
            else "Ссылка для входа устарела."
    else:                                     # «Нет» / «Это не я»
        ok = await decide_login(rest, callback.from_user.id, False)
        await callback.answer()
        text = "Вход отклонён." if ok else "Ссылка для входа устарела."
    try:
        await msg(callback).edit_text(text)
    except TelegramAPIError:             # сообщение старое или то же — шлём новым
        await msg(callback).answer(text)
