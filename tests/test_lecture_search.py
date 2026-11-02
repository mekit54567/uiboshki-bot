"""Поиск внутри лекций во вкладке «Файлы» (/api/lecture-search)."""
import pytest

from webapp.routes.files import _snippet


def test_snippet_around_query_word():
    text = "Введение. " + "слово " * 30 + "Дисконтирование денежных потоков — приведение к текущей стоимости. " + "хвост " * 40
    s = _snippet(text, "дисконтированный поток")
    assert s.startswith("…") and "Дисконтирование денежных потоков" in s and s.endswith("…")
    assert _snippet("Короткий текст", "нет такого") == "Короткий текст"
    assert len(_snippet("а " * 500, "zzz")) <= 181


@pytest.mark.asyncio
async def test_lecture_search_route(db, monkeypatch):
    from fastapi.testclient import TestClient
    from kapibara.features.ai import semantic_search
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    asked = []

    async def ready():
        return True

    async def search(q, subject="", k=10):
        asked.append((q, subject, k))
        return [{"file_id": 7, "title": "Лекция 5", "subject": "Анализ данных", "page_from": 12, "page_to": 12,
                 "kind": "слайд", "text": "NPV — чистая приведённая стоимость"}]

    monkeypatch.setattr(semantic_search, "ready", ready)
    monkeypatch.setattr(semantic_search, "search", search)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/lecture-search?q=np", headers=h).json()["items"] == []        # короче 3 — без поиска
    r = c.get("/api/lecture-search?q=NPV", headers=h).json()
    assert r["items"] == [{"file_id": 7, "title": "Лекция 5", "subject": "Анализ данных", "place": "слайд 12",
                           "page": 12, "snippet": "NPV — чистая приведённая стоимость"}]
    assert asked == [("NPV", "", 8)]

    async def not_ready():
        return False

    monkeypatch.setattr(semantic_search, "ready", not_ready)
    assert c.get("/api/lecture-search?q=NPV", headers=h).json() == {"items": [], "ready": False}
    assert c.get("/api/lecture-search?q=NPV").status_code in (401, 403)                 # без initData — нельзя


def test_files_tab_shows_lecture_hits():
    from tests.test_webapp_static import JS
    js = JS["js/files.js"]
    assert "async function loadLectureHits(q, alone)" in js and '"/api/lecture-search?q="' in js
    assert "openPage(' + h.file_id + ',' + h.page + ')" in js and "function markStems(html, stems)" in js
