"""Записи людей: жалоба и «Скрыть автора» (правило Apple 1.2, 5.99.0).

Что пишут сами люди и видят другие — заметки к парам, комментарии под парой,
доска ДЗ, файлы и общие дедлайны старост. Под каждой чужой записью в приложении — «Пожаловаться»
и «Скрыть автора»:

- жалоба уходит владельцу бота (config.STAROSTA_ID) сообщением с текстом записи,
  автором и кнопками «Удалить» / «Оставить» (handlers/reports.py); таблица
  `reports`. Удалить — запись пропадает у всех, как будто её убрал автор;
- «Скрыть автора» — только у себя (`user_blocks`): его записи больше не видны
  этому человеку. Записи владельца и Капибары (СДО, created_by 0) скрыть
  нельзя — на них можно только пожаловаться.

Правила (legal_texts.RULES): за оскорбления, угрозы, спам и чужие данные
запись удаляем, автора можем отключить.

Спор (Никита 18.10: «добавить возможность оспорить»): удалённая по жалобе
запись сохраняется копией в `reports.snapshot` на DISPUTE_DAYS дней, автору
приходит сообщение с кнопкой «Оспорить» → бот просит одним сообщением написать,
с чем он не согласен и почему (Никита 18.10, до APPEAL_MAX знаков, есть отмена;
`reports.appeal`) → владельцу заявка с этим текстом и «Вернуть» / «Оставить
скрытым» → автору ответ. «Вернуть» кладёт запись обратно с тем же id.
"""

import logging

logger = logging.getLogger(__name__)

# вид записи → (таблица, колонка автора)
KINDS = {
    "note": ("lesson_notes", "created_by"),
    "hw": ("homework", "created_by"),
    "file": ("files", "uploaded_by"),
    "deadline": ("deadlines", "created_by"),
    "comment": ("lesson_comments", "user_id"),
}
LABELS = {"note": "Заметка к паре", "hw": "ДЗ", "file": "Файл", "deadline": "Общий дедлайн",
          "comment": "Комментарий под парой"}
REASON_MAX = 300
DISPUTE_DAYS = 30
APPEAL_MIN, APPEAL_MAX = 10, 500       # объяснение автора к спору, знаков


class ReportError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


async def item(kind: str, item_id: int) -> dict | None:
    import lesson_comments
    from database import get_deadline, get_file_by_id, get_lesson_note
    from database.homework import get_hw
    get = {"note": get_lesson_note, "hw": get_hw, "file": get_file_by_id, "deadline": get_deadline,
           "comment": lesson_comments.get}.get(kind)
    if not get:
        return None
    row = await get(item_id)
    if kind == "deadline" and row and ((row.get("external_id") or "").startswith("sdo:") or row.get("personal")):
        return None                                   # из СДО или чужой личный — не запись человека
    return row


def author_of(kind: str, row: dict) -> int:
    return int(row.get(KINDS[kind][1]) or 0)


def preview(kind: str, row: dict) -> str:
    if kind == "note":
        parts = [row.get("subject") or "", row.get("text") or ""]
    elif kind == "hw":
        parts = [row.get("subject") or "", row.get("content") or "", "📎 файл" if row.get("file_id") else ""]
    elif kind == "file":
        parts = [row.get("subject") or "", row.get("title") or "", row.get("file_name") or ""]
    elif kind == "comment":
        parts = [(row.get("lesson") or "").split("|", 1)[-1], row.get("text") or ""]
    else:
        parts = [row.get("subject") or "", row.get("description") or "", row.get("due_date") or ""]
    return " · ".join(p for p in parts if p)[:900]


async def _visible_to(user_id: int, kind: str, row: dict) -> bool:
    """Жаловаться и скрывать можно только то, что человеку и правда видно."""
    from database.groups import row_group, viewer_group
    if kind == "file":
        from database.files import file_visible
        return await file_visible(row["id"], await viewer_group(user_id))
    return row_group(row.get("group_id")) == await viewer_group(user_id)


async def _checked(user_id: int, kind: str, item_id: int) -> dict:
    row = await item(kind, item_id)
    if not row or not await _visible_to(user_id, kind, row):
        raise ReportError("Запись не найдена — может, её уже убрали", 404)
    if author_of(kind, row) == user_id:
        raise ReportError("Это твоя запись — её можно просто убрать")
    return row


async def report(bot, user_id: int, kind: str, item_id: int, reason: str = "") -> int:
    """Жалоба → таблица reports и сообщение владельцу. Повтор от того же
    человека на ту же запись — та же жалоба, без второго сообщения."""
    import ratelimit
    from database._conn import connect
    if kind not in KINDS:
        raise ReportError("Не знаю такой записи")
    row = await _checked(user_id, kind, item_id)
    reason = (reason or "").strip()[:REASON_MAX]
    async with connect() as db:
        old = await (await db.execute(
            "SELECT id FROM reports WHERE user_id=? AND kind=? AND item_id=? AND status='new'",
            (user_id, kind, item_id))).fetchone()
        if old:
            return old[0]
        if not ratelimit.allow("report", user_id):
            raise ReportError("Много жалоб подряд — подожди пару минут", 429)
        cur = await db.execute("INSERT INTO reports (user_id, kind, item_id, author_id, reason) VALUES (?, ?, ?, ?, ?)",
                               (user_id, kind, item_id, author_of(kind, row) or None, reason))
        rid = cur.lastrowid
        await db.commit()
    await _notify_owner(bot, rid, kind, row, reason)
    return rid


async def _notify_owner(bot, rid: int, kind: str, row: dict, reason: str):
    import config
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from database import get_user
    from utils import esc
    if not config.STAROSTA_ID or bot is None:
        logger.warning(f"жалоба {rid}: некому отправить")
        return
    author = await get_user(author_of(kind, row)) if author_of(kind, row) else None
    who = (author or {}).get("full_name") or (author or {}).get("username") or f"id {author_of(kind, row)}"
    text = (f"🚩 <b>Жалоба</b> · {LABELS[kind]}\n\n"
            f"<blockquote>{esc(preview(kind, row))}</blockquote>\n"
            f"Автор: {esc(who)}" + (f"\nПричина: {esc(reason)}" if reason else ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"rep:del:{rid}"),
        InlineKeyboardButton(text="Оставить", callback_data=f"rep:keep:{rid}"),
    ]])
    try:
        await bot.send_message(config.STAROSTA_ID, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning(f"жалоба {rid}: не отправилась владельцу: {e}")


async def get_report(rid: int) -> dict | None:
    import aiosqlite
    from database._conn import connect
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM reports WHERE id=?", (rid,))).fetchone()
        return dict(row) if row else None


async def decide(rid: int, remove: bool) -> str:
    """«Удалить» — запись пропадает у всех (копия — в жалобе, для спора), жалобы
    на неё закрыты; «Оставить» — только закрыть."""
    import json
    import lesson_comments
    from database import delete_deadline, delete_file, delete_hw, delete_lesson_note
    from database._conn import connect
    rep = await get_report(rid)
    if not rep:
        return "missing"
    if rep["status"] != "new":
        return rep["status"]
    status = "removed" if remove else "kept"
    snap = None
    if remove and await item(rep["kind"], rep["item_id"]):
        snap = json.dumps(await _snapshot(rep["kind"], rep["item_id"]), ensure_ascii=False)
        await {"note": delete_lesson_note, "hw": delete_hw, "file": delete_file,
               "deadline": delete_deadline, "comment": lesson_comments.delete}[rep["kind"]](rep["item_id"])
    async with connect() as db:
        if remove:
            await db.execute("UPDATE reports SET status='closed' WHERE kind=? AND item_id=? AND status='new' AND id<>?",
                             (rep["kind"], rep["item_id"], rid))
            await db.execute("UPDATE reports SET status='removed', snapshot=? WHERE id=?", (snap, rid))
        else:
            await db.execute("UPDATE reports SET status='kept' WHERE id=?", (rid,))
        # копии и объяснения старше срока спора — не храним (152-ФЗ: не дольше нужного);
        # спор, который ещё ждёт решения, — держим, иначе «Вернуть» уже нечего
        await db.execute("UPDATE reports SET snapshot=NULL, appeal='' WHERE snapshot IS NOT NULL "
                         "AND status<>'disputed' AND created_at < datetime('now', ?)", (f"-{DISPUTE_DAYS} days",))
        await db.commit()
    return status


# ── Спор: копия удалённого, «Оспорить», «Вернуть» / «Оставить скрытым» ──────

_EXTRA = {"file": ("file_text", "file_summaries")}     # что delete_file убирает вместе с файлом


async def _snapshot(kind: str, item_id: int) -> dict:
    import aiosqlite
    from database._conn import connect
    table = KINDS[kind][0]
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,))).fetchone()
        snap = {"row": dict(row) if row else None}
        for t in _EXTRA.get(kind, ()):
            snap[t] = [dict(r) for r in await (await db.execute(
                f"SELECT * FROM {t} WHERE file_id=?", (item_id,))).fetchall()]
    return snap


async def _restore(kind: str, snap: dict) -> bool:
    from database._conn import connect
    row = snap.get("row")
    if not row:
        return False

    async def put(db, table: str, r: dict):
        cols = ", ".join(r)
        await db.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({', '.join('?' * len(r))})",
                         list(r.values()))

    async with connect() as db:
        await put(db, KINDS[kind][0], row)
        for t in _EXTRA.get(kind, ()):
            for r in snap.get(t) or []:
                await put(db, t, r)
        if kind == "file" and row.get("source"):            # delete_file запомнил его как «не выгружать»
            await db.execute("DELETE FROM files_skipped WHERE source=?", (row["source"],))
        await db.commit()
    return True


def _snap_preview(rep: dict) -> str:
    import json
    try:
        row = (json.loads(rep.get("snapshot") or "{}") or {}).get("row")
    except ValueError:
        row = None
    return preview(rep["kind"], row) if row else ""


async def tell_author(bot, rid: int):
    """Автору — что его запись убрали и почему, с кнопкой «Оспорить»."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from delivery import deliver
    from utils import esc
    rep = await get_report(rid)
    if not rep or rep["status"] != "removed" or not rep["author_id"] or bot is None:
        return
    text = (f"🗑 Твою запись убрали по жалобе · {LABELS[rep['kind']].lower()}\n\n"
            f"<blockquote>{esc(_snap_preview(rep))}</blockquote>\n"
            + (f"Причина: {esc(rep['reason'])}\n" if rep["reason"] else "")
            + f"Правила — /rules. Считаешь, что зря, — нажми «Оспорить» и напиши, с чем не согласен "
            f"({DISPUTE_DAYS} дней).")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оспорить", callback_data=f"dis:{rid}")]])
    try:
        await deliver(bot, rep["author_id"], text, kind="ugc", reply_markup=kb)
    except Exception as e:
        logger.info(f"жалоба {rid}: автору не сказать: {e!r}")


async def can_dispute(rid: int, user_id: int) -> str:
    """Можно ли автору оспорить: "removed" — да; иначе что ответить."""
    rep = await get_report(rid)
    if not rep or rep["author_id"] != user_id:
        return "missing"
    if rep["status"] != "removed":
        return rep["status"]
    return "removed" if rep.get("snapshot") else "expired"


async def dispute(bot, rid: int, user_id: int, appeal: str = "") -> str:
    """Спор автора с его объяснением → владельцу заявка «Вернуть» / «Оставить скрытым»."""
    import config
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from database._conn import connect
    from utils import esc
    status = await can_dispute(rid, user_id)
    if status != "removed":
        return status
    appeal = (appeal or "").strip()[:APPEAL_MAX]
    async with connect() as db:
        cur = await db.execute("UPDATE reports SET status='disputed', appeal=? WHERE id=? AND status='removed'",
                               (appeal, rid))
        await db.commit()
    if not cur.rowcount:                                  # два нажатия разом — заявка уже ушла
        return "disputed_already"
    rep = await get_report(rid)
    if config.STAROSTA_ID and bot is not None:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="↩️ Вернуть", callback_data=f"rep:back:{rid}"),
            InlineKeyboardButton(text="Оставить скрытым", callback_data=f"rep:hold:{rid}"),
        ]])
        text = (f"⚖️ <b>Оспаривают удаление</b> · {LABELS[rep['kind']]}\n\n"
                f"<blockquote>{esc(_snap_preview(rep))}</blockquote>\n"
                + (f"Жалоба была: {esc(rep['reason'])}\n" if rep["reason"] else "Жалоба без причины\n")
                + (f"\n<b>Автор не согласен:</b>\n<blockquote>{esc(appeal)}</blockquote>" if appeal else ""))
        try:
            await bot.send_message(config.STAROSTA_ID, text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"спор {rid}: не отправился владельцу: {e!r}")
    return "disputed"


async def settle(bot, rid: int, restore: bool) -> str:
    """Решение владельца по спору; автору — ответ."""
    import json
    from database._conn import connect
    from delivery import deliver
    rep = await get_report(rid)
    if not rep:
        return "missing"
    if rep["status"] != "disputed":
        return rep["status"]
    status = "upheld"
    if restore and await _restore(rep["kind"], json.loads(rep.get("snapshot") or "{}")):
        status = "restored"
    async with connect() as db:
        await db.execute("UPDATE reports SET status=?, snapshot=CASE WHEN ?='restored' THEN NULL ELSE snapshot END "
                         "WHERE id=?", (status, status, rid))
        await db.commit()
    text = ("↩️ Посмотрели ещё раз: твою запись вернули, группа снова её видит." if status == "restored" else
            "Посмотрели ещё раз: запись остаётся скрытой, она нарушает правила (/rules).")
    if rep["author_id"] and bot is not None:
        try:
            await deliver(bot, rep["author_id"], text, kind="ugc")
        except Exception as e:
            logger.info(f"спор {rid}: автору не сказать: {e!r}")
    return status


# ── Заметки к парам: антиспам ──────────────────────────────────────────────
# Заметку видит вся группа (Никита 18.10: «чтоб не спамили и понимали, что уйдёт
# всей группе»): не больше NOTE_DAY за сутки от человека и без повторов того же
# текста на тот же день. Старостам — без суточного лимита.
NOTE_DAY = 10


async def note_spam(user_id: int, date: str, text: str, group_id: int | None = None) -> str | None:
    """Почему заметку не принять (текст для человека) или None — можно."""
    from database import is_editor
    from database._conn import connect
    async with connect() as db:
        # lower() в SQLite не знает кириллицы — сравниваем в Python
        mine = await (await db.execute("SELECT text FROM lesson_notes WHERE created_by=? AND date=?",
                                       (user_id, date))).fetchall()
        if any((t or "").strip().casefold() == text.strip().casefold() for (t,) in mine):
            return "Такая заметка на этот день уже есть — группа её видит"
        n = (await (await db.execute(
            "SELECT COUNT(*) FROM lesson_notes WHERE created_by=? AND created_at > datetime('now', '-1 day')",
            (user_id,))).fetchone())[0]
    if n >= NOTE_DAY and not await is_editor(user_id, group_id):
        return f"За сутки — не больше {NOTE_DAY} заметок: их видит вся группа. Попробуй завтра"
    return None


# ── «Скрыть автора» ─────────────────────────────────────────────────────────

async def hide_author(user_id: int, kind: str, item_id: int) -> None:
    import config
    from database._conn import connect
    if kind not in KINDS:
        raise ReportError("Не знаю такой записи")
    row = await _checked(user_id, kind, item_id)
    author = author_of(kind, row)
    if not author or config.is_starosta(author):
        raise ReportError("Это записи Капибары — их не скрыть, но можно пожаловаться")
    async with connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_blocks (user_id, blocked_id) VALUES (?, ?)", (user_id, author))
        await db.commit()


async def hidden(user_id: int) -> set[int]:
    from database._conn import connect
    async with connect() as db:
        try:
            rows = await (await db.execute("SELECT blocked_id FROM user_blocks WHERE user_id=?", (user_id,))).fetchall()
        except Exception:
            return set()
        return {r[0] for r in rows}


async def unhide_all(user_id: int) -> int:
    from database._conn import connect
    async with connect() as db:
        cur = await db.execute("DELETE FROM user_blocks WHERE user_id=?", (user_id,))
        await db.commit()
        return cur.rowcount


def without_hidden(items: list[dict], hidden_ids: set[int], col: str) -> list[dict]:
    if not hidden_ids:
        return items
    return [i for i in items if (i.get(col) or 0) not in hidden_ids]
