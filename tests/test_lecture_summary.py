"""Конспект лекции (lecture_summary.py, WebApp «Сделать конспект»): один на
файл и общий для всех, делается только по нажатию, ИИ — один раз."""
import asyncio

import pytest

from kapibara.features.lectures import summary as lecture_summary

TEXT = "Бухгалтерский учёт. Дебет — левая сторона счёта, кредит — правая. Баланс: актив = пассив."
SUMMARY = "**Основы учёта**\n- Дебет — левая сторона счёта\n- Кредит — правая\n- Актив = пассив"


def _fake_ai(monkeypatch, calls):
    from kapibara.features.ai import solver as ai_solver

    async def fake_chat(history, subject="", extra_system="", lectures=""):
        calls.append(lectures)
        await asyncio.sleep(0.01)
        return {"content": SUMMARY, "reasoning": ""}

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", fake_chat)


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    return TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}


@pytest.mark.asyncio
async def test_summary_made_once_and_shared(db, monkeypatch):
    calls = []
    _fake_ai(monkeypatch, calls)
    fid = await db.add_file("ЛК1", "Бухучёт", "TG1", "lk1.pdf", 0, category="lecture")
    await db.save_file_text(fid, TEXT)
    c, h = _client(monkeypatch)

    # пока никто не нажал — конспекта нет, ИИ не звали
    view = c.get(f"/api/summary/{fid}", headers=h).json()
    assert view["summary"] is None and view["has_text"] and calls == []
    assert c.get("/api/files", headers=h).json()["items"][0]["has_summary"] is False

    made = c.post(f"/api/summary/{fid}", headers=h).json()
    assert "<b>Основы учёта</b>" in made["summary"] and len(calls) == 1
    assert "=== ЛК1 ===" in calls[0] and "Дебет" in calls[0]
    # у всех открывается готовый, повторное нажатие ИИ не зовёт
    assert c.get(f"/api/summary/{fid}", headers=h).json()["summary"] == made["summary"]
    assert c.post(f"/api/summary/{fid}", headers=h).status_code == 200 and len(calls) == 1
    assert c.get("/api/files", headers=h).json()["items"][0]["has_summary"] is True

    # удалили файл — конспект ушёл вместе с ним
    await db.delete_file(fid)
    assert await db.get_file_summary(fid) is None


@pytest.mark.asyncio
async def test_two_presses_at_once_call_ai_once(db, monkeypatch):
    calls = []
    _fake_ai(monkeypatch, calls)
    fid = await db.add_file("ЛК2", "Бухучёт", "TG2", "lk2.pdf", 0)
    await db.save_file_text(fid, TEXT)
    a, b = await asyncio.gather(lecture_summary.make(fid, "ЛК2", "Бухучёт", 1),
                                lecture_summary.make(fid, "ЛК2", "Бухучёт", 2))
    assert len(calls) == 1 and a["content"] == b["content"] == SUMMARY
    assert a["created_by"] == 1


@pytest.mark.asyncio
async def test_no_text_or_ai_failure(db, monkeypatch):
    from kapibara.features.ai import solver as ai_solver
    fid = await db.add_file("Скан", "Бухучёт", "TG3", "scan.pdf", 0)
    c, h = _client(monkeypatch)
    assert c.post(f"/api/summary/{fid}", headers=h).status_code == 422
    assert c.get("/api/summary/99999", headers=h).status_code == 404

    async def broken(*a, **kw):
        raise RuntimeError("лимит запросов")

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", broken)
    await db.save_file_text(fid, TEXT)
    r = c.post(f"/api/summary/{fid}", headers=h)
    assert r.status_code == 502 and "попробуй" in r.json()["detail"]
    assert await db.get_file_summary(fid) is None          # сбой не оставляет пустой конспект
