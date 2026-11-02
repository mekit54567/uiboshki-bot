"""/restore: копия из /backup проверяется (целостность, таблицы) и
переливается на место текущей базы; мусор и чужие базы не принимаются."""
import gzip
import os
import sqlite3

import pytest

from kapibara.ops import backup


@pytest.mark.asyncio
async def test_roundtrip_restore(db, tmp_path):
    await db.upsert_user(1, "alice", "Alice")
    data, name = await backup.make_backup()
    assert name.endswith(".db.gz")
    await db.upsert_user(2, "bob", "Bob")                      # после копии появился Боб

    tmp, info = backup.inspect_backup(data)
    assert info["users"] == 1 and os.path.exists(tmp)
    await backup.apply_backup(tmp)
    assert not os.path.exists(tmp)                             # временный файл убран
    assert await db.get_user(1) and await db.get_user(2) is None
    await db.upsert_user(3, "c", "C")                          # база рабочая после замены


@pytest.mark.asyncio
async def test_plain_db_file_accepted(db):
    await db.upsert_user(1, "a", "A")
    raw = gzip.decompress((await backup.make_backup())[0])
    tmp, info = backup.inspect_backup(raw)                     # не сжатая — тоже можно
    os.remove(tmp)
    assert info["users"] == 1


@pytest.mark.parametrize("raw, why", [
    (b"hello", "не база SQLite"),
    (b"\x1f\x8b" + b"broken", "архив повреждён"),
])
def test_garbage_rejected(raw, why):
    with pytest.raises(backup.RestoreError, match=why):
        backup.inspect_backup(raw)


def test_foreign_db_rejected(tmp_path):
    p = tmp_path / "other.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE users (id INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(backup.RestoreError, match="deadlines, files"):
        backup.inspect_backup(gzip.compress(p.read_bytes()))
    assert not [f for f in os.listdir(tmp_path) if f != "other.db"]
