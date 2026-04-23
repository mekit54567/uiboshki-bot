from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from database import upsert_user, set_subscription

router = Router()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Расписание сегодня"), KeyboardButton(text="📋 Дедлайны")],
        [KeyboardButton(text="➕ Добавить дедлайн"),  KeyboardButton(text="🤖 Решить задачу")],
        [KeyboardButton(text="🔕 Отписаться"),        KeyboardButton(text="🔔 Подписаться")],
    ],
    resize_keyboard=True,
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await upsert_user(
        user.id,
        user.username or "",
        user.full_name or "",
    )
    await message.answer(
        f"👋 Привет, <b>{user.first_name}</b>!\n\n"
        "Я бот группы МИРЭА «Бизнес-информатика» 🎓\n\n"
        "Что умею:\n"
        "📅 <b>Расписание</b> — пары на сегодня каждое утро в 7:30\n"
        "📋 <b>Дедлайны</b> — общий трекер для группы\n"
        "🤖 <b>Решалка</b> — кидай фото или текст задачи\n\n"
        "Используй кнопки ниже или команды:",
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Команды бота:</b>\n\n"
        "/start — главное меню\n"
        "/schedule — расписание на сегодня\n"
        "/deadlines — список дедлайнов\n"
        "/add — добавить дедлайн\n"
        "/done ID — отметить дедлайн выполненным\n"
        "/del ID — удалить дедлайн\n"
        "/subscribe — включить уведомления\n"
        "/unsubscribe — выключить уведомления\n\n"
        "Или просто пришли текст/фото задачи — решу! 🤖",
        parse_mode="HTML",
    )


@router.message(Command("subscribe"))
@router.message(lambda m: m.text == "🔔 Подписаться")
async def cmd_subscribe(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    await set_subscription(message.from_user.id, 1)
    await message.answer("✅ Ты подписан на уведомления! Буду писать каждое утро.")


@router.message(Command("unsubscribe"))
@router.message(lambda m: m.text == "🔕 Отписаться")
async def cmd_unsubscribe(message: Message):
    await set_subscription(message.from_user.id, 0)
    await message.answer("🔕 Отписался. Напоминания приходить не будут.\nВернуться — /subscribe")
