"""
Дедлайны СДО для других групп (этап 1 (в), PLAN.md «Своё приложение»).

У своей группы задания берутся по куке владельца (SDO_SESSION_COOKIE,
sdo_parser.sync_deadlines). Другой группе хватает одного человека: он
подключает свой вход в СДО (WebApp → СДО) и соглашается «делиться
дедлайнами с группой» (sdo_sessions.share). Его календарь СДО — это задания
всех его курсов, то есть всей группы. Бот берёт календарь по первому живому
входу (донору) и складывает задания общими дедлайнами группы
(sdo_parser.apply_items с group_id). Вход погас — следующий донор.
Предметы по выбору и чужие курсы отсекаются расписанием группы, как у своей.
"""

import logging

import sdo_net

logger = logging.getLogger(__name__)


async def _calendar_items(cookie: str) -> list[dict]:
    import sdo_parser
    from config import SDO_BASE_URL  # noqa: F401 — тот же СДО, что у своей группы
    async with sdo_net.client(cookie) as client:
        events = await sdo_parser.fetch_calendar_events(client)
    if events is None:
        raise RuntimeError("календарь СДО по AJAX недоступен")
    return sdo_parser.parse_calendar_events(events)


async def sync_group(group_id: int) -> dict:
    """Синк одной группы по её донорам. → итог apply_items или {"error"}."""
    import sdo_accounts
    import sdo_parser
    from database import get_group_donors
    from database.groups import home
    if group_id == home():
        return {"error": "своя группа синкается общим входом"}
    import sdo_check
    last = "нет входа, которым поделились"
    tried = False
    for donor in await get_group_donors(group_id):
        cookie = sdo_accounts.decrypt(donor["cookie_enc"])
        if not cookie:
            continue
        tried = True
        try:
            items = await _calendar_items(cookie)
        except sdo_parser.SdoSessionExpired as e:
            last = f"вход {donor['user_id']} погас: {e}"
            continue                                    # keepalive сам пометит и напишет человеку
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            continue
        res = await sdo_parser.apply_items(items, group_id=group_id)
        res["donor"] = donor["user_id"]
        await sdo_check.note(group_id, True)            # «СДО проверено в …» во вкладке «Сдать»
        logger.info(f"СДО группы {group_id}: +{res['added']}, обновлено {res['updated']}")
        return res
    if tried:
        await sdo_check.note(group_id, False)           # «СДО не ответил, показываю сроки от …»
    return {"error": last, "added": 0, "updated": 0, "new_ids": [], "moved": {}}


async def sync_all(bot=None) -> dict[int, dict]:
    """Все группы, где кто-то делится СДО; новые задания — людям группы."""
    import new_tasks
    from database import get_sharing_groups
    out = {}
    for gid in await get_sharing_groups():
        res = await sync_group(gid)
        out[gid] = res
        if bot and (res.get("new_ids") or res.get("moved")):
            try:
                await new_tasks.announce(bot, res["new_ids"], res["moved"])
            except Exception as e:
                logger.warning(f"новые задания группы {gid}: {e}")
    return out
