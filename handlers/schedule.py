from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from schedule_parser import get_today_schedule
from database import upsert_user

router = Router()


@router.message(Command("schedule"))
@router.message(lambda m: m.text == "📅 Расписание сегодня")
async def cmd_schedule(message: Message):
    await upsert_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name or "",
    )
    wait_msg = await message.answer("⏳ Загружаю расписание...")
    text = await get_today_schedule()
    await wait_msg.edit_text(text, parse_mode="HTML")
