"""Первые минуты после выкладки на Amvera (17.10, /status: /api/files 36 с,
баллы СДО 35 с): список файлов не читает все тексты лекций, а индекс лекций
не начинает считать, пока все разом открывают приложение."""
import pytest


@pytest.mark.asyncio
async def test_files_with_text_use_index_not_texts(db):
    from database._conn import connect
    async with connect() as c:
        plan = await (await c.execute("EXPLAIN QUERY PLAN SELECT file_id FROM file_text WHERE char_count > 0")).fetchall()
    assert "COVERING INDEX idx_file_text_chars" in " ".join(str(r[-1]) for r in plan)


def test_first_index_pass_waits_after_start():
    import scheduler
    assert scheduler.INDEX_FIRST_DELAY >= 10
