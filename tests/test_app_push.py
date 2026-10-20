"""Пуши своего приложения (app_push.py): шифрование содержимого AES-256-GCM
(сервис доставки видит только шифротекст), регистрация и отписка, отправка
FCM / RuStore / APNs с подменённым HTTP, мёртвые токены, выключено без
переменных, удаление данных."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi.testclient import TestClient

import app_push

# Тот же пример зашит в app/test/push_crypto_test.dart: приложение должно его расшифровать.
KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
DATA = {"title": "Скоро пара", "body": "Через 10 минут — Анализ данных", "tab": "today", "tag": "lesson"}
SAMPLE = ("AAECAwQFBgcICQoLPCCicrGJpzm3Y0cqYVOo01JWV4rQq+CsiLZlVa1LLJBjf8qFjfswSNN0yjwIV53oWXlRvXoGHwqHR5fImzJ3zhK8"
          "UloDQfbczOR61T833l8YWn2yxrPuuEAsFR390pWvv5k7xJ5jvHX6fUeQZFdVHt1FWImPoFbpIpF1sKuQD+QrU20Q6Omf1PvrKtA=")
APNS_TOKEN = "ab" * 32
ENV_VARS = ("FCM_SERVICE_ACCOUNT", "RUSTORE_PROJECT_ID", "RUSTORE_SERVICE_TOKEN", "APNS_KEY_ID",
            "APNS_PRIVATE_KEY", "APNS_TEAM_ID", "APPLE_TEAM_ID", "APNS_SANDBOX", "APNS_TOPIC")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ENV_VARS:
        monkeypatch.delenv(k, raising=False)
    app_push._fcm_token.update(value="", until=0.0, email="")
    app_push._apns_jwt.update(value="", until=0.0)


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _ec_key():
    return ec.generate_private_key(ec.SECP256R1())


def _all_on(monkeypatch):
    pem = _rsa_pem()
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT", json.dumps({
        "type": "service_account", "project_id": "kapibara-test", "client_email": "bot@kapibara.iam",
        "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setenv("RUSTORE_PROJECT_ID", "rs-project")
    monkeypatch.setenv("RUSTORE_SERVICE_TOKEN", "rs-secret")
    key = _ec_key()
    monkeypatch.setenv("APNS_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    monkeypatch.setenv("APNS_KEY_ID", "KEY123")
    monkeypatch.setenv("APNS_TEAM_ID", "TEAM123")
    return pem, key


class FakeHttp:
    """Подмена app_push._request: записывает запросы, отвечает по адресу."""

    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    async def __call__(self, url, *, json_body=None, form=None, headers=None, http2=False):
        self.calls.append({"url": url, "json": json_body, "form": form, "headers": headers or {}, "http2": http2})
        if "oauth2" in url:
            return 200, {"access_token": "ya29.test", "expires_in": 3600}
        for part, ans in self.answers.items():
            if part in url:
                return ans
        return 200, {}


# ── Шифрование ───────────────────────────────────────────────────────────────

def test_encrypt_roundtrip_and_fixed_sample():
    key = base64.b64decode(KEY_B64)
    assert app_push.encrypt(DATA, key, bytes(range(12))) == SAMPLE      # формат не поменялся (Dart-тест на нём)
    assert app_push.decrypt(SAMPLE, key) == DATA
    env = app_push.envelope(DATA, key)
    assert set(env) == {"v", "e"} and env["v"] == 1
    assert app_push.decrypt(env["e"], key) == DATA
    assert "Скоро" not in json.dumps(env, ensure_ascii=False)              # открытого текста нет
    assert app_push.envelope(DATA, key)["e"] != env["e"]                  # nonce каждый раз новый


def test_parse_key():
    assert app_push.parse_key(KEY_B64) == bytes(range(32))
    assert app_push.parse_key(base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")) == bytes(range(32))
    for bad in ("", "abc", base64.b64encode(b"x" * 16).decode(), "не base64!!", "A" * 100):
        assert app_push.parse_key(bad) is None


def test_off_without_env():
    assert app_push.platforms() == {"fcm": False, "rustore": False, "apns": False}


def test_on_with_env(monkeypatch):
    _all_on(monkeypatch)
    assert app_push.platforms() == {"fcm": True, "rustore": True, "apns": True}
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT", "{битый")
    assert app_push.platforms()["fcm"] is False


# ── Отправка ─────────────────────────────────────────────────────────────────

async def _register(uid, platform, token, key=KEY_B64):
    import sdo_accounts
    from database.app_push import save_app_push
    await save_app_push(uid, platform, token, sdo_accounts.encrypt(key))


@pytest.mark.asyncio
async def test_nothing_sent_when_off(db, monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr(app_push, "_request", fake)
    await _register(1, "fcm", "fcm-token-1234567890")
    assert await app_push.push_user(1, DATA) == 0
    assert fake.calls == []
    from database.app_push import get_app_pushes
    assert len(await get_app_pushes(1)) == 1                              # выключено — не забываем


@pytest.mark.asyncio
async def test_send_all_platforms_ciphertext_only(db, monkeypatch):
    pem, apns_key = _all_on(monkeypatch)
    fake = FakeHttp()
    monkeypatch.setattr(app_push, "_request", fake)
    await _register(1, "fcm", "fcm-token-1234567890")
    await _register(1, "rustore", "rustore-token-1234567890")
    await _register(1, "apns", APNS_TOKEN)
    assert await app_push.push_user(1, DATA) == 3
    key = base64.b64decode(KEY_B64)

    oauth = [c for c in fake.calls if "oauth2" in c["url"]]
    assert len(oauth) == 1 and oauth[0]["form"]["grant_type"].endswith("jwt-bearer")
    head, claims, sig = oauth[0]["form"]["assertion"].split(".")
    unb = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    assert json.loads(unb(claims))["scope"] == app_push.FCM_SCOPE
    pub = serialization.load_pem_private_key(pem.encode(), None).public_key()
    pub.verify(unb(sig), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())   # подпись верна

    fcm = next(c for c in fake.calls if "fcm.googleapis.com" in c["url"])
    assert fcm["url"].endswith("/projects/kapibara-test/messages:send")
    assert fcm["headers"]["Authorization"] == "Bearer ya29.test"
    msg = fcm["json"]["message"]
    assert set(msg) == {"token", "data", "android"} and "notification" not in msg   # data-only
    assert msg["data"]["v"] == "1" and app_push.decrypt(msg["data"]["e"], key) == DATA

    rs = next(c for c in fake.calls if "rustore" in c["url"])
    assert rs["url"] == "https://vkpns.rustore.ru/v1/projects/rs-project/messages:send"
    assert rs["headers"]["Authorization"] == "Bearer rs-secret"
    assert "notification" not in rs["json"]["message"]
    assert app_push.decrypt(rs["json"]["message"]["data"]["e"], key) == DATA

    ap = next(c for c in fake.calls if "push.apple.com" in c["url"])
    assert ap["url"] == f"https://api.push.apple.com/3/device/{APNS_TOKEN}" and ap["http2"]
    assert ap["json"]["aps"]["alert"] == {"title": "Капибара", "body": "Новое уведомление"}
    assert ap["json"]["aps"]["mutable-content"] == 1
    assert app_push.decrypt(ap["json"]["e"], key) == DATA
    assert ap["headers"]["apns-topic"] == "ru.uiboshki.app" and ap["headers"]["apns-push-type"] == "alert"
    jhead, jclaims, jsig = ap["headers"]["authorization"].split(" ")[1].split(".")
    assert json.loads(unb(jhead)) == {"alg": "ES256", "kid": "KEY123"}
    assert json.loads(unb(jclaims))["iss"] == "TEAM123"
    raw = unb(jsig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    apns_key.public_key().verify(der, f"{jhead}.{jclaims}".encode(), ec.ECDSA(hashes.SHA256()))

    for c in fake.calls:                                                  # открытого текста нигде нет
        assert "Скоро пара" not in json.dumps(c["json"] or {}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_dead_tokens_forgotten(db, monkeypatch):
    _all_on(monkeypatch)
    fake = FakeHttp({
        "fcm.googleapis.com": (404, {"error": {"status": "NOT_FOUND", "details": [
            {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]}}),
        "rustore": (404, {"error": {"code": 404, "status": "NOT_FOUND"}}),
        "push.apple.com": (410, {"reason": "Unregistered"}),
    })
    monkeypatch.setattr(app_push, "_request", fake)
    await _register(1, "fcm", "fcm-token-1234567890")
    await _register(1, "rustore", "rustore-token-1234567890")
    await _register(1, "apns", APNS_TOKEN)
    await _register(2, "fcm", "fcm-token-other-12345")
    assert await app_push.push_user(1, DATA) == 0
    from database.app_push import get_app_pushes
    assert await get_app_pushes(1) == []
    assert len(await get_app_pushes(2)) == 1


@pytest.mark.asyncio
async def test_temporary_error_keeps_token(db, monkeypatch):
    _all_on(monkeypatch)
    fake = FakeHttp({"fcm.googleapis.com": (503, {"error": {"status": "UNAVAILABLE"}}),
                     "push.apple.com": (400, {"reason": "PayloadTooLarge"})})
    monkeypatch.setattr(app_push, "_request", fake)
    await _register(1, "fcm", "fcm-token-1234567890")
    await _register(1, "apns", APNS_TOKEN)
    assert await app_push.push_user(1, DATA) == 0
    from database.app_push import get_app_pushes
    assert len(await get_app_pushes(1)) == 2


@pytest.mark.asyncio
async def test_unreadable_key_dropped(db, monkeypatch):
    _all_on(monkeypatch)
    fake = FakeHttp()
    monkeypatch.setattr(app_push, "_request", fake)
    from database.app_push import get_app_pushes, save_app_push
    await save_app_push(1, "fcm", "fcm-token-1234567890", "не-fernet")
    assert await app_push.push_user(1, DATA) == 0 and await get_app_pushes(1) == []
    assert not [c for c in fake.calls if "fcm.googleapis.com" in c["url"]]


@pytest.mark.asyncio
async def test_deliver_uses_app_push(db, monkeypatch):
    import delivery
    _all_on(monkeypatch)
    fake = FakeHttp()
    monkeypatch.setattr(app_push, "_request", fake)
    await _register(1, "fcm", "fcm-token-1234567890")

    class Bot:
        sent = []

        async def send_message(self, uid, text, **kw):
            self.sent.append((uid, text))

    await delivery.deliver(Bot(), 1, "⏰ <b>Через 10 минут пара</b>\n\nАнализ данных", kind="lesson", tab="today")
    fcm = next(c for c in fake.calls if "fcm.googleapis.com" in c["url"])
    got = app_push.decrypt(fcm["json"]["message"]["data"]["e"], base64.b64decode(KEY_B64))
    assert got == {"title": "Скоро пара", "body": "⏰ Через 10 минут пара\nАнализ данных", "tab": "today",
                   "tag": "lesson"}
    assert Bot.sent and Bot.sent[0][0] == 1


@pytest.mark.asyncio
async def test_rotate_keys(db, monkeypatch):
    import sdo_accounts
    from cryptography.fernet import Fernet
    await _register(1, "fcm", "fcm-token-1234567890")
    assert await app_push.rotate_keys() == 0
    monkeypatch.setenv("SDO_CRYPT_KEY", Fernet.generate_key().decode())
    assert await app_push.rotate_keys() == 1
    from database.app_push import get_app_pushes
    row = (await get_app_pushes(1))[0]
    assert not sdo_accounts.needs_rotation(row["key_enc"]) and sdo_accounts.decrypt(row["key_enc"]) == KEY_B64


# ── API ──────────────────────────────────────────────────────────────────────

def _client(monkeypatch):
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_api_subscribe_unsubscribe(db, monkeypatch):
    import sdo_accounts
    from database.app_push import get_app_pushes
    c, h = _client(monkeypatch)
    uid = 222
    assert c.get("/api/push/app", headers=h).json()["platforms"] == {"fcm": False, "rustore": False, "apns": False}
    r = c.post("/api/v1/push/app/subscribe", json={"platform": "fcm", "token": "fcm-token-1234567890",
                                                   "key": KEY_B64}, headers=h)
    assert r.json() == {"ok": True, "enabled": False}
    rows = await get_app_pushes(uid)
    assert len(rows) == 1 and KEY_B64 not in rows[0]["key_enc"]              # ключ — только зашифрованным
    assert sdo_accounts.decrypt(rows[0]["key_enc"]) == KEY_B64
    # повторная регистрация того же токена — новый ключ, не дубль
    other = base64.b64encode(b"k" * 32).decode()
    c.post("/api/push/app/subscribe", json={"platform": "fcm", "token": "fcm-token-1234567890", "key": other},
           headers=h)
    rows = await get_app_pushes(uid)
    assert len(rows) == 1 and sdo_accounts.decrypt(rows[0]["key_enc"]) == other

    bad = [{"platform": "sms", "token": "fcm-token-1234567890", "key": KEY_B64},
           {"platform": "fcm", "token": "short", "key": KEY_B64},
           {"platform": "fcm", "token": "fcm-token-1234567890", "key": "abc"},
           {"platform": "apns", "token": "../../evil" + "a" * 64, "key": KEY_B64},
           {"platform": "fcm", "token": "fcm token with spaces 123", "key": KEY_B64}]
    for b in bad:
        assert c.post("/api/push/app/subscribe", json=b, headers=h).status_code == 400, b

    r = c.post("/api/push/app/unsubscribe", json={"platform": "fcm", "token": "fcm-token-1234567890"}, headers=h)
    assert r.json() == {"ok": True, "removed": 1} and await get_app_pushes(uid) == []


@pytest.mark.asyncio
async def test_devices_capped(db):
    from database.app_push import MAX_DEVICES, get_app_pushes
    for i in range(MAX_DEVICES + 3):
        await _register(1, "fcm", f"fcm-token-{i:04d}-abcdefgh")
    rows = await get_app_pushes(1)
    assert len(rows) == MAX_DEVICES and rows[-1]["token"] == f"fcm-token-{MAX_DEVICES + 2:04d}-abcdefgh"


@pytest.mark.asyncio
async def test_logout_everywhere_and_erase_request(db, monkeypatch):
    from database.app_push import get_app_pushes
    c, h = _client(monkeypatch)
    uid = 222
    await _register(uid, "apns", APNS_TOKEN)
    assert c.post("/api/auth/logout?everywhere=true", headers=h).status_code == 200
    assert await get_app_pushes(uid) == []
    await _register(uid, "apns", APNS_TOKEN)
    from database.privacy import request_erase
    await request_erase(uid, "2099-01-01")
    assert await get_app_pushes(uid) == []                                # сразу, не через 7 дней
