"""Посты канала бота (/channel у старосты): список, точное превью в личку и
кнопка «В канал». Сами посты и отправка — channel_posts.py.
/channel redo — убрать из канала всё, что бот уже опубликовал, и выпустить
заново (например, когда поменялся вид постов). Закреп бот закрепляет сам.
/channel edit 1 4 6 — поправить уже выпущенные посты текстом из репозитория
(обложка, комментарии и просмотры остаются)."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from kapibara.core import config
from kapibara.core.config import is_starosta
from kapibara.core.utils import esc
from kapibara.core.errors import EXTERNAL
from kapibara.bot.tg import bot_of, data_of, msg, sender
from aiogram.exceptions import TelegramAPIError

router = Router()


def _chan(slug: str) -> str:
    """Какой канал у поста: «news» — открытый канал Капибары, иначе — разработка."""
    from kapibara.features.content.channel_posts import channel_of
    return channel_of(slug)


CHAN_NAMES = {"news": "Капибара", "dev": "Разработка"}


def _next_in(posts, chan: str, after: int = -1, done=None) -> int | None:
    """Следующий пост того же канала после номера after (done — только не выпущенные)."""
    return next((i for i, p in enumerate(posts)
                 if i > after and _chan(p["slug"]) == chan and (done is None or p["slug"] not in done)), None)


def _kb(slug: str, done: bool, other: str = "") -> InlineKeyboardMarkup:
    first = (InlineKeyboardButton(text="✅ Уже в канале", callback_data="chan:noop") if done
             else InlineKeyboardButton(text="📣 В канал", callback_data=f"chan:pub:{slug}"))
    rows = [[first, InlineKeyboardButton(text="Следующий ▸", callback_data=f"chan:next:{slug}")]]
    if other:          # Никита 05.11: листать посты по каналам — кнопка в другой канал
        rows.append([InlineKeyboardButton(text=f"↔ Канал «{CHAN_NAMES[other]}»", callback_data=f"chan:other:{slug}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _list_text(posts, done) -> str:
    from kapibara.features.identity import login_channel
    where = {"dev": esc(config.CHANNEL_ID) if config.CHANNEL_ID else "⚠️ не задан — CHANNEL_URL или CHANNEL_ID",
             "news": esc(login_channel.channel()) or "⚠️ не задан — LOGIN_CHANNEL"}
    parts = []
    for chan in ("news", "dev"):
        mine = [(i, p) for i, p in enumerate(posts) if _chan(p["slug"]) == chan]
        if not mine:
            continue
        out = sum(p["slug"] in done for _, p in mine)        # вышедшие — одной строкой, не списком
        lines = [f"▫️ <code>{i + 1}</code> {esc(p['title'])}" for i, p in mine if p["slug"] not in done]
        head = f"<b>{CHAN_NAMES[chan]}</b> · {where[chan]}" + (f" · уже вышло {out}" if out else "")
        parts.append(head + "\n" + ("\n".join(lines) if lines else "все вышли ✅"))
    return ("📣 <b>Посты каналов</b> — ждут выпуска, по порядку сверху вниз\n\n" + "\n\n".join(parts) +
            "\n\nКак выпускать: под превью жми «📣 В канал», потом «Следующий ▸» — следующий пост этого же "
            "канала. «↔ Канал …» — перейти в другой канал. <code>/channel N</code> — пост по номеру.\n"
            "⏱ <code>/channel auto</code> — выпустить всё само по очереди.")


async def _preview(bot, chat_id, posts, idx, done):
    from kapibara.features.content.channel_posts import check, send_post
    post = posts[idx]
    problem = check(post)
    if problem:
        await bot.send_message(chat_id, f"⚠️ Пост {idx + 1} «{esc(post['title'])}»: {esc(problem)}", parse_mode="HTML")
        return
    try:
        await send_post(bot, chat_id, post, config.WEBAPP_URL)
    except (*EXTERNAL, OSError, ValueError) as e:  # битая разметка поста — понятным текстом, а не общим алертом
        await bot.send_message(chat_id, f"⚠️ Пост {idx + 1} «{esc(post['title'])}» не отправился: "
                               f"{esc(str(e))[:300]}", parse_mode="HTML")
        return
    chan = _chan(post["slug"])
    other = "dev" if chan == "news" else "news"
    has_other = any(_chan(p["slug"]) == other for p in posts)
    await bot.send_message(chat_id, f"👆 Превью · пост {idx + 1} из {len(posts)} · канал «{CHAN_NAMES[chan]}»",
                           reply_markup=_kb(post["slug"], post["slug"] in done, other if has_other else ""))


async def offer_next(bot) -> str | None:
    """После деплоя (запуск бота): старосте — превью следующего ещё не
    выпущенного поста с кнопкой «В канал». Один раз на пост: запомненные в
    channel:offered не повторяются. Публикация — только по кнопке.
    → slug предложенного поста или None."""
    import json
    from kapibara.core.config import STAROSTA_ID
    from kapibara.features.content.channel_posts import load_posts, published, target
    from database import get_setting, set_setting
    if not STAROSTA_ID:
        return None
    posts, done = load_posts(), await published()
    idx = next((i for i, p in enumerate(posts) if p["slug"] not in done and target(p["slug"])), None)
    if idx is None:
        return None
    try:
        offered = set(json.loads(await get_setting("channel:offered") or "[]"))
    except ValueError:
        offered = set()
    slug = posts[idx]["slug"]
    if slug in offered:
        return None
    await bot.send_message(STAROSTA_ID, f"🆕 Готов пост для канала — «{esc(posts[idx]['title'])}». Превью ниже, "
                           "в канал уйдёт только по кнопке.", parse_mode="HTML")
    await _preview(bot, STAROSTA_ID, posts, idx, done)
    offered.add(slug)
    await set_setting("channel:offered", json.dumps(sorted(offered), ensure_ascii=False))
    return slug


@router.message(Command("channel"))
async def cmd_channel(message: Message):
    if not is_starosta(sender(message).id):
        await message.answer("❌ Только для старосты.")
        return
    from kapibara.features.content.channel_posts import load_posts, published
    posts, done = load_posts(), await published()
    if (message.text or "").split()[1:2] == ["redo"]:
        n = len(done)
        if not n:
            await message.answer("В канале пока нет постов от бота — нечего перевыпускать.")
            return
        await message.answer(
            f"Убрать из канала {n} пост(ов), которые выпустил бот, и выпустить заново в новом виде?\n"
            "Комментарии к ним пропадут. Дальше — /channel, как в первый раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🗑 Убрать и перевыпустить", callback_data="chan:redo:yes")]]))
        return
    if not posts:
        await message.answer("Постов пока нет — они лежат в репозитории, channel/posts/.")
        return
    if (message.text or "").split()[1:2] == ["edit"]:
        await _edit(message, posts, done)
        return
    if (message.text or "").split()[1:2] == ["auto"]:
        await _auto(message)
        return
    await message.answer(await _list_text(posts, done), parse_mode="HTML")
    arg = (message.text or "").split()[1:2]
    idx: int | None
    if arg and arg[0].isdigit() and 1 <= int(arg[0]) <= len(posts):
        idx = int(arg[0]) - 1
    elif arg and arg[0] in CHAN_NAMES:
        idx = _next_in(posts, arg[0], done=done)
        if idx is None:
            await message.answer(f"В канале «{CHAN_NAMES[arg[0]]}» все посты уже вышли 🎉")
            return
    else:
        idx = next((i for i, p in enumerate(posts) if p["slug"] not in done), None)
        if idx is None:
            await message.answer("Все посты уже в канале 🎉")
            return
    await _preview(message.bot, message.chat.id, posts, idx, done)


async def _edit(message: Message, posts: list, done: dict):
    """/channel edit 1 4 6 — поправить выпущенные посты (номера как в
    /channel) текстом из репозитория, с той же обложкой. Комментарии и
    просмотры остаются, в отличие от /channel redo."""
    from kapibara.features.content.channel_posts import edit_post, target
    nums = [int(x) for x in (message.text or "").split()[2:] if x.isdigit()]
    if not nums:
        await message.answer("Какие посты поправить? Номера — как в /channel: <code>/channel edit 1 4 6</code>",
                             parse_mode="HTML")
        return
    lines = []
    for n in nums:
        if not 1 <= n <= len(posts):
            lines.append(f"▫️ {n} — такого поста нет")
            continue
        post = posts[n - 1]
        ids = (done.get(post["slug"]) or {}).get("ids")
        if not ids:
            lines.append(f"▫️ {n} «{esc(post['title'])}» — ещё не в канале")
            continue
        res = await edit_post(message.bot, target(post["slug"]), post, ids, config.WEBAPP_URL)
        mark = {"ok": "✅", "same": "➖"}.get(res, "⚠️")
        note = {"ok": "поправлен", "same": "уже такой"}.get(res, esc(res)[:200])
        lines.append(f"{mark} {n} «{esc(post['title'])}» — {note}")
    await message.answer("✏️ <b>Правка постов в канале</b>\n\n" + "\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("chan:"))
async def channel_button(callback: CallbackQuery):
    if not is_starosta(callback.from_user.id):
        await callback.answer("Только для старосты", show_alert=True)
        return
    from kapibara.features.content.channel_posts import forget_published, load_posts, published, target
    _, action, *rest = data_of(callback).split(":", 2)
    slug = rest[0] if rest else ""
    posts, done = load_posts(), await published()
    if action == "auto":
        await _auto_button(callback, slug)
        return
    if action == "redo":
        by_chat: dict[str, list[int]] = {}
        for done_slug, v in done.items():
            by_chat.setdefault(target(done_slug), []).extend(v.get("ids", []))
        try:
            for chat, ids in by_chat.items():
                for k in range(0, len(ids), 100):
                    await bot_of(callback).delete_messages(chat, ids[k:k + 100])
        except TelegramAPIError as e:
            await callback.answer("Не вышло удалить", show_alert=True)
            await msg(callback).answer(f"⚠️ Не удалил: {esc(str(e))[:300]}\n"
                                          "Удали посты в канале руками, потом снова /channel redo.", parse_mode="HTML")
            return
        await forget_published()
        await msg(callback).edit_reply_markup(reply_markup=None)
        await msg(callback).answer(f"🗑 Убрал из канала {len(done)} пост(ов). Теперь /channel — выпускаем заново.")
        await callback.answer()
        return
    idx = next((i for i, p in enumerate(posts) if p["slug"] == slug), None)
    if action == "noop" or idx is None:
        await callback.answer("Уже в канале" if action == "noop" else "Такого поста больше нет")
        return
    if action == "next":                       # следующий — в том же канале
        await callback.answer()
        nxt = _next_in(posts, _chan(slug), idx)
        if nxt is None:
            await msg(callback).answer(f"Это был последний пост канала «{CHAN_NAMES[_chan(slug)]}».")
            return
        await _preview(callback.bot, msg(callback).chat.id, posts, nxt, done)
        return
    if action == "other":                      # в другой канал: его следующий не выпущенный (или первый)
        await callback.answer()
        other = "dev" if _chan(slug) == "news" else "news"
        nxt = _next_in(posts, other, done=done)
        nxt = _next_in(posts, other) if nxt is None else nxt
        if nxt is not None:
            await _preview(callback.bot, msg(callback).chat.id, posts, nxt, done)
        return
    # action == "pub"
    from kapibara.features.content.channel_posts import publish
    try:
        ids, link, pin_error = await publish(callback.bot, slug, config.WEBAPP_URL)
    except ValueError as e:                   # канал не задан
        await callback.answer(str(e)[:190], show_alert=True)
        return
    except (*EXTERNAL, OSError) as e:
        await callback.answer("Не вышло — бот админ канала?", show_alert=True)
        await msg(callback).answer(f"⚠️ Не опубликовал: {esc(str(e))[:300]}\n"
                                      "Проверь, что бот — админ канала с правом публиковать.", parse_mode="HTML")
        return
    if not ids:
        await callback.answer("Этот пост уже в канале", show_alert=True)
        return
    if pin_error:
        await msg(callback).answer(f"Не закрепил сам ({esc(pin_error)}) — закрепи руками.", parse_mode="HTML")
    await msg(callback).edit_reply_markup(reply_markup=_kb(slug, True))
    await msg(callback).answer(f"✅ В канале: «{esc(posts[idx]['title'])}»" + (f"\n{link}" if link else ""),
                                  parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                      InlineKeyboardButton(text="Следующий ▸", callback_data=f"chan:next:{slug}")]]))
    await callback.answer("Опубликовано")


# ── Очередь: всё само по очереди (Никита 05.11, channel_queue.py) ──────────

def _queue_text(items: list[dict], posts: list[dict], head: str) -> str:
    from kapibara.features.content import channel_queue
    titles = {p["slug"]: p["title"] for p in posts}
    parts = []
    for chan in ("news", "dev"):
        lines = [f"{channel_queue.when(it['at'])} — {esc(titles.get(it['slug'], it['slug']))}"
                 for it in items if _chan(it["slug"]) == chan]
        if lines:
            parts.append(f"<b>{CHAN_NAMES[chan]}</b>\n" + "\n".join(lines))
    return head + "\n\n" + "\n\n".join(parts)


async def _auto(message: Message):
    """/channel auto — что в очереди (и «Отменить») или план и «Запустить»."""
    from kapibara.features.content import channel_queue
    from kapibara.features.content.channel_posts import load_posts, published
    from datetime import datetime
    from kapibara.core.utils import TZ
    posts = load_posts()
    items = await channel_queue.load()
    if items:
        await message.answer(_queue_text(items, posts, "⏱ <b>Очередь постов</b> — выйдут сами, время по Москве:"),
                             parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                 InlineKeyboardButton(text="⏹ Отменить очередь", callback_data="chan:auto:stop")]]))
        return
    plan = channel_queue.plan(posts, await published(), datetime.now(TZ))
    if not plan:
        await message.answer("Все посты уже в канале 🎉")
        return
    await message.answer(_queue_text(plan, posts,
                                     "⏱ <b>Выпустить всё по очереди?</b>\nПервый пост каждого канала — сразу, дальше: "
                                     "«Капибара» — раз в 20–30 минут, «Разработка» — раз в 4–6 часов. "
                                     "С 23 до 9 по Москве — пауза. Примерно так:"),
                         parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                             InlineKeyboardButton(text="▶️ Запустить", callback_data="chan:auto:go")]]))


async def _auto_button(callback: CallbackQuery, what: str):
    from kapibara.features.content import channel_queue
    from kapibara.features.content.channel_posts import load_posts
    await callback.answer()
    msg = callback.message if isinstance(callback.message, Message) else None
    if msg:
        await msg.edit_reply_markup(reply_markup=None)
    if what == "stop":
        n = await channel_queue.cancel()
        if msg:
            await msg.answer(f"⏹ Очередь отменена, не вышло {n}. Выпустить руками — /channel.")
        return
    if await channel_queue.load():
        if msg:
            await msg.answer("Очередь уже идёт — посмотреть или отменить: /channel auto")
        return
    items = await channel_queue.start()
    if msg:
        await msg.answer(_queue_text(items, load_posts(), "▶️ <b>Очередь запущена</b>, время по Москве:") +
                         "\n\nПро каждый вышедший пост напишу. Посмотреть или отменить — /channel auto.",
                         parse_mode="HTML")
    await channel_queue.tick(callback.bot, night_ok=True)        # первые посты — сразу
