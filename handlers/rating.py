"""Рейтинг (xp.py) в боте — у старосты-владельца:
/nicks — новые и сменённые ники с кнопкой «Сбросить» (ручная модерация, Никита
18.10: «раз в пару дней»); /institutes — шифры групп из справочника расписания
и институт каждого (institutes.py), чтобы проверить таблицу."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import is_starosta
from utils import esc

router = Router(name="rating")


@router.message(Command("nicks"))
async def cmd_nicks(message: Message):
    if not is_starosta(message.from_user.id):
        return
    import xp
    rows = await xp.unreviewed()
    if not rows:
        await message.answer("Новых ников нет.")
        return
    for r in rows:
        who = esc(r["name"] or "без имени") + (f" (@{esc(r['username'])})" if r["username"] else "")
        await message.answer(
            f"«<b>{esc(r['nick'])}</b>» — {who}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Сбросить на имя", callback_data=f"nick:reset:{r['user_id']}"),
            ]]))
    await xp.mark_reviewed(r["user_id"] for r in rows)
    await message.answer(f"Это все новые ники ({len(rows)}). Что не сбросишь — останется.")


@router.callback_query(F.data.startswith("nick:reset:"))
async def nick_reset(callback: CallbackQuery):
    if not is_starosta(callback.from_user.id):
        await callback.answer("Это кнопка владельца бота", show_alert=True)
        return
    import xp
    await xp.reset_nick(int(callback.data.rsplit(":", 1)[1]))
    await callback.answer("Сброшено: теперь имя, свой ник поставить нельзя")
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n<b>Сброшено.</b>", parse_mode="HTML")
    except Exception:
        pass


@router.message(Command("institutes"))
async def cmd_institutes(message: Message):
    if not is_starosta(message.from_user.id):
        return
    import institutes
    from database._conn import connect
    async with connect() as db:
        try:
            names = [r[0] for r in await (await db.execute(
                "SELECT title FROM schedule_targets WHERE type = 1")).fetchall()]
        except Exception:
            names = []
    rows = institutes.table(names)
    if not rows:
        await message.answer("Справочник групп ещё пуст — загляни позже.")
        return
    lines = [f"{r['prefix']}\t{r['institute'] or '?'}\t{r['groups']}\t{r['sample']}" for r in rows]
    unknown = [r["prefix"] for r in rows if not r["institute"]]
    text = "шифр\tинститут\tгрупп\tпример\n" + "\n".join(lines)
    await message.answer_document(
        BufferedInputFile(text.encode("utf-8"), filename="institutes.tsv"),
        caption=(f"Шифров: {len(rows)}. Без института: {', '.join(unknown[:30]) or 'нет'}.\n"
                 "Поправь, что не так, — пришли «ШИФР → институт», я внесу."))
