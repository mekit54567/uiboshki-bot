"""
Резервная копия базы: раз в сутки (и по /backup) бот присылает старосте
сжатую копию SQLite — все файлы, дедлайны, заметки, закреплённые. Раньше
всё жило в одном файле на Railway без копий: потеря тома — потеря всего.

Копия снимается штатным sqlite3 backup API — консистентно, даже если бот
в этот момент пишет в базу. Восстановить: распаковать .gz и положить файл
вместо базы на томе Railway (путь — DATABASE_PATH), затем перезапустить бота.
"""

import asyncio
import gzip
import logging
import os
import sqlite3
import tempfile
from datetime import datetime

import database
from utils import TZ

logger = logging.getLogger(__name__)

MAX_SEND_BYTES = 48 * 1024 * 1024   # sendDocument бота — до 50 МБ


def _snapshot(db_path: str) -> bytes:
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(tmp, "rb") as f:
            return gzip.compress(f.read(), compresslevel=6)
    finally:
        os.remove(tmp)


async def make_backup() -> tuple[bytes, str]:
    data = await asyncio.to_thread(_snapshot, database.DATABASE_PATH)
    return data, f"uiboshki-{datetime.now(TZ).strftime('%Y-%m-%d_%H-%M')}.db.gz"


async def send_backup(bot, chat_id: int, silent: bool = True) -> bool:
    from aiogram.types import BufferedInputFile
    try:
        data, name = await make_backup()
    except Exception as e:
        logger.error(f"backup: не снялась копия базы: {e}")
        await bot.send_message(chat_id, f"⚠️ Не получилось снять копию базы: {e}")
        return False
    size_mb = len(data) / 1024 / 1024
    if len(data) > MAX_SEND_BYTES:
        await bot.send_message(chat_id, f"⚠️ Копия базы — {size_mb:.0f} МБ, больше лимита Telegram (50 МБ).")
        return False
    await bot.send_document(
        chat_id, BufferedInputFile(data, filename=name), disable_notification=silent,
        caption=(f"💾 Копия базы ({size_mb:.1f} МБ). Храни — это все файлы, дедлайны и заметки.\n"
                 "Восстановить: распаковать .gz и положить вместо базы на томе Railway."),
    )
    return True
