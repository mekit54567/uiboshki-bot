"""
Слой доставки (этап 2 (г), PLAN.md «Своё приложение»): одна функция на все
рассылки — утро, напоминание перед парой, дедлайны, новые задания, обзор
недели. Сейчас доставляет в Telegram и веб-пушем на устройства, где человек
включил уведомления в PWA (webpush.py); потом сюда же — пуши своего
приложения (FCM, APNs, RuStore), без правки каждой рассылки.
"""

import logging
import re

logger = logging.getLogger(__name__)

TITLES = {"morning": "Доброе утро", "lesson": "Скоро пара", "deadlines": "Дедлайны",
          "new_tasks": "Новое в СДО", "weekly": "Неделя", "grades": "Новые баллы", "evening": "Завтра",
          "quiz": "Тест СДО", "ugc": "Записи группы"}


def plain(html: str, limit: int = 180) -> str:
    """Текст пуша: без HTML-разметки, первые строки."""
    text = re.sub(r"<[^>]+>", "", html or "")
    text = re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", re.sub(r"&amp;", "&", text)))
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _body(html: str, title: str | None) -> str:
    """Текст пуша; со своим заголовком — без первой строки, где он уже есть."""
    text = plain(html, 10_000)
    head, _, rest = text.partition("\n")
    if title and title in head and rest.strip():
        text = rest.strip()
    return plain(text)


async def push(user_id: int, kind: str, html: str, tab: str | None = None, title: str | None = None) -> int:
    """Веб-пуш на все устройства человека. → сколько ушло. title — свой
    заголовок вместо общего по kind (вечерняя сводка: «Завтра: 3 пары с 09:00»)."""
    import webpush
    from database.push import delete_push_sub, get_push_subs
    subs = await get_push_subs(user_id)
    if not subs:
        return 0
    data = {"title": title or TITLES.get(kind, "УИБО-бот"), "body": _body(html, title),
            "url": "/app" + (f"?tab={tab}" if tab else ""), "tag": kind}
    sent = 0
    for sub in subs:
        try:
            code = await webpush.send(sub, data)
        except Exception as e:
            logger.info(f"пуш {user_id}: {type(e).__name__}: {e}")
            continue
        if code in (404, 410):
            await delete_push_sub(sub["endpoint"])      # подписку удалили в браузере
        elif code < 300:
            sent += 1
        else:
            logger.info(f"пуш {user_id}: сервис ответил {code}")
    return sent


async def _tg_copy(user_id: int) -> bool:
    """Слать ли в Telegram, когда пуш уже дошёл (тумблер «Дублировать в
    Telegram» в уведомлениях PWA). Пуш не дошёл — Telegram в любом случае."""
    import notify_prefs
    from database import get_user
    return notify_prefs.merge((await get_user(user_id) or {}).get("notify"))["tg_copy"]


async def deliver(bot, user_id: int, html: str, *, kind: str, tab: str | None = None, reply_markup=None,
                  parse_mode: str = "HTML", title: str | None = None):
    """Сообщение человеку: пуш на его устройства + Telegram (выключен
    тумблером tg_copy — только если пуш дошёл).
    Ошибка Telegram пробрасывается (рассылки её логируют), пуш — молча.
    До согласия на обработку данных (privacy.blocked) — ничего."""
    import privacy
    if await privacy.blocked(user_id):
        return None
    sent = 0
    try:
        sent = await push(user_id, kind, html, tab, **({"title": title} if title else {}))
    except Exception as e:
        logger.info(f"доставка {user_id}: пуш не ушёл: {e}")
    from database.identities import is_local
    if is_local(user_id):
        return None               # вошёл через VK/Яндекс, Telegram нет — только пуш
    if sent and not await _tg_copy(user_id):
        return None               # «только в приложение»: пуш дошёл — в Telegram не дублируем
    return await bot.send_message(user_id, html, parse_mode=parse_mode, reply_markup=reply_markup)
