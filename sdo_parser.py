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
import os
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
GONE_AFTER = 2       # столько синков подряд задания нет в календаре — убираем у себя

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


async def get_checked(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET в СДО. Протухшая сессия бывает не только редиректом на
    /login/index.php, но и бесконечным кругом «вход → единый вход МИРЭА →
    обратно» — httpx тогда бросает TooManyRedirects. Живой тест 26.09:
    это приходило старосте как «СДО недоступен с сервера», хотя дело в куке."""
    try:
        resp = await client.get(url)
    except httpx.TooManyRedirects:
        raise SdoSessionExpired("СДО гоняет по кругу редиректов на вход — кука протухла")
    if "/login/index.php" in str(resp.url):
        raise SdoSessionExpired(f"Похоже, сессия СДО протухла (итоговый URL: {resp.url})")
    return resp


IDLE_TIMEOUT: int | None = None     # сек: сколько сессия живёт без запросов (для /status)


async def _time_remaining(client: httpx.AsyncClient, html: str) -> int | None:
    """core_session_time_remaining сразу после запроса — это и есть срок жизни
    сессии без обращений (у МИРЭА меньше 6 ч; точное число — в /status)."""
    m = re.search(r'"sesskey":"([^"]+)"', html or "")
    if not m:
        return None
    method = "core_session_time_remaining"
    try:
        r = await client.post(f"{SDO_BASE_URL}/lib/ajax/service.php?sesskey={m.group(1)}&info={method}",
                              json=[{"index": 0, "methodname": method, "args": {}}])
        data = r.json()[0]
        return None if data.get("error") else int(data["data"]["timeremaining"])
    except Exception as e:
        logger.info(f"СДО: срок сессии не узнал ({e})")
        return None


async def keepalive() -> bool:
    """Лёгкий запрос в СДО, чтобы сессия Moodle не истекла без обращений
    (сколько она живёт без них — не знаем; синк раз в 6 ч её не спас).
    True — сессия жива."""
    if not SDO_SESSION_COOKIE:
        return False
    global IDLE_TIMEOUT
    try:
        async with httpx.AsyncClient(cookies={"MoodleSession": SDO_SESSION_COOKIE},
                                     follow_redirects=True, timeout=30) as client:
            resp = await get_checked(client, f"{SDO_BASE_URL}/my/")
            IDLE_TIMEOUT = await _time_remaining(client, resp.text) or IDLE_TIMEOUT
        return True
    except Exception as e:
        logger.info(f"СДО keepalive: {e}")
        return False


async def fetch_upcoming_html() -> str:
    if not SDO_SESSION_COOKIE:
        raise SdoSessionExpired("SDO_SESSION_COOKIE не задана")

    async with httpx.AsyncClient(
        cookies={"MoodleSession": SDO_SESSION_COOKIE},
        follow_redirects=True,
        timeout=30,
    ) as client:
        resp = await get_checked(client, UPCOMING_URL)
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
            "title":       title,
            "course":      course_name,
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


def course_of(subject: str) -> str:
    """Курс из названия дедлайна: последняя скобка верхнего уровня —
    «ПР 1 (Анализ данных (УИБО-03-24))» → «Анализ данных (УИБО-03-24)»."""
    s = (subject or "").rstrip()
    from deadline_names import SEP
    if SEP in s:          # уже понятное название: «Практика 2 · Анализ данных (Экз)»
        return re.sub(r"\s*\((?:Зач|Экз)\)$", "", s.rsplit(SEP, 1)[1]).strip()
    if not s.endswith(")"):
        return ""
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                return s[i + 1:-1].strip()
    return ""


# Курсы не из расписания, которые всё равно нужны (владелец: «оставь
# Учебный отдел»): приказы, объявления, документы института. Через запятую,
# по вхождению без учёта регистра; переопределяется SDO_KEEP_COURSES.
KEEP_COURSES = [c.strip().lower() for c in os.getenv("SDO_KEEP_COURSES", "Учебный отдел").split(",") if c.strip()]

# Предметы для сверки с курсами СДО — за весь семестр, а не за ±пару недель:
# предмет, у которого пары через раз или ещё не начались, иначе не попадал в
# список, и его курс уходил к похожему по словам («Учетная деятельность на
# предприятии» → «Основы предпринимательской деятельности»).
SEMESTER_WINDOW = {"days_back": 60, "days_ahead": 120}


def off_schedule(course: str, subjects: list[str]) -> bool:
    """Курса нет среди предметов нынешнего расписания группы. Живой тест:
    «Методы принятия управленческих решений», «Физкультура 3/3» и т.п.
    прошлых семестров были без метки «[II.25-26]». Нет расписания или
    курса — не выбрасываем (лучше лишний дедлайн, чем пропущенный)."""
    if not course or not subjects:
        return False
    if any(k in course.lower() for k in KEEP_COURSES):
        return False
    from sdo_files import match_subject
    return match_subject(course, subjects) not in subjects


def not_this_semester(item: dict, subjects: list[str]) -> bool:
    return is_old_semester(item["subject"]) or off_schedule(item.get("course") or course_of(item["subject"]), subjects)


async def fetch_calendar_events(client: httpx.AsyncClient, months: int = CALENDAR_MONTHS) -> list[dict] | None:
    """Все события календаря за months месяцев начиная с текущего (JSON
    Moodle). None — AJAX недоступен, пусть работает запасной путь."""
    resp = await get_checked(client, f"{SDO_BASE_URL}/my/")
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
            "title":       title,
            "course":      course,
            "external_id": f"sdo:{e['id']}",   # тот же id события, что и в «Предстоящих» — без дублей
            "subject":     f"{title} ({course})" if course else title,
            "description": e.get("url") or "",
            "due_date":    dt.date().isoformat(),
            "due_time":    dt.strftime("%H:%M"),
            "calendar":    True,               # из полного календаря — по нему видно, что пропало
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
    from database import add_deadline, get_deadline_by_external_id, is_deadline_skipped, update_deadline_due

    try:
        items = await fetch_deadline_items()
    except SdoSessionExpired as e:
        logger.warning(f"СДО sync: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": True,
                "missing": not SDO_SESSION_COOKIE}
    except Exception as e:
        logger.error(f"СДО sync: не удалось получить страницу: {e}")
        return {"added": 0, "updated": 0, "skipped": 0, "expired": False, "error": str(e)}

    from schedule_parser import get_group_subjects
    added = updated = skipped = 0
    new_ids: list[int] = []               # для рассылки «новые задания» (new_tasks.py)
    moved: dict[int, str] = {}            # id → прежний срок «YYYY-MM-DD»: преподаватель перенёс
    subjects = await get_group_subjects(**SEMESTER_WINDOW)
    old = [i for i in items if not_this_semester(i, subjects)]
    items = [i for i in items if not not_this_semester(i, subjects)]
    # понятные названия — после проверки семестра (метка «[I.26-27]» уходит)
    from deadline_names import pretty
    for i in items:
        if i.get("title"):
            i["subject"] = pretty(i["title"], i.get("course") or "", subjects)

    for item in items:
        existing = await get_deadline_by_external_id(item["external_id"])
        if existing and existing.get("manual_edit"):
            skipped += 1  # староста поправил вручную — его версия главнее СДО
            continue
        if not existing and await is_deadline_skipped(item["external_id"]):
            skipped += 1  # староста удалил его — не возвращаем
            continue
        if existing:
            fresh = (item["subject"], item["due_date"], item["due_time"])
            if (existing["subject"], existing["due_date"], existing["due_time"]) != fresh:
                await update_deadline_due(existing["id"], *fresh)
                updated += 1
                if (existing["due_date"], existing["due_time"]) != fresh[1:]:
                    moved[existing["id"]] = existing["due_date"]
            else:
                skipped += 1
            continue
        did = await add_deadline(
            subject=item["subject"],
            description=item["description"],
            due_date=item["due_date"],
            due_time=item["due_time"],
            created_by=0,
            external_id=item["external_id"],
        )
        added += 1
        if did:
            new_ids.append(did)

    gone = await drop_vanished(items + old)

    logger.info(f"СДО sync: добавлено {added}, обновлено {updated}, пропущено {skipped}, "
                f"прошлый семестр {len(old)}, пропало из СДО {len(gone)}")
    return {"added": added, "updated": updated, "skipped": skipped, "old_semester": len(old), "new_ids": new_ids,
            "moved": moved, "gone": gone,
            "old_courses": sorted({i.get("course") or course_of(i["subject"]) for i in old} - {""}),
            "expired": False}


def calendar_end(today=None) -> str:
    """Первый день после окна календаря (CALENDAR_MONTHS месяцев с текущего)."""
    today = today or datetime.now(TZ).date()
    k = today.year * 12 + today.month - 1 + CALENDAR_MONTHS
    return f"{k // 12:04d}-{k % 12 + 1:02d}-01"


async def drop_vanished(items: list[dict]) -> list[str]:
    """Убрать дедлайны, которых больше нет в СДО (преподаватель удалил или
    скрыл задание), — раньше они висели до срока и о них напоминали.

    Решаем только по полному календарю (все события окна): «Предстоящие» —
    21 день и 10 событий, по ним отсутствие ничего не значит. Пустой ответ
    тоже не повод — скорее сбой. Задание должно пропасть GONE_AFTER синков
    подряд (СДО иногда отдаёт календарь не целиком). Не трогаем прошедшие,
    сроки за окном календаря и поправленные старостой вручную. В
    deadlines_skipped не пишем: вернётся в СДО — вернётся и в боте.
    → названия убранных."""
    import json
    from database import delete_deadline, get_sdo_deadlines, get_setting, set_setting
    if not items or not all(i.get("calendar") for i in items):
        return []
    seen = {i["external_id"] for i in items}
    today, end = datetime.now(TZ).date().isoformat(), calendar_end()
    try:
        misses = json.loads(await get_setting("sdo_missing") or "{}")
    except ValueError:
        misses = {}
    left, gone = {}, []
    for d in await get_sdo_deadlines():
        ext = d["external_id"]
        if ext in seen or d.get("manual_edit") or not (today <= d["due_date"] < end):
            continue
        n = misses.get(ext, 0) + 1
        if n < GONE_AFTER:
            left[ext] = n
            continue
        await delete_deadline(d["id"], remember=False)
        gone.append(d["subject"])
    if left != misses:
        await set_setting("sdo_missing", json.dumps(left))
    if gone:
        logger.info(f"СДО sync: пропали из СДО и убраны — {gone}")
    return gone
