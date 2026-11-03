"""Бэкап (ADR 0004): битая копия при /restore не оставляет временный файл
(раньше чистил широкий except, теперь — finally)."""
import os
import sqlite3
import tempfile

import pytest

from kapibara.ops import backup


@pytest.mark.parametrize("raw", [b"not a database at all" * 100, None], ids=["junk", "no-tables"])
def test_bad_copy_leaves_no_temp(monkeypatch, tmp_path, raw):
    made = []
    real = tempfile.mkstemp

    def track(*a, **k):
        fd, path = real(*a, **k)
        made.append(path)
        return fd, path
    monkeypatch.setattr(tempfile, "mkstemp", track)
    real_db = raw is None
    if real_db:                         # настоящая база, но без нужных таблиц
        db = tmp_path / "x.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE t (x)")
        con.commit()
        con.close()
        raw = db.read_bytes()
    with pytest.raises((backup.RestoreError, sqlite3.Error)):
        backup.inspect_backup(raw)
    assert made or not real_db
    assert not any(os.path.exists(p) for p in made)
