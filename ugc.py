"""Записи людей: жалоба и «Скрыть автора» (правило Apple 1.2, 5.99.0).

Что пишут сами люди и видят другие — заметки к парам, доска ДЗ, файлы и
общие дедлайны старост. Под каждой чужой записью в приложении — «Пожаловаться»
и «Скрыть автора»:

- жалоба уходит владельцу бота (config.STAROSTA_ID) сообщением с текстом записи,
  автором и кнопками «Удалить» / «Оставить» (handlers/reports.py); таблица
  `reports`. Удалить — запись пропадает у всех, как будто её убрал автор;
- «Скрыть автора» — только у себя (`user_blocks`): его записи больше не видны
  этому человеку. Записи владельца и Капибары (СДО, created_by 0) скрыть
  нельзя — на них можно только пожаловаться.

Правила (legal_texts.RULES): за оскорбления, угрозы, спам и чужие данные
запись удаляем, автора можем отключить.
"""

import logging

logger = logging.getLogger(__name__)

# вид записи → (таблица, колонка автора)
KINDS = {
    "note": ("lesson_notes", "created_by"),
    "hw": ("homework", "created_by"),
    "file": ("files", "uploaded_by"),
    "deadline": ("deadlines", "created_by"),
}
LABELS = {"note": "Заметка к паре", "hw": "ДЗ", "file": "Файл", "deadline": "Общий дедлайн"}
REASON_MAX = 300


class ReportError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


async def item(kind: str, item_id: int) -> dict | None:
    from database import get_deadline, get_file_by_id, get_lesson_note
    from database.homework import get_hw
    get = {"note": get_lesson_note, "hw": get_hw, "file": get_file_by_id, "deadline": get_deadline}.get(kind)
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
    else:
        parts = [row.get("subject") or "", row.get("description") or "", row.get("due_date") or ""]
    return " · ".join(p for p in parts if p)[:900]


async def _visible_to(user_id: int, kind: str, row: dict) -> bool:
    """Жаловаться и скрывать можно только то, что человеку и правда видно."""
    from database.groups import row_group, viewer_group
    if kind == "file":
        from database import file_visible
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
    """«Удалить» — запись пропадает у всех, жалобы на неё закрыты; «Оставить» — только закрыть."""
    from database import delete_deadline, delete_file, delete_hw, delete_lesson_note
    from database._conn import connect
    rep = await get_report(rid)
    if not rep:
        return "missing"
    if rep["status"] != "new":
        return rep["status"]
    status = "removed" if remove else "kept"
    if remove and await item(rep["kind"], rep["item_id"]):
        await {"note": delete_lesson_note, "hw": delete_hw, "file": delete_file,
               "deadline": delete_deadline}[rep["kind"]](rep["item_id"])
    async with connect() as db:
        if remove:
            await db.execute("UPDATE reports SET status='removed' WHERE kind=? AND item_id=? AND status='new'",
                             (rep["kind"], rep["item_id"]))
        else:
            await db.execute("UPDATE reports SET status='kept' WHERE id=?", (rid,))
        await db.commit()
    return status


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
