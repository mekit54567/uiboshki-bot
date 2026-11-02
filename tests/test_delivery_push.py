"""Этап 2 (г): слой доставки и веб-пуши PWA — шифрование RFC 8291
(расшифровываем «как браузер»), подпись VAPID, подписки, доставка."""
import json
import struct

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient

import webpush


def _browser():
    """Ключи «браузера»: приватный, p256dh и auth в base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    return key, webpush.b64u(pub), webpush.b64u(auth)


def _decrypt(body: bytes, ua_key, p256dh: str, auth: str) -> bytes:
    """Расшифровка aes128gcm так, как это делает браузер (RFC 8291)."""
    salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
    as_pub = body[21:21 + idlen]
    assert rs == 4096
    shared = ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    hk = lambda salt_, ikm, info, n: HKDF(hashes.SHA256(), n, salt_, info).derive(ikm)  # noqa: E731
    ikm = hk(webpush.unb64u(auth), shared, b"WebPush: info\x00" + webpush.unb64u(p256dh) + as_pub, 32)
    cek = hk(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hk(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
    assert plain.endswith(b"\x02")                                          # последняя запись
    return plain[:-1]


def test_payload_decrypts_in_browser():
    key, p256dh, auth = _browser()
    body = webpush.encrypt('{"title": "Скоро пара"}'.encode(), p256dh, auth)
    assert json.loads(_decrypt(body, key, p256dh, auth)) == {"title": "Скоро пара"}


def test_vapid_jwt_is_valid_es256():
    header = webpush.vapid_header("https://fcm.googleapis.com/fcm/send/abc")
    t = header.split("t=")[1].split(",")[0]
    k = header.split("k=")[1]
    head, claims, sig = t.split(".")
    assert json.loads(webpush.unb64u(claims))["aud"] == "https://fcm.googleapis.com"
    raw = webpush.unb64u(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.unb64u(k))
    pub.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))    # не бросило — подпись верна
    assert k == webpush.public_key_b64() == webpush.public_key_b64()             # ключ стабилен (от BOT_TOKEN)


@pytest.mark.asyncio
async def test_deliver_sends_telegram_and_push(db, monkeypatch):
    import delivery
    from database.push import get_push_subs, save_push_sub
    _, p256dh, auth = _browser()
    await save_push_sub(1, "https://push.example/a", p256dh, auth)
    await save_push_sub(1, "https://push.example/gone", p256dh, auth)
    pushed = []

    async def send(sub, data, ttl=3600):
        pushed.append((sub["endpoint"], data))
        return 410 if sub["endpoint"].endswith("gone") else 201

    monkeypatch.setattr(webpush, "send", send)

    class Bot:
        sent = []

        async def send_message(self, uid, text, **kw):
            self.sent.append((uid, text))

    bot = Bot()
    await delivery.deliver(bot, 1, "⏰ <b>Через 10 минут пара</b>\n\nАнализ данных", kind="lesson", tab="today")
    assert bot.sent == [(1, "⏰ <b>Через 10 минут пара</b>\n\nАнализ данных")]
    titles = {d["title"] for _, d in pushed}
    assert titles == {"Скоро пара"} and pushed[0][1]["body"] == "⏰ Через 10 минут пара\nАнализ данных"
    assert pushed[0][1]["url"] == "/app?tab=today"
    assert [s["endpoint"] for s in await get_push_subs(1)] == ["https://push.example/a"]   # 410 — забыли


def test_subscribe_api(db, monkeypatch):
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    assert len(webpush.unb64u(c.get("/api/push/key", headers=h).json()["key"])) == 65
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/x", "keys": {"p256dh": "a", "auth": "b"}}
    assert c.post("/api/push/subscribe", json=sub, headers=h).json() == {"ok": True}
    assert c.post("/api/push/subscribe", json=dict(sub, endpoint="http://evil"), headers=h).status_code == 400
    # только адреса пуш-сервисов браузеров (ревью безопасности 09.10)
    for bad in ("https://push.example/x", "https://10.255.255.1/x", "https://fcm.googleapis.com.evil.ru/x"):
        assert c.post("/api/push/subscribe", json=dict(sub, endpoint=bad), headers=h).status_code == 400
    assert c.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]}, headers=h).json()["removed"] == 1


@pytest.mark.asyncio
async def test_push_only_skips_telegram_when_push_arrived(db, monkeypatch):
    """«Дублировать в Telegram» выключено (Никита 14.10: «чтоб приходили от PWA,
    а не TG»): пуш дошёл — в Telegram не шлём; пуш не дошёл — Telegram всё равно."""
    import delivery
    from database import set_notify, upsert_user
    from database.push import save_push_sub
    _, p256dh, auth = _browser()
    await upsert_user(1, "", "Аня")
    await set_notify(1, {"tg_copy": False})
    codes = [201]

    async def send(sub, data, ttl=3600):
        return codes[0]

    monkeypatch.setattr(webpush, "send", send)

    class Bot:
        sent = []

        async def send_message(self, uid, text, **kw):
            self.sent.append(uid)

    bot = Bot()
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert bot.sent == [1]                                  # пуш-подписки нет — Telegram
    await save_push_sub(1, "https://push.example/a", p256dh, auth)
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert bot.sent == [1]                                  # пуш дошёл — в Telegram не дублируем
    codes[0] = 500
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert bot.sent == [1, 1]                               # пуш не дошёл — Telegram
    await set_notify(1, {"tg_copy": True})
    codes[0] = 201
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert bot.sent == [1, 1, 1]                            # по умолчанию — и туда, и туда


@pytest.mark.asyncio
async def test_push_only_phone_app_no_pwa_copy(db, monkeypatch):
    """Никита 02.11: пуши в приложении на телефоне включены, «дублировать»
    выключено — ни Telegram, ни PWA не копируют. Включил — и туда, и туда.
    Об оплате («plus») — в PWA всегда."""
    import app_push
    import delivery
    from database import set_notify, upsert_user
    from database.push import save_push_sub
    _, p256dh, auth = _browser()
    await upsert_user(1, "", "Аня")
    await set_notify(1, {"tg_copy": False})
    await save_push_sub(1, "https://push.example/a", p256dh, auth)
    web = []

    async def send(sub, data, ttl=3600):
        web.append(data["tag"])
        return 201

    async def push_user(uid, data):
        return 1                                            # телефон принял

    monkeypatch.setattr(webpush, "send", send)
    monkeypatch.setattr(app_push, "push_user", push_user)

    class Bot:
        sent = []

        async def send_message(self, uid, text, **kw):
            self.sent.append(uid)

    bot = Bot()
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert web == [] and bot.sent == []                     # только телефон
    await delivery.deliver(bot, 1, "оплата", kind="plus")
    assert web == ["plus"]                                  # оплата — и в PWA
    await set_notify(1, {"tg_copy": True})
    await delivery.deliver(bot, 1, "пара", kind="lesson")
    assert web == ["plus", "lesson"] and bot.sent[-1:] == [1]
