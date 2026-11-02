"""
Вложенный в чат WebApp документ раньше забывался со следующего сообщения:
сервер дописывал его текст только в последний вопрос запроса, а фронт хранил
«Разбери этот файл.» без содержимого. Теперь /api/chat отдаёт сокращённый
текст файла (file_text), фронт кладёт его в запись вопроса и шлёт в истории
следующих (js/chat.js, tests/test_webapp_static.py).
"""
import base64

import pytest

from tests.test_webapp_auth import BOT_TOKEN, _make_init_data


def _client(monkeypatch):
    import webapp.server as server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_chat_returns_file_text_and_it_works_in_next_question(db, monkeypatch):
    from kapibara.features.ai import solver as ai_solver
    import webapp.routes.chat as chat
    seen = []

    async def fake_chat(history, subject="", extra_system="", lectures=""):
        seen.append([m["content"] for m in history])
        return {"content": "Разобрал", "reasoning": ""}

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", fake_chat)
    monkeypatch.setattr(chat, "FILE_MEMORY_LIMIT", 40)
    client, headers = _client(monkeypatch)
    doc = ("Лекция 5. NPV — чистая приведённая стоимость. " * 5).encode()
    r = client.post("/api/chat", headers=headers, json={
        "history": [{"role": "user", "content": ""}],
        "attachment": {"name": "lec5.txt", "mime": "text/plain", "data": base64.b64encode(doc).decode()},
    })
    assert r.status_code == 200, r.text
    file_text = r.json()["file_text"]
    assert file_text.startswith("=== Файл «lec5.txt» ===\nЛекция 5. NPV")
    assert file_text.endswith("(дальше файл обрезан)") and len(file_text) < 100    # сокращённый
    assert "Лекция 5. NPV" in seen[0][-1]                                        # сам запрос — с файлом целиком

    # следующий вопрос: фронт присылает file_text в записи первого вопроса
    r = client.post("/api/chat", headers=headers, json={"history": [
        {"role": "user", "content": "Разбери этот файл.\n\n" + file_text},
        {"role": "assistant", "content": "Разобрал"},
        {"role": "user", "content": "а что такое NPV?"},
    ]})
    assert r.status_code == 200 and "file_text" not in r.json()                  # без вложения — без поля
    assert "=== Файл «lec5.txt» ===" in seen[1][0] and seen[1][-1] == "а что такое NPV?"


@pytest.mark.asyncio
async def test_photo_answer_has_no_file_text(db, monkeypatch):
    from kapibara.features.ai import solver as ai_solver

    async def fake_image(image_bytes, mime="image/jpeg", subject="", lectures="", prompt=""):
        return "x = 2"

    monkeypatch.setattr(ai_solver, "solve_image", fake_image)
    client, headers = _client(monkeypatch)
    r = client.post("/api/chat", headers=headers, json={
        "history": [{"role": "user", "content": "Реши"}],
        "attachment": {"name": "t.png", "mime": "image/png", "data": base64.b64encode(b"PNG").decode()},
    })
    assert r.status_code == 200 and "file_text" not in r.json()
