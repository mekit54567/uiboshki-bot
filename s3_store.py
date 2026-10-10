"""
Бэкап базы в российское S3-хранилище (Yandex Object Storage, VK Cloud,
Selectel — все понимают протокол S3) вместо файла старосте в Telegram:
Telegram — заграница, а база по 152-ФЗ должна оставаться в России
(PLAN.md, «Переезд в Россию»). Подпись запросов — AWS Signature V4 своими
руками, без boto3.

Переменные: `BACKUP_S3_BUCKET`, `BACKUP_S3_KEY_ID`, `BACKUP_S3_SECRET`,
`BACKUP_S3_ENDPOINT` (по умолчанию Yandex Object Storage),
`BACKUP_S3_REGION` (по умолчанию ru-central1). Не заданы — бэкап, как
раньше, файлом в Telegram.

Копии по кругу, без удаления по списку: `daily/<день недели>.db.gz` (семь
последних дней) и `monthly/<год-месяц>.db.gz` (первое число месяца).
"""

import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import net

DEFAULT_ENDPOINT = "https://storage.yandexcloud.net"


def configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("BACKUP_S3_BUCKET", "BACKUP_S3_KEY_ID", "BACKUP_S3_SECRET"))


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign(method: str, url: str, headers: dict, payload_hash: str, key_id: str, secret: str,
         region: str, now: datetime) -> str:
    """Заголовок Authorization по AWS Signature V4. headers — все, что
    уходят в подпись (host обязателен), имена в нижнем регистре."""
    u = urlsplit(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    names = sorted(headers)
    canonical_headers = "".join(f"{n}:{str(headers[n]).strip()}\n" for n in names)
    signed = ";".join(names)
    canonical_request = "\n".join([method, quote(u.path or "/", safe="/~"), u.query, canonical_headers, signed,
                                   payload_hash])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
    k = _hmac(("AWS4" + secret).encode("utf-8"), day)
    for part in (region, "s3", "aws4_request"):
        k = _hmac(k, part)
    signature = hmac.new(k, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, SignedHeaders={signed}, Signature={signature}"


async def put(key: str, data: bytes, content_type: str = "application/gzip") -> int:
    """Положить объект. → HTTP-код (200 — положили)."""
    endpoint = (os.getenv("BACKUP_S3_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    url = f"{endpoint}/{bucket}/{quote(key, safe='/~')}"
    now = datetime.now(timezone.utc)
    payload_hash = hashlib.sha256(data).hexdigest()
    headers = {"host": urlsplit(url).netloc, "x-amz-content-sha256": payload_hash,
               "x-amz-date": now.strftime("%Y%m%dT%H%M%SZ"), "content-type": content_type}
    headers["authorization"] = sign("PUT", url, headers, payload_hash, os.getenv("BACKUP_S3_KEY_ID", "").strip(),
                                    os.getenv("BACKUP_S3_SECRET", "").strip(),
                                    os.getenv("BACKUP_S3_REGION", "ru-central1").strip(), now)
    async with net.client(timeout=120) as c:
        resp = await c.put(url, content=data, headers={k: v for k, v in headers.items() if k != "host"})
    return resp.status_code


def backup_keys(now: datetime) -> list[str]:
    """Куда положить сегодняшнюю копию: день недели и, первого числа, месяц."""
    keys = [f"daily/uiboshki-{now.isoweekday()}-{now.strftime('%a').lower()}.db.gz"]
    if now.day == 1:
        keys.append(f"monthly/uiboshki-{now.strftime('%Y-%m')}.db.gz")
    return keys
