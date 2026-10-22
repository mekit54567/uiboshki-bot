"""
Резервная копия базы: раз в сутки (и по /backup) бот присылает старосте
сжатую копию SQLite — все файлы, дедлайны, заметки, закреплённые. Раньше
всё жило в одном файле на сервере без копий: потеря тома — потеря всего.

Копия снимается штатным sqlite3 backup API — консистентно, даже если бот
в этот момент пишет в базу.

Восстановить — /restore у старосты: прислать боту файл копии (.db.gz или
.db), бот проверяет целостность и таблицы, показывает, что внутри, и после
подтверждения сначала присылает копию текущей базы, потом переливает копию
на её место тем же backup API (без перезапуска) и докатывает миграции.

Шифрование (20.10, Никита: копия уходит в Telegram за границу): с BACKUP_KEY
копия — AES-256-GCM, файл .db.gz.enc; Telegram хранит только нечитаемый файл.
Ключ — только у Никиты (переменная сервера и его менеджер паролей): без ключа
копию не открыть. Расшифровать без бота — tools/backup_decrypt.py.
"""

import asyncio
import gzip
import hashlib
import logging
import os
import sqlite3
import tempfile
import zlib
from datetime import datetime

import database
import health
from utils import TZ

logger = logging.getLogger(__name__)

MAX_SEND_BYTES = 48 * 1024 * 1024   # sendDocument бота — до 50 МБ
SEND_TRIES = 3                      # отправка копии: попыток,
SEND_PAUSE = 30                     # пауза перед повтором (сек, растёт),
SEND_TIMEOUT = 180                  # ожидание одной отправки (сек; 4–5 МБ через VPN)
MAGIC = b"UIBK1\n"                 # начало зашифрованной копии: версия формата, потом nonce и шифротекст


def backup_key() -> bytes | None:
    """Ключ копии из BACKUP_KEY (любая длинная строка, 32 байта — sha256) или None."""
    v = os.getenv("BACKUP_KEY", "").strip()
    return hashlib.sha256(b"uiboshki-backup:" + v.encode()).digest() if v else None


def encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def decrypt(raw: bytes, key: bytes | None = None) -> bytes:
    """Зашифрованная копия → .db.gz; незашифрованная — как есть."""
    if not raw.startswith(MAGIC):
        return raw
    key = key or backup_key()
    if not key:
        raise RestoreError("копия зашифрована, а BACKUP_KEY на сервере не задан")
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    body = raw[len(MAGIC):]
    try:
        return AESGCM(key).decrypt(body[:12], body[12:], MAGIC)
    except (InvalidTag, ValueError):
        raise RestoreError("копия не расшифровалась — ключ не тот (BACKUP_KEY) или файл повреждён")


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
    name = f"uiboshki-{datetime.now(TZ).strftime('%Y-%m-%d_%H-%M')}.db.gz"
    if key := backup_key():
        return await asyncio.to_thread(encrypt, data, key), name + ".enc"
    return data, name


async def send_backup(bot, chat_id: int, silent: bool = True) -> bool:
    from aiogram.types import BufferedInputFile
    try:
        data, name = await make_backup()
    except Exception as e:
        logger.error(f"backup: не снялась копия базы: {e}")
        await health.note("backup", False, "копия не снялась")
        await bot.send_message(chat_id, f"⚠️ Не получилось снять копию базы: {e}")
        return False
    size_mb = len(data) / 1024 / 1024
    import s3_store
    if s3_store.configured():
        # своё российское хранилище: база не уходит за границу, старосте — только отметка
        now = datetime.now(TZ)
        try:
            codes = [await s3_store.put(key, data) for key in s3_store.backup_keys(now)]
        except Exception as e:
            codes = [f"{type(e).__name__}"]
        if all(c == 200 for c in codes):
            await health.note("backup", True, f"{size_mb:.1f} МБ в хранилище")
            await bot.send_message(chat_id, f"💾 Копия базы ({size_mb:.1f} МБ) — в хранилище: "
                                            f"{', '.join(s3_store.backup_keys(now))}.", disable_notification=silent)
            return True
        await health.note("backup", False, f"хранилище: {codes}")
        await bot.send_message(chat_id, f"⚠️ Копия базы не легла в хранилище ({', '.join(map(str, codes))}). "
                                        "Проверь BACKUP_S3_* в переменных сервера.")
        return False
    if len(data) > MAX_SEND_BYTES:
        await health.note("backup", False, f"{size_mb:.0f} МБ — больше лимита Telegram")
        await bot.send_message(chat_id, f"⚠️ Копия базы — {size_mb:.0f} МБ, больше лимита Telegram (50 МБ).")
        return False
    if name.endswith(".enc"):
        caption = (f"💾 Копия базы ({size_mb:.1f} МБ), зашифрована ключом BACKUP_KEY. Храни — это все файлы, "
                   "дедлайны и заметки.\nВосстановить: /restore (или tools/backup_decrypt.py с ключом).")
    else:
        caption = (f"💾 Копия базы ({size_mb:.1f} МБ). Храни — это все файлы, дедлайны и заметки.\n"
                   "⚠️ Не зашифрована: задай BACKUP_KEY на сервере.\nВосстановить: /restore.")
    # 22.10: в 04:40 отправка упала и копия молча не пришла — файл идёт в
    # Telegram через VPN, бывает сбой сети. Пробуем ещё, ждём дольше обычного,
    # а не вышло — пишем старосте, почему.
    err = None
    for attempt in range(SEND_TRIES):
        if attempt:
            await asyncio.sleep(SEND_PAUSE * attempt)
        try:
            await bot.send_document(chat_id, BufferedInputFile(data, filename=name), disable_notification=silent,
                                    caption=caption, request_timeout=SEND_TIMEOUT)
        except Exception as e:
            err = e
            logger.warning(f"backup: отправка {attempt + 1}/{SEND_TRIES} не прошла: {type(e).__name__}: {e}")
            continue
        await health.note("backup", True, f"{size_mb:.1f} МБ")
        return True
    why = f"{type(err).__name__}: {str(err)[:200]}"
    await health.note("backup", False, f"не отправилась: {why}")
    try:
        await bot.send_message(chat_id, f"⚠️ Копия базы ({size_mb:.1f} МБ) не отправилась с {SEND_TRIES} попыток: "
                                        f"{why}\nПопробуй /backup руками.")
    except Exception:
        logger.exception("backup: не смог сообщить старосте")
    return False


# ── Восстановление (/restore) ───────────────────────────────────────────────

REQUIRED_TABLES = ("users", "deadlines", "files")
MAX_RESTORE_BYTES = 20 * 1024 * 1024    # скачать файл бот может до 20 МБ (Bot API)
MAX_UNPACKED_BYTES = 400 * 1024 * 1024  # распакованная копия — не больше (gzip-«бомба» не съест память)


class RestoreError(ValueError):
    """Копия не подходит — текст для старосты."""


def inspect_backup(raw: bytes) -> tuple[str, dict]:
    """Проверить присланную копию: распаковать, integrity_check, нужные
    таблицы. Возвращает (путь к временному .db, сводка). Временный файл
    удаляет apply_backup или вызывающий."""
    raw = decrypt(raw)
    if raw[:2] == b"\x1f\x8b":
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)      # gzip, но с пределом на размер
            raw = d.decompress(raw, MAX_UNPACKED_BYTES + 1)
            if len(raw) > MAX_UNPACKED_BYTES or d.unconsumed_tail:
                raise RestoreError(f"распакованная копия больше {MAX_UNPACKED_BYTES // 1024 // 1024} МБ")
        except zlib.error:
            raise RestoreError("архив повреждён — не распаковался")
    if not raw.startswith(b"SQLite format 3\x00"):
        raise RestoreError("это не база SQLite (нужен файл uiboshki-….db.gz из /backup)")
    fd, tmp = tempfile.mkstemp(suffix=".db")
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    try:
        con = sqlite3.connect(tmp)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RestoreError(f"база повреждена: {ok}")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if missing:
                raise RestoreError("в копии нет таблиц: " + ", ".join(missing))
            count = lambda t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tables else 0  # noqa: E731
            summary = {"users": count("users"), "deadlines": count("deadlines"), "files": count("files"),
                       "sdo": count("sdo_sessions"), "size_mb": round(len(raw) / 1024 / 1024, 1)}
        finally:
            con.close()
    except Exception:
        os.remove(tmp)
        raise
    return tmp, summary


def _copy_into(src_path: str, dst_path: str):
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)          # целиком заменяет содержимое dst, атомарно для читателей
    finally:
        dst.close()
        src.close()


async def keep_local_copy() -> str | None:
    """Копия текущей базы файлом рядом с ней на томе — страховка перед
    /restore, когда прислать копию в Telegram не вышло (больше 50 МБ или
    база повреждена — тогда копируем файл как есть). → путь или None."""
    import shutil
    path = database.DATABASE_PATH + ".before-restore"
    try:
        await asyncio.to_thread(_copy_into, database.DATABASE_PATH, path)
        return path
    except Exception as e:
        logger.warning(f"restore: копия через backup API не снялась ({e}) — копирую файл")
    try:
        await asyncio.to_thread(shutil.copyfile, database.DATABASE_PATH, path)
        return path
    except Exception as e:
        logger.error(f"restore: не сохранил текущую базу рядом: {e}")
        return None


def _drop_search_index():
    """Индекс поиска по смыслу — производные данные с id файлов; после
    восстановления id раздаются заново, и старые куски подклеились бы к чужим
    файлам. Удаляем — index_pending соберёт заново."""
    from semantic_index import index_path
    for suffix in ("", "-wal", "-shm"):
        p = index_path() + suffix
        if os.path.exists(p):
            os.remove(p)


async def apply_backup(tmp_path: str):
    """Перелить проверенную копию на место текущей базы и докатить миграции
    (копия могла быть снята старой версией бота)."""
    try:
        await asyncio.to_thread(_copy_into, tmp_path, database.DATABASE_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    try:
        _drop_search_index()
    except Exception as e:
        logger.error(f"restore: индекс поиска не удалился: {e}")
    from database.users import forget_user
    forget_user()               # «уже записан» относилось к прежней базе
    await database.init_db()
