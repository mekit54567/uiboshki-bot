"""Заголовки безопасности, ограничение размера запроса, лимиты частоты."""
import pytest


@pytest.fixture
def client(db, monkeypatch):
    from fastapi.testclient import TestClient
    import ratelimit
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    ratelimit.reset()
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


def test_headers(client):
    c, h = client
    r = c.get("/api/me", headers=h)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"
    health = c.get("/health")
    assert health.headers["X-Content-Type-Options"] == "nosniff" and health.headers.get("Cache-Control") != "no-store"


def test_body_limits(client):
    c, h = client
    big = "x" * (2 * 1024 * 1024)
    r = c.post("/api/deadlines", content='{"subject": "' + big + '"}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 413
    # сдаче работ можно больше
    r = c.post("/api/sdo/submit", content='{"files": "' + big + '"}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code != 413


@pytest.mark.parametrize("path", ["/api/v1/sdo/submit", "/api/v1/chat"])
def test_body_limits_api_v1(client, path):
    """Приложение и PWA ходят по /api/v1: файл больше 1 МБ — не 413 (аудит 21.10, R1)."""
    c, h = client
    big = "x" * (2 * 1024 * 1024)
    r = c.post(path, content='{"files": "' + big + '"}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code != 413
    # настоящее превышение и на /api/v1 — 413
    huge = "x" * (17 * 1024 * 1024)
    r = c.post("/api/v1/chat", content='{"text": "' + huge + '"}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 413
    r = c.post("/api/v1/deadlines", content='{"subject": "' + big + '"}', headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_body_limit_paths():
    from webapp.server import body_limit, BODY_LIMIT_DEFAULT
    assert body_limit("/api/v1/sdo/submit") == body_limit("/api/sdo/submit") > BODY_LIMIT_DEFAULT
    assert body_limit("/api/v1/chat") == body_limit("/api/chat") > BODY_LIMIT_DEFAULT
    assert body_limit("/api/v1/me") == BODY_LIMIT_DEFAULT


def test_deadline_rate_limit(client):
    c, h = client
    codes = [c.post("/api/deadlines", json={"subject": f"д{i}", "due_date": "2099-01-01"}, headers=h).status_code
             for i in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_cors_only_own_origin(monkeypatch):
    import webapp.server as server
    monkeypatch.setattr(server.deps, "WEBAPP_URL", "https://uiboshki-bot-production.up.railway.app/app?x=1")
    assert server._allowed_origins() == ["https://uiboshki-bot-production.up.railway.app"]
    monkeypatch.setattr(server.deps, "WEBAPP_URL", "")
    assert server._allowed_origins() == ["*"]


def test_httpx_urls_not_logged():
    import logging
    import webapp.server  # noqa: F401 — настраивает логи
    assert logging.getLogger("httpx").level >= logging.WARNING


def test_versioned_assets_cached_long_unversioned_not():
    """js/… и app.css по ссылке с ?v=<хэш> — кэш на год (новое содержимое —
    новая ссылка); без ?v= и index — перепроверять; API — не хранить."""
    import re
    from fastapi.testclient import TestClient
    import webapp.server as server
    c = TestClient(server.app)
    index = c.get("/")
    assert index.headers["cache-control"] == "no-cache"
    url = re.search(r'src="(js/core\.js\?v=\w+)"', index.text).group(1)
    assert c.get("/" + url).headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "immutable" not in c.get("/js/core.js").headers.get("cache-control", "")
    assert c.get("/" + url).status_code == 200
