"""Резервная копия базы: консистентный снимок, сжатие, отправка старосте."""
import gzip
import sqlite3

import pytest
from aiogram import Bot

from tests.conftest import STAROSTA_ID
from tests.test_sdo_files import _BotSession


class _Session(_BotSession):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.payloads = []

    async def make_request(self, bot, method, timeout=None):
        if type(method).__name__ == "SendDocument":
            self.payloads.append((method.chat_id, method.document.data, method.disable_notification))
        return await super().make_request(bot, method, timeout)


@pytest.mark.asyncio
async def test_backup_is_a_working_copy_of_the_db(db, tmp_path):
    import backup
    await db.add_deadline("СР-2", "", "2099-10-01", None, 0)
    fid = await db.add_file("Лекция 1", "ОБА", "a", "l1.pdf", 1)
    await db.save_file_text(fid, "текст лекции")

    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=_Session())
    assert await backup.send_backup(bot, STAROSTA_ID)
    [(chat_id, data, silent)] = bot.session.payloads
    assert chat_id == STAROSTA_ID and silent is True
    assert bot.session.documents[0].startswith("uiboshki-") and bot.session.documents[0].endswith(".db.gz")

    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(data))
    con = sqlite3.connect(restored)
    assert con.execute("SELECT subject FROM deadlines").fetchall() == [("СР-2",)]
    assert con.execute("SELECT content FROM file_text").fetchall() == [("текст лекции",)]
    con.close()


def test_backup_job_is_scheduled():
    import scheduler
    jobs = {j.func.__name__: j for j in scheduler.start_scheduler(object()).get_jobs()}
    assert "send_backup" in jobs


@pytest.mark.asyncio
async def test_backup_encrypted_with_key(db, monkeypatch, tmp_path):
    """20.10: с BACKUP_KEY в Telegram уходит только шифротекст; /restore и
    tools/backup_decrypt.py открывают его тем же ключом, чужой ключ — нет."""
    import backup
    monkeypatch.setenv("BACKUP_KEY", "секрет-" + "x" * 40)
    await db.add_deadline("СР-3", "", "2099-10-01", None, 0)
    bot = Bot(token="123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA", session=_Session())
    assert await backup.send_backup(bot, STAROSTA_ID)
    [(_, data, _)] = bot.session.payloads
    assert bot.session.documents[0].endswith(".db.gz.enc")
    assert data.startswith(backup.MAGIC) and b"SQLite" not in data and b"\x1f\x8b" not in data[:8]

    tmp, info = backup.inspect_backup(data)          # /restore
    con = sqlite3.connect(tmp)
    assert con.execute("SELECT subject FROM deadlines").fetchall() == [("СР-3",)]
    con.close()

    import sys
    sys.path.insert(0, "tools")
    import backup_decrypt
    enc = tmp_path / "copy.db.gz.enc"
    enc.write_bytes(data)
    out = backup_decrypt.main(str(enc))
    assert out.endswith(".db.gz") and gzip.decompress(open(out, "rb").read()).startswith(b"SQLite format 3")

    monkeypatch.setenv("BACKUP_KEY", "другой-ключ")
    with pytest.raises(backup.RestoreError, match="ключ не тот"):
        backup.inspect_backup(data)
    monkeypatch.delenv("BACKUP_KEY")
    with pytest.raises(backup.RestoreError, match="не задан"):
        backup.inspect_backup(data)


def test_policy_says_backup_encrypted(monkeypatch):
    import privacy
    import s3_store
    monkeypatch.setattr(s3_store, "configured", lambda: False)
    monkeypatch.delenv("BACKUP_KEY", raising=False)
    assert "зашифр" not in privacy.backup_texts()["BACKUP_WHERE"]
    monkeypatch.setenv("BACKUP_KEY", "k" * 40)
    t = privacy.backup_texts()
    assert "зашифрованная ключом" in t["BACKUP_WHERE"] and "без доступа к содержимому" in t["BACKUP_TO"]


@pytest.mark.asyncio
async def test_status_warns_unencrypted_backup(db, monkeypatch):
    import health
    import s3_store
    monkeypatch.setattr(s3_store, "configured", lambda: False)
    monkeypatch.delenv("BACKUP_KEY", raising=False)
    assert "задай BACKUP_KEY" in await health.report()
    monkeypatch.setenv("BACKUP_KEY", "k" * 40)
    assert "BACKUP_KEY" not in await health.report()
