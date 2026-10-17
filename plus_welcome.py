"""Одно сообщение «У тебя активна «Капибара+»» (Никита 17.10): своей группе с
подарком — при первом заходе после выпуска (сообщение боту или запрос из
приложения — middleware.StatsMiddleware, webapp/deps.get_current_user), не
рассылкой; тот же текст со сроком — тому, кому Никита выдал вручную (/grant,
plus_grant.py). Отметка «отправлено» — таблица plus_welcome, по разу на
человека. Доставка — delivery.deliver (Telegram и веб-пуш), в iPhone-
приложении о подписке ни слова (App Store 3.1.1) — туда не идёт."""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

AUTO = True                    # тесты выключают (conftest): своё приветствие только где проверяют
AI_THINK_DAILY = int(os.getenv("AI_THINK_DAILY", "10") or 0)   # «Подумать ещё» — свой лимит (другой PR)

_checked: set[int] = set()     # кого уже проверили в этом процессе — в базу второй раз не ходим
_tasks: set = set()


def _day(iso: str) -> str:
    from datetime import date
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def text(until: str | None, *, granted: bool = False, unlimited: bool = False) -> str:
    """until — последний день (None — навсегда, только у безлимита)."""
    import config
    term = f"до {_day(until)}" if until else "навсегда"
    if unlimited:
        head = f"✨ Тебе выдали безлимит: «Капибара+» {term} — бесплатно, и ИИ без дневных лимитов."
        limits = ["🤖 Вопросы к ИИ, решалка, фото и конспекты — без дневного лимита",
                  "💭 «Подумать ещё» — тоже без лимита"]
    else:
        head = (f"✨ Тебе продлили «Капибару+»: активна {term} — бесплатно." if granted else
                f"✨ У тебя активна «Капибара+» {term} — бесплатно.")
        limits = [f"🤖 {config.AI_SUB_DAILY} вопросов к ИИ в день — чат, решалка, фото, конспекты",
                  f"💭 Кнопка «Подумать ещё» — {AI_THINK_DAILY} в день"]
    return "\n".join([head, "", "<b>Что входит:</b>", *limits,
                      "🎨 Иконки и наряды капибары «по подписке», значок «друг Капибары»",
                      "📅 Расписание, дедлайны, баллы СДО и файлы — как и были, без лимитов",
                      "", "Подробнее — /plus"])


async def mark(uid: int) -> bool:
    from database.billing import mark_welcome
    _checked.add(uid)
    return await mark_welcome(uid)


async def maybe_send(bot, uid: int) -> bool:
    """Подарок своей группе действует, а приветствия ещё не было — прислать.
    True — отправили сейчас."""
    import billing
    import privacy
    from database.billing import welcomed
    if bot is None or await welcomed(uid) or await privacy.blocked(uid):
        return False
    st = await billing.status(uid)
    if not st["gift"] or st["unlimited"]:
        return False
    if not await mark(uid):
        return False                         # параллельный запрос успел первым
    await billing.notify(bot, uid, text(st["until"]))
    return True


def later(bot, uid: int):
    """Проверить в фоне при первом заходе в этом процессе (не задерживая ответ)."""
    if not AUTO or bot is None or uid in _checked:
        return
    _checked.add(uid)

    async def run():
        try:
            await maybe_send(bot, uid)
        except Exception as e:
            logger.info(f"приветствие «Капибары+» {uid}: {type(e).__name__}: {e}")
    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
