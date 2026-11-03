"""Файлы курсов, тексты лекций для ИИ и поиск по файлам."""

import aiosqlite

from database._conn import connect


# ── Files ─────────────────────────────────────────────────────────────────────

async def add_file(title, subject, file_id, file_name, uploaded_by, category: str | None = None,
                   source: str | None = None, group_id: int | None = None) -> int:
    """category — тип внутри предмета (file_categories); None — определить
    по названию и имени файла. source — откуда файл выгружен автоматически.
    group_id не задан — группа того, кто загружает (current_group; синк и
    своя группа — NULL, как раньше)."""
    from database.groups import g_or_home, stored
    from kapibara.core.categories import LABELS, detect_category
    if category not in LABELS:
        category = detect_category(title or "", file_name or "")
    async with connect() as db:
        cursor = await db.execute("""
            INSERT INTO files (title, subject, file_id, file_name, uploaded_by, category, source, group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, subject, file_id, file_name, uploaded_by, category, source, stored(g_or_home(group_id))))
        await db.commit()
        return cursor.lastrowid


async def get_file_sources() -> set[str]:
    """Что уже выгружено из СДО — и что удалили вручную (не выгружать снова)."""
    async with connect() as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files_skipped (source TEXT PRIMARY KEY)")
        cursor = await db.execute("SELECT source FROM files WHERE source IS NOT NULL "
                                  "UNION SELECT source FROM files_skipped")
        return {r[0] for r in await cursor.fetchall()}


async def get_file_by_id(fid: int) -> dict | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM files WHERE id=?", (fid,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_sdo_file_subjects() -> dict[str, tuple[int, str]]:
    """source → (id, предмет) у файлов из СДО: чтобы переложить их, если
    курс раньше сопоставился не с тем предметом."""
    async with connect() as db:
        cursor = await db.execute("SELECT source, id, subject FROM files WHERE source IS NOT NULL")
        return {r[0]: (r[1], r[2] or "") for r in await cursor.fetchall()}


async def set_files_subject(moves: list[tuple[int, str]]):
    """[(id файла, новый предмет)]."""
    async with connect() as db:
        await db.executemany("UPDATE files SET subject=? WHERE id=?", [(s, i) for i, s in moves])
        await db.commit()


async def update_file_meta(fid: int, title: str, subject: str, category: str):
    """Правка файла (WebApp): название, предмет, тип."""
    async with connect() as db:
        await db.execute("UPDATE files SET title=?, subject=?, category=? WHERE id=?", (title, subject, category, fid))
        await db.commit()


async def rename_files(changes: dict[int, str]) -> int:
    """Новые названия (file_names.tidy_titles); старое — в orig_title,
    если его там ещё нет (повторный /tidyfiles не теряет самое первое)."""
    async with connect() as db:
        await db.executemany("UPDATE files SET orig_title = COALESCE(orig_title, title), title = ? WHERE id = ?",
                             [(t, i) for i, t in changes.items()])
        await db.commit()
    return len(changes)


async def undo_file_renames() -> int:
    async with connect() as db:
        cur = await db.execute("UPDATE files SET title = orig_title, orig_title = NULL WHERE orig_title IS NOT NULL")
        await db.commit()
        return cur.rowcount


def _fscope(group_id: int | None) -> tuple[str, tuple]:
    """Файлы группы (свои и общие с ней — file_groups); None — своя группа бота."""
    from database.groups import file_scope_sql, g_or_home
    g = g_or_home(group_id)
    return file_scope_sql("f"), (g, g)


async def file_visible(fid: int, group_id: int) -> bool:
    """Файл виден группе (свой или общий с ней) — для обработчиков «по номеру»:
    скачать, страница, конспект (ревью безопасности 09.10)."""
    sql, params = _fscope(group_id)
    async with connect() as db:
        row = await (await db.execute(f"SELECT 1 FROM files f WHERE f.id = ? AND {sql}", (fid, *params))).fetchone()
    return row is not None


async def get_files(subject: str = None, group_id: int | None = None) -> list[dict]:
    where, params = _fscope(group_id)
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if subject:
            cursor = await db.execute(f"SELECT * FROM files f WHERE subject=? AND {where} ORDER BY created_at DESC",
                                      (subject, *params))
        else:
            cursor = await db.execute(f"SELECT * FROM files f WHERE {where} ORDER BY created_at DESC", params)
        return [dict(r) for r in await cursor.fetchall()]


async def delete_file(fid: int):
    await delete_files([fid])


async def delete_files(fids: list[int]) -> int:
    """Удаляет файлы вместе с их текстом для ИИ. Удалённое из СДО
    запоминается (files_skipped), чтобы следующий /sdofiles не выгрузил
    его обратно."""
    if not fids:
        return 0
    marks = ",".join("?" * len(fids))
    async with connect() as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files_skipped (source TEXT PRIMARY KEY)")
        await db.execute(f"INSERT OR IGNORE INTO files_skipped (source) "
                         f"SELECT source FROM files WHERE id IN ({marks}) AND source IS NOT NULL", fids)
        cursor = await db.execute(f"DELETE FROM files WHERE id IN ({marks})", fids)
        deleted = cursor.rowcount
        await db.execute(f"DELETE FROM file_text WHERE file_id IN ({marks})", fids)
        await db.execute(f"DELETE FROM file_summaries WHERE file_id IN ({marks})", fids)
        await db.commit()
        return deleted


async def get_file_text(file_id: int) -> str:
    """Текст одной лекции (для конспекта); пусто — текста нет."""
    async with connect() as db:
        row = await (await db.execute("SELECT content FROM file_text WHERE file_id=?", (file_id,))).fetchone()
        return row[0] if row else ""


async def get_text_heads(file_ids, chars: int = 2500) -> dict[int, str]:
    """Начало текста файлов (титульный слайд, первая страница) — тема лекции
    для /tidyfiles (file_names.text_titles)."""
    want = set(file_ids)
    async with connect() as db:
        rows = await (await db.execute("SELECT file_id, substr(content, 1, ?) FROM file_text WHERE char_count > 0",
                                       (chars,))).fetchall()
    return {fid: text for fid, text in rows if fid in want}


def text_hash(text: str) -> str:
    """Отпечаток текста лекции: та же лекция в другом курсе СДО (другая
    группа потока, другое имя файла) — тот же отпечаток (этап 1 (в))."""
    import hashlib
    import re
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:32] if norm else ""


async def get_file_summary(file_id: int) -> dict | None:
    """Готовый конспект лекции (общий для всех) или None. Своего нет, но
    есть у той же лекции в другом файле (отпечаток текста) — его: ИИ второй
    раз не зовём."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM file_summaries WHERE file_id=?", (file_id,))).fetchone()
        if row:
            return dict(row)
        row = await (await db.execute(
            "SELECT s.* FROM file_text me JOIN file_text other ON other.text_hash = me.text_hash "
            "AND other.file_id != me.file_id JOIN file_summaries s ON s.file_id = other.file_id "
            "WHERE me.file_id = ? AND me.text_hash IS NOT NULL AND me.text_hash != '' LIMIT 1",
            (file_id,))).fetchone()
        return dict(row) if row else None


async def save_file_summary(file_id: int, content: str, created_by: int):
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO file_summaries (file_id, content, created_by) VALUES (?, ?, ?)",
                         (file_id, content, created_by))
        await db.commit()


async def get_file_ids_with_summary() -> set[int]:
    """Файлы с конспектом — своим или той же лекции в другом файле."""
    async with connect() as db:
        own = {r[0] for r in await (await db.execute("SELECT file_id FROM file_summaries")).fetchall()}
        same = {r[0] for r in await (await db.execute(
            "SELECT me.file_id FROM file_text me JOIN file_text other ON other.text_hash = me.text_hash "
            "AND other.file_id != me.file_id JOIN file_summaries s ON s.file_id = other.file_id "
            "WHERE me.text_hash IS NOT NULL AND me.text_hash != ''")).fetchall()}
        return own | same


async def save_file_text(file_id: int, text: str):
    """Сохраняет извлечённый из файла лекции текст (см. file_text.py). Вызывается
    один раз при загрузке/синхронизации файла — не при каждом решении задачи,
    это и есть "кэш" контекста лекций, о котором шла речь в обсуждении."""
    async with connect() as db:
        await db.execute("""
            INSERT INTO file_text (file_id, content, char_count, extracted_at, text_hash)
            VALUES (?, ?, ?, datetime('now'), ?)
            ON CONFLICT(file_id) DO UPDATE SET
                content=excluded.content, char_count=excluded.char_count, extracted_at=excluded.extracted_at,
                text_hash=excluded.text_hash
        """, (file_id, text, len(text), text_hash(text)))
        await db.commit()


async def get_subject_lecture_context(subject: str, group_id: int | None = None) -> str:
    """Склеенный текст всех лекций предмета (в порядке добавления файлов) —
    контекст для решалки по лекциям (Фаза 9, Gemini). Каждая лекция отделена
    заголовком с названием файла, чтобы при желании модель могла сослаться
    на конкретный источник в ответе."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        where, params = _fscope(group_id)
        cursor = await db.execute(f"""
            SELECT f.title, ft.content
            FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            WHERE f.subject = ? AND {where}
            ORDER BY f.id
        """, (subject, *params))
        rows = await cursor.fetchall()
    return "\n\n".join(f"=== {r['title']} ===\n{r['content']}" for r in rows)


async def get_all_lecture_context(group_id: int | None = None) -> str:
    """Тексты лекций всех предметов — для подбора под вопрос в чате без
    выбранного предмета (lecture_picker). Заголовок блока — «предмет: файл»."""
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        where, params = _fscope(group_id)
        cursor = await db.execute(f"""
            SELECT f.title, f.subject, ft.content
            FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            WHERE {where}
            ORDER BY f.subject, f.id
        """, params)
        rows = await cursor.fetchall()
    return "\n\n".join(f"=== {r['subject'] or 'Без предмета'}: {r['title']} ===\n{r['content']}" for r in rows)


async def get_file_ids_with_text() -> set[int]:
    """id файлов, текст которых извлечён (участвуют в контексте ИИ) — для
    отметки 📖 в списке файлов WebApp."""
    async with connect() as db:
        cursor = await db.execute("SELECT file_id FROM file_text WHERE char_count > 0")
        return {r[0] for r in await cursor.fetchall()}


async def get_subjects_with_lecture_text(group_id: int | None = None) -> list[str]:
    """Предметы, по которым есть хоть один файл с извлечённым текстом — решалка
    по лекциям предлагает выбор только из них (иначе можно было бы выбрать
    предмет без единой лекции и получить пустой контекст)."""
    async with connect() as db:
        where, params = _fscope(group_id)
        cursor = await db.execute(f"""
            SELECT DISTINCT f.subject FROM file_text ft
            JOIN files f ON f.id = ft.file_id
            WHERE f.subject IS NOT NULL AND f.subject != '' AND {where}
            ORDER BY f.subject
        """, params)
        return [r[0] for r in await cursor.fetchall()]


async def search_files(query: str, limit: int = 20, group_id: int | None = None) -> list[dict]:
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
        async with connect() as db:
            db.row_factory = aiosqlite.Row
            where, params = _fscope(group_id)
            cursor = await db.execute(f"""
                SELECT f.* FROM files_fts
                JOIN files f ON f.id = files_fts.rowid
                WHERE files_fts MATCH ? AND {where}
                ORDER BY bm25(files_fts)
                LIMIT ?
            """, (fts_query, *params, limit))
            return [dict(r) for r in await cursor.fetchall()]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"search_files failed: {e}")
        return []
