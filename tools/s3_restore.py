"""Перенос базы на новый сервер из резервной копии в S3 (19.10, переезд на
Timeweb Cloud): на старом сервере /backup кладёт копию в хранилище
(BACKUP_S3_*), здесь — забираем её и кладём базой, пока бот не запущен.

    docker compose run --rm bot python tools/s3_restore.py           # копия за сегодня
    docker compose run --rm bot python tools/s3_restore.py daily/uiboshki-1-mon.db.gz

База на месте уже с людьми — не трогаем без --force (вдруг это живой сервер).
Без S3 база переносится, как раньше: /backup файлом → /restore в новом боте.
"""

import asyncio
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup  # noqa: E402
import database  # noqa: E402
import s3_store  # noqa: E402
from utils import TZ  # noqa: E402


def people(path: str) -> int:
    """Сколько людей в базе по пути (нет файла или таблицы — 0)."""
    if not os.path.exists(path):
        return 0
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        con.close()


async def restore(key: str | None = None, force: bool = False) -> str:
    """→ строка-итог; ошибка — SystemExit с понятным текстом."""
    if not s3_store.configured():
        raise SystemExit("BACKUP_S3_* не заданы — переноси базу через /backup → /restore в боте.")
    path = database.DATABASE_PATH
    if people(path) and not force:
        raise SystemExit(f"В {path} уже есть люди — не трогаю. Точно заменить? Запусти с --force.")
    key = key or s3_store.backup_keys(datetime.now(TZ))[0]
    code, raw = await s3_store.get(key)
    if code != 200:
        raise SystemExit(f"Копия {key} не скачалась (HTTP {code}). Сделай /backup на старом сервере.")
    tmp, info = backup.inspect_backup(raw)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        backup._copy_into(tmp, path)
    finally:
        os.remove(tmp)
    backup._drop_search_index()
    return (f"База из {key} ({info['size_mb']} МБ): людей {info['users']}, дедлайнов {info['deadlines']}, "
            f"файлов {info['files']}, входов СДО {info['sdo']} → {path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(asyncio.run(restore(args[0] if args else None, force="--force" in sys.argv)))
