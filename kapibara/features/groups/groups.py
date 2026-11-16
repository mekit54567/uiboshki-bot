"""
Любая группа института (этап 1, PLAN.md «Своё приложение»).

Группа человека — id группы на зеркале расписания МИРЭА (тот же, что в
english.mirea.ru/schedule/api/ical/1/<id>; справочник имён — schedule_index).
«Своя» группа (config.HOME_GROUP_ID, из ICAL_URL) — та, для которой бот
делался: у неё всё как раньше. Кто был в боте до этапа 1, записан в свою
группу миграцией; новые выбирают группу при первом входе (/start, WebApp).
"""

import logging

logger = logging.getLogger(__name__)

MIRROR = "https://english.mirea.ru/schedule/api/ical/1/{id}"


def home_id() -> int:
    from kapibara.core.config import HOME_GROUP_ID
    return HOME_GROUP_ID


def ical_url(group_id: int) -> str:
    """Календарь группы; для своей — ICAL_URL как есть (его можно переопределить)."""
    from kapibara.core.config import ICAL_URL
    return ICAL_URL if group_id == home_id() else MIRROR.format(id=int(group_id))


async def ensure_home():
    """Своя группа в справочнике групп (при старте бота)."""
    from kapibara.core.config import GROUP_NAME
    from database import upsert_group
    if home_id():
        await upsert_group(home_id(), GROUP_NAME, own=True)


# Латиница → кириллица для названий групп (05.11): проверяющий App Store и
# иностранцы пишут «UIBO-03-24», а то и забыли переключить раскладку
# («eb,j» = «уибо»). Названия групп МИРЭА — кириллица, буквы читаются по одной.
_TRANSLIT = dict(zip("abvgdezijklmnoprstufhcy", "абвгдезийклмнопрстуфхцы", strict=True))
_LAYOUT = dict(zip("qwertyuiop[]asdfghjkl;'zxcvbnm,.`", "йцукенгшщзхъфывапролджэячсмитьбюё", strict=True))


def _cyrillic_variants(q: str) -> list[str]:
    """Как ещё мог иметься в виду запрос с латиницей: по буквам и по раскладке."""
    low = q.lower()
    if not any("a" <= ch <= "z" for ch in low):
        return []
    out = []
    for table in (_TRANSLIT, _LAYOUT):
        v = "".join(table.get(ch, ch) for ch in low)
        if v != low and v not in out:
            out.append(v)
    return out


async def search(query: str, limit: int = 8) -> list[dict]:
    """Группы по названию (справочник schedule_index): [{id, name}].
    Латиницей тоже находит: «uibo-03» и «eb,j» → УИБО…"""
    from kapibara.features.schedule import index as schedule_index
    q = (query or "").strip()
    if len(q) < 2:
        return []
    items: list[dict] = []
    for variant in (q, *_cyrillic_variants(q)):
        for r in await schedule_index.search(variant, (1,), limit):
            if len(items) < limit and all(it["id"] != r["id"] for it in items):
                items.append({"id": r["id"], "name": r["title"]})
    return items


async def name_of(group_id: int | None) -> str:
    from database import get_group
    if not group_id:
        return ""
    g = await get_group(group_id)
    return g["name"] if g else ""


async def of_user(user_id: int) -> dict | None:
    """{id, name, own} группы человека или None (ещё не выбрал)."""
    from database import get_group, get_user_group
    gid = await get_user_group(user_id)
    if not gid:
        return None
    g = await get_group(gid)
    return {"id": gid, "name": g["name"] if g else "", "own": bool(g and g["own"]) or gid == home_id()}


HOME_ONLY_MEMBERS = "в эту группу — только участники её чата в Telegram. Попроси старосту добавить тебя в чат"


async def choose(user_id: int, group_id: int, bot=None) -> dict | None:
    """Записать человека в группу. None — такой группы нет в справочнике;
    {"denied": …} — своя группа, а человек не в её чате (members.py)."""
    from kapibara.features.schedule import index as schedule_index
    from database import set_user_group, upsert_group
    group_id = int(group_id)
    if group_id == home_id():
        from kapibara.features.groups import members
        if await members.is_member(user_id, bot) is False:
            return {"denied": HOME_ONLY_MEMBERS}
        await ensure_home()
        name = await name_of(group_id)
    else:
        title = await schedule_index.get_title(1, group_id)
        if not title:
            return None
        name = title
        await upsert_group(group_id, name)
    await set_user_group(user_id, group_id)
    logger.info(f"группа: {user_id} → {name} ({group_id})")
    return {"id": group_id, "name": name, "own": group_id == home_id()}


async def in_home_group(user_id: int) -> bool:
    """Человек — из своей группы бота (тариф own, подарок «Капибары+»):
    староста, участник чата группы или выбрал её (и не вышел из чата).
    Жило в billing/plans._own (03.11): его спрашивает и сама оплата."""
    from kapibara.core import config
    from database import get_user_group
    if config.is_starosta(user_id):
        return True
    if not home_id():
        return False
    from database import members
    member = await members.known(user_id)
    if member:              # в чате своей группы — своя, какую бы группу ни выбрал (владелец 09.10)
        return True
    gid = await get_user_group(user_id)
    if gid and gid == home_id():
        return member is not False
    if gid:
        from database import get_group
        g = await get_group(gid)
        if g and g["own"]:
            return True
    return False
