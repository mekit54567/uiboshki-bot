"""СДО: входы студентов (зашифрованные куки) и история баллов."""

import aiosqlite

from database._conn import connect


async def save_score_points(user_id: int, day: str, scores: dict[int, float]):
    async with connect() as db:
        await db.executemany("INSERT OR REPLACE INTO sdo_score_history (user_id, course_id, day, score) VALUES (?, ?, ?, ?)",
                             [(user_id, cid, day, sc) for cid, sc in scores.items()])
        await db.commit()


async def get_score_points(user_id: int, course_id: int, since: str) -> list[tuple[str, float]]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT day, score FROM sdo_score_history WHERE user_id=? AND course_id=? AND day>=? ORDER BY day",
            (user_id, course_id, since))).fetchall()
        return [(d, s) for d, s in rows]


async def save_attendance_points(user_id: int, day: str, points: dict[int, tuple[float, float]]):
    """{курс: (баллы за посещаемость, максимум)} на день — последняя за день."""
    async with connect() as db:
        await db.executemany(
            "INSERT OR REPLACE INTO sdo_attendance_history (user_id, course_id, day, score, max) VALUES (?, ?, ?, ?, ?)",
            [(user_id, cid, day, sc, mx) for cid, (sc, mx) in points.items()])
        await db.commit()


async def get_attendance_points(user_id: int, course_id: int, since: str) -> list[tuple[str, float]]:
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT day, score FROM sdo_attendance_history WHERE user_id=? AND course_id=? AND day>=? ORDER BY day",
            (user_id, course_id, since))).fetchall()
        return [(d, s) for d, s in rows]


async def get_attendance_marks(user_id: int, course_id: int) -> dict[str, str]:
    async with connect() as db:
        rows = await (await db.execute("SELECT day, mark FROM attendance_marks WHERE user_id=? AND course_id=?",
                                       (user_id, course_id))).fetchall()
        return {d: m for d, m in rows}


async def set_attendance_mark(user_id: int, course_id: int, day: str, mark: str | None):
    """mark — "ok" / "excused"; None — снять отметку."""
    async with connect() as db:
        if mark:
            await db.execute("INSERT OR REPLACE INTO attendance_marks (user_id, course_id, day, mark) VALUES (?, ?, ?, ?)",
                             (user_id, course_id, day, mark))
        else:
            await db.execute("DELETE FROM attendance_marks WHERE user_id=? AND course_id=? AND day=?",
                             (user_id, course_id, day))
        await db.commit()


async def get_last_scores(user_id: int) -> dict[int, float]:
    """Последняя записанная сумма баллов по каждому предмету человека."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT h.course_id, h.score FROM sdo_score_history h JOIN (SELECT course_id, MAX(day) d "
            "FROM sdo_score_history WHERE user_id=? GROUP BY course_id) m "
            "ON h.course_id=m.course_id AND h.day=m.d WHERE h.user_id=?", (user_id, user_id))).fetchall()
        return {cid: sc for cid, sc in rows}


async def save_sdo_session(user_id: int, cookie_enc: str, next_check_at: str | None = None, via: str | None = None):
    """Новый вход поверх старого: «делиться с группой» остаётся, как было
    (раньше INSERT OR REPLACE сбрасывал его при каждом переподключении)."""
    async with connect() as db:
        await db.execute("INSERT INTO sdo_sessions (user_id, cookie_enc, status, checked_at, next_check_at, jitter_left, via) "
                         "VALUES (?, ?, 'ok', datetime('now'), ?, 3, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET cookie_enc=excluded.cookie_enc, status='ok', "
                         "checked_at=excluded.checked_at, next_check_at=excluded.next_check_at, jitter_left=3, "
                         "via=excluded.via", (user_id, cookie_enc, next_check_at, via))
        await db.commit()


async def get_sdo_session(user_id: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM sdo_sessions WHERE user_id=?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_sdo_sessions(status: str = "ok") -> list[dict]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM sdo_sessions WHERE status=?", (status,))
        return [dict(r) for r in await cursor.fetchall()]


async def set_sdo_status(user_id: int, status: str, only_if: str | None = None) -> bool:
    """only_if — зашифрованная кука, которую проверяли: если за время проверки
    человек подключил новую, её статус не трогаем. → изменилось ли."""
    sql, args = "UPDATE sdo_sessions SET status=?, checked_at=datetime('now') WHERE user_id=?", [status, user_id]
    if only_if is not None:
        sql, args = sql + " AND cookie_enc=?", args + [only_if]
    async with connect() as db:
        cur = await db.execute(sql, args)
        await db.commit()
        return cur.rowcount > 0


async def update_sdo_cookie(user_id: int, cookie_enc: str, only_if: str | None = None) -> bool:
    """Перешифровка на новый ключ — без сброса расписания проверок; only_if —
    как у set_sdo_status (не затереть только что подключённый новый вход)."""
    sql, args = "UPDATE sdo_sessions SET cookie_enc=? WHERE user_id=?", [cookie_enc, user_id]
    if only_if is not None:
        sql, args = sql + " AND cookie_enc=?", args + [only_if]
    async with connect() as db:
        cur = await db.execute(sql, args)
        await db.commit()
        return cur.rowcount > 0


async def set_sdo_next_check(user_id: int, next_check_at: str, jitter_left: int):
    async with connect() as db:
        await db.execute("UPDATE sdo_sessions SET next_check_at=?, jitter_left=? WHERE user_id=?",
                         (next_check_at, jitter_left, user_id))
        await db.commit()


async def delete_sdo_session(user_id: int):
    async with connect() as db:
        await db.execute("DELETE FROM sdo_sessions WHERE user_id=?", (user_id,))
        await db.commit()


async def count_sdo_connected() -> int:
    async with connect() as db:
        return (await (await db.execute("SELECT COUNT(*) FROM sdo_sessions WHERE status='ok'")).fetchone())[0]


async def set_sdo_share(user_id: int, share: bool) -> bool:
    """Согласие делиться дедлайнами СДО с группой. → есть ли вход."""
    async with connect() as db:
        cur = await db.execute("UPDATE sdo_sessions SET share=? WHERE user_id=?", (1 if share else 0, user_id))
        await db.commit()
        return cur.rowcount > 0


async def get_group_donors(group_id: int) -> list[dict]:
    """Живые входы людей группы, согласных делиться (свежепроверенные — первыми)."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT s.* FROM sdo_sessions s JOIN users u ON u.user_id = s.user_id "
            "WHERE u.group_id = ? AND s.status = 'ok' AND COALESCE(s.share, 0) = 1 "
            "ORDER BY s.checked_at DESC", (group_id,))
        return [dict(r) for r in await cursor.fetchall()]


async def get_sharing_groups() -> list[int]:
    """Чужие группы, где хоть кто-то делится СДО."""
    from config import HOME_GROUP_ID
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT DISTINCT u.group_id FROM sdo_sessions s JOIN users u ON u.user_id = s.user_id "
            "WHERE s.status = 'ok' AND COALESCE(s.share, 0) = 1 AND u.group_id IS NOT NULL AND u.group_id != ?",
            (HOME_GROUP_ID,))).fetchall()
        return [r[0] for r in rows]


# ── Ограничение по времени у тестов (quiz_time.py) ───────────────────────────

async def save_quiz_limits(limits: dict[int, int]):
    """{cmid теста: минуты (0 — без ограничения)} — последнее увиденное."""
    if not limits:
        return
    async with connect() as db:
        await db.executemany(
            "INSERT INTO quiz_limits (cmid, minutes) VALUES (?, ?) "
            "ON CONFLICT(cmid) DO UPDATE SET minutes=excluded.minutes, seen_at=datetime('now')",
            list(limits.items()))
        await db.commit()


async def get_quiz_limits(cmids) -> dict[int, int]:
    cmids = sorted({int(c) for c in cmids if c})
    if not cmids:
        return {}
    async with connect() as db:
        rows = await (await db.execute(
            f"SELECT cmid, minutes FROM quiz_limits WHERE cmid IN ({','.join('?' * len(cmids))})", cmids)).fetchall()
        return {c: m for c, m in rows}


async def get_quiz_deadline_links(since: str) -> list[str]:
    """Ссылки тестов из дедлайнов своей группы со сроком не раньше since."""
    async with connect() as db:
        rows = await (await db.execute(
            "SELECT description FROM deadlines WHERE group_id IS NULL AND due_date >= ? "
            "AND description LIKE '%/mod/quiz/view.php%'", (since,))).fetchall()
        return [r[0] for r in rows]


# ── Тесты СДО в уведомлениях (quiz_alerts.py) ────────────────────────────────

async def get_quiz_opens(cmids=None) -> dict[int, str]:
    """{cmid: «ГГГГ-ММ-ДД ЧЧ:ММ» МСК или '' — открыт, когда — не знаем}."""
    async with connect() as db:
        if cmids is None:
            rows = await (await db.execute("SELECT cmid, open_at FROM quiz_opens")).fetchall()
        else:
            cmids = sorted({int(c) for c in cmids if c})
            if not cmids:
                return {}
            rows = await (await db.execute(
                f"SELECT cmid, open_at FROM quiz_opens WHERE cmid IN ({','.join('?' * len(cmids))})",
                cmids)).fetchall()
        return {c: a for c, a in rows}


async def save_quiz_opens(opens: dict[int, str]):
    if not opens:
        return
    async with connect() as db:
        await db.executemany(
            "INSERT INTO quiz_opens (cmid, open_at) VALUES (?, ?) "
            "ON CONFLICT(cmid) DO UPDATE SET open_at=excluded.open_at, seen_at=datetime('now')",
            list(opens.items()))
        await db.commit()


async def get_quiz_deadlines(since: str) -> list[dict]:
    """Тесты СДО (ссылка на mod/quiz) всех групп со сроком не раньше since."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, subject, description, due_date, due_time, group_id FROM deadlines "
            "WHERE external_id LIKE 'sdo:%' AND due_date >= ? AND description LIKE '%/mod/quiz/view.php%' "
            "ORDER BY due_date, due_time", (since,))).fetchall()
        return [dict(r) for r in rows]


async def mark_quiz_alert(user_id: int, deadline_id: int, kind: str, at: str) -> bool:
    """Отметить «ушло»; True — только в первый раз (проверка и отметка разом:
    напоминание и рассылка после синка не пришлют одно и то же дважды)."""
    async with connect() as db:
        cur = await db.execute("INSERT OR IGNORE INTO quiz_alerts (user_id, deadline_id, kind, at) VALUES (?, ?, ?, ?)",
                               (user_id, deadline_id, kind, at))
        await db.commit()
        return cur.rowcount == 1


async def purge_quiz_alerts():
    """Отметки старше месяца и о дедлайнах, которых уже нет."""
    async with connect() as db:
        await db.execute("DELETE FROM quiz_alerts WHERE sent_at < datetime('now', '-30 days') "
                         "OR deadline_id NOT IN (SELECT id FROM deadlines)")
        await db.commit()
