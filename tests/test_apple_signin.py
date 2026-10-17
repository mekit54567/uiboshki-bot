"""Вход через Apple (apple_signin.py, POST /api/auth/apple): подпись по ключам
Apple, aud и nonce, новый аккаунт без Telegram, отзыв входа при удалении."""
import base64
import hashlib
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi.testclient import TestClient

import apple_signin

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _int(n: int) -> str:
    return _b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def id_token(**over) -> str:
    claims = {"iss": apple_signin.ISSUER, "aud": "ru.uiboshki.app", "sub": "001234.abc",
              "exp": time.time() + 600, "nonce": hashlib.sha256(b"raw-nonce").hexdigest(), **over}
    head = _b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    body = _b64(json.dumps(claims).encode())
    sig = RSA_KEY.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{_b64(sig)}"


@pytest.fixture
def apple(db, monkeypatch):
    import ratelimit
    pem = EC_KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode()
    monkeypatch.setenv("APPLE_TEAM_ID", "TEAM123")
    monkeypatch.setenv("APPLE_KEY_ID", "KEY123")
    monkeypatch.setenv("APPLE_PRIVATE_KEY", pem.replace("\n", "\\n"))
    pub = RSA_KEY.public_key().public_numbers()
    monkeypatch.setitem(apple_signin._jwks, "keys", [])

    async def fake_get(url):
        assert url == apple_signin.KEYS_URL
        return {"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "n": _int(pub.n), "e": _int(pub.e)}]}

    posts = []

    async def fake_post(url, data):
        posts.append((url, data))
        return 200, ({"refresh_token": "rt-1"} if url == apple_signin.TOKEN_URL else {})

    monkeypatch.setattr(apple_signin, "_get", fake_get)
    monkeypatch.setattr(apple_signin, "_post", fake_post)
    ratelimit.reset()
    return posts


@pytest.fixture
def client(apple):
    import webapp.server as server
    return TestClient(server.app, headers={"X-App": "ios"})


def test_flag_only_with_keys(client, monkeypatch):
    assert client.get("/api/auth/providers").json()["apple"] is True
    monkeypatch.delenv("APPLE_KEY_ID")
    assert client.get("/api/auth/providers").json()["apple"] is False
    assert client.post("/api/auth/apple", json={"id_token": id_token()}).status_code == 404


@pytest.mark.asyncio
async def test_sign_in_creates_account_and_keeps_token(client, apple):
    from database.identities import find_user, is_local
    body = {"id_token": id_token(), "code": "c-1", "nonce": "raw-nonce", "name": "Аня  Петрова"}
    r = client.post("/api/auth/apple", json=body)
    assert r.status_code == 200
    uid = await find_user("apple", "001234.abc")
    assert is_local(uid)
    me = client.get("/api/me", headers={"Authorization": "Bearer " + r.json()["token"]}).json()
    assert me["first_name"] == "Аня"
    url, data = apple[0]
    assert url == apple_signin.TOKEN_URL and data["code"] == "c-1" and data["client_id"] == "ru.uiboshki.app"
    # второй вход — тот же аккаунт
    client.post("/api/auth/apple", json=body)
    assert await find_user("apple", "001234.abc") == uid


@pytest.mark.parametrize("bad", [{"aud": "com.other.app"}, {"iss": "https://evil"}, {"exp": time.time() - 5}])
def test_foreign_or_old_token_is_rejected(client, bad):
    r = client.post("/api/auth/apple", json={"id_token": id_token(**bad), "nonce": "raw-nonce"})
    assert r.status_code == 401


def test_nonce_and_signature_checked(client):
    assert client.post("/api/auth/apple", json={"id_token": id_token(), "nonce": "другой"}).status_code == 401
    head, body, sig = id_token().split(".")
    forged = _b64(json.dumps({**json.loads(base64.urlsafe_b64decode(body + "==")), "sub": "чужой"}).encode())
    assert client.post("/api/auth/apple", json={"id_token": f"{head}.{forged}.{sig}",
                                               "nonce": "raw-nonce"}).status_code == 401


@pytest.mark.asyncio
async def test_delete_account_revokes_apple(client, apple):
    from database.identities import find_user
    r = client.post("/api/auth/apple", json={"id_token": id_token(), "code": "c-1", "nonce": "raw-nonce"})
    uid = await find_user("apple", "001234.abc")
    h = {"Authorization": "Bearer " + r.json()["token"]}
    assert client.post("/api/me/delete", json={"confirm": True}, headers=h).status_code == 200
    url, data = apple[-1]
    assert url == apple_signin.REVOKE_URL and data["token"] == "rt-1"
    assert await apple_signin.revoke_for(uid) is False                 # токена больше нет
    assert await find_user("apple", "001234.abc") is None              # привязки Apple тоже нет


def test_client_secret_is_es256_jwt(apple):
    head, body, sig = apple_signin.client_secret().split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    assert claims["iss"] == "TEAM123" and claims["sub"] == "ru.uiboshki.app" and claims["aud"] == apple_signin.ISSUER
    raw = base64.urlsafe_b64decode(sig + "==")
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    EC_KEY.public_key().verify(der, f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
