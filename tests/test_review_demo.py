"""Демо-вход проверяющих App Store / RuStore (review_demo.py): код из
REVIEW_CODE → сессия демо-аккаунта, ответы — запись стенда со сдвигом на
текущую неделю, настоящие данные и обработчики не трогаются."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import review_demo
from utils import TZ

CODE = "kapibara-review-2026"


@pytest.fixture
def client(db, monkeypatch):
    import config
    import ratelimit
    import webapp.server as server
    monkeypatch.setattr(config, "REVIEW_CODE", CODE)
    ratelimit.reset()
    return TestClient(server.app, headers={"User-Agent": "Dart/3", "X-App": "ios"})


def _login(client) -> dict:
    r = client.post("/api/v1/auth/review", json={"code": CODE})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_code_login_and_flag(client):
    assert client.get("/api/auth/providers").json()["code"] is True
    assert client.post("/api/auth/review", json={"code": "не тот код"}).status_code == 403
    h = _login(client)
    assert h["Authorization"].startswith("Bearer rv.")
    me = client.get("/api/v1/me", headers=h).json()
    assert me["group"]["name"] == "УИБО-03-24"


def test_off_without_code(db, monkeypatch):
    import config
    import webapp.server as server
    monkeypatch.setattr(config, "REVIEW_CODE", "")
    c = TestClient(server.app)
    assert c.get("/api/auth/providers").json()["code"] is False
    assert c.post("/api/auth/review", json={"code": ""}).status_code == 404


def test_short_code_is_ignored(monkeypatch):
    import importlib

    import config
    monkeypatch.setenv("REVIEW_CODE", "123")
    try:
        assert importlib.reload(config).REVIEW_CODE == ""
    finally:
        monkeypatch.delenv("REVIEW_CODE")
        importlib.reload(config)


def test_attempts_are_limited(client):
    codes = [client.post("/api/auth/review", json={"code": f"x{i}"}).status_code for i in range(6)]
    assert codes[-1] == 429


def test_forged_rv_token_is_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer rv.fake"})
    assert r.status_code == 401


def test_delete_and_logout_keep_demo_account(client):
    h = _login(client)
    assert client.post("/api/me/delete", json={"confirm": True}, headers=h).json() == {"ok": True}
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 200      # тот же вход живёт дальше


def test_week_shift_keeps_weekdays():
    assert review_demo.shift_days(date(2026, 10, 8)) == 0
    assert review_demo.shift_days(date(2026, 11, 22)) == 42          # воскресенье — та же неделя
    assert review_demo.shift_days(date(2026, 11, 23)) == 49


def test_answers_follow_today():
    now = datetime(2026, 11, 24, 11, 0, tzinfo=TZ)                   # вторник, через 7 недель
    st, day = review_demo.answer("GET", "/api/day", "date=2026-11-27", b"", now)
    assert st == 200 and day["date"] == "2026-11-27" and day["label"] == "27 ноября"
    assert day["weekday"] == "Пятница" and day["lessons"]
    assert day["lessons"][0]["start_iso"].startswith("2026-11-27T")

    st, week = review_demo.answer("GET", "/api/week", "start=2026-11-23", b"", now)
    assert week["days"][0]["date"] == "2026-11-23" and week["week"] == 13

    today = review_demo.today_view(now)
    assert today["date"] == "2026-11-24" and today["weekday"] == "Вторник"
    assert today["now"].startswith("2026-11-24T11:00")
    assert all(x["status"] in ("now", "past", "later") for x in today["lessons"])
    soon = today["deadlines"]["soon"][0]
    assert soon["days"] == (date.fromisoformat(soon["due_date"]) - now.date()).days

    _, grades = review_demo.answer("GET", "/api/sdo/grades/18672", "", b"", now)
    text = str(grades)
    assert "15 октября 2026" not in text and "четверг, 3 декабря 2026" in text


def test_unknown_answers_like_fake_api():
    now = datetime(2026, 10, 8, 10, 0, tzinfo=TZ)
    assert review_demo.answer("GET", "/api/nothing", "", b"", now) == (200, {"ok": True})
    assert review_demo.answer("POST", "/api/sdo/submit", "", b"", now)[1]["status"]


def test_real_users_are_not_intercepted(client, monkeypatch):
    """Обычный вход (не rv.) идёт в настоящие обработчики."""
    r = client.get("/api/me", headers={"Authorization": "Bearer obychny-token"})
    assert r.status_code == 401 and "сессия" in r.json()["detail"]
