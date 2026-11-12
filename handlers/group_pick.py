"""
Своя группа в боте (этап 1: любая группа института): /group и первый /start.

Кто был в боте до этапа 1 — уже в своей группе (миграция). Новый человек
после /start пишет название группы, бот ищет её в справочнике расписания
(groups.search) и даёт кнопки; выбор — groups.choose. Сменить — /group.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from kapibara.core.utils import esc
from kapibara.core.telegram import cosmetic
from kapibara.bot.tg import bot_of, data_of, msg, sender, text_of
from aiogram.exceptions import TelegramAPIError

router = Router(name="group_pick")

ASK = "Из какой ты группы? Напиши название, например <b>УИБО-03-24</b>."


class GroupPick(StatesGroup):
    query = State()


async def ask_group(message: Message, state: FSMContext, intro: str = ""):
    await state.set_state(GroupPick.query)
    await message.answer((intro + "\n\n" if intro else "") + ASK, parse_mode="HTML")


@router.message(Command("group"))
async def cmd_group(message: Message, state: FSMContext):
    from kapibara.features.groups import groups
    from kapibara.features.privacy.privacy import upsert_user
    user = sender(message)
    await upsert_user(user.id, user.username or "", user.full_name or "")
    g = await groups.of_user(user.id)
    await ask_group(message, state, f"Сейчас ты в группе <b>{esc(g['name'])}</b>." if g else "")


@router.message(GroupPick.query, F.text)
async def group_query(message: Message, state: FSMContext):
    from kapibara.features.groups import groups
    found = await groups.search(text_of(message))
    if not found:
        await message.answer("Не нашёл такую группу. Напиши, как в расписании: <b>УИБО-03-24</b>. "
                             "Передумал — /cancel", parse_mode="HTML")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=g["name"], callback_data=f"grp:{g['id']}")]
                                               for g in found[:8]])
    await message.answer("Выбери свою:", reply_markup=kb)


@router.callback_query(F.data.startswith("grp:"))
async def group_chosen(callback: CallbackQuery, state: FSMContext):
    from kapibara.features.groups import groups
    gid = data_of(callback).split(":", 1)[1]
    g = await groups.choose(callback.from_user.id, int(gid), callback.bot) if gid.isdigit() else None
    if not g:
        await callback.answer("Такой группы нет", show_alert=True)
        return
    if g.get("denied"):
        await callback.answer(g["denied"].capitalize(), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    text = f"Готово: ты в группе <b>{esc(g['name'])}</b>. Сменить — /group"
    try:
        await msg(callback).edit_text(text, parse_mode="HTML")
    except TelegramAPIError:             # сообщение не изменить — шлём новым
        await msg(callback).answer(text, parse_mode="HTML")
    if g["own"]:
        from kapibara.bot.optional import ask_optional
        await ask_optional(msg(callback), callback.from_user.id)


# ── Старосты групп (этап 1 (б)): общие дедлайны, ДЗ и заметки группы правят
# старосты бота и старосты своей группы (group_admins). Стать старостой —
# по запросу: «Я староста» → владельцу бота кнопки «Одобрить / Отклонить».

async def request_admin(bot, user, group: dict) -> str:
    """Запрос «я староста группы» владельцу бота. → текст ответа человеку."""
    from kapibara.core.config import STAROSTA_ID
    from database import is_group_admin
    if await is_group_admin(user.id, group["id"]):
        return f"Ты уже староста группы {group['name']}."
    if not STAROSTA_ID:
        return "Некому одобрить — у бота не задан владелец."
    name = esc(user.full_name or "") + (f" (@{esc(user.username)})" if getattr(user, "username", None) else "")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"gadm:ok:{group['id']}:{user.id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"gadm:no:{group['id']}:{user.id}"),
    ]])
    await bot.send_message(STAROSTA_ID, f"🎓 <a href=\"tg://user?id={user.id}\">{name}</a> пишет, что он староста "
                                        f"группы <b>{esc(group['name'])}</b>.", parse_mode="HTML", reply_markup=kb)
    return "Отправил запрос владельцу бота — как одобрит, бот напишет."


@router.message(Command("iamstarosta"))
async def cmd_iam_starosta(message: Message):
    from kapibara.features.groups import groups
    g = await groups.of_user(sender(message).id)
    if not g:
        await message.answer("Сначала выбери группу — /group")
        return
    if g["own"]:
        await message.answer("В этой группе старосту назначает владелец бота.")
        return
    await message.answer(await request_admin(bot_of(message), sender(message), g))


@router.callback_query(F.data.startswith("gadm:"))
async def admin_decision(callback: CallbackQuery):
    from kapibara.core.config import is_starosta
    from database import add_group_admin
    from kapibara.features.groups import groups
    if not is_starosta(callback.from_user.id):
        await callback.answer("Только владелец бота", show_alert=True)
        return
    _, verdict, gid, uid = data_of(callback).split(":")
    name = await groups.name_of(int(gid))
    if verdict == "ok":
        await add_group_admin(int(gid), int(uid), callback.from_user.id)
        note = f"Теперь ты староста группы <b>{esc(name)}</b>: можешь добавлять общие дедлайны (/add), ДЗ (/addhw) и заметки к парам для всей группы."
    else:
        note = f"Запрос «староста группы {esc(name)}» отклонён."
    with cosmetic("group_pick.admin_decision"):
        await bot_of(callback).send_message(int(uid), note, parse_mode="HTML")
    await callback.answer("Готово")
    with cosmetic("group_pick.admin_decision"):
        await msg(callback).edit_text(msg(callback).html_text + ("\n\n✅ Одобрено" if verdict == "ok" else "\n\n✖️ Отклонено"),
                                         parse_mode="HTML")
