"""Сколько длится тест СДО («Сколько займёт работа», Никита 12.10, вариант Б).

Только у тестов (mod/quiz) и только своё ограничение по времени из СДО
(«Ограничение по времени: 30 мин.» на странице теста) — у заданий и тестов без
ограничения ничего не показываем, своих оценок «на глаз» нет.

Календарь СДО (sdo_parser) этого не отдаёт, поэтому ограничение запоминается,
когда страницу теста кто-то уже открыл своим входом (экран предмета —
sdo_grades.course_detail, экран теста — task_detail), и фоном после синка СДО
(learn_missing: тесты своей группы, которых ещё нет, общей кукой). Оно одно
на всех — таблица quiz_limits по cmid, без user_id. /api/deadlines только
читает её (attach), в СДО не ходит.
"""

import logging
import re

logger = logging.getLogger(__name__)

QUIZ_RE = re.compile(r"/mod/quiz/view\.php\?(?:[^#\s\"']*&)?id=(\d+)")
MAX_PER_RUN = 10        # страниц тестов за один фоновый проход


def quiz_cmid(text: str | None) -> int | None:
    """cmid теста из ссылки дедлайна; у задания и своего срока — None."""
    m = QUIZ_RE.search(text or "")
    return int(m.group(1)) if m else None


def learned(page: dict | None) -> int | None:
    """Что узнали со страницы теста (sdo_grades.parse_assign_page): минуты,
    0 — ограничения нет (блок сведений теста есть, строки о времени нет),
    None — страница не та (нет доступа, тест ещё закрыт) — не запоминаем."""
    if not page:
        return None
    if page.get("time_limit"):
        return int(page["time_limit"])
    return 0 if page.get("quiz_info") else None


async def remember(pages: dict[int, dict | None]):
    """{cmid: разобранная страница теста} → quiz_limits. Сбой базы экран не
    ломает — это лишь подпись."""
    rows = {int(c): v for c, p in pages.items() if c and (v := learned(p)) is not None}
    if not rows:
        return
    try:
        from database import save_quiz_limits
        await save_quiz_limits(rows)
    except Exception as e:
        logger.warning(f"время тестов: не сохранил {len(rows)}: {e}")


async def attach(items: list[dict]):
    """Каждому дедлайну — time_limit: минуты у теста с ограничением, иначе None."""
    from database import get_quiz_limits
    cmids = [quiz_cmid(d.get("description")) for d in items]
    known = await get_quiz_limits([c for c in cmids if c])
    for d, c in zip(items, cmids):
        d["time_limit"] = known.get(c) or None


async def learn_missing(cookie: str | None = None, limit: int = MAX_PER_RUN) -> int:
    """Фоном после синка СДО: тесты своей группы со сроком впереди, о которых
    ещё ничего не знаем, — страница каждого общей кукой. → сколько узнали."""
    from config import SDO_SESSION_COOKIE
    from database import get_quiz_deadline_links, get_quiz_limits
    from utils import today_msk
    cookie = cookie or SDO_SESSION_COOKIE
    if not cookie:
        return 0
    cmids = {c for link in await get_quiz_deadline_links(today_msk().isoformat()) if (c := quiz_cmid(link))}
    known = await get_quiz_limits(cmids)
    todo = sorted(cmids - set(known))[:limit]
    if not todo:
        return 0
    import httpx
    from config import SDO_BASE_URL
    from sdo_files import make_client
    from sdo_grades import parse_assign_page
    from sdo_parser import get_checked
    pages: dict[int, dict | None] = {}
    async with make_client(cookie) as client:
        for cmid in todo:
            try:
                r = await get_checked(client, f"{SDO_BASE_URL}/mod/quiz/view.php?id={cmid}")
                pages[cmid] = parse_assign_page(r.text)
            except httpx.HTTPError as e:
                logger.info(f"время тестов: тест {cmid} не открылся: {type(e).__name__}")
    await remember(pages)
    return sum(learned(p) is not None for p in pages.values())
