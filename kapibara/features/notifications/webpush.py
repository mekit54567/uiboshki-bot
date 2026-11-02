"""
Веб-пуши PWA (этап 2 (г)) без внешних библиотек: шифрование RFC 8291
(aes128gcm) и подпись VAPID RFC 8292 на `cryptography` — pywebpush тянет
http-ece, который не везде собирается.

Ключ VAPID — из VAPID_PRIVATE_KEY (base64url, 32 байта), а если её нет —
производный от BOT_TOKEN: настраивать ничего не нужно, ключ стабилен между
деплоями (смена ключа — подписки придётся оформить заново).
"""

import base64
import hashlib
import json
import os
import struct
import time
from urllib.parse import urlsplit

import net
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
SUBJECT = os.getenv("VAPID_SUBJECT", "https://www.uiboshki.ru")


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def private_key() -> ec.EllipticCurvePrivateKey:
    raw = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if raw:
        num = int.from_bytes(unb64u(raw), "big")
    else:
        from config import BOT_TOKEN
        seed = hashlib.sha256(b"uiboshki-vapid:" + (BOT_TOKEN or "").encode()).digest()
        num = int.from_bytes(seed, "big") % (P256_ORDER - 1) + 1
    return ec.derive_private_key(num, ec.SECP256R1())


def public_key_b64() -> str:
    """Публичный ключ VAPID для PushManager.subscribe (applicationServerKey)."""
    pub = private_key().public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
    return b64u(pub)


def vapid_header(endpoint: str) -> str:
    u = urlsplit(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                              "sub": SUBJECT}, separators=(",", ":")).encode())
    signing = f"{head}.{claims}".encode()
    r, s = decode_dss_signature(private_key().sign(signing, ec.ECDSA(hashes.SHA256())))
    jwt = f"{head}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={public_key_b64()}"


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: str, auth: str, salt: bytes | None = None,
            server_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """Тело пуша aes128gcm (RFC 8291): заголовок (соль, размер записи, ключ
    сервера) + одна запись шифра."""
    ua_pub = unb64u(p256dh)
    auth_secret = unb64u(auth)
    salt = salt or os.urandom(16)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = server_key.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    shared = server_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    cipher = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", 4096, len(as_pub)) + as_pub + cipher


async def send(sub: dict, data: dict, ttl: int = 3600) -> int:
    """Отправить пуш подписке {endpoint, p256dh, auth}. → HTTP-код сервиса
    пушей (404/410 — подписки больше нет, её надо забыть)."""
    body = encrypt(json.dumps(data, ensure_ascii=False).encode(), sub["p256dh"], sub["auth"])
    async with net.client(timeout=5) as client:     # рассылка ждёт пуш — висящий адрес не тормозит всех
        r = await client.post(sub["endpoint"], content=body, headers={
            "TTL": str(ttl), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
            "Authorization": vapid_header(sub["endpoint"]), "Urgency": "normal"})
    return r.status_code
