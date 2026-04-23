from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import upsert_user, set_subscription
from config import GROUP_NAME

router = Router()

MAIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📅 Сегодня"),    KeyboardButton(text="📆 Неделя"),      KeyboardButton(text="🌅 Завтра")],
    [KeyboardButton(text="⏭ Следующая"),   KeyboardButton(text="📋 Дедлайны"),    KeyboardButton(text="➕ Дедлайн")],
    [KeyboardButton(text="🤖 Решить"),      KeyboardButton(text="📁 Файлы"),       KeyboardButton(text="🗳 Голосование")],
    [KeyboardButton(text="❓ Вопрос анон"), KeyboardButton(text="🔔 Подписка"),    KeyboardButton(text="⚙️ Настройки")],
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
        "⏭ <b>Следующая пара</b> — что сейчас\n"
        "📋 <b>Дедлайны</b> — общий трекер группы\n"
        "🤖 <b>Решалка</b> — текст или фото задачи\n"
        "📁 <b>Файлы</b> — методички и материалы\n"
        "🗳 <b>Голосования</b> — для группы\n"
        "❓ <b>Анонимный вопрос</b> — старосте без имени\n"
        "━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
        reply_markup=MAIN_KB,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Все команды:</b>\n\n"
        "/schedule — расписание сегодня\n"
        "/tomorrow — расписание завтра\n"
        "/week — расписание на неделю\n"
        "/next — следующая пара\n"
        "/deadlines — список дедлайнов\n"
        "/stats — статистика дедлайнов\n"
        "/add — добавить дедлайн\n"
        "/done ID — выполнено\n"
        "/del ID — удалить\n"
        "/solve — решить задачу\n"
        "/history — история решений\n"
        "/files — файлы группы\n"
        "/upload — загрузить файл\n"
        "/vote Вопрос — создать голосование\n"
        "/anon — анонимный вопрос старосте\n"
        "/setreminder 10 — напоминание за N минут\n"
        "/subscribe — включить уведомления\n"
        "/unsubscribe — выключить уведомления",
        parse_mode="HTML",
    )


@router.message(Command("subscribe"))
@router.message(F.text == "🔔 Подписка")
async def cmd_subscribe(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await set_subscription(message.from_user.id, 1)
    await message.answer("✅ Подписан на уведомления!\n\nБуду писать каждое утро в 7:30 🌅")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    await set_subscription(message.from_user.id, 0)
    await message.answer("🔕 Отписался. Вернуться — /subscribe")


@router.message(Command("setreminder"))
async def cmd_setreminder(message: Message):
    from database import set_reminder_minutes
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /setreminder 15\nНапример /setreminder 10 — за 10 минут до пары")
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
    from database import get_user
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
