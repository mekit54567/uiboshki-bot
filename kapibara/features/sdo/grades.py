"""
Баллы БРС из СДО: страница «Оценки» каждого курса (отчёт по пользователю,
/grade/report/user/index.php?id=<курс>), входом самого студента.

Загрузка из СДО и кэш — здесь; разбор отчёта и подсчёт — в gradebook.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from kapibara.core import forget as forget_hooks
from kapibara.core.config import SDO_BASE_URL
from kapibara.features.sdo import gradebook
from kapibara.features.sdo.pages import (  # noqa: F401 — их брали отсюда
    _activity_dates, _clean, parse_assign_page, parse_quiz_page, parse_task_page, parse_time_limit,
)

logger = logging.getLogger(__name__)

CACHE_SECONDS = 10 * 60
# Экран предмета ждёт страницы работ (порог, статус, срок) не дольше этого:
# 19.10 СДО отвечал медленно, и экран с целью грузился 76–100 с. Не успевшие
# страницы — из прошлого раза или без порога; такой ответ не кэшируется.
PAGES_BUDGET = 20

_cache: dict[tuple, tuple[float, Any]] = {}
# Страницы заданий (порог «зачтено», вердикт) — для подсчёта в списке
# предметов тем же правилом, что на экране предмета (Б4). Порог меняется
# редко: держим дольше баллов и не стираем после сдачи.
PAGES_SECONDS = 6 * 3600
_pages: dict[tuple[int, int], tuple[float, dict]] = {}


def known_page(user_id: int, cmid: int) -> dict | None:
    hit = _pages.get((user_id, cmid))
    return hit[1] if hit and time.time() - hit[0] < PAGES_SECONDS else None


# ── загрузка из СДО ──────────────────────────────────────────────────────────

def _cached(key):
    hit = _cache.get(key)
    return hit[1] if hit and time.time() - hit[0] < CACHE_SECONDS else None


def _store(key, value):
    _cache[key] = (time.time(), value)
    return value


@forget_hooks.register
def forget(user_id: int):
    for k in [k for k in _cache if k[1] == user_id]:
        _cache.pop(k, None)


async def _report(client: httpx.AsyncClient, course_id: int) -> dict:
    from kapibara.features.sdo.net import get_checked
    resp = await get_checked(client, f"{SDO_BASE_URL}/grade/report/user/index.php?id={course_id}")
    return gradebook.parse_report(resp.text)


async def this_semester_courses(client: httpx.AsyncClient) -> list[dict]:
    from kapibara.features.schedule.parser import get_group_subjects
    from kapibara.features.sdo.courses import clean_course_name
    from kapibara.features.sdo.files import list_courses
    from kapibara.features.sdo.courses import KEEP_COURSES, SEMESTER_WINDOW, is_old_semester, off_schedule
    subjects = await get_group_subjects(**SEMESTER_WINDOW)
    out = []
    for c in await list_courses(client):
        name = c["name"]
        if is_old_semester(name) or off_schedule(name, subjects) or any(k in name.lower() for k in KEEP_COURSES):
            continue
        out.append({"id": c["id"], "name": name, "title": clean_course_name(name)})
    return out


_inflight: dict[int, asyncio.Future] = {}


async def overview(user_id: int, cookie: str, fresh: bool = False) -> dict:
    """Все предметы семестра со сводкой баллов. Кэш на 10 минут.

    16.10 (Amvera): приложение на старте спрашивало баллы трижды разом — 12
    соединений к СДО, часть не открылась, и неполный список (4 предмета)
    лёг в кэш на 10 минут. Теперь одновременные запросы одного человека
    ждут один общий, а не открывшийся предмет пробуем ещё раз; не вышло —
    отдаём что есть, но в кэш не кладём."""
    key = ("all", user_id)
    if not fresh and (hit := _cached(key)):
        return hit
    if (running := _inflight.get(user_id)) is not None:
        return await asyncio.shield(running)
    fut = asyncio.get_running_loop().create_future()
    _inflight[user_id] = fut
    try:
        result = await _overview(user_id, cookie, fresh)
    except asyncio.CancelledError:
        fut.cancel()
        raise
    except Exception as e:
        fut.set_exception(e)
        fut.exception()                # чтобы без ждущих не было «exception never retrieved»
        raise
    else:
        fut.set_result(result)
        return result
    finally:
        _inflight.pop(user_id, None)


async def _overview(user_id: int, cookie: str, fresh: bool) -> dict:
    key = ("all", user_id)
    if fresh:                  # «обновить» — и экраны предметов тоже, иначе там до 10 минут старое
        for k in [k for k in _cache if k[0] == "detail" and k[1] == user_id]:
            _cache.pop(k, None)
    from kapibara.features.sdo.net import make_client
    failed = object()
    async with make_client(cookie) as client:
        courses = await this_semester_courses(client)
        sem = asyncio.Semaphore(4)

        async def one(c, retry=False):
            async with sem:
                try:
                    rep = await _report(client, c["id"])
                except httpx.HTTPError as e:
                    logger.info(f"Баллы СДО: курс {c['id']} не открылся{' (повтор)' if retry else ''}: "
                                f"{type(e).__name__}")
                    return failed
            s = gradebook.summarize(rep, c["name"])
            if not s["categories"] and not s["works"]:
                return None      # курс без журнала БРС («Учебный отдел» и т.п.)
            s = gradebook.recount(s, [known_page(user_id, w["cmid"]) for w in s["works"]])
            _store(("course", user_id, c["id"]), (c, s))
            return dict(s, id=c["id"], name=c["name"], title=c["title"])

        got = list(await asyncio.gather(*(one(c) for c in courses)))
        for i, c in enumerate(courses):           # повтор по одному, не залпом
            if got[i] is failed:
                got[i] = await one(c, retry=True)
    partial = any(x is failed for x in got)
    items = [x for x in got if x and x is not failed]
    items.sort(key=lambda x: (x["closed"], x["need"] if not x["closed"] else -x["score"]))
    data = {"courses": items, "updated": int(time.time())}
    if partial:
        if not items:          # ни одного предмета — это «СДО не отвечает», а не пустой семестр
            raise httpx.ConnectError("СДО не отдал ни одного журнала")
        return data            # неполный список — показать, но не запоминать
    return _store(key, data)


async def course_detail(user_id: int, cookie: str, course_id: int, stale_ok: bool = False) -> dict:
    """Предмет подробно + по каждой работе текущего контроля страница задания
    (порог, статус, срок) — для экрана «Текущий контроль».

    19.10: смена цели шла по 15 с — экран предмета ещё грузился из медленного
    СДО, а каждое нажатие начинало ту же загрузку заново. Теперь одновременные
    запросы ждут одну загрузку, а действиям (цель, отметка посещения) хватает
    прошлой загрузки любой давности (stale_ok) — баллы им не нужны свежими."""
    key = ("detail", user_id, course_id)
    if hit := _cached(key):
        return hit
    if stale_ok and (old := _cache.get(key)):
        return old[1]
    if (running := _inflight_detail.get(key)) is not None:
        return await asyncio.shield(running)
    fut = asyncio.get_running_loop().create_future()
    _inflight_detail[key] = fut
    try:
        result = await _course_detail(user_id, cookie, course_id)
    except asyncio.CancelledError:
        fut.cancel()
        raise
    except BaseException as e:
        fut.set_exception(e)
        fut.exception()
        raise
    else:
        fut.set_result(result)
        return result
    finally:
        _inflight_detail.pop(key, None)


_inflight_detail: dict[tuple, asyncio.Future] = {}


async def _course_detail(user_id: int, cookie: str, course_id: int) -> dict:
    key = ("detail", user_id, course_id)
    from kapibara.features.sdo.net import make_client
    async with make_client(cookie) as client:
        base = _cached(("course", user_id, course_id))
        # когда баллы брали из СДО — «обновлено в 09:40» на экране предмета
        fetched = _cache[("course", user_id, course_id)][0] if base else time.time()
        if base:
            course, s = base
        else:
            course = next((c for c in await this_semester_courses(client) if c["id"] == course_id), None)
            if not course:
                raise LookupError("курс не найден")
            s = gradebook.summarize(await _report(client, course_id), course["name"])
        sem = asyncio.Semaphore(5)

        async def page(w):
            if w["module"] not in ("assign", "quiz"):
                return None
            async with sem:
                try:
                    from kapibara.features.sdo.net import get_checked
                    r = await get_checked(client, f"{SDO_BASE_URL}/mod/{w['module']}/view.php?id={w['cmid']}")
                    return parse_assign_page(r.text)
                except httpx.HTTPError:
                    return None

        tasks = [asyncio.ensure_future(page(w)) for w in s["works"]]
        if tasks:
            await asyncio.wait(tasks, timeout=PAGES_BUDGET)
        late = [t for t in tasks if not t.done()]
        for t in late:
            t.cancel()
        if late:
            await asyncio.gather(*late, return_exceptions=True)
            logger.info(f"предмет {course_id}: {len(late)} из {len(tasks)} страниц работ не успели за {PAGES_BUDGET} с")
        # не успевшую страницу берём из прошлого раза (если была) — лучше старый порог, чем никакого
        pages = [t.result() if t.done() and not t.cancelled() else (_pages.get((user_id, w["cmid"])) or (0, None))[1]
                 for t, w in zip(tasks, s["works"], strict=False)]
    for t, w, p in zip(tasks, s["works"], pages, strict=False):
        if p is not None and t.done() and not t.cancelled():
            _pages[(user_id, w["cmid"])] = (time.time(), p)
    from kapibara.features.deadlines import quiz_time        # время тестов — одно на всех, видно в «Сдать»
    await quiz_time.remember({w["cmid"]: p for w, p in zip(s["works"], pages, strict=False) if w["module"] == "quiz"})
    s = gradebook.recount(s, pages)
    works = []
    for w, p in zip(s["works"], pages, strict=False):
        p = p or {}
        works.append(dict(w, pass_mark=p.get("pass"), status=gradebook.work_status(w, p), due=p.get("due", ""),
                          opens=p.get("opens", ""), remaining=p.get("remaining", ""), time_limit=p.get("time_limit"),
                          can_submit=bool(p.get("can_submit")) and w["module"] == "assign",
                          url=f"{SDO_BASE_URL}/mod/{w['module']}/view.php?id={w['cmid']}"))
    works = gradebook.order_works(works)
    out = dict(s, id=course_id, name=course["name"], title=course["title"], works=works, updated=int(fetched))
    # список предметов из кэша — те же «зачтено X из Y», что здесь (Б4)
    if hit := _cached(("all", user_id)):
        for c in hit["courses"]:
            if c["id"] == course_id:
                c.update({k: s[k] for k in ("works_passed", "works_need", "auto")})
    if late:
        return out                  # не всё успели — в кэш не кладём, следующий заход доберёт
    return _store(key, out)


# ── задание целиком: описание, файлы преподавателя ───────────────────────────

async def task_detail(cookie: str, cmid: int, module: str = "assign") -> dict:
    from kapibara.features.sdo.net import make_client
    from kapibara.features.sdo.net import get_checked
    from kapibara.features.sdo import submit as sdo_submit
    url = f"{SDO_BASE_URL}/mod/{module}/view.php?id={cmid}"
    async with make_client(cookie) as client:
        html = (await get_checked(client, url)).text
        page = parse_task_page(html)
        page["maxfiles"] = 0
        if module == "quiz":
            page.update(parse_quiz_page(html), can_submit=False)
            from kapibara.features.deadlines import quiz_time
            await quiz_time.remember({cmid: page})
        if page["can_submit"]:
            try:
                edit = sdo_submit.parse_edit_page((await get_checked(client, url + "&action=editsubmission")).text)
                page["maxfiles"] = edit["maxfiles"]
                page["maxbytes"] = edit["maxbytes"]
            except sdo_submit.SubmitError:
                page["can_submit"] = page["can_edit"] = False
        if module == "assign":
            # комментарии к ответу, как в СДО (карточка задания, Никита 18.11);
            # не вышло — задание всё равно показываем, без переписки
            from kapibara.features.sdo import comments as sdo_comments
            try:
                page["comments"] = await sdo_comments.fetch(client, html)
            except (sdo_comments.CommentError, httpx.HTTPError) as e:
                logger.info(f"СДО: комментарии задания {cmid} не открылись: {e}")
                page["comments"] = None
    page.update(cmid=cmid, url=url, limit=min(sdo_submit.MAX_FILES, page["maxfiles"] or sdo_submit.MAX_FILES))
    return page
