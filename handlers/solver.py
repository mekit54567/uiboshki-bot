import logging
import re

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)

from ai_solver import solve_text, solve_image, solve_with_history, SUBJECTS
from gemini_solver import solve_with_lecture_context
from database import (
    upsert_user, add_solver_history, get_solver_history,
    get_subjects_with_lecture_text, get_subject_lecture_context,
)
from keyboards import MAIN_KB, STOP_DIALOG_KB, CANCEL_KB, MENU_BUTTON_TEXTS
from intent_router import classify_intent, dispatch_intent
from utils import esc, md_to_tg_html_parts, utc_to_msk_date

logger = logging.getLogger(__name__)
router = Router()

# Решалка — только в личке: в группе (если боту видны все сообщения) любой
# текст длиннее 15 символов уходил к ИИ и бот отвечал всем подряд.
PRIVATE = F.chat.type == "private"
TOO_MANY = "⏳ Много вопросов подряд — подожди минутку и спроси ещё раз."


async def _ai_block(message: Message, day: bool = True) -> str | None:
    """Лимит запросов к ИИ, как в WebApp (ai_quota): бесплатный лимит Gemini
    один человек сжечь не должен. Почему нельзя — текст ответа, или None.
    day=False — только минутный (классификатор намерений — не вопрос к ИИ)."""
    import ai_quota
    return _why_text(await ai_quota.gate(message.from_user.id, day=day))


async def _ai_day(message: Message) -> str | None:
    """Только дневной счёт — минутный уже проверен перед классификатором."""
    import ai_quota
    return _why_text(await ai_quota.day_only(message.from_user.id))


def _why_text(why: str | None) -> str | None:
    import ai_quota
    if why and why != "minute":
        return "⏳ " + ai_quota.text(why, capital=True) + "."
    return TOO_MANY if why else None

SUBJECT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SUBJECTS],
    resize_keyboard=True, one_time_keyboard=True
)
LECTURE_MARK = "📖 "


async def solve_subject_kb() -> ReplyKeyboardMarkup:
    """Кнопки предметов для /solve: сначала те, по которым загружены лекции
    (📖 — решалка будет опираться на них), потом остальные предметы группы
    из расписания, в конце «Другое». Раньше был фиксированный список
    «Математика/Экономика/…», который не совпадал ни с одним предметом, по
    которому есть лекции, — и лекции в обычной решалке не участвовали."""
    from schedule_parser import get_group_subjects
    with_lectures = await get_subjects_with_lecture_text()
    rest = [s for s in await get_group_subjects() if s not in with_lectures]
    if not with_lectures and not rest:
        return SUBJECT_KB
    rows = [[KeyboardButton(text=LECTURE_MARK + s)] for s in with_lectures]
    rows += [[KeyboardButton(text=s)] for s in rest]
    rows.append([KeyboardButton(text="Другое")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


async def _lectures_for(data: dict, query: str = "") -> str:
    """Лекции выбранного предмета под вопрос: сначала поиск по смыслу (куски
    с номерами [n], как в чате приложения: ~16 тыс. символов вместо целых
    лекций — в ~10 раз дешевле, 5.94), иначе — целыми лекциями (lecture_picker):
    «объясни 3 лекцию», пустой индекс, пустой вопрос. Пусто — если лекций нет."""
    if not data.get("has_lectures"):
        return ""
    import lecture_picker
    subject = data.get("subject", "")
    if query.strip() and not lecture_picker.wants_course(query):
        try:
            import semantic_search
            if await semantic_search.ready():
                hits = await semantic_search.search(query, subject)
                if hits:
                    return semantic_search.build_context(hits)[0]
        except Exception as e:
            logger.warning(f"поиск по смыслу в боте: {type(e).__name__}: {e} — подбираю лекции по словам")
    return lecture_picker.pick(await get_subject_lecture_context(subject), query)


_CHUNK_HEAD = re.compile(r"^=== \[(\d+)\] (.+) ===$", re.M)


BOT_TITLE = 40      # название лекции в строке источников (робот 18.10: 28 резало «Лекция 5. Дисконтир…»)


def with_sources(answer: str, lectures: str) -> str:
    """Под ответом по кускам поиска — откуда они («[2] Лекция 5 · слайд 12»):
    в приложении это чипы, в боте — строка. Только номера, на которые ИИ сослался."""
    if not answer or not lectures.lstrip().startswith("=== [1]"):
        return answer
    from semantic_search import short_title
    heads = {}
    for n, head in _CHUNK_HEAD.findall(lectures):
        title = head.split(": ", 1)[-1]
        name, _, where = title.rpartition(" · ")
        heads[n] = (f"{short_title(name, BOT_TITLE)} · {where}" if name   # в строке места больше, чем в чипе
                    else short_title(title, BOT_TITLE))
    cited = [n for n in dict.fromkeys(re.findall(r"\[(\d+)\]", answer)) if n in heads]
    if not cited:
        return answer
    return answer + "\n\n📚 " + "; ".join(f"[{n}] {heads[n]}" for n in cited)


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


@router.message(Command("solve"), PRIVATE)
@router.message(Command("solve_ds"), PRIVATE)
@router.message(F.text == "🤖 Решить", PRIVATE)
async def cmd_solve(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    backend = "deepseek" if (message.text or "").startswith("/solve_ds") else "gemini"
    await state.update_data(backend=backend)
    await state.set_state(SolverState.choose_subject)
    label = " (🐋 DeepSeek)" if backend == "deepseek" else ""
    await message.answer(f"📚 Выбери предмет{label}:", reply_markup=await solve_subject_kb())


@router.message(SolverState.choose_subject, F.text)
async def choose_subject(message: Message, state: FSMContext):
    # Защита на случай, если MenuInterruptMiddleware почему-то не сработал
    # (например, при апдейте aiogram) — не даём тексту кнопки меню стать
    # "названием предмета".
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    data = await state.get_data()
    backend = data.get("backend", "gemini")
    subject = message.text.strip().removeprefix(LECTURE_MARK.strip()).strip()
    has_lectures = backend == "gemini" and subject in await get_subjects_with_lecture_text()
    await state.update_data(subject=subject, history=[], msg_ids=[], backend=backend, hinted=False,
                            has_lectures=has_lectures)
    await state.set_state(SolverState.waiting_task)
    note = "\n\n(фото — всегда через Gemini, у DeepSeek нет зрения)" if backend == "deepseek" else ""
    lectures_note = "\n📖 Буду опираться на загруженные лекции по этому предмету." if has_lectures else ""
    msg = await message.answer(
        f"✅ Предмет: <b>{esc(subject)}</b>{lectures_note}\n\nПришли задачу — текстом или фото 📸{note}",
        parse_mode="HTML", reply_markup=STOP_DIALOG_KB
    )
    msg_ids = [msg.message_id]
    if backend == "gemini":
        arm = await offer_arm(message)
        if arm:
            msg_ids.append(arm.message_id)
            await state.update_data(think_arm=arm.message_id)
    await state.update_data(msg_ids=msg_ids)


@router.message(F.text == "🛑 Завершить диалог")
async def stop_dialog(message: Message, state: FSMContext, bot: Bot, interrupted_fsm_data: dict | None = None):
    # "🛑 Завершить диалог" входит в MENU_BUTTON_TEXTS, поэтому к этому моменту
    # MenuInterruptMiddleware уже сбросил state — msg_ids берём из того, что он
    # успел сохранить перед сбросом.
    data = interrupted_fsm_data if interrupted_fsm_data is not None else await state.get_data()
    await state.clear()

    # Удаляем сообщения диалога из чата
    msg_ids = data.get("msg_ids", [])
    for mid in msg_ids:
        try:
            await bot.delete_message(message.chat.id, mid)
        except Exception:
            pass  # сообщение уже удалено или старше 48 ч — не страшно

    await message.answer("✅ Диалог завершён.", reply_markup=MAIN_KB)


@router.message(Command("cancel"), SolverState.waiting_task)
@router.message(Command("cancel"), SolverState.choose_subject)
@router.message(Command("cancel"), SolverState.in_dialog)
async def cancel_solve(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


async def answer_model_text(message: Message, answer: str) -> list[Message]:
    """Ответ модели -> сообщения с HTML-разметкой (см. md_to_tg_html_chunks).
    Если Telegram всё же не принял разметку куска — тот же кусок без неё."""
    sent = []
    for md, chunk in md_to_tg_html_parts(answer):
        try:
            sent.append(await message.answer(chunk, parse_mode="HTML"))
        except Exception as e:
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
        await offer_think(message.from_user.id, state, sent, history[:-1], data)

    # Подсказка — один раз за диалог, а не после каждого ответа
    if not data.get("hinted"):
        hint = await message.answer(
            "💬 Можно задать уточняющий вопрос — я помню условие.\n"
            "Закончил — жми <b>🛑 Завершить диалог</b>.",
            parse_mode="HTML"
        )
        msg_ids.append(hint.message_id)
    await state.update_data(msg_ids=msg_ids, hinted=True)


@router.message(SolverState.waiting_task, F.text, PRIVATE)
async def handle_first_task(message: Message, state: FSMContext):
    data    = await state.get_data()
    subject = data.get("subject", "")
    backend = data.get("backend", "gemini")
    if data.get("think_next"):
        await first_think(message, state, data)
        return
    if (why := await _ai_block(message)):
        await message.answer(why)
        return
    await drop_arm(message, state, data)
    wait    = await message.answer("🧠 Решаю, секунду...")
    try:
        lectures = await _lectures_for(data, message.text)
        answer = with_sources(await solve_text(message.text, subject, backend=backend, lectures=lectures), lectures)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог обработать. Попробуй переформулировать.")
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer, subject)

        history = [
            {"role": "user",      "content": f"Задание:\n{message.text}"},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(SolverState.in_dialog)
        await send_answer(message, state, answer)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


def _photo_prompt(caption: str, history: list | None = None) -> str:
    """Подпись к фото («реши только 2 пункт») — в запрос: раньше она терялась.
    В диалоге — ещё и прошлые реплики, чтобы фото было в контексте."""
    earlier = "\n".join(f"{'Студент' if m['role'] == 'user' else 'Ты'}: {m['content'][:500]}"
                        for m in (history or [])[-6:])
    question = caption.strip() or "Реши задание на фото с подробным объяснением."
    return ((f"Предыдущий разговор:\n{earlier}\n\n" if earlier else "")
            + f"Сообщение студента: {question}\n\nНе используй LaTeX.")


async def _photo_answer(message: Message, bot: Bot, data: dict, history: list | None = None) -> str:
    photo      = message.photo[-1]
    file       = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    caption    = message.caption or ""
    lectures   = await _lectures_for(data, caption)
    return with_sources(await solve_image(file_bytes.read(), subject=data.get("subject", ""), lectures=lectures,
                                          prompt=_photo_prompt(caption, history)), lectures)


def _photo_task(message: Message) -> str:
    return "Задание на фото" + (f": {message.caption}" if message.caption else "")


PHOTO_FAIL = ("📝 Не смог распознать фото.\n\n"
              "Попробуй:\n• Переслать текстом\n• Сделать чёткое фото\n• Прислать скриншот")


@router.message(SolverState.waiting_task, F.photo, PRIVATE)
async def handle_first_photo(message: Message, state: FSMContext, bot: Bot):
    data    = await state.get_data()
    subject = data.get("subject", "")
    if (why := await _ai_block(message)):
        await message.answer(why)
        return
    await drop_arm(message, state, data)        # к фото «Подумать» нет — решаем как обычно
    wait    = await message.answer("🧠 Анализирую фото...")
    try:
        answer = await _photo_answer(message, bot, data)

        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return

        await wait.delete()
        await add_solver_history(message.from_user.id, ("[фото] " + (message.caption or "")).strip(), answer, subject)

        history = [
            {"role": "user",      "content": _photo_task(message)},
            {"role": "assistant", "content": answer},
        ]
        await state.update_data(history=history)
        await state.set_state(SolverState.in_dialog)
        await send_answer(message, state, answer)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(SolverState.in_dialog, F.text, PRIVATE)
async def handle_dialog(message: Message, state: FSMContext):
    import lecture_picker
    data    = await state.get_data()
    subject = data.get("subject", "")
    backend = data.get("backend", "gemini")
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])

    # Сохраняем ID входящего сообщения
    msg_ids.append(message.message_id)
    if (why := await _ai_block(message)):
        msg_ids.append((await message.answer(why)).message_id)
        await state.update_data(msg_ids=msg_ids)
        return
    history.append({"role": "user", "content": message.text})

    wait = await message.answer("🧠 Думаю...")
    try:
        # «а почему?», «подробнее» — лекции ищем по теме прошлых вопросов
        query = lecture_picker.search_query(history)
        lectures = await _lectures_for(data, query)
        answer = with_sources(await solve_with_history(history, subject, backend=backend, lectures=lectures), lectures)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text("🤔 Не смог ответить. Попробуй иначе.")
            return

        await wait.delete()
        history.append({"role": "assistant", "content": answer})
        if len(history) > 10:
            history = history[-10:]
        await state.update_data(history=history, msg_ids=msg_ids)
        await send_answer(message, state, answer)

    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(SolverState.in_dialog, F.photo, PRIVATE)
async def handle_dialog_photo(message: Message, state: FSMContext, bot: Bot):
    """Фото посреди диалога («а вот ещё задача») — раньше молча терялось."""
    data    = await state.get_data()
    history = data.get("history", [])
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(message.message_id)
    if (why := await _ai_block(message)):
        msg_ids.append((await message.answer(why)).message_id)
        await state.update_data(msg_ids=msg_ids)
        return
    wait = await message.answer("🧠 Анализирую фото...")
    try:
        answer = await _photo_answer(message, bot, data, history)
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return
        await wait.delete()
        history += [{"role": "user", "content": _photo_task(message)}, {"role": "assistant", "content": answer}]
        await state.update_data(history=history[-10:], msg_ids=msg_ids)
        await send_answer(message, state, answer)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")


@router.message(Command("history"))
async def cmd_history(message: Message):
    history = await get_solver_history(message.from_user.id, limit=5)
    if not history:
        await message.answer("📭 История пустая — ещё не решал задачи.")
        return
    lines = ["📜 <b>Последние 5 задач:</b>\n"]
    for i, h in enumerate(history, 1):
        # Экранирование обязательно: в условиях задач постоянно встречаются
        # "<"/">" ("x < 5"), и одна такая задача среди последних пяти
        # раньше навсегда ломала /history ("can't parse entities").
        subj = f" [{esc(h['subject'])}]" if h.get("subject") else ""
        task = esc(h["task_text"][:80]) + ("..." if len(h["task_text"]) > 80 else "")
        lines.append(f"{i}.{subj} {task}\n   <i>{utc_to_msk_date(h['created_at'])}</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# StateFilter(None) обязателен: этот catch-all зарегистрирован в роутере РАНЬШЕ
# хендлеров решалки по лекциям (LectureSolverState ниже). Без фильтра он
# забирал себе любой текст в любом состоянии и просто выходил по проверке
# state ниже — апдейт считался обработанным, и lecture_choose_subject /
# lecture_handle_task не вызывались никогда (/solve_lectures зависал на
# выборе предмета).
@router.message(F.text & ~F.text.startswith("/"), StateFilter(None), PRIVATE)
async def handle_plain_text(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        return
    if await state.get_state() is not None:
        return

    # «скинь практику 3 по основам предпр деят» — файл, а не вопрос к ИИ
    from handlers.files import answer_file_request
    if await answer_file_request(message):
        return

    # классификатор — тоже запрос к ИИ, но не «вопрос»: только минутный лимит
    if len(message.text.strip()) >= 3 and (why := await _ai_block(message, day=False)):
        await message.answer(why)
        return

    # Фаза 1: сначала пробуем понять намерение без команд/кнопок
    # ("когда следующая пара", "покажи дедлайны" и т.д.). Если не удалось —
    # при достаточной длине считаем это учебной задачей для решалки, как раньше.
    intent = await classify_intent(message.text)
    if intent != "none":
        handled = await dispatch_intent(intent, message)
        if handled:
            return

    text = message.text
    backend = "gemini"
    for prefix in ("дипсик:", "deepseek:", "через дипсик:"):
        if text.lower().startswith(prefix):
            backend = "deepseek"
            text = text[len(prefix):].strip()
            break

    if len(text) < 15:
        return
    if (why := await _ai_day(message)):          # а вот это уже вопрос к ИИ — в дневной счёт
        await message.answer(why)
        return
    wait = await message.answer("🤖 Похоже задание — решаю..." + (" (🐋 DeepSeek)" if backend == "deepseek" else ""))
    try:
        answer = await solve_text(text, backend=backend)
        if not answer or len(answer.strip()) < 10:
            # раньше «решаю…» молча пропадало — человек оставался без ответа
            await wait.edit_text("🤷 ИИ вернул пустой ответ — попробуй переформулировать или /solve")
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, text, answer)
        sent = await answer_model_text(message, answer)
        await offer_think(message.from_user.id, state, sent, [{"role": "user", "content": f"Задание:\n{text}"}], {})
    except Exception as e:
        logger.error(f"решалка (свободный текст): {e!r}")
        await wait.edit_text("❌ ИИ сейчас не ответил — попробуй ещё раз через минуту")


# ── «Подумать ещё» (think.py, «Капибара+») ────────────────────────────────
# Под ответом подписчика — кнопка: тот же вопрос заново решает модель
# второго уровня со своим дневным лимитом. Вопрос (история до ответа) — в
# данных FSM; к фото кнопки нет: модель читает только текст.
THINK_CB = "think:go"
GONE_TEXT = "Этот вопрос уже не найти — задай его ещё раз"


def think_kb(left: int | None) -> InlineKeyboardMarkup:
    """left=None — безлимит, без счётчика."""
    import think
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"🧠 {think.LABEL}" + ("" if left is None else f" · {left}"), callback_data=THINK_CB)]])


async def offer_think(uid: int, state: FSMContext, sent: list[Message], question: list, data: dict):
    import think
    if not sent or not question or question[-1]["role"] != "user" \
            or question[-1]["content"].startswith("Задание на фото"):
        return
    offer = await think.offer(uid)
    if not offer or offer["left"] == 0:         # на сегодня кончилось — кнопки нет (нажать всё равно нельзя)
        return
    await state.update_data(think_q=question, think_d={"subject": data.get("subject", ""),
                                                        "has_lectures": data.get("has_lectures", False)})
    try:
        await sent[-1].edit_reply_markup(reply_markup=think_kb(offer["left"]))
    except Exception as e:
        logger.warning(f"«Подумать ещё»: кнопку не поставил: {e!r}")


@router.callback_query(F.data == THINK_CB)
async def think_again(callback: CallbackQuery, state: FSMContext):
    import lecture_picker
    import think
    data = await state.get_data()
    question, d = data.get("think_q"), data.get("think_d") or {}
    if not question:
        await callback.answer(GONE_TEXT, show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    wait = await callback.message.answer("🧠 Думаю ещё раз…")
    uid = callback.from_user.id
    try:
        lectures = await _lectures_for(d, lecture_picker.search_query(question))
        answer = await think.solve(uid, question, d.get("subject", ""), lectures)
    except think.ThinkError as e:
        await wait.edit_text("⏳ " + str(e))
        if "не списана" in str(e):          # не ответила — кнопка снова под ответом
            try:
                offer = await think.offer(uid)
                if offer and offer["left"] != 0:
                    await callback.message.edit_reply_markup(reply_markup=think_kb(offer["left"]))
            except Exception:
                pass
        return
    await wait.delete()
    sent = await answer_model_text(callback.message, answer)
    history = data.get("history") or []
    if await state.get_state() == SolverState.in_dialog.state and history and history[-1]["role"] == "assistant":
        history[-1] = {"role": "assistant", "content": answer}     # уточнять дальше — от нового ответа
        await state.update_data(history=history,
                                msg_ids=data.get("msg_ids", []) + [m.message_id for m in sent])
    await offer_think(uid, state, sent, question, d)


# ── «Подумать» сразу (Никита 18.10: «выбрать перед ответом») ──────────────
# В решалке (/solve) под «Пришли задачу» — кнопка-переключатель: включил —
# задачу сразу решает модель второго уровня, без первого обычного ответа.
# Вне решалки — /think вопрос (или /think, потом вопрос). Лимит — think.py,
# обычный дневной счёт ai_quota не трогается; к фото — нет.
THINK_ARM_CB = "think:arm"
ARM_TEXT = ("🧠 Нужен разбор поглубже? Включи «Подумать» — Капибара решит задачу, "
            "подумав подольше («Капибара+», {left}).\nВне решалки — /think и вопрос.")
ARM_GONE = "Задача уже решена — включи «Подумать» в новой: /solve"
THINK_ASK = ("🧠 Пиши вопрос — Капибара решит его, подумав подольше ({left}).\n"
             "Передумал — /cancel")
PHOTO_NO_THINK = "К фото «Подумать» не работает — пришли задачу текстом или /cancel"


class ThinkState(StatesGroup):
    waiting = State()       # /think без текста: следующий вопрос — «подумав»


def _left_text(left: int | None) -> str:
    return "без лимита" if left is None else f"{left} на сегодня"


def arm_kb(left: int | None, on: bool) -> InlineKeyboardMarkup:
    """left=None — безлимит, без счётчика."""
    n = "" if left is None else f" · {left}"
    text = f"✅ Подумать включено{n}" if on else f"🧠 Подумать{n}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=THINK_ARM_CB)]])


async def offer_arm(message: Message) -> Message | None:
    """Переключатель «Подумать» под «Пришли задачу» — подписчику, пока на
    сегодня не кончилось (кончилось — не предлагаем вовсе)."""
    import think
    offer = await think.offer(message.from_user.id)
    if not offer or offer["left"] == 0:
        return None
    return await message.answer(ARM_TEXT.format(left=_left_text(offer["left"])),
                                reply_markup=arm_kb(offer["left"], False))


async def drop_arm(message: Message, state: FSMContext, data: dict):
    """Задача ушла — переключатель под «Пришли задачу» больше не нужен."""
    mid = data.get("think_arm")
    if not mid:
        return
    await state.update_data(think_arm=None, think_next=False)
    try:
        await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=mid, reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data == THINK_ARM_CB)
async def toggle_arm(callback: CallbackQuery, state: FSMContext):
    import think
    data = await state.get_data()
    if await state.get_state() != SolverState.waiting_task.state or data.get("think_arm") != callback.message.message_id:
        await callback.answer(ARM_GONE, show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    uid = callback.from_user.id
    on = not data.get("think_next")
    why = await think.why_not(uid) if on else None
    if why:
        await state.update_data(think_next=False)
        await callback.answer(why, show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    await state.update_data(think_next=on)
    await callback.answer("Капибара решит задачу, подумав подольше" if on else "Решу как обычно")
    try:
        await callback.message.edit_reply_markup(reply_markup=arm_kb(await think.left_or_none(uid), on))
    except Exception:
        pass


async def _think_first(message: Message, question: list, subject: str = "", lectures: str = "") -> str | None:
    """Вопрос сразу моделью второго уровня: ответ или None (причина уже
    написана человеку; попытка при сбое не списана)."""
    import think
    wait = await message.answer("🧠 Думаю как следует…")
    try:
        answer = await think.solve(message.from_user.id, question, subject, lectures, first=True)
    except think.ThinkError as e:
        await wait.edit_text("⏳ " + str(e))
        return None
    try:
        await wait.delete()
    except Exception:
        pass
    return answer


async def first_think(message: Message, state: FSMContext, data: dict):
    """Задача в решалке со включённым «Подумать»: дальше — обычный диалог."""
    subject = data.get("subject", "")
    await drop_arm(message, state, data)
    question = [{"role": "user", "content": f"Задание:\n{message.text}"}]
    answer = await _think_first(message, question, subject, await _lectures_for(data, message.text))
    if answer is None:
        await message.answer("Можно прислать задачу ещё раз — решу как обычно.")
        return
    await add_solver_history(message.from_user.id, message.text, answer, subject)
    await state.update_data(history=question + [{"role": "assistant", "content": answer}])
    await state.set_state(SolverState.in_dialog)
    await send_answer(message, state, answer)


async def _think_free(message: Message, state: FSMContext, text: str):
    question = [{"role": "user", "content": f"Задание:\n{text}"}]
    answer = await _think_first(message, question)
    if answer is None:
        return
    await add_solver_history(message.from_user.id, text, answer)
    sent = await answer_model_text(message, answer)
    await offer_think(message.from_user.id, state, sent, question, {})


@router.message(Command("think"), PRIVATE)
async def cmd_think(message: Message, state: FSMContext):
    """/think вопрос — сразу «подумав»; /think — следующий вопрос «подумав»."""
    import think
    why = await think.why_not(message.from_user.id)
    if why:
        await message.answer("⏳ " + why)
        return
    text = ((message.text or "").split(maxsplit=1)[1:] or [""])[0].strip()
    if text:
        await _think_free(message, state, text)
        return
    await state.set_state(ThinkState.waiting)
    await message.answer(THINK_ASK.format(left=_left_text(await think.left_or_none(message.from_user.id))))


@router.message(ThinkState.waiting, F.text, PRIVATE)
async def think_waiting_text(message: Message, state: FSMContext):
    await state.clear()
    await _think_free(message, state, message.text)


@router.message(ThinkState.waiting, F.photo, PRIVATE)
async def think_waiting_photo(message: Message):
    await message.answer(PHOTO_NO_THINK)


@router.message(Command("aithink"), PRIVATE)
async def cmd_aithink(message: Message):
    """/aithink on|off — выключатель «Подумать ещё» для отката (у старосты)."""
    import think
    from config import is_starosta
    from database import set_setting
    if not is_starosta(message.from_user.id):
        return
    arg = (message.text or "").split(maxsplit=1)[1:]
    if arg and arg[0].strip().lower() in ("on", "off"):
        await set_setting("ai_think", arg[0].strip().lower())
    await message.answer(await think.status_line() + "\n\n/aithink on · /aithink off")


# /start обещает «пришли фото задачи — отвечу», а фото без /solve раньше
# никто не ловил. Подпись к фото — вопрос к нему.
@router.message(F.photo, StateFilter(None), PRIVATE)
async def handle_plain_photo(message: Message, bot: Bot):
    if (why := await _ai_block(message)):
        await message.answer(why)
        return
    wait = await message.answer("🧠 Анализирую фото...")
    try:
        answer = await _photo_answer(message, bot, {})
        if not answer or len(answer.strip()) < 10:
            await wait.edit_text(PHOTO_FAIL)
            return
        await wait.delete()
        await add_solver_history(message.from_user.id, ("[фото] " + (message.caption or "")).strip(), answer)
        await answer_model_text(message, answer)
    except Exception as e:
        logger.error(f"решалка (фото): {e!r}")
        await wait.edit_text("❌ ИИ сейчас не ответил — попробуй ещё раз через минуту")


# ── Решалка по лекциям (Gemini, Фаза 9) ─────────────────────────────────────

@router.message(Command("solve_lectures"), PRIVATE)
async def cmd_solve_lectures(message: Message, state: FSMContext):
    await upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    subjects = await get_subjects_with_lecture_text()
    if not subjects:
        await message.answer(
            "📖 Пока ни по одному предмету нет загруженных лекций с текстом "
            "(PDF/DOCX/PPTX не-сканы). Сначала загрузи через /upload — если формат "
            "поддерживается, бот сам заберёт текст в контекст."
        )
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=s)] for s in subjects],
        resize_keyboard=True, one_time_keyboard=True
    )
    await state.set_state(LectureSolverState.choose_subject)
    await message.answer("📖 По какому предмету решаем — на основе загруженных лекций?", reply_markup=kb)


@router.message(LectureSolverState.choose_subject, F.text)
async def lecture_choose_subject(message: Message, state: FSMContext):
    if message.text in MENU_BUTTON_TEXTS:
        await state.clear()
        return
    subject = message.text.strip()
    subjects = await get_subjects_with_lecture_text()
    if subject not in subjects:
        await message.answer("Не нашёл такой предмет среди тех, где есть лекции — выбери кнопкой из списка выше.")
        return
    await state.update_data(subject=subject)
    await state.set_state(LectureSolverState.waiting_task)
    await message.answer(
        f"✅ Предмет: <b>{esc(subject)}</b>\n\nПришли текст задания (практики) — решу, опираясь на лекции этого предмета.",
        parse_mode="HTML", reply_markup=CANCEL_KB
    )


@router.message(LectureSolverState.waiting_task, F.text, PRIVATE)
async def lecture_handle_task(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=MAIN_KB)
        return
    if (why := await _ai_block(message)):
        await message.answer(why)       # состояние не сбрасываем — можно прислать ещё раз
        return

    data    = await state.get_data()
    subject = data.get("subject", "")
    wait = await message.answer("📖 Читаю лекции и решаю — с большим контекстом это может занять чуть больше времени...")
    try:
        import lecture_picker
        context_text = lecture_picker.pick(await get_subject_lecture_context(subject), message.text)
        answer = await solve_with_lecture_context(message.text, subject, context_text)
        await wait.delete()
        await add_solver_history(message.from_user.id, message.text, answer, subject)
        await answer_model_text(message, answer)
        await message.answer("Готово ✅ (/solve_lectures — ещё раз по этому или другому предмету)", reply_markup=MAIN_KB)
    except Exception as e:
        logger.error(e)
        await wait.edit_text(f"❌ Ошибка: {e}")
    finally:
        await state.clear()
