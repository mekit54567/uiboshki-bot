from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery

from database import upsert_user, set_subscription, get_user
from config import GROUP_NAME, STAROSTA_ID, WEBAPP_URL, SCHEDULE_HOUR, SCHEDULE_MINUTE
from keyboards import MAIN_KB, ACTIONS_KB, webapp_keyboard
from utils import esc

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
    await cmd_start(message)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await upsert_user(user.id, user.username or "", user.full_name or "")
    await message.answer(
        f"👋 Привет, <b>{esc(user.first_name)}</b>!\n\n"
        f"Я бот группы <b>{GROUP_NAME}</b> 🎓\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📅 Расписание — сегодня, завтра, неделя\n"
        "📋 Дедлайны — трекер группы\n"
        "🤖 Решалка — текст или фото задачи\n"
        "📁 Файлы — лекции и методички\n"
        "📝 ДЗ — доска домашних заданий\n"
        "🌤 Погода — прямо сейчас\n"
        "🗣 Подслушано — анонимная лента группы\n"
        "⋯ Действия — всё остальное\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Кстати, можно просто написать вопрос своими словами — "
        "например «когда следующая пара» или «какие дедлайны на неделе» — "
        "бот попробует понять и ответить без команд.",
        parse_mode="HTML",
        reply_markup=MAIN_KB
    )
    kb = webapp_keyboard()
    if kb:
        await message.answer("Или открой всё сразу в приложении 👇", reply_markup=kb)


@router.message(Command("app"))
async def cmd_app(message: Message):
    kb = webapp_keyboard()
    if not kb:
        await message.answer("🚧 Приложение ещё не развёрнуто (WEBAPP_URL не настроен).")
        return
    await message.answer(
        "🚀 Расписание, дедлайны, ДЗ, файлы и чат с ИИ — в одном окне.",
        reply_markup=kb,
    )


@router.message(F.text == "⋯ Действия")
async def cmd_actions(message: Message):
    await message.answer("Выбери действие:", reply_markup=ACTIONS_KB)


@router.callback_query(F.data.startswith("act:"))
async def handle_action(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    await callback.message.delete()

    if action == "add_deadline":
        await callback.bot.send_message(callback.from_user.id, "/add")

    elif action == "solve_ds":
        await callback.bot.send_message(callback.from_user.id, "/solve_ds")

    elif action == "solve_lectures":
        await callback.bot.send_message(callback.from_user.id, "/solve_lectures")

    elif action == "nextweek":
        from schedule_parser import get_next_week_schedule
        wait = await callback.bot.send_message(callback.from_user.id, "⏳ Загружаю следующую неделю...")
        text = await get_next_week_schedule()
        await callback.bot.delete_message(callback.from_user.id, wait.message_id)
        for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            await callback.bot.send_message(callback.from_user.id, chunk, parse_mode="HTML")

    elif action == "vote":
        await callback.bot.send_message(
            callback.from_user.id,
            "🗳 <b>Голосование</b>\n\n"
            "Создать: /vote Твой вопрос\n"
            "Например: <code>/vote Идём на пары в пятницу?</code>\n\n"
            "Посмотреть текущее: /vote",
            parse_mode="HTML"
        )

    elif action == "feed":
        await callback.bot.send_message(callback.from_user.id, "/feed")

    elif action == "anon":
        await callback.bot.send_message(callback.from_user.id, "/anon")

    elif action == "add_hw":
        await callback.bot.send_message(callback.from_user.id, "/addhw")

    elif action == "history":
        await callback.bot.send_message(callback.from_user.id, "/history")

    elif action == "subscribe":
        await upsert_user(callback.from_user.id, callback.from_user.username or "", callback.from_user.full_name or "")
        user = await get_user(callback.from_user.id)
        is_sub = user and user.get("subscribed")
        if is_sub:
            await set_subscription(callback.from_user.id, 0)
            await callback.bot.send_message(callback.from_user.id, "🔕 Отписался от уведомлений.")
        else:
            await set_subscription(callback.from_user.id, 1)
            await callback.bot.send_message(callback.from_user.id, "✅ Подписан на уведомления!")

    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Команды:</b>\n\n"
        "/app — открыть WebApp (расписание/ДЗ/дедлайны/файлы/чат в одном окне)\n"
        "/schedule — расписание сегодня\n"
        "/tomorrow — завтра\n"
        "/week — неделя\n"
        "/nextweek — следующая неделя\n"
        "/next — следующая пара\n"
        "/teacher ФИО — расписание препода (по всему университету)\n"
        "/room номер — расписание аудитории (по всему университету)\n"
        "/deadlines — дедлайны\n"
        "/done ID — выполнено\n"
        "/del ID — удалить дедлайн\n"
        "/solve — решить задачу\n"
        "/solve_ds — решить через DeepSeek\n"
        "/solve_lectures — решить опираясь на загруженные лекции предмета (Gemini)\n"
        "/history — история решений\n"
        "/rating — рейтинг\n"
        "/hw — доска ДЗ\n"
        "/weather — погода\n"
        "/files — файлы\n"
        "/search запрос — поиск по файлам\n"
        "/vote Вопрос — голосование\n"
        "/feed — анонимный пост в общую ленту группы\n"
        "/note — заметка на пару (сегодня/завтра)\n"
        "/anon — анонимный вопрос лично старосте\n"
        "/setreminder N — напоминание за N мин\n"
        "/subscribe — уведомления вкл\n"
        "/unsubscribe — уведомления выкл\n\n"
        "💬 Можно писать и обычным текстом без команд — бот попробует понять,\n"
        "что ты хочешь (расписание, дедлайны, файлы и т.д.)."
    )
    if STAROSTA_ID:
        text += (
            "\n<b>Только для старосты:</b>\n"
            "/announce — рассылка\n"
            "/addhw — добавить ДЗ\n"
            "/setzam ID — установить зама\n"
            "/syncfiles — загрузить файлы\n"
            "/importdeadlines — импорт дедлайнов\n"
            "/syncsdo — вручную синхронизировать дедлайны из СДО\n"
            "/delpost ID — удалить пост из ленты\n"
            "/clearsem — сбросить дедлайны/ДЗ/файлы/голосования (новый семестр)\n"
        )
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


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message):
    user = await get_user(message.from_user.id)
    mins = user.get("reminder_minutes", 15) if user else 15
    sub  = "✅ включены" if (user and user.get("subscribed")) else "❌ выключены"
    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"🔔 Уведомления: {sub}\n"
        f"⏰ Напоминание до пары: <b>{mins} мин</b>\n\n"
        f"Изменить: /setreminder 15\n"
        f"Уведомления: /subscribe или /unsubscribe",
        parse_mode="HTML"
    )


@router.message(F.text == "🏆 Рейтинг")
async def rating_button(message: Message):
    from handlers.announce import cmd_rating
    await cmd_rating(message)


@router.message(F.text == "📝 ДЗ")
async def hw_button(message: Message):
    from handlers.announce import cmd_hw
    await cmd_hw(message)
