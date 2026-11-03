"""Куда уходит резервная копия базы (своё S3 в России или Telegram): только
настройки, без клиента. Нужны и политике (features/privacy), и бэкапу
(ops/backup, ops/s3_store) — поэтому в core: features не может импортировать ops."""
import os
from urllib.parse import urlsplit

DEFAULT_ENDPOINT = "https://storage.yandexcloud.net"

PROVIDERS = (("yandexcloud", "Yandex Cloud"), ("vkcloud", "VK Cloud"), ("mcs.mail", "VK Cloud"),
             ("selcdn", "Selectel"), ("selectel", "Selectel"), ("timeweb", "Timeweb Cloud"),
             ("cloud.ru", "Cloud.ru"))


def configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("BACKUP_S3_BUCKET", "BACKUP_S3_KEY_ID", "BACKUP_S3_SECRET"))


def provider() -> str:
    """Чьё хранилище — для политики обработки данных."""
    host = urlsplit(os.getenv("BACKUP_S3_ENDPOINT") or DEFAULT_ENDPOINT).netloc.lower()
    return next((name for key, name in PROVIDERS if key in host), host or "хранилище S3")
