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
