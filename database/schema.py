"""Схема базы: таблицы, индексы, миграции (init_db)."""

from config import STAROSTA_ID
from database._conn import connect


async def init_db():
    async with connect() as db:
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
        # Конструктор уведомлений (notify_prefs.py): JSON, пусто — умолчания
        try:
            await db.execute("ALTER TABLE users ADD COLUMN notify TEXT")
        except Exception:
            pass  # колонка уже есть
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
        # Название до /tidyfiles («Лекция 3» вместо «ЛК3_бизнес») — для отката
        try:
            await db.execute("ALTER TABLE files ADD COLUMN orig_title TEXT")
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
            CREATE TABLE IF NOT EXISTS optional_subjects (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                attend  INTEGER NOT NULL,
                PRIMARY KEY (user_id, subject)
            )
        """)
        # Статистика (stats.py, /stats у старосты): только «кто, что, когда»
        # — без текстов вопросов, файлов и оценок. Старше 180 дней удаляется.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                user_id INTEGER NOT NULL,
                kind    TEXT NOT NULL,
                at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS events_at ON events(at)")
        # Вход в СДО у каждого свой (кука MoodleSession, зашифрована —
        # sdo_accounts.py): сдача работ из WebApp от своего имени.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sdo_sessions (
                user_id    INTEGER PRIMARY KEY,
                cookie_enc TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'ok',
                checked_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Проверка входов СДО вразнобой (sdo_accounts.keepalive_due): у каждого
        # своё время следующей проверки; первые проверки — через 50–59 мин
        # случайно, чтобы входы разошлись по часу, потом ровно 55.
        for col in ("next_check_at TEXT", "jitter_left INTEGER DEFAULT 3"):
            try:
                await db.execute(f"ALTER TABLE sdo_sessions ADD COLUMN {col}")
            except Exception:
                pass  # колонка уже есть
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
        # Настройки группы (зам старосты) и отметки /status (health.py). Раньше
        # создавалась лениво в init_hw_table — первая отметка на свежей базе
        # молча терялась.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Конспект лекции от ИИ (lecture_summary.py): один на файл и общий для
        # всех — делается, только когда кто-то нажмёт «Сделать конспект».
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_summaries (
                file_id    INTEGER PRIMARY KEY,
                content    TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
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
        # Свои напоминания о дедлайне (deadline_reminders.py): кто, о каком, когда
        # (время МСК «ГГГГ-ММ-ДД ЧЧ:ММ»); sent — уже пришло.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadline_reminders (
                user_id     INTEGER NOT NULL,
                deadline_id INTEGER NOT NULL,
                remind_at   TEXT NOT NULL,
                sent        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, deadline_id, remind_at)
            )
        """)
        # История баллов СДО (sdo_history.py): сумма по предмету раз в день —
        # для графика «как росли баллы» на экране предмета.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sdo_score_history (
                user_id   INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                day       TEXT NOT NULL,
                score     REAL NOT NULL,
                PRIMARY KEY (user_id, course_id, day)
            )
        """)
        # Баллы за посещаемость по дням (attendance.py): по приросту видно,
        # какие лекции засчитаны. Только баллы, без отметок по датам.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sdo_attendance_history (
                user_id   INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                day       TEXT NOT NULL,
                score     REAL NOT NULL,
                max       REAL NOT NULL,
                PRIMARY KEY (user_id, course_id, day)
            )
        """)
        # Свои отметки «был / по уважительной» для лекций до начала истории
        # посещаемости (attendance.py) — только для показа в боте, на СДО не
        # влияют.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attendance_marks (
                user_id   INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                day       TEXT NOT NULL,
                mark      TEXT NOT NULL,
                PRIMARY KEY (user_id, course_id, day)
            )
        """)
        # Автопилот (autopilot.py): «сделал» и сколько заняло — план учится,
        # сколько человеку нужно на похожие работы, и не планирует сделанное.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autopilot_log (
                user_id     INTEGER NOT NULL,
                key         TEXT NOT NULL,
                kind        TEXT NOT NULL,
                planned_min INTEGER,
                actual_min  INTEGER,
                at          TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, key)
            )
        """)
        # Последний удачный календарь группы (schedule_parser.fetch_schedule_raw):
        # если зеркало МИРЭА не отвечает, а бот только что перезапустился —
        # показываем его, а не ошибку.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_backup (
                id       INTEGER PRIMARY KEY CHECK (id = 1),
                data     BLOB NOT NULL,
                saved_at TEXT NOT NULL
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
