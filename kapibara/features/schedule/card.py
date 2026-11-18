"""
Картинки расписания для inline-режима (@бот в любом чате) в стиле
приложения. День — пары лентой: время, полоса цвета предмета, название,
тип, аудитория, преподаватель, перерывы. Неделя — по дню карточка.
Рисует card_draw.py (Pillow, шрифты приложения — assets/fonts), JPEG. Отдаёт
их webapp/routes/schedule.py по подписанной ссылке /card/… — Telegram сам
забирает картинку по URL. Здесь — ссылки с подписью, кэш и сборка картинки
из календаря.
"""

import asyncio
import hashlib
import hmac
import logging
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from kapibara.core.errors import NETWORK

logger = logging.getLogger(__name__)

# Рисование — в card_draw.py; снаружи эти имена берут отсюда, как раньше
from kapibara.features.schedule.card_draw import (  # noqa: E402, F401
    FONTS, STYLE, STYLES, THUMB_W, W, _gap, _pairs_word, day_subtitle, render_day, render_week, thumbnail,
)


# ── ссылки и сборка ─────────────────────────────────────────────────────────
# Ссылка на картинку подписана (HMAC от токена бота), чтобы сервер не рисовал
# по чужим запросам расписание чего угодно. Ключ включает дату и метку
# времени — Telegram кэширует картинки по URL, а расписание меняется.

def sign(key: str) -> str:
    from kapibara.core.config import BOT_TOKEN
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан — ссылку на картинку не подписать")
    return hmac.new(BOT_TOKEN.encode(), f"card:{key}".encode(), hashlib.sha256).hexdigest()[:24]


DAY = 24 * 6          # десятиминуток в сутках


def card_url(base: str, kind: str, target_type: int = 0, target_id: int = 0, ver: str = "") -> str:
    """kind: today / tomorrow / week (своя группа) или target (неделя найденного).
    Метка — начало суток (в десятиминутках, как раньше), ver — хэш готовой
    картинки (prepare): пока расписание то же, ссылка та же и Telegram не
    качает картинку заново. Превью — та же ссылка с «&thumb=1»."""
    key = f"{kind}-{target_type}-{target_id}-{int(time.time()) // 86400 * DAY}" + (f"-{ver}" if ver else "")
    return f"{base.rstrip('/')}/card/{key}.jpg?sig={sign(key)}"


# Ссылка живёт месяц: иначе ссылку из старого сообщения можно дёргать вечно
# (каждый раз рендер Pillow и запрос к зеркалу). Метка — десятиминутки.
CARD_MAX_AGE = 30 * 24 * 6


def parse_key(key: str, sig: str) -> tuple[str, int, int] | None:
    if not hmac.compare_digest(sig, sign(key)):
        return None
    parts = key.split("-")
    if len(parts) == 5 and re.fullmatch(r"[0-9a-f]{1,16}", parts[4]):
        parts = parts[:4]
    if len(parts) != 4 or not (parts[0] in ("today", "tomorrow", "week", "target", "now")
                               or re.fullmatch(r"d\d{8}", parts[0])):
        return None
    try:
        kind, target_type, target_id, stamp = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None
    if not 0 <= int(time.time()) // 600 - stamp <= CARD_MAX_AGE:
        return None
    return kind, target_type, target_id


# ── готовые картинки ────────────────────────────────────────────────────────
# Раньше картинка рисовалась, только когда за ней приходил Telegram, а
# ссылка менялась каждые 10 минут — превью в списке @бота грузились секундами
# (Никита 03.11). Теперь бот рисует их, пока отвечает на запрос (prepare), и
# кладёт сюда вместе с превью: Telegram приходит — всё уже готово.

CACHE_TTL = 30 * 60
CACHE_MAX = 120
PREPARE_TIMEOUT = 4.0
_cache: OrderedDict[str, tuple[float, bytes, bytes | None]] = OrderedDict()


def cached(key: str, thumb: bool = False) -> bytes | None:
    hit = _cache.get(key)
    if not hit or hit[0] < time.time():
        return None
    return hit[2] if thumb else hit[1]


def put(key: str, data: bytes, thumb: bytes | None = None):
    _cache[key] = (time.time() + CACHE_TTL, data, thumb)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


async def render(kind: str, target_type: int = 0, target_id: int = 0, now: datetime | None = None) -> bytes | None:
    """Нарисовать карточку (None — расписание не загрузилось)."""
    from kapibara.core.config import BOT_USERNAME, GROUP_NAME
    from kapibara.core.utils import TZ
    now = now or datetime.now(TZ)
    if kind == "target" or target_id:
        from kapibara.features.schedule import index as schedule_index
        from kapibara.features.schedule.mirea_api import fetch_ical
        ttype = target_type if kind == "target" else 1
        raw = await fetch_ical(target_id, ttype)
        if raw is None:
            return None
        title = await schedule_index.get_title(ttype, target_id)
        if kind == "target":
            return await asyncio.to_thread(build_target, raw, title or "Расписание", now, BOT_USERNAME)
        return await asyncio.to_thread(build_own, raw, kind, now, title or "Группа", BOT_USERNAME)
    from kapibara.features.schedule.parser import fetch_schedule_raw
    raw = await fetch_schedule_raw()
    return await asyncio.to_thread(build_own, raw, kind, now, GROUP_NAME, BOT_USERNAME)


async def prepare(base: str, kind: str, target_type: int = 0, target_id: int = 0) -> str:
    """Нарисовать заранее и вернуть ссылку с хэшем картинки. Не успели или
    сбой — ссылка без хэша: сервер дорисует, когда Telegram придёт."""
    try:
        data = await asyncio.wait_for(render(kind, target_type, target_id), PREPARE_TIMEOUT)
        if data is None:
            raise ValueError("расписание не загрузилось")
        thumb = await asyncio.to_thread(thumbnail, data)
    except (*NETWORK, OSError, ValueError, RuntimeError) as e:   # ответ всё равно уйдёт — дорисует /card
        logger.info(f"card: заранее не нарисовали {kind} {target_type}/{target_id}: {type(e).__name__}: {e}")
        return card_url(base, kind, target_type, target_id)
    url = card_url(base, kind, target_type, target_id, hashlib.sha1(data).hexdigest()[:10])
    put(url.split("/card/")[1].split(".jpg")[0], data, thumb)
    return url


def _monday_for(today: date) -> date:
    """Неделя для картинки: текущая, а в воскресенье — следующая."""
    return today - timedelta(days=today.weekday()) + (timedelta(days=7) if today.weekday() == 6 else timedelta(0))


def week_title(raw: bytes, monday: date) -> tuple[str, str]:
    from kapibara.features.schedule.parser import MONTHS_GEN, week_number
    sunday = monday + timedelta(days=6)
    num = week_number(raw, monday) or week_number(raw, monday + timedelta(days=1))
    span = (f"{monday.day}–{sunday.day} {MONTHS_GEN[sunday.month - 1]}" if monday.month == sunday.month
            else f"{monday.day} {MONTHS_GEN[monday.month - 1]} – {sunday.day} {MONTHS_GEN[sunday.month - 1]}")
    return (f"Неделя {num}" if num else "Неделя"), span


def build_own(raw: bytes, kind: str, now: datetime, group: str, bot: str) -> bytes:
    from kapibara.features.schedule.parser import DAY_NAMES, MONTHS_GEN, lessons_for_date
    footer = f"{group} · @{bot}"
    if kind == "week":
        monday = _monday_for(now.date())
        days = [(monday + timedelta(days=i), lessons_for_date(raw, monday + timedelta(days=i))) for i in range(7)]
        title, span = week_title(raw, monday)
        n = sum(l.get("pairs", 1) for _, ls in days for l in ls)
        return render_week(title, f"{span} · {n} {_pairs_word(n)}", days, footer, today=now.date())
    if kind == "now":
        return build_now(raw, now, footer)
    d = kind_date(kind, now.date())
    lessons = lessons_for_date(raw, d)
    return render_day(f"{DAY_NAMES[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}", day_subtitle(lessons),
                      lessons, footer)


def kind_date(kind: str, today: date) -> date:
    """today / tomorrow / dГГГГММДД (любой день, inline «пятница», «12 ноября»)."""
    if kind.startswith("d") and len(kind) == 9:
        return date(int(kind[1:5]), int(kind[5:7]), int(kind[7:9]))
    return today + timedelta(days=1 if kind == "tomorrow" else 0)


def _mins(m: int) -> str:
    h, m = divmod(max(m, 0), 60)
    return f"{h} ч {m} мин" if h and m else f"{h} ч" if h else f"{m} мин"


def build_now(raw: bytes, now: datetime, footer: str) -> bytes:
    """«Сейчас»: идущая пара или ближайшая следующая (до недели вперёд) и
    остальные пары того же дня."""
    from kapibara.features.schedule.parser import DAY_NAMES, MONTHS_GEN, lessons_for_date
    today = now.date()
    hm = now.strftime("%H:%M")
    lessons = lessons_for_date(raw, today)
    rest = [l for l in lessons if l["end"] > hm]
    if rest:
        l = rest[0]
        if l["start"] <= hm:
            title = f"Идёт {l['num']} пара" if l.get("num") else "Идёт пара"
            sub = f"до конца {_mins(_gap(hm, l['end']))}"
            tag = "идёт"
        else:
            title = f"Через {_mins(_gap(hm, l['start']))}"
            sub = f"следующая пара · в {l['start']}"
            tag = "следующая"
        more = len(rest) - 1
        sub += f" · потом ещё {more}" if more else " · последняя сегодня"
        return render_day(title, sub, rest, footer, pose="day", highlight=(0, tag))
    for i in range(1, 8):
        d = today + timedelta(days=i)
        if ls := lessons_for_date(raw, d):
            when = "завтра" if i == 1 else f"{DAY_NAMES[d.weekday()].lower()}, {d.day} {MONTHS_GEN[d.month - 1]}"
            return render_day("Сегодня пар больше нет" if lessons else "Сегодня пар нет",
                              f"следующие — {when} с {ls[0]['start']}", ls, footer, pose="night",
                              highlight=(0, "следующая"))
    return render_day("Пар нет", "ближайшую неделю свободно", [], footer)


def build_target(raw: bytes, title: str, now: datetime, bot: str) -> bytes:
    from kapibara.features.schedule.parser import target_weeks
    monday = _monday_for(now.date())
    week = target_weeks(raw, monday, weeks=1)[0]
    days = [(date.fromisoformat(x["date"]), x["lessons"]) for x in week["days"]]
    wt, span = week_title(raw, monday)
    return render_week(title, f"{wt.lower()} · {span}", days, f"@{bot}", today=now.date())
