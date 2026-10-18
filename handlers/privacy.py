"""152-ФЗ в боте (privacy.py): согласие на обработку персональных данных
кнопкой «Даю согласие», /privacy — ссылки на тексты, /deleteme — удалить
все свои данные: фразой privacy.ERASE_PHRASE, полностью — через 7 дней
(до этого староста может вернуть — /undelete). Кто ещё не дал согласия —
кнопкой и сразу.

Согласие спрашивает ConsentMiddleware (middleware.py): новый человек до
«Даю согласие» получает только это сообщение (и /privacy, /deleteme); после
кнопки — обычное приветствие /start. Кто был до согласий — один раз
(privacy.ask_once)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
    try:
        await privacy.give(user.id, "pd", "bot")
    except privacy.Erasing as e:
        await callback.answer(str(e)[:200], show_alert=True)
        return
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


class EraseFlow(StatesGroup):
    phrase = State()


@router.message(Command("deleteme"))
async def cmd_deleteme(message: Message, state: FSMContext):
    import privacy
    _, policy = links()
    uid = message.from_user.id
    due = await privacy.erasing(uid)
    if due:
        await message.answer("🗑 " + privacy.erasing_text(due))
        return
    if await privacy.blocked(uid):      # согласия ещё не давал — хранить нечего, кнопкой и сразу
        await message.answer(
            "🗑 <b>Удалить все твои данные?</b>\n\nСогласия ты ещё не давал — сотру то немногое, что "
            f"есть: id и отметки о входе. Подробнее — в {policy}.",
            parse_mode="HTML", reply_markup=DELETE_KB, disable_web_page_preview=True)
        return
    await state.set_state(EraseFlow.phrase)
    await message.answer(
        "🗑 <b>Удалить все твои данные?</b>\n\n"
        "Сотру профиль, группу, настройки, вход в СДО, историю баллов и посещений, личные "
        "дедлайны, напоминания, устройства и входы через VK, Яндекс и Apple, согласия. "
        "Общее для группы (дедлайны старосты, файлы, ДЗ) останется, но без твоего имени.\n\n"
        f"Сразу — выход со всех устройств и из СДО, рассылки и ИИ остановятся. Полностью — через "
        f"{privacy.ERASE_DAYS} дней: если удалил по ошибке, до этого можно попросить вернуть "
        f"({privacy.CONTACT}), без гарантии.\n\n"
        f"Чтобы удалить, отправь фразой: <code>{privacy.ERASE_PHRASE}</code>\n"
        f"Передумал — /cancel. Подробнее — в {policy}.",
        parse_mode="HTML", disable_web_page_preview=True)


@router.message(EraseFlow.phrase)
async def erase_phrase(message: Message, state: FSMContext):
    import privacy
    await state.clear()
    if not privacy.phrase_ok(message.text or ""):
        await message.answer("Фраза не совпала — ничего не удаляю. Начать заново — /deleteme.")
        return
    due = await privacy.request_erase(message.from_user.id, message.bot)
    await message.answer(
        f"✅ Готово: вход на всех устройствах и в СДО удалён, рассылки остановлены. Полностью "
        f"всё сотру {privacy.fmt_day(due)}, из ночных копий базы — "
        f"{privacy.backup_texts()['BACKUP_ERASE']}.\n\n"
        f"Удалил по ошибке — напиши {privacy.CONTACT} до {privacy.fmt_day(due)}: вернём вручную, "
        "если получится, без гарантии.")


@router.message(Command("undelete"))
async def cmd_undelete(message: Message):
    """Вернуть данные по заявке (староста): /undelete <id>, до полного стирания."""
    from config import is_starosta
    import privacy
    if not is_starosta(message.from_user.id):
        return
    args = (message.text or "").split()[1:]
    if not args or not args[0].isdigit():
        await message.answer("Кого вернуть: /undelete <id> — id из сообщения об удалении.")
        return
    uid = int(args[0])
    due = await privacy.erasing(uid)
    if not due or not await privacy.undo_erase(uid):
        await message.answer("Этого человека нет среди удаляющих: уже стёрт или не просил.")
        return
    await message.answer(
        f"✅ Вернул <code>{uid}</code>: профиль и данные на месте. Входы на устройствах и в СДО были "
        "удалены сразу — войдёт заново; согласие бот спросит снова.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "↩️ Твои данные вернули. Войди в приложение и СДО заново "
                                            "и дай согласие на обработку данных — бот спросит.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("erase:"))
async def erase_decision(callback: CallbackQuery):
    if callback.data != "erase:yes":
        await callback.message.edit_text("Ничего не удалял.")
        await callback.answer()
        return
    import privacy
    if not await privacy.blocked(callback.from_user.id) or await privacy.erasing(callback.from_user.id):
        await callback.message.edit_text("Удаление — через /deleteme, фразой.")   # старая кнопка
        await callback.answer()
        return
    await privacy.erase(callback.from_user.id)
    await callback.message.edit_text(
        "✅ Готово: всё о тебе удалено. Сообщения в этом чате можешь удалить сам. "
        "Если напишешь снова — начнём с нуля.")
    await callback.answer("Удалено")
