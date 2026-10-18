"""Схема базы: таблицы, индексы, миграции (init_db)."""

import logging

from config import STAROSTA_ID
from database._conn import connect


async def init_db():
    async with connect() as db:
        # WAL снижает риск "database is locked" при параллельных cron-джобах
        # (scheduler.py гоняет несколько задач) вместе с обычными хендлерами.
        mode = (await (await db.execute("PRAGMA journal_mode=WAL;")).fetchone())[0]
        if mode != "wal":       # диск не дал WAL (сетевой?) — чтения ждут каждую запись; видно и в /status
            logging.getLogger(__name__).warning(f"база не в WAL, а в {mode} — возможны «database is locked»")
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
        # Личный дедлайн старосты (из WebApp): created_by старосты иначе = общий.
        try:
            await db.execute("ALTER TABLE deadlines ADD COLUMN personal INTEGER DEFAULT 0")
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
        # Группа человека (этап 1: любая группа института) — id на зеркале
        # расписания МИРЭА. Колонка новая — всех, кто уже есть, записываем в
        # свою группу (до этого бот был только для неё); новые выбирают сами.
        try:
            await db.execute("ALTER TABLE users ADD COLUMN group_id INTEGER")
            from config import HOME_GROUP_ID
            if HOME_GROUP_ID:
                await db.execute("UPDATE users SET group_id = ?", (HOME_GROUP_ID,))
        except Exception:
            pass  # колонка уже есть
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                own        INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Общие данные — по группам (этап 1 (б)): NULL — своя группа (всё,
        # что было до этапа 1). Старосты чужих групп — group_admins.
        for table in ("deadlines", "files", "lesson_notes"):
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN group_id INTEGER")
            except Exception:
                pass  # колонка уже есть (или таблица создаётся ниже — тогда добавит второй заход)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                group_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                added_by   INTEGER,
                added_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (group_id, user_id)
            )
        """)
        # Файл, общий для нескольких групп (один курс СДО у потока, этап 1 (в))
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_groups (
                file_id  INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                PRIMARY KEY (file_id, group_id)
            )
        """)
        # Вход в приложение без Telegram (этап 2): коды входа через бота и сессии
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_logins (
                code       TEXT PRIMARY KEY,
                device     TEXT,
                status     TEXT NOT NULL DEFAULT 'wait',
                user_id    INTEGER,
                expires_at TEXT NOT NULL
            )
        """)
        # Проверочное число входа (как у Google): устройство показывает одно,
        # бот предлагает три — нажать то же (ревью безопасности 09.10)
        cols = {r[1] for r in await (await db.execute("PRAGMA table_info(auth_logins)")).fetchall()}
        if "pick" not in cols:
            await db.execute("ALTER TABLE auth_logins ADD COLUMN pick INTEGER")
        # Вход через VK ID / Яндекс ID (oauth.py): кто есть кто у провайдера;
        # oauth_states — начатые входы (state → код входа, PKCE, «привязать к»).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS identities (
                provider   TEXT NOT NULL,
                subject    TEXT NOT NULL,
                user_id    INTEGER NOT NULL,
                name       TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (provider, subject)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state      TEXT PRIMARY KEY,
                provider   TEXT NOT NULL,
                verifier   TEXT NOT NULL,
                code       TEXT NOT NULL,
                client     TEXT NOT NULL DEFAULT 'web',
                link_user  INTEGER,
                expires_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                device     TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_seen  TEXT,
                expires_at TEXT NOT NULL,
                revoked    INTEGER DEFAULT 0
            )
        """)
        # Веб-пуши PWA (этап 2 (г), delivery.py): устройство = endpoint
        await db.execute("""
            CREATE TABLE IF NOT EXISTS push_subs (
                endpoint   TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                p256dh     TEXT NOT NULL,
                auth       TEXT NOT NULL,
                device     TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Подписка (ИИ сверх базы): до какой даты; source — откуда (вручную
        # старостой, оплата — потом)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    INTEGER PRIMARY KEY,
                until      TEXT NOT NULL,
                source     TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
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
        try:        # via='sdo' — сдачу подтвердило СДО (sdo_done), а не галочка: в счёт опыта (xp.py)
            await db.execute("ALTER TABLE deadline_done ADD COLUMN via TEXT")
        except Exception:
            pass  # уже есть
        # Рейтинг (xp.py, 5.100.3): свой ник и «показывать меня в рейтинге»
        # (по умолчанию нет). reviewed — Никита видел ник (/nicks), locked —
        # свой ник ставить нельзя (после сброса).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rating_profiles (
                user_id   INTEGER PRIMARY KEY,
                nick      TEXT,
                show      INTEGER NOT NULL DEFAULT 0,
                nick_at   TEXT,
                reviewed  INTEGER NOT NULL DEFAULT 1,
                locked    INTEGER NOT NULL DEFAULT 0
            )
        """)
        # «Показывать меня всем» (5.100.5): виден и тем, кто открыл группу из рейтинга
        try:
            await db.execute("ALTER TABLE rating_profiles ADD COLUMN show_all INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # колонка уже есть
        # «Капибара №…» — ник для чужих групп, если свой не задан: случайный
        # номер, без связи с id и именем (ревью 152-ФЗ 18.10)
        try:
            await db.execute("ALTER TABLE rating_profiles ADD COLUMN alias INTEGER")
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
        # share — согласие делиться дедлайнами СДО с группой (этап 1 (в)): по
        # такому входу бот синхронизирует задания всей группы (group_sync.py)
        for col in ("next_check_at TEXT", "jitter_left INTEGER DEFAULT 3", "share INTEGER DEFAULT 0"):
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
        # Дедлайны СДО, которые староста удалил: синк их больше не возвращает
        # (как files_skipped у файлов).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadlines_skipped (
                external_id TEXT PRIMARY KEY,
                at          TEXT DEFAULT (datetime('now'))
            )
        """)
        # Своя правка общего дедлайна (владелец 08.10: «каждый может менять,
        # но только у себя»): поля — что видит этот человек вместо общих
        # (NULL — как у всех), hidden=1 — убрал у себя. Общий не меняется.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadline_mine (
                user_id     INTEGER NOT NULL,
                deadline_id INTEGER NOT NULL,
                subject     TEXT,
                description TEXT,
                due_date    TEXT,
                due_time    TEXT,
                hidden      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, deadline_id)
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
            logging.getLogger(__name__).warning(f"FTS5 недоступен, поиск по файлам работать не будет: {e}")

        # Отпечаток текста лекции (этап 1 (в)): та же лекция у другой группы —
        # готовый конспект без ИИ. Старым строкам — посчитать один раз.
        try:
            await db.execute("ALTER TABLE file_text ADD COLUMN text_hash TEXT")
        except Exception:
            pass  # уже есть
        rows = await (await db.execute("SELECT file_id, content FROM file_text WHERE text_hash IS NULL")).fetchall()
        if rows:
            from database.files import text_hash
            await db.executemany("UPDATE file_text SET text_hash=? WHERE file_id=?",
                                 [(text_hash(c), fid) for fid, c in rows])
        await db.execute("CREATE INDEX IF NOT EXISTS idx_file_text_hash ON file_text(text_hash)")
        # «у каких файлов есть текст» (/api/files) — по индексу, а не чтением
        # всех текстов лекций: char_count лежит после content, и без индекса
        # SQLite читал десятки МБ с медленного диска Amvera (17.10: 36 с)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_file_text_chars ON file_text(char_count)")
        for table in ("deadlines", "files", "lesson_notes"):
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN group_id INTEGER")
            except Exception:
                pass  # уже есть

        # 152-ФЗ (privacy.py): согласия по версиям текста и последний заход —
        # от него срок хранения (год без заходов — данные удаляются).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS consents (
                user_id  INTEGER,
                kind     TEXT,
                version  TEXT,
                via      TEXT,
                at       TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, kind, version)
            )
        """)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
        except Exception:
            pass  # уже есть
        await db.execute("UPDATE users SET last_seen = datetime('now') WHERE last_seen IS NULL")
        try:        # кто был до согласий — пользуется и без него (privacy.blocked)
            await db.execute("ALTER TABLE users ADD COLUMN legacy INTEGER")
            await db.execute("UPDATE users SET legacy = 1")
        except Exception:
            pass  # уже есть
        try:        # версия текста, о которой уже спросили (privacy.ask_once) — один раз
            await db.execute("ALTER TABLE users ADD COLUMN consent_asked TEXT")
        except Exception:
            pass  # уже есть
        # Сколько длится тест СДО (quiz_time.py): ограничение по времени со
        # страницы теста, одно на всех — по cmid. 0 — ограничения нет.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_limits (
                cmid     INTEGER PRIMARY KEY,
                minutes  INTEGER NOT NULL,
                seen_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        # Тесты СДО в уведомлениях (quiz_alerts.py, Никита 12.10): когда тест
        # открывается (из календаря СДО, по cmid — одно на всех; '' — открыт,
        # когда — не знаем) и что кому уже ушло (напоминание до закрытия,
        # «открыли тест») — по одному разу.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_opens (
                cmid     INTEGER PRIMARY KEY,
                open_at  TEXT NOT NULL,
                seen_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_alerts (
                user_id     INTEGER NOT NULL,
                deadline_id INTEGER NOT NULL,
                kind        TEXT NOT NULL,
                at          TEXT NOT NULL,
                sent_at     TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, deadline_id, kind, at)
            )
        """)
        # Подписка «Капибара+» (billing.py): оплаты — по налоговым правилам
        # хранятся и после «удалить мои данные», без человека (payer_id NULL);
        # бонусы (ранг ачивок, «пригласи друга») — по разу; кто кого пригласил
        # (referrals) стирается вместе с любым из двух, у пригласившего
        # остаётся только счёт в bonuses.
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN founder INTEGER DEFAULT 0")
        except Exception:
            pass  # колонка уже есть
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id         TEXT PRIMARY KEY,
                provider   TEXT NOT NULL,
                payer_id   INTEGER,
                plan       TEXT NOT NULL,
                amount     INTEGER NOT NULL,
                days       INTEGER NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                paid_at    TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bonuses (
                user_id  INTEGER NOT NULL,
                kind     TEXT NOT NULL,
                key      TEXT NOT NULL,
                days     INTEGER NOT NULL,
                at       TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, kind, key)
            )
        """)
        # Ручные выдачи Никиты (/grant, plus_grant.py): безлимит (until NULL —
        # навсегда), журнал всех продлений подписки (ручных, оплат, бонусов —
        # чтобы «/grant off» снял только ручные дни) и отметка «приветствие
        # «Капибары+» отправлено» (plus_welcome.py, один раз на человека).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS plus_unlimited (
                user_id    INTEGER PRIMARY KEY,
                until      TEXT,
                granted_by INTEGER,
                at         TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS plus_grants (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                by_id      INTEGER,
                kind       TEXT NOT NULL,
                source     TEXT,
                days       INTEGER,
                prev_until TEXT,
                until      TEXT,
                revoked    INTEGER DEFAULT 0,
                at         TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_plus_grants_user ON plus_grants(user_id)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS plus_welcome (
                user_id INTEGER PRIMARY KEY,
                at      TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ref_codes (
                user_id  INTEGER PRIMARY KEY,
                code     TEXT NOT NULL UNIQUE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                friend_id   INTEGER PRIMARY KEY,
                inviter_id  INTEGER NOT NULL,
                at          TEXT DEFAULT (datetime('now')),
                rewarded_at TEXT
            )
        """)
        await db.commit()
