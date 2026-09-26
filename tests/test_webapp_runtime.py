"""
WebApp живёт в том же процессе, что и бот (bot.start_webapp): одна служба
на Railway, один том с SQLite. Плюс кнопка меню бота открывает WebApp сама
(без BotFather), и чат WebApp работает на Gemini, если ключа DeepSeek нет.
"""
import asyncio
import socket

import httpx
import pytest

from tests.test_webapp_auth import BOT_TOKEN, _make_init_data


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_webapp_starts_inside_bot_process_and_stops_cleanly(db):
    import bot
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        async with httpx.AsyncClient() as client:
            health = await client.get(f"http://127.0.0.1:{port}/health")
            page = await client.get(f"http://127.0.0.1:{port}/")
            api = await client.get(f"http://127.0.0.1:{port}/api/me")
        assert health.json() == {"ok": True}
        assert page.status_code == 200 and "УИБО-03-24" in page.text
        assert api.status_code == 401  # без initData — никаких данных
    finally:
        await bot.stop_webapp(server, task)
    assert task.done()


@pytest.mark.asyncio
async def test_menu_button_opens_webapp_when_url_set(monkeypatch):
    import bot
    calls = {}

    class FakeBot:
        async def set_my_commands(self, commands):
            calls["commands"] = [c.command for c in commands]

        async def set_chat_menu_button(self, menu_button):
            calls["menu"] = menu_button

    monkeypatch.setattr(bot, "WEBAPP_URL", "https://example.up.railway.app")
    await bot.setup_bot_menu(FakeBot())
    assert "schedule" in calls["commands"] and "solve" in calls["commands"]
    assert calls["menu"].web_app.url == "https://example.up.railway.app"

    calls.clear()
    monkeypatch.setattr(bot, "WEBAPP_URL", "")
    await bot.setup_bot_menu(FakeBot())
    assert "menu" not in calls


@pytest.mark.asyncio
async def test_chat_without_deepseek_key_uses_gemini_and_returns_pretty_html(db, monkeypatch):
    import ai_solver
    import webapp.server as server
    from fastapi.testclient import TestClient

    async def fake_history(history, subject="", backend="gemini", lectures="", extra_system=""):
        assert backend == "gemini"
        assert "Контекст группы" in extra_system  # чат знает дату, пары, дедлайны
        return "**Ответ:** x^2 <= 4"

    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(ai_solver, "solve_with_history", fake_history)
    monkeypatch.setattr(server, "BOT_TOKEN", BOT_TOKEN)

    client = TestClient(server.app)
    resp = client.post(
        "/api/chat",
        json={"history": [{"role": "user", "content": "реши"}]},
        headers={"X-Telegram-Init-Data": _make_init_data()},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "**Ответ:** x^2 <= 4"
    assert data["reasoning"] == ""
    assert data["html"] == "<b>Ответ:</b> x² ≤ 4"


# ── чат WebApp: вложения ─────────────────────────────────────────────────────

def _chat_client(monkeypatch):
    import webapp.server as server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_chat_photo_goes_to_gemini_vision_with_question(db, monkeypatch):
    import base64
    import ai_solver
    seen = {}

    async def fake_image(image_bytes, mime="image/jpeg", subject="", lectures="", prompt=""):
        seen.update(bytes=image_bytes, mime=mime, prompt=prompt)
        return "**Ответ:** x = 2"

    monkeypatch.setattr(ai_solver, "solve_image", fake_image)
    client, headers = _chat_client(monkeypatch)
    resp = client.post("/api/chat", headers=headers, json={
        "history": [{"role": "user", "content": "Реши систему"}],
        "attachment": {"name": "task.png", "mime": "image/png", "data": base64.b64encode(b"PNGDATA").decode()},
    })
    assert resp.status_code == 200
    assert resp.json()["html"] == "<b>Ответ:</b> x = 2"
    assert seen["bytes"] == b"PNGDATA" and seen["mime"] == "image/png"
    assert "Реши систему" in seen["prompt"] and "Контекст группы" in seen["prompt"]


@pytest.mark.asyncio
async def test_chat_document_text_goes_into_message(db, monkeypatch):
    import base64
    import ai_solver
    seen = {}

    async def fake_history(history, subject="", backend="gemini", lectures="", extra_system=""):
        seen["last"] = history[-1]["content"]
        return "Разобрал"

    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(ai_solver, "solve_with_history", fake_history)
    client, headers = _chat_client(monkeypatch)
    doc = "Лекция 5. NPV — чистая приведённая стоимость".encode("cp1251")
    resp = client.post("/api/chat", headers=headers, json={
        "history": [{"role": "user", "content": ""}],
        "attachment": {"name": "lec5.txt", "mime": "text/plain", "data": base64.b64encode(doc).decode()},
    })
    assert resp.status_code == 200
    assert seen["last"].startswith("Разбери этот файл.")
    assert "=== Файл «lec5.txt» ===" in seen["last"] and "чистая приведённая стоимость" in seen["last"]


@pytest.mark.asyncio
async def test_chat_rejects_unsupported_and_too_big(db, monkeypatch):
    import base64
    import webapp.server as server
    client, headers = _chat_client(monkeypatch)
    hist = [{"role": "user", "content": "что тут?"}]
    resp = client.post("/api/chat", headers=headers, json={
        "history": hist, "attachment": {"name": "a.exe", "mime": "application/x-msdownload", "data": "AAAA"}})
    assert resp.status_code == 415 and "PDF" in resp.json()["detail"]

    monkeypatch.setattr(server, "MAX_ATTACHMENT_BYTES", 3)
    resp = client.post("/api/chat", headers=headers, json={
        "history": hist, "attachment": {"name": "a.txt", "mime": "text/plain",
                                        "data": base64.b64encode(b"long text").decode()}})
    assert resp.status_code == 413
