"""Решалка, общая часть: как ответить моделью — лекции и источники под ответом, состояния FSM, кнопка «Подумать ещё».

Роутера здесь нет: обработчики в solver, solver_think и solver_lectures.
"""

import logging
import re
from contextlib import asynccontextmanager

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import get_subject_lecture_context
from kapibara.core.utils import md_to_tg_html_parts
from kapibara.core.telegram import cosmetic
from kapibara.core.errors import aside, log_failure
from kapibara.bot.tg import sender

logger = logging.getLogger("handlers.solver")  # старое имя: /status


AI_DOWN = "❌ ИИ сейчас не ответил — попробуй ещё раз через минуту"


@asynccontextmanager
async def ai_reply(wait: Message, what: str):
    """Граница ответа ИИ в боте (ADR 0004): что бы ни сломалось — человеку
    «не ответил» на месте «Думаю…», в лог сеть строкой, баг с traceback.
    Раньше в семи местах свой except и человеку — текст исключения."""
    try:
        yield
    except Exception as e:      # граница хендлера
        log_failure(logger, what, e)
        with cosmetic("решалка: «не ответил» вместо «Думаю…»"):
            await wait.edit_text(AI_DOWN)


# Решалка — только в личке: в группе (если боту видны все сообщения) любой
# текст длиннее 15 символов уходил к ИИ и бот отвечал всем подряд.
PRIVATE = F.chat.type == "private"
TOO_MANY = "⏳ Много вопросов подряд — подожди минутку и спроси ещё раз."


async def ai_block(message: Message, day: bool = True) -> str | None:
    """Лимит запросов к ИИ, как в WebApp (ai_quota): бесплатный лимит Gemini
    один человек сжечь не должен. Почему нельзя — текст ответа, или None.
    day=False — только минутный (классификатор намерений — не вопрос к ИИ)."""
    from kapibara.features.ai import quota as ai_quota
    return _why_text(await ai_quota.gate(sender(message).id, day=day))


async def ai_day(message: Message) -> str | None:
    """Только дневной счёт — минутный уже проверен перед классификатором."""
    from kapibara.features.ai import quota as ai_quota
    return _why_text(await ai_quota.day_only(sender(message).id))


def _why_text(why: str | None) -> str | None:
    from kapibara.features.ai import quota as ai_quota
    if why and why != "minute":
        return "⏳ " + ai_quota.text(why, capital=True) + "."
    return TOO_MANY if why else None


async def lectures_for(data: dict, query: str = "") -> str:
    """Лекции выбранного предмета под вопрос: сначала поиск по смыслу (куски
    с номерами [n], как в чате приложения: ~16 тыс. символов вместо целых
    лекций — в ~10 раз дешевле, 5.94), иначе — целыми лекциями (lecture_picker):
    «объясни 3 лекцию», пустой индекс, пустой вопрос. Пусто — если лекций нет."""
    if not data.get("has_lectures"):
        return ""
    from kapibara.features.lectures import picker as lecture_picker
    subject = data.get("subject", "")
    if query.strip() and not lecture_picker.wants_course(query):
        with aside(logger, "поиск по смыслу в боте"):
            from kapibara.features.ai import semantic_search
            if await semantic_search.ready():
                hits = await semantic_search.search(query, subject)
                if hits:
                    return semantic_search.build_context(hits)[0]
    return lecture_picker.pick(await get_subject_lecture_context(subject), query)


_CHUNK_HEAD = re.compile(r"^=== \[(\d+)\] (.+) ===$", re.M)


BOT_TITLE = 40      # название лекции в строке источников (робот 18.10: 28 резало «Лекция 5. Дисконтир…»)


def with_sources(answer: str, lectures: str) -> str:
    """Под ответом по кускам поиска — откуда они («[2] Лекция 5 · слайд 12»):
    в приложении это чипы, в боте — строка. Только номера, на которые ИИ сослался."""
    if not answer or not lectures.lstrip().startswith("=== [1]"):
        return answer
    from kapibara.features.ai.semantic_search import short_title
    heads = {}
    for n, head in _CHUNK_HEAD.findall(lectures):
        title = head.split(": ", 1)[-1]
        name, _, where = title.rpartition(" · ")
        heads[n] = (f"{short_title(name, BOT_TITLE)} · {where}" if name   # в строке места больше, чем в чипе
                    else short_title(title, BOT_TITLE))
    cited = [n for n in dict.fromkeys(re.findall(r"\[(\d+)\]", answer)) if n in heads]
    if not cited:
        return answer
    first: dict[str, str] = {}                   # одно место — одна строка, даже под двумя номерами
    for n in cited:
        first.setdefault(heads[n], n)
    return answer + "\n\n📚 " + "; ".join(f"[{n}] {head}" for head, n in first.items())


class SolverState(StatesGroup):
    choose_subject = State()
    waiting_task   = State()
    in_dialog      = State()


class LectureSolverState(StatesGroup):
    """Отдельная (не мульти-turn) машина состояний для решалки по лекциям —
    см. gemini_solver.py. Не переиспользует SolverState: там subject — это
    произвольная категория из фиксированного SUBJECTS, здесь — обязательно
    точное название предмета, по которому реально есть загруженные лекции
    (иначе неоткуда взять контекст)."""
    choose_subject = State()
    waiting_task   = State()


async def answer_model_text(message: Message, answer: str) -> list[Message]:
    """Ответ модели -> сообщения с HTML-разметкой (см. md_to_tg_html_chunks).
    Если Telegram всё же не принял разметку куска — тот же кусок без неё."""
    sent = []
    for md, chunk in md_to_tg_html_parts(answer):
        try:
            sent.append(await message.answer(chunk, parse_mode="HTML"))
        except TelegramBadRequest as e:      # не разобрал разметку — тот же кусок текстом
            logger.warning(f"Ответ модели не прошёл как HTML, шлю текстом: {e}")
            sent.append(await message.answer(md))
    return sent


async def send_answer(message: Message, state: FSMContext, answer: str):
    """Отправляем ответ и сохраняем msg_id."""
    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])

    sent = await answer_model_text(message, answer)
    msg_ids += [m.message_id for m in sent]

    history = data.get("history", [])
    if history and history[-1]["role"] == "assistant":
        await offer_think(sender(message).id, state, sent, history[:-1], data)

    # Подсказка — один раз за диалог, а не после каждого ответа
    if not data.get("hinted"):
        hint = await message.answer(
            "💬 Можно задать уточняющий вопрос — я помню условие.\n"
            "Закончил — жми <b>🛑 Завершить диалог</b>.",
            parse_mode="HTML"
        )
        msg_ids.append(hint.message_id)
    await state.update_data(msg_ids=msg_ids, hinted=True)


THINK_CB = "think:go"


def think_kb(left: int | None) -> InlineKeyboardMarkup:
    """left=None — безлимит, без счётчика."""
    from kapibara.features.ai import think
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"🧠 {think.LABEL}" + ("" if left is None else f" · {left}"), callback_data=THINK_CB)]])


async def offer_think(uid: int, state: FSMContext, sent: list[Message], question: list, data: dict):
    from kapibara.features.ai import think
    if not sent or not question or question[-1]["role"] != "user" \
            or question[-1]["content"].startswith("Задание на фото"):
        return
    offer = await think.offer(uid)
    if not offer or offer["left"] == 0:         # на сегодня кончилось — кнопки нет (нажать всё равно нельзя)
        return
    await state.update_data(think_q=question, think_d={"subject": data.get("subject", ""),
                                                        "has_lectures": data.get("has_lectures", False)})
    with cosmetic("«Подумать ещё»: кнопка"):        # без кнопки «Подумать ещё» ответ всё равно есть
        await sent[-1].edit_reply_markup(reply_markup=think_kb(offer["left"]))
