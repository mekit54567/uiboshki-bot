"""Дедлайны (общие и личные, «сделано» у каждого своё), свои напоминания о
них и доска ДЗ."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webapp import deps
from webapp.deps import CurrentUser

router = APIRouter()


# ── Дедлайны (общие + личные, "done" персональный для каждого) ──────────────

@router.get("/api/deadlines")
async def api_deadlines(include_done: bool = False, user: dict = CurrentUser):
    from database import get_active_deadlines, get_deadline_stats, is_shared_deadline
    from database import is_editor
    from sdo_submit import can_submit
    from database import get_user_deadline_reminders
    from deadline_reminders import label as dl_label
    import ugc
    hidden = await ugc.hidden(user["id"])
    items = [d for d in await get_active_deadlines(user["id"], include_done=include_done)
             if not (hidden and is_shared_deadline(d) and d.get("created_by") in hidden)]
    editor = await is_editor(user["id"])
    reminders = await get_user_deadline_reminders(user["id"])
    for d in items:
        d["personal"] = not is_shared_deadline(d)
        d["mine"] = d.get("created_by") == user["id"]
        # Править/удалять может каждый (владелец 08.10): свой личный и общий
        # у старосты — для всех, общий у остальных — только у себя.
        d["can_edit"] = True
        d["edit_scope"] = "all" if (d["personal"] and d["mine"]) or (not d["personal"] and editor) else "me"
        d["mine_changed"] = bool(d.get("mine_changed"))
        d["can_submit"] = can_submit(d)
        # общий срок, который завёл человек (не СДО и не сам) — «Пожаловаться» (ugc.py)
        d["reportable"] = (not d["personal"] and not d["mine"] and bool(d.get("created_by"))
                           and not (d.get("external_id") or "").startswith("sdo:"))
        d["reminders"] = [{"at": at, "label": dl_label(at)} for at in reminders.get(d["id"], [])]
    import quiz_time    # у тестов — ограничение по времени из СДО (минуты или None)
    await quiz_time.attach(items)
    stats = await get_deadline_stats(user["id"])
    # последняя проверка СДО группы: «СДО проверено в 12:40» / «СДО не ответил»
    import sdo_check
    from database.groups import g_or_home
    return {"items": items, "stats": stats, "sdo": await sdo_check.state(g_or_home(None))}


class NewDeadline(BaseModel):
    subject: str
    due_date: str
    due_time: str = ""
    description: str = ""


def _validate_deadline(body: NewDeadline) -> tuple[str, str, str | None, str]:
    from datetime import date as date_cls
    from handlers.deadlines import parse_due_time
    subject = body.subject.strip()
    if not subject or len(subject) > 200:
        raise HTTPException(status_code=400, detail="название — от 1 до 200 символов")
    try:
        due = date_cls.fromisoformat(body.due_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="дата в формате ГГГГ-ММ-ДД")
    due_time = None
    if body.due_time.strip():
        ok, due_time = parse_due_time(body.due_time)
        if not ok:
            raise HTTPException(status_code=400, detail="время в формате ЧЧ:ММ")
    return subject, due.isoformat(), due_time, body.description.strip()[:1500]


async def _can_edit_deadline(existing: dict, user_id: int) -> bool:
    from database import deadline_group, is_editor, is_shared_deadline
    if is_shared_deadline(existing):
        return await is_editor(user_id, await deadline_group(existing))
    return existing["created_by"] == user_id


@router.post("/api/deadlines")
async def api_deadline_add(body: NewDeadline, user: dict = CurrentUser):
    """Свой (личный) дедлайн из WebApp — как /add в боте: виден только
    автору. Общие дедлайны группы по-прежнему заводит староста/СДО."""
    from database import add_deadline
    import ratelimit
    if not ratelimit.allow("deadline", user["id"]):
        raise HTTPException(429, "Слишком много дедлайнов подряд — подожди пару минут")
    subject, due, due_time, desc = _validate_deadline(body)
    did = await add_deadline(subject, desc, due, due_time, user["id"], personal=True)
    return {"ok": True, "id": did}


@router.patch("/api/deadlines/{deadline_id}")
async def api_deadline_edit(deadline_id: int, body: NewDeadline, user: dict = CurrentUser):
    """Правка дедлайна: свой личный — автор, общий (в т.ч. из СДО) —
    староста и зам для всех (автосинк СДО его больше не трогает), остальные
    — только у себя (deadline_mine, владелец 08.10)."""
    from database import can_see_deadline, edit_deadline, get_deadline, set_deadline_mine
    existing = await get_deadline(deadline_id)
    if not existing or not await can_see_deadline(existing, user["id"]):
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    subject, due, due_time, desc = _validate_deadline(body)
    if await _can_edit_deadline(existing, user["id"]):
        await edit_deadline(deadline_id, subject, desc, due, due_time)
        return {"ok": True, "id": deadline_id, "scope": "all"}
    await set_deadline_mine(user["id"], deadline_id, subject, desc, due, due_time)
    return {"ok": True, "id": deadline_id, "scope": "me"}


@router.delete("/api/deadlines/{deadline_id}")
async def api_deadline_delete(deadline_id: int, user: dict = CurrentUser):
    """Свой личный — автор, общий — староста и зам для всех; остальные
    убирают общий только у себя (у группы он остаётся)."""
    from database import can_see_deadline, delete_deadline, get_deadline, hide_deadline_for
    existing = await get_deadline(deadline_id)
    if not existing or not await can_see_deadline(existing, user["id"]):
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    if await _can_edit_deadline(existing, user["id"]):
        await delete_deadline(deadline_id)
        return {"ok": True, "scope": "all"}
    await hide_deadline_for(user["id"], deadline_id)
    return {"ok": True, "scope": "me"}


@router.delete("/api/deadlines/{deadline_id}/mine")
async def api_deadline_reset_mine(deadline_id: int, user: dict = CurrentUser):
    """«Вернуть как у всех»: снять свою правку общего дедлайна."""
    from database import reset_deadline_mine
    return {"ok": await reset_deadline_mine(user["id"], deadline_id)}


@router.get("/api/homework")
async def api_homework(user: dict = CurrentUser):
    """Доска ДЗ (/addhw в боте): свежие сверху. Файл ДЗ WebApp открывает
    диплинком в бота (t.me/<бот>?start=hw_<id>) — file_id наружу не отдаём."""
    from group_context import list_homework
    from database.groups import viewer_group
    import ugc
    items = ugc.without_hidden(await list_homework(60, await viewer_group(user["id"])),
                               await ugc.hidden(user["id"]), "created_by")
    return {"items": [
        {"id": h["id"], "subject": h["subject"], "content": h.get("content") or "",
         "lesson_date": h.get("lesson_date") or "", "created_at": (h.get("created_at") or "")[:10],
         "has_file": bool(h.get("file_id")), "mine": h.get("created_by") == user["id"]}
        for h in items
    ]}


@router.post("/api/homework/{hw_id}/send")
async def api_send_hw(hw_id: int, user: dict = CurrentUser):
    from handlers.start import send_hw_to
    import ratelimit
    if not ratelimit.allow("send", user["id"]):
        raise HTTPException(429, "Много файлов подряд — подожди минутку")
    if not await send_hw_to(deps.tg_bot(), user["id"], hw_id):
        raise HTTPException(404, "Файл ДЗ не найден")
    return {"ok": True}


class ToggleBody(BaseModel):
    done: bool


class RemindBody(BaseModel):
    preset: str | None = None      # 1d / 3h / 1h
    at: str | None = None          # своё время, «ГГГГ-ММ-ДДTЧЧ:ММ» (МСК)


async def _visible_deadline(deadline_id: int, user_id: int) -> dict:
    from database import get_active_deadlines
    for d in await get_active_deadlines(user_id, include_done=True):
        if d["id"] == deadline_id:
            return d
    raise HTTPException(status_code=404, detail="дедлайн не найден")


@router.post("/api/deadlines/{deadline_id}/remind")
async def api_deadline_remind(deadline_id: int, body: RemindBody, user: dict = CurrentUser):
    """Своё напоминание о дедлайне (deadline_reminders.py)."""
    import deadline_reminders
    from database import add_deadline_reminder, get_user_deadline_reminders
    d = await _visible_deadline(deadline_id, user["id"])
    try:
        at = deadline_reminders.resolve(d, body.preset, body.at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if len((await get_user_deadline_reminders(user["id"])).get(deadline_id, [])) >= 5:
        raise HTTPException(status_code=400, detail="хватит пяти напоминаний на дедлайн")
    await add_deadline_reminder(user["id"], deadline_id, at)
    return {"ok": True, "at": at, "label": deadline_reminders.label(at)}


@router.delete("/api/deadlines/{deadline_id}/remind")
async def api_deadline_unremind(deadline_id: int, at: str, user: dict = CurrentUser):
    from database import delete_deadline_reminder
    await delete_deadline_reminder(user["id"], deadline_id, at)
    return {"ok": True}


@router.post("/api/deadlines/{deadline_id}/toggle")
async def api_deadline_toggle(deadline_id: int, body: ToggleBody, user: dict = CurrentUser):
    from database import get_deadline, set_deadline_done
    existing = await get_deadline(deadline_id)
    if not existing:
        raise HTTPException(status_code=404, detail="дедлайн не найден")
    from database import can_see_deadline
    if not await can_see_deadline(existing, user["id"]):
        raise HTTPException(status_code=403, detail="это чужой дедлайн")
    # Персонально для user["id"] — не трогает статус остальных по этому же дедлайну.
    await set_deadline_done(deadline_id, user["id"], body.done)
    return {"ok": True, "id": deadline_id, "done": body.done}
