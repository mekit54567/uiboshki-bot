import aiosqlite
from config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                subscribed  INTEGER DEFAULT 1,
                reminder_minutes INTEGER DEFAULT 15,
                joined_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                description TEXT,
                due_date    TEXT NOT NULL,
                due_time    TEXT,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                done        INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS solver_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                task_text  TEXT,
                answer     TEXT,
                subject    TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                subject     TEXT,
                file_id     TEXT NOT NULL,
                file_name   TEXT,
                uploaded_by INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                question    TEXT NOT NULL,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                active      INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vote_answers (
                vote_id  INTEGER,
                user_id  INTEGER,
                answer   TEXT,
                PRIMARY KEY (vote_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                user_id   INTEGER PRIMARY KEY,
                full_name TEXT,
                username  TEXT
            )
        """)
        await db.commit()


# ── Users ─────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()

async def get_all_subscribed_users() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE subscribed = 1")
        return [r[0] for r in await cursor.fetchall()]

async def set_subscription(user_id: int, value: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET subscribed = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

async def get_reminder_minutes(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT reminder_minutes FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 15

async def set_reminder_minutes(user_id: int, minutes: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE users SET reminder_minutes = ? WHERE user_id = ?", (minutes, user_id))
        await db.commit()

async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# ── Deadlines ─────────────────────────────────────────────────────────────────

async def add_deadline(subject, description, due_date, due_time, created_by) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO deadlines (subject, description, due_date, due_time, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (subject, description, due_date, due_time, created_by))
        await db.commit()
        return cursor.lastrowid

async def get_active_deadlines() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE done=0 ORDER BY due_date, due_time")
        return [dict(r) for r in await cursor.fetchall()]

async def get_deadlines_soon(days=3) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM deadlines WHERE done=0
            AND due_date BETWEEN date('now') AND date('now', ? || ' days')
            ORDER BY due_date, due_time
        """, (str(days),))
        return [dict(r) for r in await cursor.fetchall()]

async def get_deadline_stats() -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        total   = (await (await db.execute("SELECT COUNT(*) FROM deadlines")).fetchone())[0]
        done    = (await (await db.execute("SELECT COUNT(*) FROM deadlines WHERE done=1")).fetchone())[0]
        overdue = (await (await db.execute("SELECT COUNT(*) FROM deadlines WHERE done=0 AND due_date < date('now')")).fetchone())[0]
        active  = (await (await db.execute("SELECT COUNT(*) FROM deadlines WHERE done=0 AND due_date >= date('now')")).fetchone())[0]
        return {"total": total, "done": done, "overdue": overdue, "active": active}

async def mark_deadline_done(did: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE deadlines SET done=1 WHERE id=?", (did,))
        await db.commit()

async def delete_deadline(did: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM deadlines WHERE id=?", (did,))
        await db.commit()


# ── Solver history ────────────────────────────────────────────────────────────

async def add_solver_history(user_id: int, task: str, answer: str, subject: str = ""):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO solver_history (user_id, task_text, answer, subject)
            VALUES (?, ?, ?, ?)
        """, (user_id, task[:500], answer[:2000], subject))
        await db.commit()

async def get_solver_history(user_id: int, limit=5) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM solver_history WHERE user_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit))
        return [dict(r) for r in await cursor.fetchall()]


# ── Files ─────────────────────────────────────────────────────────────────────

async def add_file(title, subject, file_id, file_name, uploaded_by) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO files (title, subject, file_id, file_name, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
        """, (title, subject, file_id, file_name, uploaded_by))
        await db.commit()
        return cursor.lastrowid

async def get_files(subject: str = None) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if subject:
            cursor = await db.execute("SELECT * FROM files WHERE subject=? ORDER BY created_at DESC", (subject,))
        else:
            cursor = await db.execute("SELECT * FROM files ORDER BY created_at DESC")
        return [dict(r) for r in await cursor.fetchall()]

async def delete_file(fid: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM files WHERE id=?", (fid,))
        await db.commit()


# ── Votes ─────────────────────────────────────────────────────────────────────

async def create_vote(question: str, created_by: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO votes (question, created_by) VALUES (?, ?)
        """, (question, created_by))
        await db.commit()
        return cursor.lastrowid

async def get_active_vote() -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM votes WHERE active=1 ORDER BY created_at DESC LIMIT 1")
        row = await cursor.fetchone()
        return dict(row) if row else None

async def add_vote_answer(vote_id: int, user_id: int, answer: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO vote_answers (vote_id, user_id, answer) VALUES (?, ?, ?)
        """, (vote_id, user_id, answer))
        await db.commit()

async def get_vote_results(vote_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT answer, COUNT(*) as cnt FROM vote_answers WHERE vote_id=? GROUP BY answer
        """, (vote_id,))
        rows = await cursor.fetchall()
        return {r[0]: r[1] for r in rows}

async def close_vote(vote_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE votes SET active=0 WHERE id=?", (vote_id,))
        await db.commit()
