"""Копия базы перед запуском (02.11): init_db меняет схему, и если новая
сборка сделала это неудачно, рядом остаётся база, какой она была до неё."""
import sqlite3

from kapibara.ops import backup


async def test_copy_before_start(db):
    from database._conn import connect
    async with connect() as c:
        await c.execute("INSERT INTO settings (key, value) VALUES ('x', 'до запуска')")
        await c.commit()
    path = await backup.keep_before_start()
    assert path == db.DATABASE_PATH + ".before-start"
    row = sqlite3.connect(path).execute("SELECT value FROM settings WHERE key = 'x'").fetchone()
    assert row == ("до запуска",)
    assert await backup.keep_before_start() == path          # одна копия, перезаписывается


async def test_no_db_yet(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "нет.db"))
    assert await backup.keep_before_start() is None


async def test_skips_when_disk_is_full(db, monkeypatch):
    import shutil
    from types import SimpleNamespace
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(total=10, used=10, free=0))
    assert await backup.keep_before_start() is None


def test_bot_copies_before_init_db():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "bot.py").read_text(encoding="utf-8")
    assert text.index("backup.keep_before_start()") < text.index("await init_db()")
