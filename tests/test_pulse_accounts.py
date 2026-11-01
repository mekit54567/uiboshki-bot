"""Вход в Пульс на сервере: хранение зашифрованным и поддержание, как у СДО."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import pulse_accounts
import pulse_attendance
import pulse_probe
from tests.test_pulse_probe import ME


def _answer(status=200, body=b"", headers=None):
    def handler(request):
        assert request.headers["cookie"] == "sid=abc"
        assert request.headers["pulse-app-type"] == "pulse-app"
        return httpx.Response(status, content=body, headers=headers or {"content-type": "application/grpc-web+proto"})
    return httpx.MockTransport(handler)


TRAILER_OK = b"\x80" + (len(b"grpc-status:0\r\n")).to_bytes(4, "big") + b"grpc-status:0\r\n"
TRAILER_16 = b"\x80" + (len(b"grpc-status:16\r\n")).to_bytes(4, "big") + b"grpc-status:16\r\n"


@pytest.mark.parametrize("status,body,ctype,want", [
    (200, pulse_probe.frame(ME) + TRAILER_OK, "application/grpc-web+proto", "ok"),
    (200, TRAILER_16, "application/grpc-web+proto", "expired"),
    (401, b"", "text/plain", "expired"),
    (403, b"<html>DDoS-Guard</html>", "text/html", "blocked"),
    (502, b"<html>ddos-guard check</html>", "text/html", "blocked"),
])
async def test_check(monkeypatch, status, body, ctype, want):
    monkeypatch.setattr(pulse_accounts, "_transport", _answer(status, body, {"content-type": ctype}))
    assert await pulse_accounts.check("sid=abc") == want


def test_clean_cookie_header():
    raw = "_ga=GA1.1; __ddg8_=x1; sid=abc; ; мусор; _ym_uid=5"
    assert pulse_accounts.clean_cookie_header(raw) == "__ddg8_=x1; sid=abc"
    assert pulse_accounts.clean_cookie_header("_ga=1") is None
    assert pulse_accounts.clean_cookie_header("") is None


async def test_connect_keepalive_expire(db, monkeypatch):
    answers = ["ok"]

    async def fake_check(cookie):
        assert cookie == "sid=abc"
        return answers[0]
    monkeypatch.setattr(pulse_accounts, "check", fake_check)

    async def no_sync(uid, now=None):
        return None
    monkeypatch.setattr(pulse_attendance, "sync_due", no_sync)
    answers[0] = "blocked"
    assert (await pulse_accounts.connect_from_app(1, "sid=abc"))["state"] == "blocked"
    assert (await pulse_accounts.status_for(1))["state"] == "off"      # сервер не пускают — не храним
    answers[0] = "ok"
    assert (await pulse_accounts.connect_from_app(1, "sid=abc; _ga=1"))["state"] == "ok"
    assert await pulse_accounts.cookie_for(1) == "sid=abc"
    row = await pulse_accounts._row(1)
    assert "sid=abc" not in row["cookie_enc"]                          # в базе — только шифр

    later = datetime.now(timezone.utc) + timedelta(minutes=pulse_accounts.keepalive_minutes() + 1)
    await pulse_accounts.keepalive_due(later)
    st = await pulse_accounts.status_for(1)
    assert st["state"] == "ok" and st["lived_min"] >= pulse_accounts.keepalive_minutes()

    answers[0] = "blocked"                      # DDoS-Guard разок не пустил — вход не теряем
    await pulse_accounts.keepalive_due(later + timedelta(hours=2))
    assert (await pulse_accounts.status_for(1))["state"] == "ok"
    answers[0] = "expired"
    await pulse_accounts.keepalive_due(later + timedelta(hours=4))
    assert (await pulse_accounts.status_for(1))["state"] == "expired"
    assert await pulse_accounts.cookie_for(1) is None
    await pulse_accounts.forget(1)
    assert (await pulse_accounts.status_for(1))["state"] == "off"


def test_endpoints_only_for_starosta(db, monkeypatch):
    from fastapi.testclient import TestClient

    import webapp.server as server
    from tests.conftest import STAROSTA_ID
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)

    async def fake_check(cookie):
        return "ok"
    monkeypatch.setattr(pulse_accounts, "check", fake_check)

    async def no_sync(uid, now=None):
        return None
    monkeypatch.setattr(pulse_attendance, "sync_due", no_sync)
    c = TestClient(server.app)
    other = {"X-Telegram-Init-Data": _make_init_data(user={"id": 222, "first_name": "U"})}
    me = {"X-Telegram-Init-Data": _make_init_data(user={"id": STAROSTA_ID, "first_name": "N"})}
    assert c.post("/api/pulse/connect", headers=other, json={"cookie": "sid=abc"}).status_code == 403
    assert c.get("/api/pulse/status", headers=other).status_code == 403
    assert c.post("/api/pulse/connect", headers=me, json={"cookie": "sid=abc"}).json() == {"state": "ok"}
    assert c.get("/api/v1/pulse/status", headers=me).json()["state"] == "ok"
    assert c.post("/api/pulse/disconnect", headers=me).json() == {"ok": True}
    assert c.get("/api/pulse/status", headers=me).json() == {"state": "off"}
