"""Вход через Apple в iPhone-приложении (App Store, правило 4.8: раз есть вход
через Telegram, VK и Яндекс, нужен и вход, который прячет почту).

Приложение получает у системы identityToken (JWT Apple, RS256) и
authorizationCode → POST /api/auth/apple. Сервер:
  1. проверяет подпись по ключам Apple (appleid.apple.com/auth/keys), aud —
     идентификатор приложения, iss, срок и nonce (тот же, что приложение
     отдало Apple, или его sha256);
  2. sub — человек у Apple: свой (привязан раньше) или новый аккаунт без
     Telegram, как у VK/Яндекса (database/identities.py);
  3. меняет код на refresh-токен и хранит его шифровкой (apple_tokens): при
     удалении аккаунта или отвязке Apple токен отзывается — Apple это требует.

Ключи — из аккаунта Apple Developer: APPLE_TEAM_ID, APPLE_KEY_ID,
APPLE_PRIVATE_KEY (содержимое .p8), APPLE_CLIENT_ID (по умолчанию
ru.uiboshki.app). Нет ключей — кнопки нет. Сеть — только через _post/_get
(тесты подменяют).
"""

import base64
import hashlib
import json
import logging
import os
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

logger = logging.getLogger(__name__)

ISSUER = "https://appleid.apple.com"
KEYS_URL = ISSUER + "/auth/keys"
TOKEN_URL = ISSUER + "/auth/token"
REVOKE_URL = ISSUER + "/auth/revoke"
NAME = "Apple"
_jwks: dict = {"at": 0.0, "keys": []}


def client_id() -> str:
    return os.getenv("APPLE_CLIENT_ID", "ru.uiboshki.app").strip()


def enabled() -> bool:
    return all(os.getenv(k, "").strip() for k in ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY"))


class AppleError(Exception):
    pass


def _b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


async def _get(url: str) -> dict:
    import net
    async with net.client(timeout=15) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _post(url: str, data: dict) -> tuple[int, dict]:
    import net
    async with net.client(timeout=15) as c:
        r = await c.post(url, data=data)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {}


async def _keys(refresh: bool = False) -> list[dict]:
    if refresh or not _jwks["keys"] or time.time() - _jwks["at"] > 3600:
        _jwks["keys"] = (await _get(KEYS_URL)).get("keys", [])
        _jwks["at"] = time.time()
    return _jwks["keys"]


async def verify(id_token: str, nonce: str = "") -> dict:
    """identityToken → его поля (sub, email…); не тот — AppleError."""
    try:
        head_b64, body_b64, sig_b64 = id_token.split(".")
        head, claims = json.loads(_b64(head_b64)), json.loads(_b64(body_b64))
    except ValueError as e:
        raise AppleError("не JWT") from e
    if head.get("alg") != "RS256":
        raise AppleError("не та подпись")
    key = next((k for k in await _keys() if k.get("kid") == head.get("kid")), None)
    if key is None:                                      # Apple сменил ключи — спросить заново
        key = next((k for k in await _keys(refresh=True) if k.get("kid") == head.get("kid")), None)
    if key is None:
        raise AppleError("нет такого ключа у Apple")
    pub = rsa.RSAPublicNumbers(int.from_bytes(_b64(key["e"]), "big"),
                               int.from_bytes(_b64(key["n"]), "big")).public_key()
    try:
        pub.verify(_b64(sig_b64), f"{head_b64}.{body_b64}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as e:
        raise AppleError("подпись не сошлась") from e
    if claims.get("iss") != ISSUER or claims.get("aud") != client_id():
        raise AppleError("токен не для этого приложения")
    if float(claims.get("exp", 0)) < time.time():
        raise AppleError("токен устарел")
    # приложение отдаёт Apple nonce как есть (или его sha256) и тот же — нам
    if claims.get("nonce") and claims["nonce"] not in (nonce, hashlib.sha256(nonce.encode()).hexdigest()):
        raise AppleError("nonce не сошёлся")
    if not claims.get("sub"):
        raise AppleError("нет sub")
    return claims


def client_secret() -> str:
    """JWT ES256 ключом .p8 — «пароль» приложения для /auth/token и /auth/revoke."""
    pem = os.getenv("APPLE_PRIVATE_KEY", "").replace("\\n", "\n").strip().encode()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise AppleError("APPLE_PRIVATE_KEY — не ключ .p8")
    now = int(time.time())
    head = {"alg": "ES256", "kid": os.getenv("APPLE_KEY_ID", "").strip()}
    body = {"iss": os.getenv("APPLE_TEAM_ID", "").strip(), "iat": now, "exp": now + 300,
            "aud": ISSUER, "sub": client_id()}
    signing = f"{_b64e(json.dumps(head).encode())}.{_b64e(json.dumps(body).encode())}"
    r, s = decode_dss_signature(key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing}.{_b64e(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


async def exchange(code: str) -> str:
    """authorizationCode → refresh-токен ('' — Apple не дал: вход всё равно идёт)."""
    if not code:
        return ""
    status, data = await _post(TOKEN_URL, {"client_id": client_id(), "client_secret": client_secret(),
                                           "code": code, "grant_type": "authorization_code"})
    if status != 200:
        logger.warning(f"Apple /auth/token: {status} {data.get('error', '')}")
    return data.get("refresh_token", "") if status == 200 else ""


async def save_token(user_id: int, refresh_token: str):
    import sdo_accounts
    from database._conn import connect
    if not refresh_token:
        return
    async with connect() as db:
        await db.execute("INSERT OR REPLACE INTO apple_tokens (user_id, token) VALUES (?, ?)",
                         (user_id, sdo_accounts.encrypt(refresh_token)))
        await db.commit()


async def revoke_for(user_id: int) -> bool:
    """Отозвать вход через Apple (удаление аккаунта, отвязка). → был ли токен."""
    import sdo_accounts
    from database._conn import connect
    async with connect() as db:
        row = await (await db.execute("SELECT token FROM apple_tokens WHERE user_id = ?", (user_id,))).fetchone()
        await db.execute("DELETE FROM apple_tokens WHERE user_id = ?", (user_id,))
        await db.commit()
    token = sdo_accounts.decrypt(row[0]) if row else None
    if not token or not enabled():
        return bool(token)
    try:
        status, _ = await _post(REVOKE_URL, {"client_id": client_id(), "client_secret": client_secret(),
                                             "token": token, "token_type_hint": "refresh_token"})
        if status != 200:
            logger.warning(f"Apple /auth/revoke: {status}")
    except Exception as e:  # noqa: BLE001 — удаление аккаунта не должно падать из-за Apple
        logger.warning(f"Apple /auth/revoke: {e}")
    return True
