"""Карта корпусов (campus_map.py, 5.100.4): данные, поиск, маршрут, API."""
import json
from pathlib import Path

import pytest

import campus_map

TEST_DIR = Path(__file__).parent / "data" / "map"


@pytest.fixture(autouse=True)
def _test_campus(monkeypatch):
    monkeypatch.setenv("MAP_DIR", str(TEST_DIR))
    monkeypatch.delenv("MAP", raising=False)
    campus_map.forget()
    yield
    campus_map.forget()


def test_test_data_valid_and_fresh():
    """Тестовый корпус проходит проверку и совпадает с tools/map_demo.py."""
    import tools.map_demo as demo
    data = json.loads((TEST_DIR / "test.json").read_text(encoding="utf-8"))
    assert campus_map.check(data) == []
    assert [f["n"] for f in data["floors"]] == [1, 2, 3]
    floors = [demo.floor(n) for n in (1, 2, 3)]
    assert data["floors"] == json.loads(json.dumps(floors, ensure_ascii=False)), "запусти python tools/map_demo.py"


def test_check_catches_broken_data():
    data = json.loads((TEST_DIR / "test.json").read_text(encoding="utf-8"))
    data["floors"][0]["rooms"][0]["door"] = "1:нет"
    data["floors"][1]["edges"] = []                       # второй этаж — без коридора
    errs = campus_map.check(data)
    assert any("дверь 1:нет" in e for e in errs)
    data["floors"][0]["rooms"][0]["door"] = "1:t0"
    assert any("не дойти" in e for e in campus_map.check(data))


@pytest.mark.parametrize("q", ["Т-201", "т201", "t 201", "T-201"])
def test_find_normalizes(q):
    hits = campus_map.find(q)
    assert hits[0]["name"] == "Т-201" and hits[0]["floor"] == 2 and hits[0]["campus"] == "test"


def test_find_prefix_and_empty():
    assert {h["name"] for h in campus_map.find("т3")} >= {"Т-301", "Т-311"}
    assert campus_map.find("") == [] and campus_map.find("—") == []


def test_route_across_floors_merges_transit():
    r = campus_map.route("test", "Т-101", "Т-305")
    assert (r["from"]["floor"], r["to"]["floor"]) == (1, 3)
    assert r["steps"] == [{"kind": "stairs", "from": 1, "to": 3}]     # 2-й этаж — насквозь
    assert [leg["floor"] for leg in r["legs"]] == [1, 3]
    assert r["meters"] > 0 and r["minutes"] >= 1
    lift = campus_map.route("test", "Т-101", "Т-305", lift=True)
    assert lift["steps"] == [{"kind": "lift", "from": 1, "to": 3}]


def test_route_same_floor_and_unknown():
    r = campus_map.route("test", "Т-201", "Т-205")
    assert r["steps"] == [] and [leg["floor"] for leg in r["legs"]] == [2]
    assert r["legs"][0]["points"][0] == [195, 210]            # от двери Т-201
    assert campus_map.route("test", "Т-201", "Т-999") is None
    assert campus_map.route("нет", "Т-201", "Т-205") is None


def test_switch_and_no_data(monkeypatch, tmp_path):
    assert campus_map.enabled()
    monkeypatch.setenv("MAP", "0")
    assert not campus_map.enabled()
    monkeypatch.setenv("MAP", "1")
    monkeypatch.setenv("MAP_DIR", str(tmp_path))
    campus_map.forget()
    assert not campus_map.enabled() and campus_map.campuses() == []


@pytest.mark.asyncio
async def test_api_map(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/meta").json()["features"]["map"] is True
    lst = c.get("/api/map", headers=h).json()["campuses"]
    assert lst == [{"id": "test", "name": "Тестовый корпус", "short": "Т", "address": "тестовые данные",
                    "source": "тестовые данные", "floors": [1, 2, 3]}]
    assert len(c.get("/api/map/test", headers=h).json()["floors"]) == 3
    assert c.get("/api/map/find?q=т-10", headers=h).json()["rooms"][0]["name"] == "Т-101"
    r = c.get("/api/map/route?campus=test&src=Т-101&dst=Т-205", headers=h)
    assert r.status_code == 200 and r.json()["steps"][0]["to"] == 2
    assert c.get("/api/map/route?campus=test&src=Т-101&dst=нет", headers=h).status_code == 404
    assert c.get("/api/map/test").status_code == 401
    monkeypatch.setenv("MAP", "0")
    assert c.get("/api/meta").json()["features"]["map"] is False
    assert c.get("/api/map", headers=h).json() == {"campuses": []}
    assert c.get("/api/map/test", headers=h).status_code == 404
