"""Команда /weather. Сама погода — kapibara/features/weather/forecast.py
(её берут и рассылки, а им нельзя импортировать обработчики бота)."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from kapibara.features.weather.forecast import format_weather

router = Router()


@router.message(Command("weather"))
@router.message(F.text == "🌤 Погода")
async def cmd_weather(message: Message):
    wait = await message.answer("⏳ Получаю погоду...")
    text = await format_weather()
    await wait.edit_text(text, parse_mode="HTML")
