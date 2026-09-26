import secrets

import aiosqlite
from config import DATABASE_PATH, STAROSTA_ID
from utils import today_msk


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # WAL снижает риск "database is locked" при параллельных cron-джобах
        # (scheduler.py гоняет несколько задач) вместе с обычными хендлерами.
        await db.execute("PRAGMA journal_mode=WAL;")
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deadline_done'"
        )
        deadline_done_is_new = (await cursor.fetchone()) is None
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
        # Дедлайн отредактирован вручную (староста поправил название/срок
        # задания из СДО) — автосинк его больше не перезаписывает.
        try:
            await db.execute("ALTER TABLE deadlines ADD COLUMN manual_edit INTEGER DEFAULT 0")
        except Exception:
            pass  # колонка уже есть

        # Персональный токен подписки на ICS-календарь (Фаза 12) — каждому
        # студенту своя приватная ссылка, не одна общая на группу. Генерится
        # лениво при первом /calendar (см. get_or_create_calendar_token), не
        # при регистрации — чтобы не плодить токены тем, кто им не пользуется.
        try:
            await db.execute("ALTER TABLE users ADD COLUMN calendar_token TEXT")
        except Exception:
            pass  # колонка уже есть
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_calendar_token ON users(calendar_token)"
            )
        except Exception:
            pass

        # Статус "выполнено" раньше был общим на всех (колонка deadlines.done),
        # теперь — персональный для каждого пользователя (свой чек-марк не влияет
        # на остальных, см. запрос владельца). Колонку deadlines.done не трогаем
        # (легаси, нигде больше не читается), а факты "кто отметил" храним тут.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadline_done (
                deadline_id INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                done_at     TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (deadline_id, user_id)
            )
        """)
        if deadline_done_is_new:
            # Единоразовый перенос: то, что было отмечено выполненным при старой
            # (общей) схеме, засчитываем старосте — чтобы история не терялась
            # молча при обновлении бота.
            await db.execute(
                "INSERT OR IGNORE INTO deadline_done (deadline_id, user_id) "
                "SELECT id, ? FROM deadlines WHERE done = 1",
                (STAROSTA_ID,)
            )
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
        # Тип файла внутри предмета (лекции/практики/КР/…, см. file_categories).
        # NULL у старых файлов — тип определяется по названию на лету.
        try:
            await db.execute("ALTER TABLE files ADD COLUMN category TEXT")
        except Exception:
            pass  # колонка уже есть
        # Откуда файл пришёл автоматически ("sdo:<cmid>:<имя>" — выгрузка из
        # СДО, см. sdo_files.py): повторная выгрузка не плодит дубли.
        try:
            await db.execute("ALTER TABLE files ADD COLUMN source TEXT")
        except Exception:
            pass  # колонка уже есть
        # Закреплённые в поиске WebApp группы/преподаватели/аудитории —
        # в базе, а не в браузере: видны с телефона и с компьютера.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pinned_targets (
                user_id     INTEGER NOT NULL,
                target_type INTEGER NOT NULL,
                target_id   INTEGER NOT NULL,
                title       TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, target_type, target_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_text (
                file_id      INTEGER PRIMARY KEY,
                content      TEXT NOT NULL,
                char_count   INTEGER,
                extracted_at TEXT DEFAULT (datetime('now'))
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

# ── Персональные ссылки на ICS-календарь ────────────────────────────────────
# Токен — случайная непредсказуемая строка (не user_id), чтобы ссылку нельзя
# было подобрать перебором и увидеть чужое расписание/ДЗ. Ссылка привязана к
# конкретному студенту, но сам .ics-эндпоинт не требует initData (календарные
# приложения не умеют слать кастомные заголовки при периодическом опросе
# webcal-подписки) — секретность держится на непредсказуемости токена, как у
# большинства calendar-share ссылок (Google/Apple делают так же).

async def get_or_create_calendar_token(user_id: int) -> str:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT calendar_token FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            return row[0]
        token = secrets.token_urlsafe(24)
        # INSERT ... ON CONFLICT — а не UPDATE — потому что get_or_create_calendar_token
        # может быть вызвана до /start (юзер ещё не встречался upsert_user), тогда
        # обычный UPDATE тихо обновит 0 строк и токен нигде не сохранится.
        await db.execute("""
            INSERT INTO users (user_id, calendar_token) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET calendar_token = excluded.calendar_token
        """, (user_id, token))
        await db.commit()
        return token

async def get_user_by_calendar_token(token: str) -> dict | None:
    if not token:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE calendar_token = ?", (token,))
        row = await cursor.fetchone()
        return dict(row) if row else None

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

async def edit_deadline(did: int, subject: str, description: str, due_date: str, due_time: str | None):
    """Ручная правка (WebApp): помечает manual_edit, чтобы автосинк СДО не
    вернул старое название/срок при следующем проходе."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE deadlines SET subject=?, description=?, due_date=?, due_time=?, manual_edit=1 WHERE id=?",
            (subject, description, due_date, due_time, did),
        )
        await db.commit()


async def update_deadline_due(did: int, subject: str, due_date: str, due_time: str | None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE deadlines SET subject=?, due_date=?, due_time=? WHERE id=?",
            (subject, due_date, due_time, did)
        )
        await db.commit()

async def get_deadline_by_external_id(external_id: str) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE external_id=?", (external_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

# Дедлайн считается "общим" (видят все), если его добавил/утвердил староста,
# либо это автосинк из СДО (created_by=0) — всё остальное видит только автор.
_DEADLINE_COLS = ("d.id, d.subject, d.description, d.due_date, d.due_time, d.created_by, d.created_at, "
                  "d.external_id, d.manual_edit")


def is_shared_deadline(d: dict) -> bool:
    return d.get("created_by") in (0, STAROSTA_ID)


async def get_active_deadlines(viewer_id: int, include_done: bool = False) -> list[dict]:
    """Дедлайны, видимые viewer_id: общие (старосты/СДО) + свои личные.
    "done" в каждой записи — персональный статус именно viewer_id, не общий."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = f"""
            SELECT {_DEADLINE_COLS},
                   EXISTS(
                       SELECT 1 FROM deadline_done dd
                       WHERE dd.deadline_id = d.id AND dd.user_id = ?
                   ) AS done
            FROM deadlines d
            WHERE (d.created_by = ? OR d.created_by IN (0, ?))
        """
        params = [viewer_id, viewer_id, STAROSTA_ID]
        if not include_done:
            query += """
                AND NOT EXISTS (
                    SELECT 1 FROM deadline_done dd2
                    WHERE dd2.deadline_id = d.id AND dd2.user_id = ?
                )
            """
            params.append(viewer_id)
        query += " ORDER BY d.due_date, d.due_time"
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]

async def get_deadlines_soon(days=3, viewer_id: int | None = None, shared_only: bool = False) -> list[dict]:
    """shared_only=True — для группового поста (модерация старостой): только
    общие дедлайны, не выполненные старостой. Иначе — персональная подборка
    для viewer_id (общие + его личные, не отмеченные им самим).

    "Сегодня" — по Москве, передаётся параметром, а не date('now'): в SQLite
    это дата по UTC, и в рассылке после полуночи МСК вчерашние дедлайны ещё
    считались бы "сегодняшними"."""
    today = today_msk().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if shared_only:
            query = f"""
                SELECT {_DEADLINE_COLS} FROM deadlines d
                WHERE d.created_by IN (0, ?)
                AND d.due_date BETWEEN ? AND date(?, ? || ' days')
                AND NOT EXISTS (SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)
                ORDER BY d.due_date, d.due_time
            """
            params = (STAROSTA_ID, today, today, str(days), STAROSTA_ID)
        else:
            if viewer_id is None:
                raise ValueError("viewer_id обязателен при shared_only=False")
            query = f"""
                SELECT {_DEADLINE_COLS} FROM deadlines d
                WHERE (d.created_by = ? OR d.created_by IN (0, ?))
                AND d.due_date BETWEEN ? AND date(?, ? || ' days')
                AND NOT EXISTS (SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)
                ORDER BY d.due_date, d.due_time
            """
            params = (viewer_id, STAROSTA_ID, today, today, str(days), viewer_id)
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]

async def get_deadline_stats(viewer_id: int) -> dict:
    """Статистика по дедлайнам, видимым viewer_id, с учётом его личного done.
    Просрочено/активно — относительно сегодняшней даты по Москве (см.
    get_deadlines_soon)."""
    today = today_msk().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        visible = "(d.created_by = ? OR d.created_by IN (0, ?))"
        vparams = (viewer_id, STAROSTA_ID)
        done_expr = "EXISTS(SELECT 1 FROM deadline_done dd WHERE dd.deadline_id=d.id AND dd.user_id=?)"

        total = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible}", vparams
        )).fetchone())[0]
        done = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND {done_expr}",
            vparams + (viewer_id,)
        )).fetchone())[0]
        overdue = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND d.due_date < ? AND NOT {done_expr}",
            vparams + (today, viewer_id)
        )).fetchone())[0]
        active = (await (await db.execute(
            f"SELECT COUNT(*) FROM deadlines d WHERE {visible} AND d.due_date >= ? AND NOT {done_expr}",
            vparams + (today, viewer_id)
        )).fetchone())[0]
        return {"total": total, "done": done, "overdue": overdue, "active": active}

async def mark_deadline_done(did: int, user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO deadline_done (deadline_id, user_id) VALUES (?, ?)",
            (did, user_id)
        )
        await db.commit()

async def unmark_deadline_done(did: int, user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM deadline_done WHERE deadline_id=? AND user_id=?", (did, user_id)
        )
        await db.commit()

async def set_deadline_done(did: int, user_id: int, done: bool):
    """Персональная отметка "выполнено" — у каждого своя, не влияет на других
    (ни в боте через /done, ни в WebApp через чекбокс)."""
    if done:
        await mark_deadline_done(did, user_id)
    else:
        await unmark_deadline_done(did, user_id)

async def is_deadline_done(did: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM deadline_done WHERE deadline_id=? AND user_id=?", (did, user_id)
        )
        return (await cursor.fetchone()) is not None

async def get_deadline(did: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM deadlines WHERE id=?", (did,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_deadline(did: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM deadline_done WHERE deadline_id=?", (did,))
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

async def add_file(title, subject, file_id, file_name, uploaded_by, category: str | None = None,
                   source: str | None = None) -> int:
    """category — тип внутри предмета (file_categories); None — определить
    по названию и имени файла. source — откуда файл выгружен автоматически."""
    from file_categories import LABELS, detect_category
    if category not in LABELS:
        category = detect_category(title or "", file_name or "")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO files (title, subject, file_id, file_name, uploaded_by, category, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, subject, file_id, file_name, uploaded_by, category, source))
        await db.commit()
        return cursor.lastrowid

async def get_file_sources() -> set[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT source FROM files WHERE source IS NOT NULL")
        return {r[0] for r in await cursor.fetchall()}


async def update_file_meta(fid: int, title: str, subject: str, category: str):
    """Правка файла (WebApp): название, предмет, тип."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE files SET title=?, subject=?, category=? WHERE id=?", (title, subject, category, fid))
        await db.commit()


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
        # file_text не связана FK/CASCADE (SQLite её не включает по умолчанию,
        # заводить ради одной таблицы отдельный PRAGMA не стали) — чистим руками,
        # иначе после удаления файла его текст молча остаётся висеть в контексте
        # предмета для решалки по лекциям (Фаза 9).
        await db.execute("DELETE FROM file_text WHERE file_id=?", (fid,))
        await db.commit()

async def save_file_text(file_id: int, text: str):
    """Сохраняет извлечённый из файла лекции текст (см. file_text.py). Вызывается
    один раз при загрузке/синхронизации файла — не при каждом решении задачи,
    это и есть "кэш" контекста лекций, о котором шла речь в обсуждении."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO file_text (file_id, content, char_count, extracted_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(file_id) DO UPDATE SET
                content=excluded.content, char_count=excluded.char_count, extracted_at=excluded.extracted_at
        """, (file_id, text, len(text)))
        await db.commit()

async def get_subject_lecture_context(subject: str) -> str:
    """Склеенный текст всех лекций предмета (в порядке добавления файлов) —
    контекст для решалки по лекциям (Фаза 9, Gemini). Каждая лекция отделена
    заголовком с названием файла, чтобы при желании модель могла сослаться
    на конкретный источник в ответе."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT f.title, ft.content
            FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            WHERE f.subject = ?
            ORDER BY f.id
        """, (subject,))
        rows = await cursor.fetchall()
    return "\n\n".join(f"=== {r['title']} ===\n{r['content']}" for r in rows)

async def get_all_lecture_context() -> str:
    """Тексты лекций всех предметов — для подбора под вопрос в чате без
    выбранного предмета (lecture_picker). Заголовок блока — «предмет: файл»."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT f.title, f.subject, ft.content
            FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            ORDER BY f.subject, f.id
        """)
        rows = await cursor.fetchall()
    return "\n\n".join(f"=== {r['subject'] or 'Без предмета'}: {r['title']} ===\n{r['content']}" for r in rows)


async def get_file_ids_with_text() -> set[int]:
    """id файлов, текст которых извлечён (участвуют в контексте ИИ) — для
    отметки 📖 в списке файлов WebApp."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT file_id FROM file_text WHERE char_count > 0")
        return {r[0] for r in await cursor.fetchall()}


async def get_subjects_with_lecture_text() -> list[str]:
    """Предметы, по которым есть хоть один файл с извлечённым текстом — решалка
    по лекциям предлагает выбор только из них (иначе можно было бы выбрать
    предмет без единой лекции и получить пустой контекст)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            SELECT DISTINCT f.subject FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            WHERE f.subject IS NOT NULL AND f.subject != ''
            ORDER BY f.subject
        """)
        return [r[0] for r in await cursor.fetchall()]

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
        # file_text — вместе с files: иначе извлечённый текст всех лекций
        # семестра навсегда остаётся в базе сиротами (см. delete_file).
        for table in ("deadlines", "deadline_done", "homework", "files", "file_text", "vote_answers", "votes"):
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


# ── Закреплённое в поиске расписания (WebApp) ────────────────────────────────

MAX_PINS = 20


async def get_pins(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT target_type, target_id, title FROM pinned_targets WHERE user_id=? ORDER BY created_at, rowid",
            (user_id,))
        return [{"type": t, "id": i, "title": title} for t, i, title in await cursor.fetchall()]


async def pin_target(user_id: int, target_type: int, target_id: int, title: str) -> bool:
    """False — уже MAX_PINS закреплённых (повторное закрепление — не ошибка)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*), SUM(target_type=? AND target_id=?) FROM pinned_targets WHERE user_id=?",
            (target_type, target_id, user_id))
        count, exists = await cursor.fetchone()
        if not exists and count >= MAX_PINS:
            return False
        await db.execute(
            "INSERT OR REPLACE INTO pinned_targets (user_id, target_type, target_id, title) VALUES (?, ?, ?, ?)",
            (user_id, target_type, target_id, title))
        await db.commit()
        return True


async def unpin_target(user_id: int, target_type: int, target_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM pinned_targets WHERE user_id=? AND target_type=? AND target_id=?",
                         (user_id, target_type, target_id))
        await db.commit()
