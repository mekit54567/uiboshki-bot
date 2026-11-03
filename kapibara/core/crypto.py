"""Шифрование секретов в базе (Fernet): входы СДО и Пульса, ключи пушей
приложения, токены входа через Apple. 152-ФЗ — утечка одной базы (бэкап) не
раскрывает чужие входы.

Ключ — отдельный секрет на хостинге: SDO_CRYPT_KEY (ключ Fernet) или
SDO_CRYPT_PASSPHRASE (фраза, из неё ключ через scrypt); нет их — производный
от BOT_TOKEN, и /status об этом предупреждает. Шифруем основным ключом,
расшифровываем любым: сменили ключ — старые записи перешифровываются
(sdo.accounts.rotate_all, notifications.app_push).

Жило в sdo/accounts (03.11): им пользуются и Пульс, и пуши, и вход через
Apple, а sdo/accounts сам зовёт уведомления — выходил клубок импортов."""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from kapibara.core.config import BOT_TOKEN

logger = logging.getLogger(__name__)


def _bot_token_key() -> bytes:
    digest = hashlib.sha256(b"uiboshki-sdo-cookie:" + (BOT_TOKEN or "").encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _passphrase_key(phrase: str) -> bytes:
    """Ключ из секретной фразы владельца (SDO_CRYPT_PASSPHRASE на хостинге):
    scrypt — медленная функция, перебором фразу не подобрать. Соль своя для
    бота: одна и та же фраза в другом проекте даст другой ключ."""
    raw = hashlib.scrypt(phrase.encode(), salt=b"uiboshki-bot/sdo-cookies/v1", n=2 ** 14, r=8, p=1, dklen=32)
    return base64.urlsafe_b64encode(raw)


def _keys() -> list[bytes]:
    """Ключи по старшинству: первым шифруем, любым — расшифровываем. Так
    можно сменить ключ (задать фразу) без потери уже подключённых СДО —
    старые записи перешифровываются при проверке входа (keepalive_all)."""
    keys = []
    if os.getenv("SDO_CRYPT_KEY"):
        key = os.getenv("SDO_CRYPT_KEY").strip().encode()
        try:
            Fernet(key)
            keys.append(key)
        except ValueError:
            # не ключ Fernet (например, фраза вместо SDO_CRYPT_PASSPHRASE): без
            # проверки MultiFernet падал целиком и все входы считались протухшими
            logger.error("SDO_CRYPT_KEY — не ключ Fernet (нужны 32 байта в base64), пропускаю его")
    if os.getenv("SDO_CRYPT_PASSPHRASE"):
        keys.append(_passphrase_key(os.getenv("SDO_CRYPT_PASSPHRASE")))
    keys.append(_bot_token_key())
    return keys


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in _keys()])


def _key_ok(key: str) -> bool:
    try:
        Fernet(key.strip().encode())
        return True
    except ValueError:
        return False


def key_source() -> str:
    """Откуда ключ — для экрана «Безопасность» (без самого ключа)."""
    if os.getenv("SDO_CRYPT_KEY") and _key_ok(os.getenv("SDO_CRYPT_KEY")):
        return "key"
    if os.getenv("SDO_CRYPT_PASSPHRASE"):
        return "passphrase"
    return "bot_token"


def needs_rotation(token: str) -> bool:
    """Запись зашифрована не основным ключом — перешифровать."""
    try:
        Fernet(_keys()[0]).decrypt(token.encode())
        return False
    except (InvalidToken, ValueError):
        return True


def encrypt(cookie: str) -> str:
    return _fernet().encrypt(cookie.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
