"""Расшифровать ночную копию базы без бота (20.10): сервер пропал, а копия
.db.gz.enc лежит в Telegram — нужен только ключ BACKUP_KEY из менеджера паролей.

    BACKUP_KEY=… python tools/backup_decrypt.py uiboshki-2026-10-21_04-40.db.gz.enc

Рядом появится .db.gz (распаковать — gunzip, получится база SQLite).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup  # noqa: E402


def main(path: str) -> str:
    key = backup.backup_key()
    if not key:
        raise SystemExit("Задай ключ: BACKUP_KEY=… python tools/backup_decrypt.py файл.enc")
    with open(path, "rb") as f:
        raw = f.read()
    if not raw.startswith(backup.MAGIC):
        raise SystemExit("Файл не зашифрован — это уже обычная копия .db.gz")
    try:
        data = backup.decrypt(raw, key)
    except backup.RestoreError as e:
        raise SystemExit(f"Не вышло: {e}")
    out = path[:-4] if path.endswith(".enc") else path + ".db.gz"
    with open(out, "wb") as f:
        f.write(data)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print("Готово:", main(sys.argv[1]))
