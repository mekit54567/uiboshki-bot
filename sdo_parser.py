"""
Парсер СДО (Moodle) поверх переиспользуемой сессионной куки.

Вместо автоматизации логина+2FA (которую по факту невозможно сделать
надёжно без ручного вмешательства — см. PLAN.md, Фаза 4) используется
кука MoodleSession, полученная один раз обычным входом в браузере
(с галочкой "запомнить меня"). Скрипт просто переиспользует эту куку
в запросах. Когда она протухнет, Moodle редиректит на страницу логина
вместо нужной страницы — это ловится явно и превращается в понятное
уведомление старосте, а не в молчаливый сбой или мусорные данные.

Источник данных — стандартная страница Moodle "Календарь: Предстоящие
события" (/calendar/view.php?view=upcoming). Она отдаёt события с
data-атрибутами (data-event-id, data-event-title, data-course-id,
data-event-component, data-event-eventtype) — парсится надёжно, без
регулярок по русским названиям месяцев.

Фильтруем только data-event-component="mod_assign" и
data-event-eventtype="due" — это реальные сроки сдачи практических/
лабораторных работ. Остальные типы событий Moodle (закрытие опросов
mod_feedback, обычные события курса и т.д.) пропускаем — они не
дедлайны в смысле, который нужен боту.
"""

import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from config import SDO_SESSION_COOKIE, SDO_BASE_URL, TIMEZONE

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)

UPCOMING_URL = f"{SDO_BASE_URL}/calendar/view.php?view=upcoming"


class SdoSessionExpired(Exception):
    """Кука MoodleSession больше не валидна — нужен ручной релогин."""
    pass


async def fetch_upcoming_html() -> str:
    if not SDO_SESSION_COOKIE:
        raise SdoSessionExpired("SDO_SESSION_COOKIE не задана")

    async with httpx.AsyncClient(
        cookies={"MoodleSession": SDO_SESSION_COOKIE},
        follow_redirects=True,
        timeout=30,
    ) as client:
        resp = await client.get(UPCOMING_URL)
        resp.raise_for_status()
        html = resp.text

        # Если кука протухла, Moodle молча редиректит на страницу логина —
        # никакой HTTP-ошибки не будет, страница просто не та, что мы просили.
        if "usermenu" not in html or str(resp.url).rstrip("/").endswith("/login/index.php"):
            raise SdoSessionExpired(
                f"Похоже, сессия СДО протухла (итоговый URL: {resp.url})"
            )

        return html


def parse_deadlines(html: str) -> list[dict]:
    """Возвращает список {external_id, subject, course, due_date, due_time, url}."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for event_div in soup.select('div[data-type="event"]'):
        component  = event_div.get("data-event-component", "")
        event_type = event_div.get("data-event-eventtype", "")
        if component != "mod_assign" or event_type != "due":
            continue

        event_id = event_div.get("data-event-id", "")
        title    = event_div.get("data-event-title", "Без названия").strip()

        # Таймстамп события — из ссылки "Когда" (calendar/view.php?...&time=UNIX)
        when_link = event_div.select_one('a[href*="time="]')
        due_date = due_time = None
        if when_link:
            m = re.search(r"time=(\d+)", when_link["href"])
            if m:
                dt = datetime.fromtimestamp(int(m.group(1)), tz=TZ)
                due_date = dt.date().isoformat()
                due_time = dt.strftime("%H:%M")

        # Название курса — ссылка на course/view.php внутри блока описания
        course_link = event_div.select_one('a[href*="course/view.php"]')
        course_name = course_link.get_text(strip=True) if course_link else ""

        # Прямая ссылка на элемент курса (mod/assign/view.php)
        item_link = event_div.select_one('a.card-link')
        item_url  = item_link["href"] if item_link else ""

        if not due_date:
            # Без даты это событие нам не нужно — не сможем ни отсортировать,
            # ни напомнить вовремя.
            continue

        results.append({
            "external_id": f"sdo:{event_id}",
            "subject":     f"{title} ({course_name})" if course_name else title,
            "description": item_url,
            "due_date":    due_date,
            "due_time":    due_time,
        })

    return results


async def sync_deadlines() -> dict:
    """Тянет актуальные дедлайны из СДО и добавляет новые в базу бота.

    Возвращает {"added": int, "updated": int, "skipped": int, "expired": bool}.
    updated — уже известные задания, у которых в СДО поменялись срок или
    название (препод продлил/перенёс сдачу): раньше дедуп по external_id их
    просто пропускал, и бот до конца семестра показывал и напоминал старую
    дату.
    При протухшей куке НЕ бросает исключение наружу — возвращает
    expired=True, чтобы вызывающий код (scheduler/хендлер) сам решил,
    как об этом сообщить старосте, вместо падения джобы целиком.
    """
    from database import add_deadline, get_deadline_by_external_id, update_deadline_due

    try:
        html = await fetch_upcoming_html()
    except SdoSessionExpired as e:
        logger.warning(f"СДО sync: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": True,
                "missing": not SDO_SESSION_COOKIE}
    except Exception as e:
        logger.error(f"СДО sync: не удалось получить страницу: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": False, "error": str(e)}

    items = parse_deadlines(html)
    added = updated = skipped = 0

    for item in items:
        existing = await get_deadline_by_external_id(item["external_id"])
        if existing:
            fresh = (item["subject"], item["due_date"], item["due_time"])
            if (existing["subject"], existing["due_date"], existing["due_time"]) != fresh:
                await update_deadline_due(existing["id"], *fresh)
                updated += 1
            else:
                skipped += 1
            continue
        await add_deadline(
            subject=item["subject"],
            description=item["description"],
            due_date=item["due_date"],
            due_time=item["due_time"],
            created_by=0,
            external_id=item["external_id"],
        )
        added += 1

    logger.info(f"СДО sync: добавлено {added}, обновлено {updated}, пропущено {skipped}")
    return {"added": added, "updated": updated, "skipped": skipped, "expired": False}
