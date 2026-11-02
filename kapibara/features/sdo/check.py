"""
Чем кончилась последняя проверка СДО у группы — для вкладки «Сдать»
(дизайн 5.79, «Пусто и ошибка»): «СДО проверено в 12:40» или «СДО не
ответил, показываю сроки от 09:41».

Общие сроки группы берутся одним синком (своя группа — кука владельца,
scheduler.sync_sdo_deadlines; другие — по входу, которым поделились,
group_sync.sync_group), поэтому и состояние — у группы, а не у человека:
свой вход студента в СДО список сроков не наполняет.

Лежит в settings, ключ ``sdo_check:<группа>``:
{"at": когда проверяли, "ok": получилось ли, "last_ok": когда получилось в последний раз}.
"""

import json
import logging
from datetime import datetime

from health import TZ

logger = logging.getLogger(__name__)


def _key(group_id: int) -> str:
    return f"sdo_check:{int(group_id)}"


async def note(group_id: int, ok: bool):
    """Запомнить итог проверки; при сбое прошлый удачный раз остаётся."""
    from database import get_setting, set_setting
    try:
        at = datetime.now(TZ).isoformat()
        last_ok = at if ok else (_load(await get_setting(_key(group_id))) or {}).get("last_ok")
        await set_setting(_key(group_id), json.dumps({"at": at, "ok": ok, "last_ok": last_ok}))
    except Exception as e:
        logger.info(f"sdo_check.note {group_id}: {e}")


async def note_home(result: dict):
    """Итог sdo_parser.sync_deadlines своей группы. Нет куки — не проверяли."""
    from database.groups import home
    if result.get("missing"):
        return
    await note(home(), "error" not in result and not result.get("expired"))


def _load(raw: str | None) -> dict | None:
    try:
        v = json.loads(raw) if raw else None
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


async def state(group_id: int | None) -> dict | None:
    """{"ok", "checked_at", "last_ok"} или None — группу не проверяли (нет СДО)."""
    from database import get_setting
    from database.groups import home
    if not group_id:
        return None
    s = _load(await get_setting(_key(group_id)))
    if s is None and group_id == home():
        # до 5.80 итог своей группы был только в /status (health:sdo_sync)
        h = _load(await get_setting("health:sdo_sync"))
        if h and h.get("at"):
            s = {"at": h["at"], "ok": bool(h.get("ok")), "last_ok": h["at"] if h.get("ok") else None}
    if not s or not s.get("at"):
        return None
    return {"ok": bool(s.get("ok")), "checked_at": s["at"], "last_ok": s.get("last_ok")}
