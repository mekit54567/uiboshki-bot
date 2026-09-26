from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import upsert_user, set_subscription, get_user
from config import GROUP_NAME, STAROSTA_ID, WEBAPP_URL, SCHEDULE_HOUR, SCHEDULE_MINUTE
from keyboards import MAIN_KB, ACTIONS_KB, webapp_keyboard
from utils import esc, split_by_lines

router = Router()


@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject):
    """Диплинк с параметром — сейчас единственный кейс: t.me/bot?start=file_<id>,
    им бьёт кнопка "Открыть в Telegram" у файла в WebApp (WebApp не может сама
    отдать файл по file_id — это может только сам бот). Всё остальное (просто
    /start без параметра) идёт в обычный cmd_start ниже."""
    user = message.from_user
    await upsert_user(user.id, user.username or "", user.full_name or "")
    payload = command.args or ""
    if payload.startswith("file_"):
        from database import get_files
        try:
            fid = int(payload.removeprefix("file_"))
        except ValueError:
            fid = None
        target = None
        if fid is not None:
            for f in await get_files():
                if f["id"] == fid:
                    target = f
                    break
        if target:
            await message.bot.send_document(
                user.id, target["file_id"],
                caption=f"📄 <b>{esc(target['title'])}</b>" + (f" ({esc(target['subject'])})" if target.get('subject') else ""),
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Файл не найден (возможно, его удалили).")
        return
    if payload.startswith("hw_"):
        # Кнопка «Открыть файл» у ДЗ в WebApp — файл может отдать только бот.
        from group_context import list_homework
        hw_id = payload.removeprefix("hw_")
        item = next((h for h in await list_homework(500) if str(h["id"]) == hw_id), None)
        if not item or not item.get("file_id"):
            await message.answer("❌ Файл ДЗ не найден (возможно, его удалили).")
            return
        caption = f"📝 <b>{esc(item['subject'])}</b>" + (f"\n{esc(item['content'][:900])}" if item.get("content") else "")
        if item.get("file_type") == "photo":
            await message.bot.send_photo(user.id, item["file_id"], caption=caption, parse_mode="HTML")
        else:
            await message.bot.send_document(user.id, item["file_id"], caption=caption, parse_mode="HTML")
        return
    await cmd_start(message)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await upsert_user(user.id, user.username or "", user.full_name or "")
    await message.answer(
        f"👋 Привет, <b>{esc(user.first_name)}</b>! Я бот группы <b>{GROUP_NAME}</b> 🎓\n\n"
        "📅 <b>Расписание</b> — сегодня, неделя, следующая пара, напоминания\n"
        "📋 <b>Дедлайны и ДЗ</b> — общие группы и свои\n"
        "🤖 <b>Решалка</b> — текст или фото задачи, по лекциям предмета\n"
        "📁 <b>Файлы</b> — лекции и методички группы\n"
        "🔍 <b>Любое расписание МИРЭА</b> — препод, группа, аудитория\n\n"
        "💡 Пиши и своими словами: «когда следующая пара», «что сдавать на неделе» "
        "или просто условие задачи.\n"
        "Все команды — /help",
        parse_mode="HTML",
        reply_markup=MAIN_KB
    )
    kb = webapp_keyboard()
    if kb:
        await message.answer(
            "🚀 Всё то же — в приложении: главная с ближайшей парой, дедлайны, поиск и чат с ИИ "
            "(можно кидать фото и файлы). Ещё оно всегда под кнопкой «Приложение» слева от поля ввода.",
            reply_markup=kb,
        )


@router.message(Command("app"))
async def cmd_app(message: Message):
    kb = webapp_keyboard()
    if not kb:
        await message.answer("🚧 Приложение скоро появится — его ещё не включили.")
        return
    await message.answer(
        "🚀 Расписание, дедлайны, ДЗ, файлы и чат с ИИ — в одном окне.",
        reply_markup=kb,
    )


@router.message(F.text == "⋯ Действия")
async def cmd_actions(message: Message):
    await message.answer("Выбери действие:", reply_markup=ACTIONS_KB)


# Кнопка «Действия» не может сама «нажать» команду за пользователя — раньше
# бот просто присылал голое "/add". Теперь — понятная подсказка, в которой
# команда кликабельна: одно касание, и понятно, что будет дальше.
ACTION_HINTS = {
    "add_deadline":   "➕ Свой дедлайн — нажми /add\n(видишь только ты; общие добавляет староста)",
    "upload":         "📤 Загрузить лекции и методички пачкой — нажми /upload\n"
                      "Выберешь предмет и пересылай файлы — ИИ их прочитает.",
    "lookup":         "🔍 Чужое расписание по всему МИРЭА:\n"
                      "/teacher Фамилия — преподаватель\n/group УИБО-02-24 — группа\n/room А-18 — аудитория",
    "solve_lectures": "📖 Решить строго по лекциям предмета — нажми /solve_lectures\n"
                      "(обычная /solve тоже опирается на лекции, если они загружены)",
    "history":        "📜 Прошлые решения — /history",
    "feed":           "🗣 Анонимный пост в «Подслушано» — нажми /feed",
    "anon":           "❓ Анонимный вопрос старосте — нажми /anon",
    "add_hw":         "📝 Добавить ДЗ на доску (староста и зам) — /addhw",
    "solve_ds":       "🐋 Решить через DeepSeek — нажми /solve_ds",
}


@router.callback_query(F.data.startswith("act:"))
async def handle_action(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    uid = callback.from_user.id
    await callback.answer()

    if action in ACTION_HINTS:
        await callback.bot.send_message(uid, ACTION_HINTS[action])

    elif action == "nextweek":
        from schedule_parser import get_next_week_schedule
        wait = await callback.bot.send_message(uid, "⏳ Загружаю следующую неделю...")
        text = await get_next_week_schedule()
        await callback.bot.delete_message(uid, wait.message_id)
        for chunk in split_by_lines(text):
            await callback.bot.send_message(uid, chunk, parse_mode="HTML")

    elif action == "vote":
        await callback.bot.send_message(
            uid,
            "🗳 <b>Голосование</b>\n\n"
            "Создать: /vote Твой вопрос\n"
            "Например: <code>/vote Идём на пары в пятницу?</code>\n\n"
            "Посмотреть текущее: /vote",
            parse_mode="HTML"
        )

    elif action == "settings":
        await upsert_user(uid, callback.from_user.username or "", callback.from_user.full_name or "")
        text, kb = _settings_view(await get_user(uid))
        await callback.bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)

    elif action == "subscribe":  # старая кнопка в уже отправленных сообщениях
        await upsert_user(uid, callback.from_user.username or "", callback.from_user.full_name or "")
        user = await get_user(uid)
        is_sub = user and user.get("subscribed")
        await set_subscription(uid, 0 if is_sub else 1)
        await callback.bot.send_message(uid, "🔕 Отписался от уведомлений." if is_sub else "✅ Подписан на уведомления!")


HELP_TEXT = (
    "📖 <b>Что умеет бот</b>\n\n"
    "📅 <b>Расписание</b>\n"
    "/schedule · /tomorrow — сегодня и завтра\n"
    "/week · /nextweek — эта и следующая неделя\n"
    "/next — следующая пара\n"
    "/teacher Фамилия · /group УИБО-03-24 · /room А-18 — чужое расписание\n"
    "/note — заметка к паре · /calendar — расписание в свой календарь\n\n"
    "📋 <b>Дедлайны и ДЗ</b>\n"
    "/deadlines — список · /add — добавить свой\n"
    "/done ID — выполнено · /undone ID — вернуть · /del ID — удалить\n"
    "/hw — доска домашних заданий\n\n"
    "🤖 <b>Решалка</b>\n"
    "/solve — задача текстом или фото\n"
    "/solve_lectures — по загруженным лекциям предмета\n"
    "/solve_ds — через DeepSeek · /history — прошлые решения\n\n"
    "📁 <b>Файлы</b>\n"
    "/files — лекции и методички · /search запрос — поиск\n"
    "/upload — загрузить файлы, можно пачкой · /delfile ID — удалить свой\n\n"
    "💬 <b>Группа</b>\n"
    "/feed — анонимный пост в «Подслушано»\n"
    "/anon — анонимный вопрос старосте\n"
    "/vote Вопрос — голосование · /closevote — закрыть своё\n"
    "/rating — рейтинг\n\n"
    "⚙️ <b>Настройки</b>\n"
    "/settings — уведомления · /setreminder N — напомнить за N мин\n"
    "/subscribe · /unsubscribe — утренняя рассылка\n"
    "/weather — погода · /app — приложение\n\n"
    "💡 Можно писать и своими словами: «когда следующая пара», "
    "«какие дедлайны на неделе» или просто условие задачи."
)

STAROSTA_HELP = (
    "\n\n👑 <b>Для старосты</b>\n"
    "/announce — рассылка · /addhw — добавить ДЗ\n"
    "/setzam ID — назначить зама\n"
    "/syncfiles — загрузить файлы\n"
    "/importdeadlines · /syncsdo — дедлайны из СДО\n"
    "/delpost ID — удалить пост из ленты\n"
    "/clearsem — сбросить всё под новый семестр"
)


@router.message(Command("help"))
async def cmd_help(message: Message):
    # Команды старосты видит только староста (и зам): остальным они только
    # мешали — и всё равно отвечали бы «только для старосты».
    from handlers.announce import is_editor
    text = HELP_TEXT
    if await is_editor(message.from_user.id):
        text += STAROSTA_HELP
    await message.answer(text, parse_mode="HTML")


@router.message(Command("subscribe"))
@router.message(F.text == "🔔 Подписка")
async def cmd_subscribe(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await set_subscription(message.from_user.id, 1)
    await message.answer(f"✅ Подписан! Расписание каждое утро в {SCHEDULE_HOUR}:{SCHEDULE_MINUTE:02d} 🌅")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    await set_subscription(message.from_user.id, 0)
    await message.answer("🔕 Отписался. Вернуться — /subscribe")


@router.message(Command("setreminder"))
async def cmd_setreminder(message: Message):
    from database import set_reminder_minutes
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /setreminder 15")
        return
    mins = int(parts[1])
    if mins < 1 or mins > 60:
        await message.answer("❌ Введи число от 1 до 60")
        return
    await set_reminder_minutes(message.from_user.id, mins)
    await message.answer(f"✅ Буду напоминать за <b>{mins} минут</b> до пары!", parse_mode="HTML")


REMINDER_CHOICES = (5, 10, 15, 30)


def _settings_view(user: dict | None) -> tuple[str, InlineKeyboardMarkup]:
    """Настройки — кнопками, а не «напиши /setreminder 15»: одно касание."""
    mins = (user or {}).get("reminder_minutes", 15) or 15
    sub = bool((user or {}).get("subscribed"))
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"🔔 Утренняя рассылка и напоминания: <b>{'включены' if sub else 'выключены'}</b>\n"
        f"⏰ Напоминать о паре за <b>{mins} мин</b>\n\n"
        f"Рассылка приходит каждое утро в {SCHEDULE_HOUR}:{SCHEDULE_MINUTE:02d}: расписание и погода."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔕 Выключить уведомления" if sub else "🔔 Включить уведомления",
                              callback_data="set:sub")],
        [InlineKeyboardButton(text=("✓ " if m == mins else "") + f"за {m} мин", callback_data=f"set:rem:{m}")
         for m in REMINDER_CHOICES],
    ])
    return text, kb


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    text, kb = _settings_view(await get_user(message.from_user.id))
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("set:"))
async def settings_change(callback: CallbackQuery):
    from database import set_reminder_minutes
    uid = callback.from_user.id
    await upsert_user(uid, callback.from_user.username or "", callback.from_user.full_name or "")
    parts = callback.data.split(":")
    if parts[1] == "sub":
        user = await get_user(uid)
        await set_subscription(uid, 0 if (user and user.get("subscribed")) else 1)
    elif parts[1] == "rem" and len(parts) == 3 and parts[2].isdigit() and int(parts[2]) in REMINDER_CHOICES:
        await set_reminder_minutes(uid, int(parts[2]))
    text, kb = _settings_view(await get_user(uid))
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass  # «message is not modified» — нажали уже выбранное
    await callback.answer("Сохранено ✓")


@router.message(F.text == "🏆 Рейтинг")
async def rating_button(message: Message):
    from handlers.announce import cmd_rating
    await cmd_rating(message)


@router.message(F.text == "📝 ДЗ")
async def hw_button(message: Message):
    from handlers.announce import cmd_hw
    await cmd_hw(message)
