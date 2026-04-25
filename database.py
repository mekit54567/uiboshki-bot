"""
database.py — работает с Turso (облачный SQLite).
Данные хранятся в облаке и не теряются при перезапуске Railway.

Переменные окружения (Railway Variables):
    TURSO_URL   — libsql://mirea-bot-mekit54567.aws-eu-west-1.turso.io
    TURSO_TOKEN — eyJhbGci...
"""

import os
import libsql_experimental as libsql

TURSO_URL   = os.getenv("TURSO_URL")
TURSO_TOKEN = os.getenv("TURSO_TOKEN")


def get_conn():
    """Открывает соединение с Turso."""
    return libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)


async def init_db():
    """Создаёт все таблицы если их нет. Вызывается при старте бота."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id          INTEGER PRIMARY KEY,
            username         TEXT,
            full_name        TEXT,
            subscribed       INTEGER DEFAULT 1,
            reminder_minutes INTEGER DEFAULT 15,
            joined_at        TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS deadlines (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject     TEXT NOT NULL,
            description TEXT,
            due_date    TEXT NOT NULL,
            due_time    TEXT,
            created_by  INTEGER,
            created_at  TEXT DEFAULT (datetime('now')),
            done        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS solver_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            task_text  TEXT,
            answer     TEXT,
            subject    TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            subject     TEXT,
            file_id     TEXT NOT NULL,
            file_name   TEXT,
            uploaded_by INTEGER,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS votes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            question   TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            active     INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS vote_answers (
            vote_id INTEGER,
            user_id INTEGER,
            answer  TEXT,
            PRIMARY KEY (vote_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS group_members (
            user_id   INTEGER PRIMARY KEY,
            full_name TEXT,
            username  TEXT
        );
        CREATE TABLE IF NOT EXISTS homework (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            subject    TEXT NOT NULL,
            content    TEXT,
            file_id    TEXT,
            file_type  TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rows_as_dicts(cursor) -> list[dict]:
    """Конвертирует строки курсора в список словарей."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username  = excluded.username,
            full_name = excluded.full_name
    """, (user_id, username, full_name))
    conn.commit()


async def get_user(user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


async def get_all_subscribed_users() -> list[int]:
    conn = get_conn()
    cur = conn.execute("SELECT user_id FROM users WHERE subscribed = 1")
    return [r[0] for r in cur.fetchall()]


async def set_subscription(user_id: int, value: int):
    conn = get_conn()
    conn.execute("UPDATE users SET subscribed = ? WHERE user_id = ?", (value, user_id))
    conn.commit()


async def get_reminder_minutes(user_id: int) -> int:
    conn = get_conn()
    cur = conn.execute("SELECT reminder_minutes FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 15


async def set_reminder_minutes(user_id: int, minutes: int):
    conn = get_conn()
    conn.execute("UPDATE users SET reminder_minutes = ? WHERE user_id = ?", (minutes, user_id))
    conn.commit()


# ── Deadlines ─────────────────────────────────────────────────────────────────

async def add_deadline(subject, description, due_date, due_time, created_by) -> int:
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO deadlines (subject, description, due_date, due_time, created_by)
        VALUES (?, ?, ?, ?, ?)
    """, (subject, description, due_date, due_time, created_by))
    conn.commit()
    return cur.lastrowid


async def get_active_deadlines() -> list[dict]:
    conn = get_conn()
    cur = conn.execute("SELECT * FROM deadlines WHERE done=0 ORDER BY due_date, due_time")
    return _rows_as_dicts(cur)


async def get_deadlines_soon(days=3) -> list[dict]:
    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM deadlines WHERE done=0
        AND due_date BETWEEN date('now') AND date('now', ? || ' days')
        ORDER BY due_date, due_time
    """, (str(days),))
    return _rows_as_dicts(cur)


async def get_deadline_stats() -> dict:
    conn = get_conn()
    total   = conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
    done    = conn.execute("SELECT COUNT(*) FROM deadlines WHERE done=1").fetchone()[0]
    overdue = conn.execute("SELECT COUNT(*) FROM deadlines WHERE done=0 AND due_date < date('now')").fetchone()[0]
    active  = conn.execute("SELECT COUNT(*) FROM deadlines WHERE done=0 AND due_date >= date('now')").fetchone()[0]
    return {"total": total, "done": done, "overdue": overdue, "active": active}


async def mark_deadline_done(did: int):
    conn = get_conn()
    conn.execute("UPDATE deadlines SET done=1 WHERE id=?", (did,))
    conn.commit()


async def delete_deadline(did: int):
    conn = get_conn()
    conn.execute("DELETE FROM deadlines WHERE id=?", (did,))
    conn.commit()


# ── Solver history ────────────────────────────────────────────────────────────

async def add_solver_history(user_id: int, task: str, answer: str, subject: str = ""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO solver_history (user_id, task_text, answer, subject)
        VALUES (?, ?, ?, ?)
    """, (user_id, task[:500], answer[:2000], subject))
    conn.commit()


async def get_solver_history(user_id: int, limit=5) -> list[dict]:
    conn = get_conn()
    cur = conn.execute("""
        SELECT * FROM solver_history WHERE user_id=?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit))
    return _rows_as_dicts(cur)


# ── Files ─────────────────────────────────────────────────────────────────────

async def add_file(title, subject, file_id, file_name, uploaded_by) -> int:
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO files (title, subject, file_id, file_name, uploaded_by)
        VALUES (?, ?, ?, ?, ?)
    """, (title, subject, file_id, file_name, uploaded_by))
    conn.commit()
    return cur.lastrowid


async def get_files(subject: str = None) -> list[dict]:
    conn = get_conn()
    if subject:
        cur = conn.execute("SELECT * FROM files WHERE subject=? ORDER BY created_at DESC", (subject,))
    else:
        cur = conn.execute("SELECT * FROM files ORDER BY created_at DESC")
    return _rows_as_dicts(cur)


async def delete_file(fid: int):
    conn = get_conn()
    conn.execute("DELETE FROM files WHERE id=?", (fid,))
    conn.commit()


# ── Votes ─────────────────────────────────────────────────────────────────────

async def create_vote(question: str, created_by: int) -> int:
    conn = get_conn()
    cur = conn.execute("INSERT INTO votes (question, created_by) VALUES (?, ?)", (question, created_by))
    conn.commit()
    return cur.lastrowid


async def get_active_vote() -> dict | None:
    conn = get_conn()
    cur = conn.execute("SELECT * FROM votes WHERE active=1 ORDER BY created_at DESC LIMIT 1")
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


async def add_vote_answer(vote_id: int, user_id: int, answer: str):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO vote_answers (vote_id, user_id, answer) VALUES (?, ?, ?)
    """, (vote_id, user_id, answer))
    conn.commit()


async def get_vote_results(vote_id: int) -> dict:
    conn = get_conn()
    cur = conn.execute("""
        SELECT answer, COUNT(*) as cnt FROM vote_answers WHERE vote_id=? GROUP BY answer
    """, (vote_id,))
    return {r[0]: r[1] for r in cur.fetchall()}


async def close_vote(vote_id: int):
    conn = get_conn()
    conn.execute("UPDATE votes SET active=0 WHERE id=?", (vote_id,))
    conn.commit()
