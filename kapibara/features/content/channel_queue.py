"""Посты каналов сами по очереди (/channel auto, Никита 05.11): одна кнопка —
первый пост каждого канала выходит сразу, остальные по одному с паузой:
«Капибара» — 20–30 минут, «Разработка» — 4–6 часов. Ночью (23–9 по Москве)
не выходит ничего — очередь ждёт утра. Очередь — в settings (переживает
перезапуск), выпускает её задача раз в минуту (scheduler → tick)."""

import json
import logging
import random
from datetime import datetime, timedelta

from kapibara.core.utils import TZ
from kapibara.features.content import channel_posts

logger = logging.getLogger(__name__)

KEY = "channel:queue"
GAPS = {"news": (20 * 60, 30 * 60), "dev": (4 * 3600, 6 * 3600)}   # пауза между постами, секунды
NIGHT_FROM, NIGHT_TO = 23, 9                                         # часы МСК, когда не публикуем


def is_night(t: datetime) -> bool:
    h = t.astimezone(TZ).hour
    return h >= NIGHT_FROM or h < NIGHT_TO


def after_night(t: datetime) -> datetime:
    """Ночное время → 9:00 ближайшего утра (плюс несколько минут, чтобы не ровно)."""
    t = t.astimezone(TZ)
    if not is_night(t):
        return t
    day = t.date() + timedelta(days=1) if t.hour >= NIGHT_FROM else t.date()
    return datetime(day.year, day.month, day.day, NIGHT_TO, 0, tzinfo=TZ)


def plan(posts: list[dict], done, now: datetime, rnd: random.Random | None = None) -> list[dict]:
    """Расписание невышедших постов: [{"slug", "at" (ISO)}] по порядку папок."""
    rnd = rnd or random.Random()
    out = []
    for chan, (lo, hi) in GAPS.items():
        at = now.astimezone(TZ)                # первый — сразу, даже ночью: Никита сам нажал

        for p in (p for p in posts if channel_posts.channel_of(p["slug"]) == chan and p["slug"] not in done):
            if channel_posts.target(p["slug"]):
                out.append({"slug": p["slug"], "at": at.isoformat(timespec="minutes")})
                at = after_night(at + timedelta(seconds=rnd.randint(lo, hi)))
    return sorted(out, key=lambda x: x["at"])


async def load() -> list[dict]:
    from database import get_setting
    raw = await get_setting(KEY)
    try:
        return json.loads(raw) if raw else []
    except ValueError:
        return []


async def save(items: list[dict]):
    from database import set_setting
    await set_setting(KEY, json.dumps(items, ensure_ascii=False))


async def start(now: datetime | None = None) -> list[dict]:
    items = plan(channel_posts.load_posts(), await channel_posts.published(), now or datetime.now(TZ))
    await save(items)
    return items


async def cancel() -> int:
    n = len(await load())
    await save([])
    return n


def when(at: str) -> str:
    t = datetime.fromisoformat(at).astimezone(TZ)
    return ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][t.weekday()] + t.strftime(" %H:%M")


async def tick(bot, now: datetime | None = None, night_ok: bool = False) -> list[str]:
    """Выпустить подошедшие посты: не больше одного на канал за раз, ночью —
    ничего (night_ok — сразу после «Запустить»: первые посты выходят тут же).
    Старосте — строчка о каждом. → slug выпущенных."""
    from kapibara.core import config
    from kapibara.core.errors import EXTERNAL
    from kapibara.core.locks import lock
    now = now or datetime.now(TZ)
    if is_night(now) and not night_ok:
        return []
    out: list[str] = []
    async with lock(KEY):
        items = await load()
        if not items:
            return out
        titles = {p["slug"]: p["title"] for p in channel_posts.load_posts()}
        seen: set[str] = set()
        left = []
        for it in items:
            chan = channel_posts.channel_of(it["slug"])
            if chan in seen or datetime.fromisoformat(it["at"]) > now:
                left.append(it)
                continue
            seen.add(chan)
            try:
                ids, link, _pin = await channel_posts.publish(bot, it["slug"], config.WEBAPP_URL)
            except (*EXTERNAL, OSError, ValueError) as e:
                logger.warning("очередь канала: %s не вышел: %s", it["slug"], e)
                await _tell(bot, f"⚠️ Из очереди не вышел пост «{titles.get(it['slug'], it['slug'])}»: {str(e)[:200]}. "
                                 "Выпусти руками через /channel.")
                continue
            if ids:
                out.append(it["slug"])
                await _tell(bot, f"✅ Вышел по очереди: «{titles.get(it['slug'], it['slug'])}»" + (f"\n{link}" if link else ""))
        await save(left)
        if not left and out:
            await _tell(bot, "Очередь постов закончилась — всё вышло 🎉")
    return out


async def _tell(bot, text: str):
    from aiogram.exceptions import TelegramAPIError
    from kapibara.core.config import STAROSTA_ID
    if not STAROSTA_ID:
        return
    try:
        await bot.send_message(STAROSTA_ID, text, disable_web_page_preview=True)
    except TelegramAPIError as e:
        logger.info("очередь канала: старосте не дошло: %s", e)
