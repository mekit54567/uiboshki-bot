import logging
import net
import time
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


# Погода нужна на каждом заходе на главную WebApp (/api/today): раньше это
# был внешний запрос до 10 с каждый раз. Теперь — кэш на 20 минут, короткий
# таймаут, а сбой запоминается на пару минут, чтобы не ждать его снова.
WEATHER_TTL = 20 * 60
WEATHER_FAIL_TTL = 2 * 60
WEATHER_TIMEOUT = 4
_weather_cache: tuple[float, dict | None] | None = None   # (до какого времени верить, данные)
# Open-Meteo иногда отвечает 503 (17.10 — 9 «ошибок» за ночь в /status): тогда
# показываем последнюю удачную погоду, если ей не больше 3 часов.
WEATHER_STALE = 3 * 60 * 60
_last_good: tuple[float, dict] | None = None              # (когда скачана, данные)


async def fetch_weather() -> dict | None:
    """Получаем погоду через Open-Meteo (бесплатно, без ключа)."""
    global _weather_cache, _last_good
    if _weather_cache and _weather_cache[0] > time.monotonic():
        return _weather_cache[1]
    data = await _fetch_weather()
    now = time.monotonic()
    if data:
        _last_good = (now, data)
        _weather_cache = (now + WEATHER_TTL, data)
        return data
    if _last_good and now - _last_good[0] < WEATHER_STALE:
        data = _last_good[1]                  # сервис лежит — последняя удачная
    _weather_cache = (now + WEATHER_FAIL_TTL, data)
    return data


async def _fetch_weather() -> dict | None:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&current=temperature_2m,apparent_temperature,precipitation,weathercode,windspeed_10m"
            f"&timezone=Europe/Moscow"
        )
        async with net.client(timeout=WEATHER_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        # сбой чужого сервиса, а не бота: предупреждение, не ошибка — иначе
        # 503 Open-Meteo будил «всплеск ошибок» старосте (health.alert_errors)
        logger.warning(f"Weather error: {e}")
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

    tip = _clothes_tip(temp)
    text += f"\n{tip[0]} {tip[2:].capitalize()}"

    return text


@router.message(Command("weather"))
@router.message(F.text == "🌤 Погода")
async def cmd_weather(message: Message):
    wait = await message.answer("⏳ Получаю погоду...")
    text = await format_weather()
    await wait.edit_text(text, parse_mode="HTML")


def _clothes_tip(temp: int) -> str:
    if temp < 0:
        return "🧥 оденься потеплее"
    if temp < 10:
        return "🧣 куртка не помешает"
    if temp < 18:
        return "👕 лёгкая куртка"
    return "😎 можно налегке"


async def get_weather_for_morning() -> str:
    """Для утренней рассылки — одна строка над расписанием. Если погоду не
    получили — пустая строка: "⚠️ Не удалось получить погоду" каждое утро
    сверху рассылки только мешало (замечено в живом тесте)."""
    data = await fetch_weather()
    if not data:
        return ""
    c = data["current"]
    temp, feels = round(c["temperature_2m"]), round(c["apparent_temperature"])
    sign = lambda t: f"+{t}" if t > 0 else str(t)
    code = c["weathercode"]
    return (f"{weather_emoji(code)} {sign(temp)}°, {weather_desc(code).lower()}, "
            f"ощущается {sign(feels)}° · {_clothes_tip(temp)}")


# Вечерняя сводка (evening_digest.py) — погода на завтра: дневной прогноз
# Open-Meteo (мин/макс и код погоды). Кэш — как у fetch_weather; сбой — None.
_tomorrow_cache: tuple[float, str, dict | None] | None = None   # (до когда верить, на какую дату, данные)


async def fetch_tomorrow() -> dict | None:
    """{"tmin": 2, "tmax": 6, "code": 63} на завтра по Москве или None."""
    global _tomorrow_cache
    from datetime import datetime, timedelta
    day = (datetime.now(TZ).date() + timedelta(days=1)).isoformat()
    if _tomorrow_cache and _tomorrow_cache[0] > time.monotonic() and _tomorrow_cache[1] == day:
        return _tomorrow_cache[2]
    data = await _fetch_tomorrow(day)
    _tomorrow_cache = (time.monotonic() + (WEATHER_TTL if data else WEATHER_FAIL_TTL), day, data)
    return data


async def _fetch_tomorrow(day: str) -> dict | None:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&daily=temperature_2m_max,temperature_2m_min,weathercode"
            f"&timezone=Europe/Moscow&start_date={day}&end_date={day}"
        )
        async with net.client(timeout=WEATHER_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            d = resp.json()["daily"]
        return {"tmin": round(d["temperature_2m_min"][0]), "tmax": round(d["temperature_2m_max"][0]),
                "code": int(d["weathercode"][0])}
    except Exception as e:
        logger.error(f"Weather (завтра) error: {e}")
        return None


def tomorrow_text(w: dict | None) -> str:
    """«+2…+6°, дождь» — без эмодзи (одно уже в начале сводки); нет данных — ""."""
    if not w:
        return ""
    sign = lambda t: f"+{t}" if t > 0 else str(t)
    temp = sign(w["tmax"]) if w["tmin"] == w["tmax"] else f"{sign(w['tmin'])}…{sign(w['tmax'])}"
    return f"{temp}°, {weather_desc(w['code']).lower()}"


async def get_weather_for_tomorrow() -> str:
    """Строка погоды на завтра для вечерней сводки; сбой — пустая строка."""
    return tomorrow_text(await fetch_tomorrow())
