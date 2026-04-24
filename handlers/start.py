from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import upsert_user, set_subscription, get_user
from config import GROUP_NAME, STAROSTA_ID

router = Router()

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),      KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),    KeyboardButton(text="➕ Дедлайн")],
    [KeyboardButton(text="🤖 Решить"),      KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="🗳 Голосование")],
    [KeyboardButton(text="❓ Вопрос анон"), KeyboardButton(text="🔔 Подписка"),    KeyboardButton(text="⚙️ Настройки")],
    [KeyboardButton(text="🌤 Погода"),      KeyboardButton(text="📝 ДЗ"),          KeyboardButton(text="🏆 Рейтинг")],
], resize_keyboard=True)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await upsert_user(user.id, user.username or "", user.full_name or "")
    await message.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        f"Я бот группы <b>{GROUP_NAME}</b> 🎓\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>Расписание</b> — пары на сегодня, завтра, неделю\n"
        "📋 <b>Дедлайны</b> — общий трекер группы\n"
        "🤖 <b>Решалка</b> — текст или фото задачи\n"
        "📁 <b>Файлы</b> — лекции и методички\n"
        "🌤 <b>Погода</b> — прямо сейчас\n"
        "📝 <b>ДЗ</b> — доска домашних заданий\n"
        "🏆 <b>Рейтинг</b> — кто решил больше задач\n"
        "━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=MAIN_KB
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Команды:</b>\n\n"
        "/schedule — расписание сегодня\n"
        "/tomorrow — расписание завтра\n"
        "/week — расписание на неделю\n"
        "/next — следующая пара\n"
        "/deadlines — дедлайны\n"
        "/add — добавить дедлайн\n"
        "/done ID — выполнено\n"
        "/del ID — удалить\n"
        "/solve — решить задачу\n"
        "/history — история решений\n"
        "/rating — рейтинг активности\n"
        "/hw — доска ДЗ\n"
        "/weather — погода\n"
        "/files — файлы группы\n"
        "/subscribe — уведомления вкл\n"
        "/unsubscribe — уведомления выкл\n"
        "/setreminder N — напоминание за N минут\n"
    )
    if STAROSTA_ID:
        text += (
            "\n<b>Только для старосты:</b>\n"
            "/announce — рассылка объявления\n"
            "/addhw — добавить ДЗ\n"
            "/setzam ID — установить зама\n"
            "/syncfiles — загрузить файлы\n"
            "/importdeadlines — импорт дедлайнов\n"
        )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("subscribe"))
@router.message(F.text == "🔔 Подписка")
async def cmd_subscribe(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await set_subscription(message.from_user.id, 1)
    user = await get_user(message.from_user.id)
    mins = user.get("reminder_minutes", 15) if user else 15
    await message.answer(
        f"✅ Подписан на уведомления!\n\n"
        f"📅 Расписание каждое утро в 6:30\n"
        f"⏰ Напоминание о парах за {mins} мин\n"
        f"🌤 Погода утром\n\n"
        f"Изменить напоминание: /setreminder 30"
    )


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
        f"⚙️ <b>Твои настройки</b>\n\n"
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
