from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import create_vote, get_active_vote, add_vote_answer, get_vote_results, close_vote
from config import STAROSTA_ID

router = Router()


# ── Голосование ───────────────────────────────────────────────────────────────

def vote_keyboard(vote_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да",  callback_data=f"vote:{vote_id}:да"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"vote:{vote_id}:нет"),
        InlineKeyboardButton(text="🤷 Не знаю", callback_data=f"vote:{vote_id}:не знаю"),
    ]])


@router.message(Command("vote"))
@router.message(F.text == "🗳 Голосование")
async def cmd_vote(message: Message):
    # Показать текущее голосование или создать новое
    parts = message.text.split(maxsplit=1) if message.text.startswith("/vote") else []

    if len(parts) >= 2:
        # Создать новое голосование
        question = parts[1].strip()
        vote_id  = await create_vote(question, message.from_user.id)
        from database import get_all_subscribed_users
        from aiogram import Bot
        # Рассылаем всем
        kb = vote_keyboard(vote_id)
        users = await get_all_subscribed_users()

        # Сначала отвечаем создателю
        await message.answer(
            f"🗳 <b>Голосование создано!</b>\n\n❓ {question}",
            parse_mode="HTML", reply_markup=kb
        )
    else:
        # Показать активное
        vote = await get_active_vote()
        if not vote:
            await message.answer(
                "Нет активного голосования.\n\n"
                "Создать: /vote Твой вопрос\n"
                "Например: /vote Идём на пары в пятницу?"
            )
            return
        results = await get_vote_results(vote["id"])
        total   = sum(results.values())
        lines   = [f"🗳 <b>{vote['question']}</b>\n"]
        for ans, cnt in results.items():
            pct  = int(cnt / total * 100) if total else 0
            bar  = "▓" * (pct // 10) + "░" * (10 - pct // 10)
            lines.append(f"{ans}: [{bar}] {cnt} ({pct}%)")
        lines.append(f"\nВсего проголосовало: {total}")
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=vote_keyboard(vote["id"]))


@router.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery):
    _, vote_id, answer = callback.data.split(":")
    vote_id = int(vote_id)

    vote = await get_active_vote()
    if not vote or vote["id"] != vote_id:
        await callback.answer("Это голосование уже закрыто.", show_alert=True)
        return

    await add_vote_answer(vote_id, callback.from_user.id, answer)

    results = await get_vote_results(vote_id)
    total   = sum(results.values())
    lines   = [f"🗳 <b>{vote['question']}</b>\n"]
    for ans, cnt in results.items():
        pct  = int(cnt / total * 100) if total else 0
        bar  = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(f"{ans}: [{bar}] {cnt} ({pct}%)")
    lines.append(f"\nВсего: {total}")

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=vote_keyboard(vote_id))
    await callback.answer(f"Твой голос: {answer} ✅")


@router.message(Command("closevote"))
async def cmd_closevote(message: Message):
    vote = await get_active_vote()
    if not vote:
        await message.answer("Нет активного голосования.")
        return
    await close_vote(vote["id"])
    await message.answer("✅ Голосование закрыто.")


# ── Анонимный вопрос старосте ─────────────────────────────────────────────────

class AnonQuestion(StatesGroup):
    waiting = State()


@router.message(Command("anon"))
@router.message(F.text == "❓ Вопрос анон")
async def cmd_anon(message: Message, state: FSMContext):
    if not STAROSTA_ID:
        await message.answer("⚠️ Старостa не настроен. Обратись к администратору бота.")
        return
    await state.set_state(AnonQuestion.waiting)
    await message.answer(
        "🕵️ Пиши анонимный вопрос — имя не будет указано.\n"
        "Вопрос получит только староста.\n\n"
        "/cancel — отмена"
    )


@router.message(AnonQuestion.waiting, F.text)
async def send_anon(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return

    await state.clear()

    try:
        from aiogram import Bot
        bot = message.bot
        await bot.send_message(
            STAROSTA_ID,
            f"❓ <b>Анонимный вопрос от группы:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Вопрос отправлен старосте анонимно!")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")
