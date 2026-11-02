"""
Вопросы к ИИ: минутный лимит (ratelimit «ai») и дневной — по тарифу
человека (plans.py, PLAN.md «ИИ и подписка»):

  own  — своя группа без «Капибары+»: config.AI_DAILY_LIMIT (0 — без него);
         Никите (config.is_starosta) — без лимитов, старостам групп — как всем;
  unl  — безлимит от Никиты (/grant): без дневных лимитов, конспекты тоже;
  sub  — «Капибара+», и подарок своей группе тоже: config.AI_SUB_DAILY;
  base — другие группы: проба AI_TRIAL_DAILY вопросов в день и не больше
         AI_TRIAL_DAY_TOTAL на всех за день (потолок пробы); новые конспекты —
         SUMMARY_WEEKLY в неделю (готовые читать — без лимита).

Счёт — по календарному дню МСК и в базе (settings «ai_day:<дата>», у пробы
ещё «ai_trial:<дата>», у конспектов — «ai_sum:<год-неделя>»): в памяти он
обнулялся бы на каждом деплое, а «сутки назад» не совпадали с обещанием
«завтра можно снова». Считаются все настоящие вопросы — ИИ-чат, решалка в
боте, фото, конспекты; классификатор намерений («покажи дедлайны») — только
минутным лимитом: это не вопрос к ИИ. По этим же цифрам /stats показывает
«ИИ сегодня».
"""

import json

import ratelimit

MINUTE_TEXT = "слишком много вопросов подряд — подожди минуту"
DAY_TEXT = ("на сегодня вопросы к ИИ кончились ({n} в сутки) — бесплатный лимит ИИ один на всю "
            "группу. Завтра можно снова")
TRIAL_TEXT = ("на сегодня пробные вопросы к ИИ кончились ({n} в день). Завтра можно снова, а без "
              "лимита ИИ будет в подписке — скоро")
# в приложении на iPhone о подписке не говорим (App Store 3.1.1, как billing: X-App: ios)
TRIAL_IOS_TEXT = "на сегодня пробные вопросы к ИИ кончились ({n} в день). Завтра можно снова"
TRIAL_ALL_TEXT = ("пробные вопросы к ИИ на сегодня кончились у всех — слишком много желающих. "
                  "Завтра можно снова")
SUB_TEXT = "на сегодня вопросы к ИИ кончились ({n} в сутки). Завтра можно снова"
SUMMARY_TEXT = ("новые конспекты на этой неделе кончились ({n} в неделю) — готовые открываются без "
                "лимита. Со следующей недели можно снова")


def _key(day=None) -> str:
    from utils import today_msk
    return f"ai_day:{(day or today_msk()).isoformat()}"


def _trial_key() -> str:
    from utils import today_msk
    return f"ai_trial:{today_msk().isoformat()}"


def _week_key() -> str:
    from utils import today_msk
    y, w, _ = today_msk().isocalendar()
    return f"ai_sum:{y}-{w:02d}"


async def _load(key: str) -> dict:
    from database import get_setting
    try:
        return json.loads(await get_setting(key) or "{}")
    except ValueError:
        return {}


async def today() -> dict[int, int]:
    """Вопросов к ИИ сегодня по людям."""
    return {int(k): int(v) for k, v in (await _load(_key())).items()}


async def summary() -> tuple[int, int]:
    """(вопросов сегодня всего, у самого активного) — одно на /stats и /status."""
    counts = await today()
    return sum(counts.values()), max(counts.values(), default=0)


async def take(user_id: int, kind: str = "ask") -> str | None:
    """Записать вопрос (kind="ask") или новый конспект (kind="summary").
    None — можно; иначе причина: "day", "trial", "trial_all", "sub", "summary"
    (тогда ничего не пишем)."""
    import config
    import locks
    import plans
    from database import set_setting
    plan = await plans.plan_of(user_id)
    async with locks.lock("ai_day"):
        counts = await today()
        n = counts.get(user_id, 0)
        if plan == plans.UNL:
            pass
        elif plan == plans.OWN:
            limit = 0 if config.is_starosta(user_id) else config.AI_DAILY_LIMIT
            if limit > 0 and n >= limit:
                return "day"
        elif plan == plans.SUB:
            if config.AI_SUB_DAILY > 0 and n >= config.AI_SUB_DAILY:
                return "sub"
        elif kind == "summary":
            week = await _load(_week_key())
            done = int(week.get(str(user_id), 0))
            if done >= config.SUMMARY_WEEKLY:
                return "summary"
            week[str(user_id)] = done + 1
            await set_setting(_week_key(), json.dumps(week))
        else:
            trial = await _load(_trial_key())
            if n >= config.AI_TRIAL_DAILY:
                return "trial"
            total = int(trial.get("total", 0))
            if config.AI_TRIAL_DAY_TOTAL > 0 and total >= config.AI_TRIAL_DAY_TOTAL:
                return "trial_all"
            await set_setting(_trial_key(), json.dumps({"total": total + 1}))
        counts[user_id] = n + 1
        await set_setting(_key(), json.dumps({str(k): v for k, v in counts.items()}))
    return None


async def left(user_id: int) -> dict | None:
    """Сколько вопросов к ИИ осталось сегодня: {"left", "limit"}; None —
    дневного лимита нет (Никита, безлимит, AI_DAILY_LIMIT=0). Для строки на пустом
    экране помощника в приложении — та же логика, что в take()."""
    import config
    import plans
    plan = await plans.plan_of(user_id)
    n = (await today()).get(user_id, 0)
    if plan == plans.UNL:
        return None
    if plan == plans.OWN:
        limit = 0 if config.is_starosta(user_id) else config.AI_DAILY_LIMIT
    elif plan == plans.SUB:
        limit = config.AI_SUB_DAILY
    else:
        limit = config.AI_TRIAL_DAILY
        total = int((await _load(_trial_key())).get("total", 0))
        if config.AI_TRIAL_DAY_TOTAL > 0 and total >= config.AI_TRIAL_DAY_TOTAL:
            return {"left": 0, "limit": limit}
    if limit <= 0:
        return None
    return {"left": max(0, limit - n), "limit": limit}


async def gate(user_id: int, day: bool = True, kind: str = "ask") -> str | None:
    """Можно ли спросить ИИ: None — можно (и вопрос записан, если day);
    иначе "minute" или причина из take()."""
    if not ratelimit.allow("ai", user_id):
        return "minute"
    if day:
        return await take(user_id, kind)
    return None


async def day_only(user_id: int) -> str | None:
    """Только дневной счёт — когда минутный уже проверен (классификатор)."""
    return await take(user_id)


def text(why: str, capital: bool = False, app: str = "") -> str:
    """Причина отказа человеку; app — заголовок X-App клиента."""
    import config
    t = {
        "day": DAY_TEXT.format(n=config.AI_DAILY_LIMIT),
        "trial": (TRIAL_IOS_TEXT if (app or "").lower() == "ios" else TRIAL_TEXT).format(n=config.AI_TRIAL_DAILY),
        "trial_all": TRIAL_ALL_TEXT,
        "sub": SUB_TEXT.format(n=config.AI_SUB_DAILY),
        "summary": SUMMARY_TEXT.format(n=config.SUMMARY_WEEKLY),
    }.get(why, MINUTE_TEXT)
    return t[:1].upper() + t[1:] if capital else t
