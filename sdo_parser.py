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

Фильтруем только сроки сдачи (DEADLINE_EVENTS): задания (mod_assign,
due), закрытие тестов (mod_quiz, close) и похожие. Остальные типы событий
Moodle (закрытие опросов mod_feedback, обычные события курса и т.д.)
пропускаем — они не дедлайны в смысле, который нужен боту.

Основной источник теперь — календарь по месяцам (AJAX
core_calendar_get_calendar_monthly_view, CALENDAR_MONTHS вперёд):
владелец заметил, что дедлайнов «маловато». «Предстоящие события» в
Moodle по умолчанию — только 21 день вперёд и не больше 10 событий, а
закрытия тестов туда ещё и не попадали в фильтр. Страница «Предстоящие»
осталась запасным путём, если AJAX на сервере СДО недоступен.
"""

import html as html_lib
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
CALENDAR_MONTHS = 5  # текущий месяц и четыре вперёд — до конца семестра

# (компонент, тип события) — сроки, которые бот считает дедлайнами
DEADLINE_EVENTS = {
    ("mod_assign", "due"),              # задание: срок сдачи
    ("mod_quiz", "close"),              # тест закрывается
    ("mod_lesson", "deadline"),         # лекция-урок: крайний срок
    ("mod_workshop", "submissionend"),  # семинар: конец приёма работ
    ("mod_forum", "due"),               # форум с оценкой: срок
}


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
        if (component, event_type) not in DEADLINE_EVENTS:
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


# Метка семестра в названии курса СДО: «Архитектура_Экзамен [I.26-27]» —
# первый (осенний) семестр 2026/27, «[II.25-26]» — весенний 2025/26.
# Владелец: дедлайны курсов прошлого семестра не нужны.
_SEM_TAG = re.compile(r"\[\s*(I{1,2})\s*\.\s*(\d{2})\s*-\s*(\d{2})\s*\]")


def current_semester_tag(today=None) -> str:
    """Сентябрь–январь (с сессией) — «I.26-27», февраль–июль — «II.25-26».
    С августа — уже осенний: курсы на новый год открывают заранее."""
    d = today or datetime.now(TZ).date()
    if d.month >= 8:
        return f"I.{d.year % 100:02d}-{(d.year + 1) % 100:02d}"
    if d.month == 1:
        return f"I.{(d.year - 1) % 100:02d}-{d.year % 100:02d}"
    return f"II.{(d.year - 1) % 100:02d}-{d.year % 100:02d}"


def is_old_semester(text: str, today=None) -> bool:
    """Есть метка семестра, и она не нынешняя. Без метки — не знаем, не трогаем."""
    tags = [f"{a}.{b}-{c}" for a, b, c in _SEM_TAG.findall(text or "")]
    return bool(tags) and current_semester_tag(today) not in tags


async def fetch_calendar_events(client: httpx.AsyncClient, months: int = CALENDAR_MONTHS) -> list[dict] | None:
    """Все события календаря за months месяцев начиная с текущего (JSON
    Moodle). None — AJAX недоступен, пусть работает запасной путь."""
    resp = await client.get(f"{SDO_BASE_URL}/my/")
    if "/login/index.php" in str(resp.url):
        raise SdoSessionExpired(f"Похоже, сессия СДО протухла (итоговый URL: {resp.url})")
    resp.raise_for_status()
    m = re.search(r'"sesskey":"([^"]+)"', resp.text)
    if not m:
        return None
    method = "core_calendar_get_calendar_monthly_view"
    today = datetime.now(TZ).date()
    year, month = today.year, today.month
    events = []
    for _ in range(months):
        try:
            r = await client.post(
                f"{SDO_BASE_URL}/lib/ajax/service.php?sesskey={m.group(1)}&info={method}",
                json=[{"index": 0, "methodname": method, "args": {
                    "year": year, "month": month, "courseid": 1, "includenavigation": False, "mini": False}}],
            )
            data = r.json()[0]
        except Exception as e:
            logger.info(f"СДО: календарь по AJAX не ответил ({e}) — беру «Предстоящие»")
            return None
        if data.get("error"):
            logger.info(f"СДО: календарь по AJAX: {data.get('exception')} — беру «Предстоящие»")
            return None
        for week in data["data"].get("weeks", []):
            for day in week.get("days", []):
                events.extend(day.get("events", []))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return events


def parse_calendar_events(events: list[dict]) -> list[dict]:
    """То же, что parse_deadlines, но из JSON календаря; прошедшие — мимо."""
    today = datetime.now(TZ).date()
    results, seen = [], set()
    for e in events:
        component = e.get("component") or (f"mod_{e['modulename']}" if e.get("modulename") else "")
        if (component, e.get("eventtype")) not in DEADLINE_EVENTS or e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        dt = datetime.fromtimestamp(int(e.get("timestart") or 0), tz=TZ)
        if dt.date() < today:
            continue
        # Moodle отдаёт названия уже экранированными для HTML (&amp;, &quot;)
        title = html_lib.unescape(e.get("name") or "Без названия").strip()
        course = html_lib.unescape((e.get("course") or {}).get("fullname") or "").strip()
        results.append({
            "external_id": f"sdo:{e['id']}",   # тот же id события, что и в «Предстоящих» — без дублей
            "subject":     f"{title} ({course})" if course else title,
            "description": e.get("url") or "",
            "due_date":    dt.date().isoformat(),
            "due_time":    dt.strftime("%H:%M"),
        })
    results.sort(key=lambda d: (d["due_date"], d["due_time"]))
    return results


async def fetch_calendar_deadlines() -> list[dict] | None:
    async with httpx.AsyncClient(cookies={"MoodleSession": SDO_SESSION_COOKIE},
                                 follow_redirects=True, timeout=30) as client:
        events = await fetch_calendar_events(client)
    return None if events is None else parse_calendar_events(events)


async def fetch_deadline_items() -> list[dict]:
    """Дедлайны из календаря по месяцам, а если AJAX недоступен — со
    страницы «Предстоящие события» (ближайшие 21 день, до 10 событий)."""
    if not SDO_SESSION_COOKIE:
        raise SdoSessionExpired("SDO_SESSION_COOKIE не задана")
    items = await fetch_calendar_deadlines()
    if items is None:
        items = parse_deadlines(await fetch_upcoming_html())
    return items


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
        items = await fetch_deadline_items()
    except SdoSessionExpired as e:
        logger.warning(f"СДО sync: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": True,
                "missing": not SDO_SESSION_COOKIE}
    except Exception as e:
        logger.error(f"СДО sync: не удалось получить страницу: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": False, "error": str(e)}

    added = updated = skipped = 0
    old = [i for i in items if is_old_semester(i["subject"])]
    items = [i for i in items if not is_old_semester(i["subject"])]

    for item in items:
        existing = await get_deadline_by_external_id(item["external_id"])
        if existing and existing.get("manual_edit"):
            skipped += 1  # староста поправил вручную — его версия главнее СДО
            continue
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

    logger.info(f"СДО sync: добавлено {added}, обновлено {updated}, пропущено {skipped}, прошлый семестр {len(old)}")
    return {"added": added, "updated": updated, "skipped": skipped, "old_semester": len(old), "expired": False}
