import aiosqlite
from config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # WAL снижает риск "database is locked" при параллельных cron-джобах
        # (scheduler.py гоняет несколько задач) вместе с обычными хендлерами.
        await db.execute("PRAGMA journal_mode=WAL;")
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
                done        INTEGER DEFAULT 0,
                external_id TEXT
            )
        """)
        # Миграция для баз, созданных до появления external_id (автосинк СДО).
        try:
            await db.execute("ALTER TABLE deadlines ADD COLUMN external_id TEXT")
        except Exception:
            pass  # колонка уже есть
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
        # ── Диффы расписания ─────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_snapshots (
                date        TEXT PRIMARY KEY,
                events_json TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Заметки на конкретный день/пару ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lesson_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                subject     TEXT,
                text        TEXT NOT NULL,
                created_by  INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # ── Лента "Подслушано" ───────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feed_posts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT,
                photo_file_id TEXT,
                author_id   INTEGER NOT NULL,
                message_id  INTEGER,
                created_at  TEXT DEFAULT (datetime('now')),
                deleted     INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feed_reactions (
                post_id  INTEGER,
                user_id  INTEGER,
                emoji    TEXT,
                PRIMARY KEY (post_id, user_id)
            )
        """)

        # ── Полнотекстовый поиск по файлам (Фаза 6) ─────────────────────────
        # external-content FTS5 таблица над files: не дублирует данные, триггеры
        # держат индекс в синхроне при add_file/delete_file. Полезно, когда файлов
        # много и пролистывать по предметам неудобно — ищем по названию/предмету/
        # имени файла одним запросом.
        try:
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                    title, subject, file_name, content='files', content_rowid='id'
                )
            """)
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                    INSERT INTO files_fts(rowid, title, subject, file_name)
                    VALUES (new.id, new.title, new.subject, new.file_name);
                END
            """)
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, title, subject, file_name)
                    VALUES ('delete', old.id, old.title, old.subject, old.file_name);
                END
            """)
            await db.execute("""
                CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, title, subject, file_name)
                    VALUES ('delete', old.id, old.title, old.subject, old.file_name);
                    INSERT INTO files_fts(rowid, title, subject, file_name)
                    VALUES (new.id, new.title, new.subject, new.file_name);
                END
            """)
            # На случай, если files_fts только что создалась, а files уже не пустая
            # (апгрейд существующей базы) — досыпаем индекс задним числом.
            await db.execute("INSERT INTO files_fts(files_fts) VALUES ('rebuild')")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"FTS5 недоступен, поиск по файлам работать не будет: {e}")

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

async def add_deadline(subject, description, due_date, due_time, created_by, external_id=None) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO deadlines (subject, description, due_date, due_time, created_by, external_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (subject, description, due_date, due_time, created_by, external_id))
        await db.commit()
        return cursor.lastrowid

async def get_deadline_by_external_id(external_id: str) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE external_id=?", (external_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

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

async def search_files(query: str, limit: int = 20) -> list[dict]:
    """Полнотекстовый поиск по title/subject/file_name через FTS5.
    Каждое слово запроса — отдельная кавычка-фраза (без спецсимволов
    FTS5-синтаксиса), между словами — неявный AND. Пустой/бессмысленный
    запрос и отсутствие таблицы (FTS5 недоступен) — просто пустой список,
    а не ошибка."""
    tokens = [t.replace('"', '') for t in query.strip().split() if t.strip('"')]
    if not tokens:
        return []
    fts_query = " ".join(f'"{t}"' for t in tokens)
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT files.* FROM files_fts
                JOIN files ON files.id = files_fts.rowid
                WHERE files_fts MATCH ?
                ORDER BY bm25(files_fts)
                LIMIT ?
            """, (fts_query, limit))
            return [dict(r) for r in await cursor.fetchall()]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"search_files failed: {e}")
        return []


# ── Очистка семестра (для /clearsem) ────────────────────────────────────────
# Сносит "живые" данные конкретного семестра — дедлайны, доску ДЗ, файлы,
# голосования. НЕ трогает: подписки/настройки пользователей, историю решений
# решалки, заметки на пары, ленту "Подслушано", zam_id в settings —
# это либо личные настройки, либо архив, который не привязан к семестру.
async def clear_semester_data():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        for table in ("deadlines", "homework", "files", "vote_answers", "votes"):
            try:
                await db.execute(f"DELETE FROM {table}")
            except Exception:
                pass  # таблицы homework/votes создаются лениво — их может не быть
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


# ── Лента "Подслушано" ────────────────────────────────────────────────────────

async def get_last_feed_post_time(author_id: int) -> str | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT created_at FROM feed_posts
            WHERE author_id=? AND deleted=0
            ORDER BY created_at DESC LIMIT 1
        """, (author_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def add_feed_post(text: str, photo_file_id: str, author_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO feed_posts (text, photo_file_id, author_id) VALUES (?, ?, ?)
        """, (text, photo_file_id, author_id))
        await db.commit()
        return cursor.lastrowid

async def set_feed_post_message_id(post_id: int, message_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE feed_posts SET message_id=? WHERE id=?", (message_id, post_id))
        await db.commit()

async def get_feed_post(post_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM feed_posts WHERE id=?", (post_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_feed_post(post_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE feed_posts SET deleted=1 WHERE id=?", (post_id,))
        await db.commit()

async def set_feed_reaction(post_id: int, user_id: int, emoji: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO feed_reactions (post_id, user_id, emoji) VALUES (?, ?, ?)
        """, (post_id, user_id, emoji))
        await db.commit()

async def get_feed_reaction_counts(post_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT emoji, COUNT(*) as cnt FROM feed_reactions WHERE post_id=? GROUP BY emoji
        """, (post_id,))
        rows = await cursor.fetchall()
        return {r[0]: r[1] for r in rows}


# ── Диффы расписания ─────────────────────────────────────────────────────────

async def get_schedule_snapshot(date_str: str) -> list | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT events_json FROM schedule_snapshots WHERE date=?", (date_str,))
        row = await cursor.fetchone()
        if not row:
            return None
        import json
        return json.loads(row[0])

async def save_schedule_snapshot(date_str: str, events: list):
    import json
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO schedule_snapshots (date, events_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(date) DO UPDATE SET
                events_json = excluded.events_json,
                updated_at  = excluded.updated_at
        """, (date_str, json.dumps(events, ensure_ascii=False)))
        await db.commit()


# ── Заметки на день/пару ─────────────────────────────────────────────────────

async def add_lesson_note(date_str: str, subject: str, text: str, created_by: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO lesson_notes (date, subject, text, created_by) VALUES (?, ?, ?, ?)
        """, (date_str, subject, text, created_by))
        await db.commit()
        return cursor.lastrowid

async def get_lesson_notes(date_str: str) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM lesson_notes WHERE date=? ORDER BY created_at
        """, (date_str,))
        return [dict(r) for r in await cursor.fetchall()]

async def delete_lesson_note(note_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM lesson_notes WHERE id=?", (note_id,))
        await db.commit()
