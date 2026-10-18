"""
«Подумать ещё» (Никита 17.10): второй уровень ИИ для «Капибара+».

Отвечает всем по-прежнему основная цепочка (Ling, Gemini). Под ответом у
подписчика — кнопка «Подумать ещё»: тот же вопрос с теми же лекциями заново
решает другая, более сильная модель — DeepSeek V4.1 Flash через OpenRouter
(платная, не «:free»: бесплатные провайдеры учатся на запросах, а у нас
152-ФЗ; и в запросе — только провайдеры без сбора данных).

Лимит — свой, даже у подписчиков: THINK_DAILY в день (по дню МСК, в
settings «ai_think:<дата>»), и потолок трат на всех за день AI_THINK_DAY_USD.
Попытка списывается заранее (две кнопки подряд не обгонят лимит) и
возвращается, если модель не ответила. Выключатель для отката — /aithink off
у старосты (settings «ai_think»). На iPhone кнопки нет (X-App: ios — как
иконки подписки: для первой модерации о платном в приложении ни слова).

«Подумать» сразу (Никита 18.10: «чтоб можно было выбрать перед ответом
сразу»): переключатель у поля ввода (приложение, Mini App), в боте — кнопка
в решалке и /think. Вопрос сразу решает MODEL, без первого обычного ответа
(solve(first=True)) — тот же лимит и та же модель, подпись «↪ «Подумать» —
ответил DeepSeek», обычный счёт ai_quota не трогается.
"""

import json
import logging
import os

import config

logger = logging.getLogger(__name__)

MODEL = os.getenv("AI_THINK_MODEL", "deepseek/deepseek-v4.1-flash").strip()
DAILY = int(os.getenv("AI_THINK_DAILY", "10") or 0)
DAY_USD = float(os.getenv("AI_THINK_DAY_USD", "3") or 0)    # на всех за день; 0 — без потолка
USD_RUB = float(os.getenv("USD_RUB", "82") or 82)
LECTURE_CHARS = 60_000          # лекций в запрос — не больше (цена: ~0,3 ₽ за ответ в худшем случае)
PRICE_IN, PRICE_OUT = 0.10, 0.55    # $ за 1M токенов — если OpenRouter не прислал цену

LABEL = "Подумать ещё"
NOTE = ("Это повторный ответ по кнопке «Подумать ещё»: студенту не хватило первого. Разбери вопрос "
        "внимательнее и глубже — по шагам, с проверкой вычислений и выводов, с примером, если он "
        "помогает. Не пересказывай прошлый ответ.")
NOTE_FIRST = ("Студент сразу попросил ответ «подумав»: разбери вопрос внимательно и глубоко — по шагам, "
              "с проверкой вычислений и выводов, с примером, если он помогает.")
FOOTER = "\n\n*↪ «Подумать ещё» — ответил DeepSeek.*"    # курсив — звёздочками: «_…_» md_to_tg_html не понимает
FOOTER_FIRST = "\n\n*↪ «Подумать» — ответил DeepSeek.*"
LIMIT_TEXT = "«Подумать ещё» на сегодня кончилось ({n} в день) — завтра снова"
BUDGET_TEXT = "«Подумать ещё» на сегодня закрыто — слишком много желающих. Завтра снова"
PLUS_TEXT = "«Подумать ещё» — в «Капибара+»"
OFF_TEXT = "«Подумать ещё» сейчас выключено"
FAIL_TEXT = "«Подумать ещё» не получилось ({why}) — попытка не списана, попробуй чуть позже"
MINUTE_TEXT = "слишком много вопросов подряд — подожди минуту"


class ThinkError(RuntimeError):
    """Понятная человеку причина, почему «Подумать ещё» не ответило."""


def _key(day=None) -> str:
    from utils import today_msk
    return f"ai_think:{(day or today_msk()).isoformat()}"


async def _load() -> dict:
    from database import get_setting
    try:
        data = json.loads(await get_setting(_key()) or "{}")
    except ValueError:
        data = {}
    data.setdefault("n", {})
    return data


async def _save(data: dict):
    from database import set_setting
    await set_setting(_key(), json.dumps(data))


async def switched_on() -> bool:
    from database import get_setting
    return (await get_setting("ai_think")) != "off"


async def enabled() -> bool:
    return bool(config.OPENROUTER_API_KEY and MODEL and DAILY > 0) and await switched_on()


async def used(uid: int) -> int:
    return int((await _load())["n"].get(str(uid), 0))


async def left(uid: int) -> int:
    return max(0, DAILY - await used(uid))


async def _unlimited(uid: int) -> bool:
    """Безлимит от Никиты (/grant … unlimited) — и здесь без дневного лимита
    (общий потолок трат за день остаётся)."""
    import plans
    return await plans.plan_of(uid) == plans.UNL


async def offer(uid: int, app: str = "") -> dict | None:
    """Кнопка под ответом: {"label", "left", "daily"} или None — не показывать
    (не подписчик, выключено, iPhone). left=None — без лимита (безлимит)."""
    import plans
    if (app or "").lower() == "ios" or not await enabled() or not await plans.has_plus(uid):
        return None
    return {"label": LABEL, "left": None if await _unlimited(uid) else await left(uid), "daily": DAILY}


async def why_not(uid: int) -> str | None:
    """Почему «Подумать» сейчас нельзя (для бота: /think, кнопка в решалке) —
    текст для человека; None — можно."""
    import plans
    if not await enabled():
        return OFF_TEXT
    if not await plans.has_plus(uid):
        return PLUS_TEXT
    if await left(uid) <= 0:
        return LIMIT_TEXT.format(n=DAILY)
    return None


def _cost(usage: dict) -> float:
    if usage.get("cost") is not None:
        return float(usage["cost"])
    return (usage.get("in", 0) * PRICE_IN + usage.get("out", 0) * PRICE_OUT) / 1e6


async def _reserve(uid: int, unlimited: bool = False):
    import locks
    async with locks.lock("ai_think"):
        data = await _load()
        n = int(data["n"].get(str(uid), 0))
        if n >= DAILY and not unlimited:
            raise ThinkError(LIMIT_TEXT.format(n=DAILY))
        if DAY_USD > 0 and float(data.get("cost", 0)) >= DAY_USD:
            raise ThinkError(BUDGET_TEXT)
        data["n"][str(uid)] = n + 1
        await _save(data)


async def _settle(uid: int, usage: dict | None):
    """usage=None — модель не ответила: попытку возвращаем."""
    import locks
    async with locks.lock("ai_think"):
        data = await _load()
        if usage is None:
            n = int(data["n"].get(str(uid), 0))
            data["n"][str(uid)] = max(0, n - 1)
        else:
            data["calls"] = int(data.get("calls", 0)) + 1
            data["cost"] = round(float(data.get("cost", 0)) + _cost(usage), 6)
            data["in"] = int(data.get("in", 0)) + usage.get("in", 0)
            data["out"] = int(data.get("out", 0)) + usage.get("out", 0)
        await _save(data)


async def solve(uid: int, history: list, subject: str = "", lectures: str = "", context: str = "",
                first: bool = False) -> str:
    """Тот же вопрос (history кончается вопросом) — моделью MODEL. Кидает
    ThinkError с текстом для человека; не ответила — попытка не списана.
    first — «Подумать» включили до вопроса: первого ответа не было."""
    import ai_solver
    import gemini_solver
    import plans
    import ratelimit
    if not await enabled():
        raise ThinkError(OFF_TEXT)
    if not await plans.has_plus(uid):
        raise ThinkError(PLUS_TEXT)
    if not ratelimit.allow("ai", uid):
        raise ThinkError(MINUTE_TEXT)
    await _reserve(uid, await _unlimited(uid))
    usage: dict = {}
    t_model = gemini_solver.forced_model.set(MODEL)
    t_usage = gemini_solver.ai_usage.set(usage)
    try:
        lectures = gemini_solver._fit_context_budget(lectures, LECTURE_CHARS)[0] if lectures else ""
        answer = await ai_solver.solve_with_history(history, subject, "gemini", lectures=lectures,
                                                    extra_system=(context + "\n\n" if context else "")
                                                    + (NOTE_FIRST if first else NOTE))
    except Exception as e:
        logger.warning(f"«Подумать ещё»: {MODEL} не ответил: {e!r}")
        await _settle(uid, None)
        why = str(e) if isinstance(e, RuntimeError) and str(e) else type(e).__name__
        raise ThinkError(FAIL_TEXT.format(why=why[:120].rstrip(".")))
    finally:
        gemini_solver.forced_model.reset(t_model)
        gemini_solver.ai_usage.reset(t_usage)
    await _settle(uid, usage)
    return answer + (FOOTER_FIRST if first else FOOTER)


async def status_line() -> str:
    """Строка для /status: сколько ответов сегодня и во что обошлись."""
    if not config.OPENROUTER_API_KEY:
        return "🧠 «Подумать ещё»: нет OPENROUTER_API_KEY"
    if not await switched_on():
        return "🧠 «Подумать ещё»: выключено (/aithink on)"
    data = await _load()
    cost = float(data.get("cost", 0))
    people = sum(1 for v in data["n"].values() if int(v) > 0)
    cap = f" из {DAY_USD:g} $" if DAY_USD > 0 else ""
    return (f"🧠 «Подумать ещё» ({MODEL}): сегодня {int(data.get('calls', 0))} отв., {people} чел., "
            f"{cost:.3f} ${cap} ≈ {cost * USD_RUB:.0f} ₽; лимит {DAILY} в день")
