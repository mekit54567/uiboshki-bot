from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from schedule_parser import get_today_schedule, get_tomorrow_schedule, get_week_schedule, get_next_lesson, get_next_week_schedule
from database import upsert_user

router = Router()


@router.message(Command("schedule"))
@router.message(F.text == "📅 Сегодня")
async def cmd_today(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    wait = await message.answer("⏳ Загружаю...")
    await wait.edit_text(await get_today_schedule(), parse_mode="HTML")


@router.message(Command("tomorrow"))
@router.message(F.text == "🌅 Завтра")
async def cmd_tomorrow(message: Message):
    wait = await message.answer("⏳ Загружаю...")
    await wait.edit_text(await get_tomorrow_schedule(), parse_mode="HTML")


@router.message(Command("week"))
@router.message(F.text == "📆 Неделя")
async def cmd_week(message: Message):
    wait = await message.answer("⏳ Загружаю неделю...")
    text = await get_week_schedule()
    await wait.delete()
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("nextweek"))
@router.message(F.text == "📆 След. неделя")
async def cmd_next_week(message: Message):
    wait = await message.answer("⏳ Загружаю следующую неделю...")
    text = await get_next_week_schedule()
    await wait.delete()
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await message.answer(chunk, parse_mode="HTML")


@router.message(Command("next"))
@router.message(F.text == "⏭ Следующая")
async def cmd_next(message: Message):
    wait = await message.answer("⏳ Смотрю...")
    await wait.edit_text(await get_next_lesson(), parse_mode="HTML")
