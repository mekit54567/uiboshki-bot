"""
Сдал в СДО — дедлайн у себя отмечен сам.

Раньше отметку «сдал» ставил только сам человек: сдал работу прямо из бота
или увидел в журнале «отправлено» — а дедлайн висит, и напоминания идут.
Теперь бот ставит её сам, у каждого свою (deadline_done):
  • сразу после сдачи через бота (/api/sdo/submit);
  • когда человек открыл предмет в СДО, а там задание зачтено («ok») или
    сдано и ждёт оценки («wait»).
Снимать отметку бот не снимает никогда: «не сдано» в журнале бывает и по
ошибке СДО, а убрать галочку человек всегда может сам.
"""

import logging

logger = logging.getLogger(__name__)

DONE_STATUSES = ("ok", "wait")


def cmid_of(text: str) -> int | None:
    """Задание или тест из описания дедлайна СДО (разбор — sdo_submit.cmid_of)."""
    from sdo_submit import cmid_of as _cmid
    return _cmid(text, quiz=True)


def is_submitted(status: str | None) -> bool:
    """Статус ответа после сдачи: ушло на проверку — да; черновик — нет."""
    low = (status or "").lower()
    if "черновик" in low or "draft" in low or "не отправ" in low or "not submitted" in low:
        return False
    return "для оценивания" in low or "отправлен" in low or "submitted" in low


def submit_state(status: str | None) -> str:
    """Что показать после сдачи (аудит 21.10, R5): submitted — ушло на проверку,
    draft — файлы лежат черновиком, unknown — СДО не сказал ясно. «Сдано» —
    только для submitted."""
    if is_submitted(status):
        return "submitted"
    low = (status or "").lower()
    if "черновик" in low or "draft" in low or "не отправ" in low or "not submitted" in low:
        return "draft"
    return "unknown"


async def mark(user_id: int, cmids) -> int:
    """Отметить сданными дедлайны с этими заданиями (cmid). → сколько отмечено."""
    from database import get_active_deadlines, mark_deadline_done
    cmids = {int(c) for c in cmids if c}
    if not cmids:
        return 0
    n = 0
    for d in await get_active_deadlines(user_id, include_done=True):
        if cmid_of(d.get("description")) in cmids:
            # и поверх своей галочки: подтверждение СДО идёт в опыт (xp.py)
            await mark_deadline_done(d["id"], user_id, via="sdo")
            n += not d.get("done")
    if n:
        logger.info(f"СДО: {user_id} — {n} дедлайн(ов) отмечено сданными по журналу")
    return n


def finished(course: dict) -> list[int]:
    """cmid заданий курса, которые в журнале зачтены или ждут оценки."""
    return [w["cmid"] for w in course.get("works") or []
            if w.get("cmid") and w.get("status") in DONE_STATUSES]
