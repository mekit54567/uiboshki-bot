"""/ready (02.11): по нему сервер после выкладки решает, поднялся ли бот.
/health — «процесс жив», /ready — «все этапы запуска пройдены и база отвечает»."""
import pytest

from kapibara.ops import health


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    import webapp.server as server
    return TestClient(server.app)


def test_not_ready_until_all_steps(client, monkeypatch):
    monkeypatch.setattr(health, "_ready", set())
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["waiting"] == list(health.READY_STEPS)
    assert r.json()["db"] is True
    for step in health.READY_STEPS:
        health.mark_ready(step)
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "waiting": [], "db": True, "commit": r.json()["commit"]}


def test_not_ready_when_db_broken(client, monkeypatch, tmp_path):
    import database
    monkeypatch.setattr(health, "_ready", set(health.READY_STEPS))
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "нет" / "такой" / "папки.db"))
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["db"] is False


def test_health_stays_simple(client, monkeypatch):
    monkeypatch.setattr(health, "_ready", set())
    assert client.get("/health").json() == {"ok": True}     # внешний аптайм-чекер не трогаем


def test_bot_marks_every_step():
    """Каждый этап из READY_STEPS отмечается в bot.py — иначе /ready не
    дождётся никогда, и выкладка будет откатываться."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "bot.py").read_text(encoding="utf-8")
    for step in health.READY_STEPS:
        assert f'health.mark_ready("{step}")' in text
    assert "dp.startup.register(polling_started)" in text
