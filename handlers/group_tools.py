"""Группа: зам старосты (/setzam), рейтинг активности (/rating), здоровье
бота (/status), проверка Пульса (/pulsecheck), сети (/netcheck), векторов (/embedtest) и статистика (/stats) — у старосты."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import STAROSTA_ID, is_starosta
from database import init_hw_table, set_setting
from utils import esc, plural

router = Router()


@router.message(Command("setzam"))
async def cmd_setzam(message: Message):
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        await message.answer("❌ Только для старосты.")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Использование: /setzam ID (числовой Telegram ID, не @username)\n"
            "Например: /setzam 123456789"
        )
        return
    await init_hw_table()
    await set_setting("zam_id", parts[1])
    await message.answer(f"✅ Зам установлен: {parts[1]}")


# ── Рейтинг активности ────────────────────────────────────────────────────────

@router.message(Command("rating"))
async def cmd_rating(message: Message):
    from database import get_solver_rating
    rows = await get_solver_rating(10)

    if not rows:
        await message.answer("📊 Рейтинг пока пустой — никто ещё не решал задачи через бота.")
        return

    medals = ["🥇", "🥈", "🥉"] + ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = ["🏆 <b>Рейтинг активности</b>\n(по количеству решённых задач)\n"]

    for i, r in enumerate(rows):
        # f"@{username}" всегда truthy (даже "@None"/"@"), поэтому "Аноним"
        # раньше не показывался никогда — вместо него было "@None".
        name = r["full_name"] or (f"@{r['username']}" if r["username"] else "Аноним")
        lines.append(f"{medals[i]} {esc(name)} — {r['cnt']} {plural(r['cnt'], 'задача', 'задачи', 'задач')}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Здоровье бота (health.py): СДО, расписание, бэкап, ошибки — только староста."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    import health
    await message.answer(await health.report(), parse_mode="HTML")


@router.message(Command("aitest"))
async def cmd_aitest(message: Message):
    """Выбор модели ИИ для других групп (ai_bench.py) — только староста:
    /aitest — отбор многих моделей с оценкой судьёй; /aitest id1 id2 — отбор
    только этих; /aitest list — кто попадёт и почём, без прогона;
    /aitest vote id1 id2 — слепое голосование финалистов."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    from config import OPENROUTER_API_KEY
    if not OPENROUTER_API_KEY:
        await message.answer("Нужен ключ OpenRouter: openrouter.ai → Credits (пополнить), Keys → Create, "
                             "и задать OPENROUTER_API_KEY в переменных Railway.")
        return
    import ai_bench
    from webapp.routes.aitest import link
    args = (message.text or "").split()[1:]
    mode = args.pop(0) if args and args[0] in ("list", "vote") else "screen"
    if mode == "vote" and len(args) < 2:
        await message.answer("Кого сравнить вслепую: /aitest vote id1 id2 … (id — со страницы отбора).")
        return
    if ai_bench._lock.locked():
        await message.answer("Прогон уже идёт — дождись итога.")
        return
    async with ai_bench._lock:
        try:
            plan = await ai_bench.prepare(OPENROUTER_API_KEY, args or None, intents=mode != "vote")
        except Exception as e:
            await message.answer(f"Не вышло: {e}")
            return
        if mode == "list":
            await message.answer(plan["text"] + "\n\nЗапустить: /aitest")
            return
        await message.answer(f"🧪 {plan['text']}\n\nГоняю — это минут 15–20, пришлю ссылку.")
        try:
            html, summary = await (ai_bench.vote if mode == "vote" else ai_bench.screen)(OPENROUTER_API_KEY, plan)
        except Exception as e:
            await message.answer(f"Не вышло: {e}")
            return
        kind = "vote" if mode == "vote" else "report"
        await ai_bench.save(html, kind, plan.get("key"))
    hint = ("Открой и в каждом блоке выбери лучший ответ, модели — в конце. Выбор — на сервере; "
            "скинь ссылку Claude, итог он посмотрит сам:" if kind == "vote"
            else "Таблица и все ответы с баллами:")
    await message.answer(f"{summary}\n\n{hint}\n{link(kind)}")


@router.message(Command("sub"))
async def cmd_sub(message: Message):
    """/sub <id> <дней> — выдать подписку вручную (0 дней — снять); без
    аргументов — тариф и группа своего аккаунта. Только староста (plans.py)."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    from datetime import timedelta
    import groups
    import plans
    from database import set_subscription_until
    from utils import today_msk
    args = (message.text or "").split()[1:]
    if len(args) != 2 or not all(a.lstrip("-").isdigit() for a in args):
        g = await groups.of_user(message.from_user.id)
        await message.answer(f"Тариф: {plans.NAMES[await plans.plan_of(message.from_user.id)]}, группа: "
                             f"{g['name'] if g else 'не выбрана'}.\n/sub <id> <дней> — выдать подписку, 0 — снять.")
        return
    uid, days = int(args[0]), int(args[1])
    until = (today_msk() + timedelta(days=days)).isoformat() if days > 0 else None
    await set_subscription_until(uid, until)
    await message.answer(f"Подписка {uid}: " + (f"до {until}" if until else "снята"))


@router.message(Command("embedtest"))
async def cmd_embedtest(message: Message):
    """Своя модель векторов против Gemini на лекциях группы (embed_bench.py) —
    только староста. /embedtest — все модели, /embedtest ключ… — выбранные."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    import embed_bench
    import local_embed
    keys = [k for k in (message.text or "").split()[1:] if k in local_embed.MODELS] or None
    if embed_bench._lock.locked():
        await message.answer("Тест уже идёт — дождись итога.")
        return
    async with embed_bench._lock:
        await message.answer("🧪 Сравниваю свои модели векторов с Gemini на лекциях группы — "
                             "пара минут, модели скачиваются при первом запуске.")
        try:
            text = await embed_bench.run(keys)
        except Exception as e:
            text = f"Не вышло: {type(e).__name__}: {e}"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("netcheck"))
async def cmd_netcheck(message: Message):
    """Кто отвечает серверу бота и каким путём (net_check.py) — только староста."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    import net_check
    await message.answer(net_check.text(await net_check.check(message.bot)), parse_mode="HTML")


@router.message(Command("pulsecheck"))
async def cmd_pulsecheck(message: Message):
    """Пускает ли pulse.mirea.ru сервер бота (pulse_check.py) — только староста."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    import pulse_check
    await message.answer(pulse_check.text(await pulse_check.check()))



STATS_PERIODS = (7, 30, 180)


def _stats_kb(days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("• " if d == days else "") + {7: "7 дней", 30: "30 дней", 180: "семестр"}[d],
                              callback_data=f"stats:{d}") for d in STATS_PERIODS],
        [InlineKeyboardButton(text="👥 Кто пользуется", callback_data=f"stats:people:{days}")],
    ])


async def _send_stats(bot, chat_id: int, days: int):
    import stats
    from aiogram.types import BufferedInputFile
    png, text = await stats.report(days)
    await bot.send_photo(chat_id, BufferedInputFile(png, filename=f"stats_{days}.png"),
                         caption=text, parse_mode="HTML", reply_markup=_stats_kb(days))


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Статистика бота картинкой (stats.py) — только староста."""
    if STAROSTA_ID and not is_starosta(message.from_user.id):
        return
    await _send_stats(message.bot, message.chat.id, 30)


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats(callback: CallbackQuery):
    if STAROSTA_ID and not is_starosta(callback.from_user.id):
        await callback.answer()
        return
    parts = callback.data.split(":")
    if parts[1] == "people":
        # «кто пользуется»: имена и ники, когда и чем — без содержимого (stats.people)
        import stats
        days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 30
        await callback.answer()
        text = stats.people_text(await stats.people(days if days in STATS_PERIODS else 30))
        await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
        return
    days = int(parts[1]) if parts[1].isdigit() else 30
    await callback.answer("Считаю…")
    await _send_stats(callback.bot, callback.message.chat.id, days if days in STATS_PERIODS else 30)
