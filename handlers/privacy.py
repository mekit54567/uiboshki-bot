"""152-ФЗ в боте (privacy.py): согласие на обработку персональных данных
кнопкой «Даю согласие», /privacy — ссылки на тексты, /deleteme — удалить
все свои данные с подтверждением.

Согласие спрашивает ConsentMiddleware (middleware.py): новый человек до
«Даю согласие» получает только это сообщение (и /privacy, /deleteme); после
кнопки — обычное приветствие /start. Кто был до согласий — один раз
(privacy.ask_once)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()


def site() -> str:
    """Где лежат /consent и /privacy — тот же сервер, что у приложения."""
    from urllib.parse import urlsplit
    from config import WEBAPP_URL
    if WEBAPP_URL:
        u = urlsplit(WEBAPP_URL)
        return f"{u.scheme}://{u.netloc}"
    return "https://www.uiboshki.ru"


def links() -> tuple[str, str]:
    base = site()
    return (f'<a href="{base}/consent">согласие на обработку персональных данных</a>',
            f'<a href="{base}/privacy">Политике обработки персональных данных</a>')


def consent_text(new: bool = False, first_name: str = "") -> str:
    consent, policy = links()
    from utils import esc
    hello = (f"👋 Привет, <b>{esc(first_name or 'друг')}</b>! Я Капибара — расписание, дедлайны, "
             "баллы и файлы группы. Сначала одно дело.\n\n") if new else ""
    return (hello + "🔒 <b>Твои данные</b>\n\n"
            "Чтобы присылать расписание и напоминания, боту нужно хранить твой id в Telegram, "
            "группу и настройки.\n\n"
            f"Нажимая «Даю согласие», ты даёшь {consent}.\n"
            f"Подробнее — в {policy}.")


CONSENT_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Даю согласие", callback_data="consent:pd")]])
# пришёл по ссылке из приложения в App Store (/start ios) — приветствие потом без строк об оплате
CONSENT_KB_IOS = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Даю согласие", callback_data="consent:pd:ios")]])


async def ask_consent(bot, chat_id: int, new: bool = False, first_name: str = "", store: bool = False):
    await bot.send_message(chat_id, consent_text(new, first_name), parse_mode="HTML",
                           reply_markup=CONSENT_KB_IOS if store else CONSENT_KB, disable_web_page_preview=True)


@router.callback_query(F.data.in_({"consent:pd", "consent:pd:ios"}))
async def consent_given(callback: CallbackQuery, state: FSMContext | None = None):
    import privacy
    user = callback.from_user
    first = await privacy.blocked(user.id)          # новый — дальше приветствие, как у /start
    await privacy.give(user.id, "pd", "bot")
    consent, policy = links()
    try:
        await callback.message.edit_text(
            f"✅ Спасибо! Ты дал {consent}.\nПодробнее — в {policy}. "
            "Удалить всё о себе — /deleteme.",
            parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        pass
    await callback.answer("Готово")
    if first:
        from handlers.start import welcome
        await welcome(callback.message, user, state, store=callback.data.endswith(":ios"))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    import privacy
    consent, policy = links()
    given = not await privacy.needs(message.from_user.id)
    text = ("🔒 <b>Твои данные</b>\n\n"
            f"Как бот хранит и защищает данные — в {policy}.\n"
            + (f"Ты уже дал {consent}.\n\n" if given else
               f"Ты ещё не дал {consent}.\n\n")
            + "/deleteme — удалить всё о себе.")
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True,
                         reply_markup=None if given else CONSENT_KB)


DELETE_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🗑 Да, удалить всё", callback_data="erase:yes")],
    [InlineKeyboardButton(text="Отмена", callback_data="erase:no")]])


@router.message(Command("deleteme"))
async def cmd_deleteme(message: Message):
    _, policy = links()
    await message.answer(
        "🗑 <b>Удалить все твои данные?</b>\n\n"
        "Сотру профиль, группу, настройки, вход в СДО, историю баллов и посещений, личные "
        "дедлайны, напоминания, устройства и входы через VK и Яндекс, согласия. "
        "Общее для группы (дедлайны старосты, файлы, ДЗ) останется, но без твоего имени.\n\n"
        "Отменить нельзя. Если потом напишешь боту — начнём с нуля.\n"
        f"Подробнее — в {policy}.",
        parse_mode="HTML", reply_markup=DELETE_KB, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("erase:"))
async def erase_decision(callback: CallbackQuery):
    if callback.data != "erase:yes":
        await callback.message.edit_text("Ничего не удалял.")
        await callback.answer()
        return
    import privacy
    await privacy.erase(callback.from_user.id)
    await callback.message.edit_text(
        "✅ Готово: всё о тебе удалено. Из ночных копий базы оно уйдёт при ежемесячной чистке копий.\n\n"
        "Сообщения в этом чате можешь удалить сам. Если напишешь снова — начнём с нуля.")
    await callback.answer("Удалено")
