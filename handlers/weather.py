import httpx
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()
TZ = ZoneInfo("Europe/Moscow")

# Координаты Москвы (МИРЭА)
LAT = 55.7522
LON = 37.6156
CITY = "Москва"


async def fetch_weather() -> dict | None:
    """Получаем погоду через Open-Meteo (бесплатно, без ключа)."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&current=temperature_2m,apparent_temperature,precipitation,weathercode,windspeed_10m"
            f"&timezone=Europe/Moscow"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return None


def weather_emoji(code: int) -> str:
    if code == 0:               return "☀️"
    elif code in (1, 2):        return "🌤"
    elif code == 3:             return "☁️"
    elif code in (45, 48):      return "🌫"
    elif code in (51, 53, 55):  return "🌦"
    elif code in (61, 63, 65):  return "🌧"
    elif code in (71, 73, 75):  return "❄️"
    elif code in (80, 81, 82):  return "🌦"
    elif code in (95, 96, 99):  return "⛈"
    return "🌡"


def weather_desc(code: int) -> str:
    descs = {
        0: "Ясно", 1: "Почти ясно", 2: "Переменная облачность", 3: "Пасмурно",
        45: "Туман", 48: "Туман с изморозью",
        51: "Лёгкая морось", 53: "Морось", 55: "Сильная морось",
        61: "Лёгкий дождь", 63: "Дождь", 65: "Сильный дождь",
        71: "Лёгкий снег", 73: "Снег", 75: "Сильный снег",
        80: "Ливень", 81: "Сильный ливень", 82: "Очень сильный ливень",
        95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза",
    }
    return descs.get(code, "Переменная облачность")


async def format_weather() -> str:
    data = await fetch_weather()
    if not data:
        return "⚠️ Не удалось получить погоду"

    c = data["current"]
    temp     = round(c["temperature_2m"])
    feels    = round(c["apparent_temperature"])
    code     = c["weathercode"]
    wind     = round(c["windspeed_10m"])
    precip   = c["precipitation"]

    emoji = weather_emoji(code)
    desc  = weather_desc(code)

    temp_str  = f"+{temp}" if temp > 0 else str(temp)
    feels_str = f"+{feels}" if feels > 0 else str(feels)

    text = (
        f"{emoji} <b>Погода в Москве</b>\n\n"
        f"🌡 {temp_str}°C (ощущается {feels_str}°C)\n"
        f"☁️ {desc}\n"
        f"💨 Ветер {wind} км/ч\n"
    )

    if precip > 0:
        text += f"🌧 Осадки {precip} мм\n"

    # Совет по одежде
    if temp < 0:
        text += "\n🧥 Оденься потеплее!"
    elif temp < 10:
        text += "\n🧣 Куртка не помешает"
    elif temp < 18:
        text += "\n👕 Лёгкая куртка"
    else:
        text += "\n😎 Можно налегке"

    return text


@router.message(Command("weather"))
@router.message(F.text == "🌤 Погода")
async def cmd_weather(message: Message):
    wait = await message.answer("⏳ Получаю погоду...")
    text = await format_weather()
    await wait.edit_text(text, parse_mode="HTML")


async def get_weather_for_morning() -> str:
    """Для утренней рассылки."""
    return await format_weather()
