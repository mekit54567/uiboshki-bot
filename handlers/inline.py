"""
Inline-режим: в любом чате пишешь «@UiboshkiBot» — и отправляешь туда
карточку расписания: сегодня, завтра, неделя группы. Дальше в запросе можно
набрать фамилию преподавателя, группу или аудиторию — придёт их расписание
(справочник schedule_index). Включается один раз в BotFather: /setinline.

Если задан WEBAPP_URL — карточки картинками (schedule/card.py, в стиле
приложения): бот рисует их сразу, пока отвечает (card.prepare), а Telegram
забирает готовые по подписанной ссылке /card/… с сервера бота. Без
WEBAPP_URL — текстом, как раньше.

Карточки собираются только когда их спрашивают; расписание чужих — не больше
трёх и с ограничением по времени, чтобы Telegram успел получить ответ.
"""

import asyncio
import hashlib
import logging
import re
from datetime import date, timedelta

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultArticle, InlineQueryResultPhoto,
    InputTextMessageContent,
)

logger = logging.getLogger(__name__)
router = Router()

MAX_TEXT = 4000          # лимит текста сообщения Telegram — 4096
TARGET_TIMEOUT = 6.0
DAY_WORDS = {"сегодня": "today", "завтра": "tomorrow", "неделя": "week", "неделю": "week"}
NOW_WORDS = {"сейчас", "щас", "сейчас пара", "пара", "следующая", "след", "след пара", "next", "now"}
WEEKDAYS = [("пн", "понедельник"), ("вт", "вторник"), ("ср", "среда", "среду"), ("чт", "четверг"),
            ("пт", "пятница", "пятницу"), ("сб", "суббота", "субботу"), ("вс", "воскресенье")]
MONTHS = ["янв", "фев", "мар", "апр", "ма", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
SHARE_WORDS = {"share", "позвать", "пригласить", "поделиться"}    # «Поделиться» из бота и Mini App


def parse_day(q: str, today: date) -> date | None:
    """«пятница», «в пт», «послезавтра», «12 ноября», «12.11» → дата
    (ближайшая: день недели — сегодня или впереди, число — в этом году,
    а давно прошедшее — в следующем)."""
    q = re.sub(r"^(в|во|на)\s+", "", q.lower().strip().replace("ё", "е"))
    if q == "послезавтра":
        return today + timedelta(days=2)
    for wd, names in enumerate(WEEKDAYS):
        if q in names:
            return today + timedelta(days=(wd - today.weekday()) % 7)
    m = re.fullmatch(r"(\d{1,2})\s*(?:[./]\s*(\d{1,2})(?:[./]\d{2,4})?|\s([а-я]+))", q)
    if not m:
        return None
    month = int(m[2]) if m[2] else next((i + 1 for i, st in enumerate(MONTHS) if m[3].startswith(st)), 0)
    try:
        d = date(today.year, month, int(m[1]))
    except ValueError:
        return None
    return d.replace(year=today.year + 1) if d < today - timedelta(days=60) else d


def _cut(text: str) -> str:
    """Обрезать по строкам до лимита Telegram."""
    if len(text) <= MAX_TEXT:
        return text
    out = text[:MAX_TEXT].rsplit("\n", 1)[0]
    return out + "\n…"


def _app_kb() -> InlineKeyboardMarkup:
    from kapibara.core.config import BOT_USERNAME
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📱 Открыть в приложении", url=f"https://t.me/{BOT_USERNAME}?startapp")]])


def _article(rid: str, title: str, description: str, text: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=hashlib.md5(rid.encode()).hexdigest(), title=title, description=description[:120],
        input_message_content=InputTextMessageContent(message_text=_cut(text), parse_mode="HTML",
                                                      disable_web_page_preview=True),
        reply_markup=_app_kb(),
    )


def _photo(rid: str, url: str, title: str, description: str, caption: str) -> InlineQueryResultPhoto:
    # превью — своим адресом (?thumb=1): с одной ссылкой на двоих фото в чате
    # приходило обрезанным снизу
    return InlineQueryResultPhoto(
        id=hashlib.md5(rid.encode()).hexdigest(), photo_url=url, thumbnail_url=url + "&thumb=1",
        title=title, description=description[:120], caption=caption, reply_markup=_app_kb(),
    )


def _card_base() -> str:
    from kapibara.core.config import WEBAPP_URL
    return WEBAPP_URL.rstrip("/")


def _own_cards(only: str | None, name: str, today: date) -> list[tuple[str, str, str]]:
    """(ключ картинки, заголовок, описание). Пустой запрос — сегодня, завтра,
    неделя и «сейчас»; слово или дата — одна карточка."""
    from kapibara.features.schedule.parser import DAY_NAMES, MONTHS_GEN
    if only and only.startswith("d"):
        d = date.fromisoformat(f"{only[1:5]}-{only[5:7]}-{only[7:9]}")
        return [(only, f"📅 {DAY_NAMES[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]} — {name}",
                 "пары на этот день")]
    cards = [("today", f"📅 Сегодня — {name}", "пары на сегодня"),
             ("tomorrow", f"🌙 Завтра — {name}", "пары на завтра"),
             ("week", f"🗓 Неделя — {name}", "вся неделя"),
             ("now", f"⏰ Сейчас — {name}", "какая пара идёт или будет следующей")]
    return [c for c in cards if not only or c[0] == only]


async def _own_results(only: str | None, user_id: int | None = None) -> list:
    """«Сегодня/завтра/неделя/сейчас/любой день» — группы того, кто пишет
    (этап 1): своя — как раньше, чужая — её календарь (в ссылке — id группы)."""
    from kapibara.features.groups import groups
    from kapibara.core.config import GROUP_NAME
    from kapibara.core.utils import today_msk
    from database.groups import viewer_group
    try:
        gid = await viewer_group(user_id) if user_id else groups.home_id()
    except Exception as e:                # база недоступна — своя группа, как раньше
        logger.info(f"inline: группа {user_id}: {e}")
        gid = groups.home_id()
    other = bool(gid) and gid > 0 and gid != groups.home_id()
    name = (await groups.name_of(gid) or GROUP_NAME) if other else GROUP_NAME
    cards = _own_cards(only, name, today_msk())
    if base := _card_base():
        from kapibara.features.schedule import card as schedule_card
        # рисуем сразу, пока отвечаем: Telegram придёт за готовыми картинками
        urls = await asyncio.gather(*(schedule_card.prepare(base, key, *((1, gid) if other else ()))
                                      for key, _, _ in cards))
        return [_photo(f"own:{key}:{url}", url, title, desc, title)
                for (key, title, desc), url in zip(cards, urls)]
    from kapibara.features.schedule import parser
    g = (gid,) if other else ()
    out = []
    for key, title, desc in cards:
        if key.startswith("d"):
            text = await parser.get_date_schedule(date.fromisoformat(f"{key[1:5]}-{key[5:7]}-{key[7:9]}"), *g)
        else:
            text = await {"today": parser.get_today_schedule, "tomorrow": parser.get_tomorrow_schedule,
                          "week": parser.get_week_schedule, "now": parser.get_next_lesson}[key](*g)
        out.append(_article(f"own:{key}:{hash(text)}", title, desc, text))
    return out


async def _target_results(query: str) -> list:
    from kapibara.features.schedule import index as schedule_index
    from handlers.schedule import _TARGET_EMOJI, render_target_schedule
    found = (await schedule_index.search(query, limit=3))[:3]
    if base := _card_base():
        from kapibara.features.schedule import card as schedule_card
        urls = await asyncio.gather(*(schedule_card.prepare(base, "target", t["type"], t["id"]) for t in found))
        out = []
        for t, url in zip(found, urls):
            title = f"{_TARGET_EMOJI[t['type']]} {t['title']}"
            out.append(_photo(f"t:{url}", url, title, "расписание на неделю", title))
        return out

    async def one(t):
        try:
            text = await asyncio.wait_for(render_target_schedule(t["id"], t["type"], t["title"]), TARGET_TIMEOUT)
        except Exception as e:
            logger.info(f"inline: {t['title']}: {type(e).__name__}")
            return None
        return _article(f"t:{t['type']}:{t['id']}:{hash(text)}", f"{_TARGET_EMOJI[t['type']]} {t['title']}",
                        "расписание на 2 недели", text)

    return [r for r in await asyncio.gather(*(one(t) for t in found)) if r]


async def _share_results(user_id: int) -> list:
    """Готовое сообщение про Капибару с личной ссылкой (referrals.py)."""
    from kapibara.features.billing import referrals
    from handlers.plus import share_kb
    kb = await share_kb(user_id)
    if _card_base():
        url = referrals.share_image()
        return [InlineQueryResultPhoto(id="share", photo_url=url, thumbnail_url=url,
                                       title=f"Позвать в {referrals.NAME}", description=referrals.share_text(),
                                       caption=referrals.share_text(), reply_markup=kb)]
    return [InlineQueryResultArticle(id="share", title=f"Позвать в {referrals.NAME}",
                                     description=referrals.share_text()[:120],
                                     input_message_content=InputTextMessageContent(
                                         message_text=referrals.share_text()), reply_markup=kb)]


@router.inline_query()
async def inline_schedule(query: InlineQuery):
    q = (query.query or "").strip()
    only = DAY_WORDS.get(q.lower()) or ("now" if q.lower() in NOW_WORDS else None)
    if not only and q:
        from kapibara.core.utils import today_msk
        if d := parse_day(q, today_msk()):
            only = f"d{d:%Y%m%d}"
    try:
        if q.lower() in SHARE_WORDS:
            results = await _share_results(query.from_user.id)
        elif not q or only:
            results = await _own_results(only, query.from_user.id)
        elif len(q) >= 3:
            results = await _target_results(q)
        else:
            results = []
    except Exception as e:
        logger.warning(f"inline: {e}")
        results = []
    await query.answer(results, cache_time=60, is_personal=True)
