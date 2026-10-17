"""
Тариф человека (PLAN.md «ИИ и подписка»): от него зависит только ИИ.

  own  — своя группа (УИБО-03-24) и старосты: ИИ как раньше (AI_DAILY_LIMIT);
  sub  — подписка (subscriptions.until не прошла): до AI_SUB_DAILY в день;
  base — все остальные: проба ИИ (ai_quota) и конспекты с недельным лимитом.

Всё остальное — расписание, дедлайны, баллы СДО, файлы, поиск по лекциям —
бесплатно всем и от тарифа не зависит.
"""

OWN, SUB, BASE = "own", "sub", "base"
NAMES = {OWN: "своя группа", SUB: "подписка", BASE: "база"}


async def plan_of(user_id: int) -> str:
    """Своя группа важнее подписки: у своей ИИ без дневного лимита, а
    подписка дала бы AI_SUB_DAILY (своим ничего не урезаем)."""
    import groups
    if await _own(user_id):
        return OWN
    if await has_plus(user_id):
        return SUB
    if not groups.home_id():
        return OWN          # копия бота на одну группу (ICAL_URL без id) — тарифов нет
    return BASE


async def has_plus(user_id: int) -> bool:
    """Оплачена ли «Капибара+» (или подарена: бонусом или своей группе до
    billing.GIFT_UNTIL) — для платных мелочей: иконки и скины «по подписке»,
    значок. Своей группе ИИ и так бесплатно."""
    import billing
    from database import get_subscription
    from utils import today_msk
    until = await get_subscription(user_id)
    return bool(until and until >= today_msk().isoformat()) or bool(await billing.gift_for(user_id))


async def _own(user_id: int) -> bool:
    import config
    import groups
    from database import get_user_group
    if config.is_starosta(user_id):
        return True
    if not groups.home_id():
        return False
    import members
    member = await members.known(user_id)
    if member:              # в чате своей группы — своя, какую бы группу ни выбрал (владелец 09.10)
        return True
    gid = await get_user_group(user_id)
    if gid and gid == groups.home_id():
        return member is not False
    if gid:
        from database import get_group
        g = await get_group(gid)
        if g and g["own"]:
            return True
    return False
