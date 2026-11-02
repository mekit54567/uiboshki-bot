"""
Тариф человека (PLAN.md «ИИ и подписка»): от него зависит только ИИ.

  own  — Никита (config.is_starosta) — без лимитов; своя группа (УИБО-03-24)
         без «Капибары+» — бесплатный лимит группы AI_DAILY_LIMIT;
  unl  — безлимит, выданный Никитой (/grant … unlimited): всё из «Капибары+»
         и ИИ без дневных лимитов;
  sub  — «Капибара+» (оплата, бонус или подарок своей группе до
         billing.GIFT_UNTIL): до AI_SUB_DAILY вопросов в день;
  base — все остальные: проба ИИ (ai_quota) и конспекты с недельным лимитом.

Своя группа с подарком живёт в лимитах подписки (Никита 17.10: «совсем без
лимита — не очень»); кончился подарок — снова own. Старосты групп
(group_admins) — в лимитах своей группы, без исключений.

Всё остальное — расписание, дедлайны, баллы СДО, файлы, поиск по лекциям —
бесплатно всем и от тарифа не зависит.
"""

OWN, UNL, SUB, BASE = "own", "unl", "sub", "base"
NAMES = {OWN: "своя группа", UNL: "безлимит", SUB: "подписка", BASE: "база"}


async def plan_of(user_id: int) -> str:
    """Никита → own (без лимитов), выданный безлимит → unl, «Капибара+» (и
    подарок своей группе) → sub, своя группа → own, остальные → base."""
    import billing
    import config
    import groups
    if config.is_starosta(user_id):
        return OWN
    if await billing.unlimited_for(user_id):
        return UNL
    if await has_plus(user_id):
        return SUB
    if await _own(user_id):
        return OWN
    if not groups.home_id():
        return OWN          # копия бота на одну группу (ICAL_URL без id) — тарифов нет
    return BASE


async def has_plus(user_id: int) -> bool:
    """Есть ли «Капибара+»: оплачена, бонусом, подарком своей группе до
    billing.GIFT_UNTIL или безлимитом от Никиты — для платных мелочей:
    иконки и скины «по подписке», значок, и для лимитов ИИ (sub)."""
    import billing
    from database import get_subscription
    from utils import today_msk
    until = await get_subscription(user_id)
    return (bool(until and until >= today_msk().isoformat()) or bool(await billing.gift_for(user_id))
            or bool(await billing.unlimited_for(user_id)))


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
