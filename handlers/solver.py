import logging
import re

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

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
    await state.update_data(msg_ids=[msg.message_id])


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

    for msg in await answer_model_text(message, answer):
        msg_ids.append(msg.message_id)

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
    if (why := await _ai_block(message)):
        await message.answer(why)
        return
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
        await answer_model_text(message, answer)
    except Exception as e:
        logger.error(f"решалка (свободный текст): {e!r}")
        await wait.edit_text("❌ ИИ сейчас не ответил — попробуй ещё раз через минуту")


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
