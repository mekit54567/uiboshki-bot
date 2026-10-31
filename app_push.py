"""
Пуши своего приложения (Android и iPhone) с шифрованием содержимого (152-ФЗ):
сервисы доставки за границей (Google FCM, Apple APNs) и RuStore видят только
шифротекст — не заголовок, не текст, не имя.

Как устроено:
- приложение при включении уведомлений делает свой случайный ключ AES-256 и
  присылает его с токеном устройства (`POST /api/push/app/subscribe`); ключ в
  базе — зашифрованным, тем же секретом, что входы СДО (sdo_accounts.encrypt);
- сервер шифрует `{"title","body","tab","tag"}` AES-256-GCM этим ключом и шлёт
  только `{"v": 1, "e": base64(nonce(12) | шифротекст | тег(16))}`;
- Android (FCM и RuStore) — data-сообщение без notification, приложение само
  расшифровывает и показывает уведомление; iPhone — APNs с mutable-content и
  заглушкой «Капибара / Новое уведомление», расшифровывает Notification Service
  Extension (app/ios/KapibaraNotify), без него видна заглушка.

Каналы включаются переменными окружения; нет переменных — канал выключен:
- FCM: `FCM_SERVICE_ACCOUNT` — JSON сервисного аккаунта Firebase (текстом или
  в base64). OAuth-токен — JWT RS256 на `cryptography`, без SDK Google.
- RuStore: `RUSTORE_PROJECT_ID`, `RUSTORE_SERVICE_TOKEN`.
- APNs: `APNS_KEY_ID`, `APNS_PRIVATE_KEY` (.p8), `APNS_TEAM_ID` (или
  `APPLE_TEAM_ID`), `APNS_TOPIC` (по умолчанию ru.uiboshki.app),
  `APNS_SANDBOX=1` — для сборок из Xcode (development). Нужен HTTP/2 (h2).
Запросы — через net.client() (прокси — только для хостов из PROXY_HOSTS).
"""

import base64
import binascii
import json
import logging
import os
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

VERSION = 1
TTL = 3600
STUB_TITLE, STUB_BODY = "Капибара", "Новое уведомление"   # что видно на iPhone без расширения

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
RUSTORE_URL = "https://vkpns.rustore.ru/v1/projects/{project}/messages:send"
APNS_HOST = "https://api.push.apple.com"
APNS_SANDBOX_HOST = "https://api.sandbox.push.apple.com"

OK, GONE, ERROR = "ok", "gone", "error"


# ── Шифрование ───────────────────────────────────────────────────────────────

def parse_key(raw: str) -> bytes | None:
    """Ключ устройства из base64 (обычного или url-safe); не 32 байта — None."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 64:
        return None
    try:
        key = base64.b64decode(raw.replace("-", "+").replace("_", "/") + "=" * (-len(raw) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None
    return key if len(key) == 32 else None


def encrypt(data: dict, key: bytes, nonce: bytes | None = None) -> str:
    """`{"title","body","tab","tag"}` → base64(nonce | шифротекст | тег) — поле `e`."""
    nonce = nonce or os.urandom(12)
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, plain, None)).decode()


def decrypt(e: str, key: bytes) -> dict:
    """Обратно — для тестов и проверки формата (так же делает приложение)."""
    raw = base64.b64decode(e)
    return json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None))


def envelope(data: dict, key: bytes) -> dict:
    return {"v": VERSION, "e": encrypt(data, key)}


# ── Настройки каналов ────────────────────────────────────────────────────────

def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _fcm_account() -> dict | None:
    raw = _env("FCM_SERVICE_ACCOUNT")
    if not raw:
        return None
    try:
        acc = json.loads(raw if raw.lstrip().startswith("{") else base64.b64decode(raw))
    except (ValueError, binascii.Error):
        logger.error("FCM_SERVICE_ACCOUNT — не JSON сервисного аккаунта")
        return None
    if not all(acc.get(k) for k in ("project_id", "client_email", "private_key")):
        logger.error("FCM_SERVICE_ACCOUNT: нет project_id, client_email или private_key")
        return None
    return acc


def _apns_ok() -> bool:
    if not (_env("APNS_KEY_ID") and _env("APNS_PRIVATE_KEY") and (_env("APNS_TEAM_ID") or _env("APPLE_TEAM_ID"))):
        return False
    try:
        import h2  # noqa: F401 — APNs принимает только HTTP/2
    except ImportError:
        logger.error("APNs: нет пакета h2 (HTTP/2) — пуши iPhone выключены")
        return False
    return True


def platforms() -> dict[str, bool]:
    """Какие каналы включены — приложение показывает тумблер только с ними."""
    return {"fcm": _fcm_account() is not None,
            "rustore": bool(_env("RUSTORE_PROJECT_ID") and _env("RUSTORE_SERVICE_TOKEN")),
            "apns": _apns_ok()}


def enabled(platform: str) -> bool:
    return platforms().get(platform, False)


# ── HTTP (один шов для тестов) ───────────────────────────────────────────────

async def _request(url: str, *, json_body: dict | None = None, form: dict | None = None,
                   headers: dict | None = None, http2: bool = False) -> tuple[int, dict]:
    import net
    async with net.client(timeout=15, http2=http2) as c:
        r = await c.post(url, json=json_body, data=form, headers=headers or {})
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {}
        return r.status_code, body if isinstance(body, dict) else {}


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwt(head: dict, claims: dict, sign) -> str:
    signing = f"{_b64u(json.dumps(head, separators=(',', ':')).encode())}." \
              f"{_b64u(json.dumps(claims, separators=(',', ':')).encode())}"
    return f"{signing}.{_b64u(sign(signing.encode()))}"


# ── FCM HTTP v1 ──────────────────────────────────────────────────────────────

_fcm_token: dict = {"value": "", "until": 0.0, "email": ""}


def fcm_assertion(acc: dict) -> str:
    """JWT RS256 сервисного аккаунта — обменивается на OAuth-токен Google."""
    key = serialization.load_pem_private_key(acc["private_key"].replace("\\n", "\n").encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("private_key сервисного аккаунта — не RSA")
    now = int(time.time())
    claims = {"iss": acc["client_email"], "scope": FCM_SCOPE,
              "aud": acc.get("token_uri") or "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}
    head = {"alg": "RS256", "typ": "JWT", **({"kid": acc["private_key_id"]} if acc.get("private_key_id") else {})}
    return _jwt(head, claims, lambda b: key.sign(b, padding.PKCS1v15(), hashes.SHA256()))


async def _fcm_access(acc: dict) -> str:
    if _fcm_token["value"] and _fcm_token["email"] == acc["client_email"] and time.time() < _fcm_token["until"]:
        return _fcm_token["value"]
    code, body = await _request(acc.get("token_uri") or "https://oauth2.googleapis.com/token", form={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": fcm_assertion(acc)})
    if code != 200 or not body.get("access_token"):
        raise RuntimeError(f"OAuth Google: {code} {body.get('error', '')}")
    _fcm_token.update(value=body["access_token"], email=acc["client_email"],
                      until=time.time() + int(body.get("expires_in", 3600)) - 300)
    return _fcm_token["value"]


def _fcm_gone(code: int, body: dict) -> bool:
    err = body.get("error") or {}
    codes = {d.get("errorCode") for d in err.get("details") or [] if isinstance(d, dict)}
    if codes & {"UNREGISTERED", "SENDER_ID_MISMATCH"} or code == 404:
        return True
    return code == 400 and "registration token" in str(err.get("message", "")).lower()


async def send_fcm(token: str, env: dict) -> str:
    acc = _fcm_account()
    if acc is None:
        return ERROR
    msg = {"message": {"token": token, "data": {"v": str(env["v"]), "e": env["e"]},
                       "android": {"priority": "high", "ttl": f"{TTL}s"}}}
    url = FCM_URL.format(project=acc["project_id"])
    code, body = await _request(url, json_body=msg, headers={"Authorization": f"Bearer {await _fcm_access(acc)}"})
    if code == 401:                                    # токен Google протух раньше срока — ещё раз
        _fcm_token["value"] = ""
        code, body = await _request(url, json_body=msg,
                                    headers={"Authorization": f"Bearer {await _fcm_access(acc)}"})
    if code < 300:
        return OK
    if _fcm_gone(code, body):
        return GONE
    logger.info(f"FCM: {code} {(body.get('error') or {}).get('status', '')}")
    return ERROR


# ── RuStore Push ─────────────────────────────────────────────────────────────

async def send_rustore(token: str, env: dict) -> str:
    project, secret = _env("RUSTORE_PROJECT_ID"), _env("RUSTORE_SERVICE_TOKEN")
    if not (project and secret):
        return ERROR
    msg = {"message": {"token": token, "data": {"v": str(env["v"]), "e": env["e"]},
                       "android": {"ttl": f"{TTL}s"}}}
    code, body = await _request(RUSTORE_URL.format(project=project), json_body=msg,
                                headers={"Authorization": f"Bearer {secret}"})
    if code < 300:
        return OK
    status = str((body.get("error") or {}).get("status", "")).upper()
    if code == 404 or status in ("NOT_FOUND", "UNREGISTERED"):
        return GONE
    logger.info(f"RuStore: {code} {status}")
    return ERROR


# ── APNs ─────────────────────────────────────────────────────────────────────

_apns_jwt: dict = {"value": "", "until": 0.0}


def apns_jwt() -> str:
    """Токен провайдера APNs — JWT ES256 ключом .p8; Apple просит не чаще раза в 20 мин."""
    if _apns_jwt["value"] and time.time() < _apns_jwt["until"]:
        return _apns_jwt["value"]
    key = serialization.load_pem_private_key(_env("APNS_PRIVATE_KEY").replace("\\n", "\n").encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("APNS_PRIVATE_KEY — не ключ .p8")

    def sign(b: bytes) -> bytes:
        r, s = decode_dss_signature(key.sign(b, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    team = _env("APNS_TEAM_ID") or _env("APPLE_TEAM_ID")
    value = _jwt({"alg": "ES256", "kid": _env("APNS_KEY_ID")}, {"iss": team, "iat": int(time.time())}, sign)
    _apns_jwt.update(value=value, until=time.time() + 40 * 60)
    return value


def apns_payload(env: dict, tag: str = "") -> dict:
    aps = {"alert": {"title": STUB_TITLE, "body": STUB_BODY}, "mutable-content": 1, "sound": "default"}
    if tag:
        aps["thread-id"] = tag
    return {"aps": aps, "v": env["v"], "e": env["e"]}


async def send_apns(token: str, env: dict, tag: str = "") -> str:
    if not _apns_ok():
        return ERROR
    host = APNS_SANDBOX_HOST if _env("APNS_SANDBOX") in ("1", "true", "yes") else APNS_HOST
    headers = {"authorization": f"bearer {apns_jwt()}", "apns-push-type": "alert", "apns-priority": "10",
               "apns-topic": _env("APNS_TOPIC") or "ru.uiboshki.app",
               "apns-expiration": str(int(time.time()) + TTL)}
    if tag:
        headers["apns-collapse-id"] = tag[:64]
    code, body = await _request(f"{host}/3/device/{token}", json_body=apns_payload(env, tag),
                                headers=headers, http2=True)
    if code < 300:
        return OK
    reason = str(body.get("reason", ""))
    if reason == "ExpiredProviderToken":
        _apns_jwt["value"] = ""
    if code == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
        return GONE
    logger.info(f"APNs: {code} {reason}")
    return ERROR


# ── Отправка человеку ────────────────────────────────────────────────────────

async def send(row: dict, data: dict) -> str:
    """Одно устройство (строка app_push) → ok / gone / error."""
    import sdo_accounts
    key = parse_key(sdo_accounts.decrypt(row["key_enc"]) or "")
    if key is None:
        return GONE                                    # ключ не читается — пусть приложение подпишется заново
    env = envelope({k: data.get(k) or "" for k in ("title", "body", "tab", "tag")}, key)
    if row["platform"] == "fcm":
        return await send_fcm(row["token"], env)
    if row["platform"] == "rustore":
        return await send_rustore(row["token"], env)
    if row["platform"] == "apns":
        return await send_apns(row["token"], env, data.get("tag") or "")
    return GONE


async def push_report(user_id: int, data: dict) -> list[dict]:
    """Пуш на все телефоны человека, по устройству: platform, device, result
    (ok / gone / error / off — канал выключен на сервере). Мёртвый токен — забываем."""
    from database.app_push import delete_app_push, get_app_pushes
    on = platforms()
    out = []
    for row in await get_app_pushes(user_id):
        item = {"platform": row["platform"], "device": row.get("device") or ""}
        out.append(item)
        if not on.get(row["platform"]):
            item["result"] = "off"
            continue
        try:
            res = await send(row, data)
        except Exception as e:
            logger.info(f"пуш приложения {user_id} ({row['platform']}): {type(e).__name__}: {e}")
            res = ERROR
        if res == GONE:
            await delete_app_push(row["platform"], row["token"])
        item["result"] = res
    return out


async def push_user(user_id: int, data: dict) -> int:
    """Пуш на все телефоны человека. → сколько ушло."""
    return sum(1 for r in await push_report(user_id, data) if r["result"] == OK)


async def rotate_keys() -> int:
    """Задали новый SDO_CRYPT_KEY/фразу — перешифровать ключи устройств (как
    sdo_accounts.rotate_all). → сколько перешифровано."""
    import sdo_accounts
    from database.app_push import all_app_pushes, update_app_push_key
    n = 0
    for row in await all_app_pushes():
        enc = row["key_enc"]
        if not sdo_accounts.needs_rotation(enc):
            continue
        key = sdo_accounts.decrypt(enc)
        if key is not None and await update_app_push_key(row["id"], sdo_accounts.encrypt(key), only_if=enc):
            n += 1
    return n
