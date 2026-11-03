"""Запасной ИИ: Gemini упал (таймаут/5xx — ещё попытка; лимит — сразу) →
DeepSeek с пометкой; DeepSeek упал → Gemini. Постоянная ошибка (ключ,
модель) не маскируется."""
from pathlib import Path
import pytest

from kapibara.features.ai import solver as ai_solver
from kapibara.features.ai import gemini as gemini_solver
from kapibara.features.ai.gemini import GeminiError

HIST = [{"role": "user", "content": "2+2?"}]


@pytest.fixture
def ai(monkeypatch):
    calls = {"gemini": [], "ds": []}
    state = {"gemini": [], "ds": None}      # очереди ответов: строка или исключение

    async def fake_gemini(history, system, **kw):
        calls["gemini"].append(system + "".join(m["content"] for m in history))
        r = state["gemini"].pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    async def fake_ds(messages, **params):
        calls["ds"].append("".join(m["content"] for m in messages))
        if isinstance(state["ds"], Exception):
            raise state["ds"]
        return {"content": state["ds"], "reasoning_content": "думал"}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(gemini_solver, "generate_text", fake_gemini)
    monkeypatch.setattr(ai_solver, "_deepseek_chat", fake_ds)
    monkeypatch.setattr(ai_solver.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "k")
    return state, calls


@pytest.mark.asyncio
async def test_timeout_retried_then_ok(ai):
    state, calls = ai
    state["gemini"] = [GeminiError("таймаут", transient=True), "4"]
    assert await ai_solver.solve_with_history(HIST) == "4"
    assert len(calls["gemini"]) == 2 and not calls["ds"]


@pytest.mark.asyncio
async def test_limit_goes_to_deepseek_with_note(ai):
    state, calls = ai
    state["gemini"] = [GeminiError("лимит", transient=True, status=429)]
    state["ds"] = "четыре"
    out = await ai_solver.solve_with_history(HIST, lectures="Лекция 1. " * 20000)
    assert out.startswith("четыре") and "DeepSeek" in out
    assert len(calls["gemini"]) == 1                       # на лимит не повторяем
    assert len(calls["ds"][0]) < len(calls["gemini"][0])   # лекции для DeepSeek короче
    assert HIST == [{"role": "user", "content": "2+2?"}]   # лекции — в копии истории, не в исходной


@pytest.mark.asyncio
async def test_permanent_error_not_masked(ai):
    state, calls = ai
    state["gemini"] = [GeminiError("проверь GEMINI_API_KEY", status=403)]
    with pytest.raises(GeminiError, match="GEMINI_API_KEY"):
        await ai_solver.solve_with_history(HIST)
    assert not calls["ds"]


@pytest.mark.asyncio
async def test_both_down_shows_gemini_reason(ai, monkeypatch):
    state, _ = ai
    state["gemini"] = [GeminiError("лимит Gemini", transient=True, status=429)]
    state["ds"] = RuntimeError("ds down")
    with pytest.raises(GeminiError, match="лимит Gemini"):
        await ai_solver.solve_with_history(HIST)


@pytest.mark.asyncio
async def test_no_deepseek_key_no_fallback(ai, monkeypatch):
    state, calls = ai
    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "")
    state["gemini"] = [GeminiError("лимит", transient=True, status=429)]
    with pytest.raises(GeminiError):
        await ai_solver.solve_with_history(HIST)


@pytest.mark.asyncio
async def test_webapp_chat_deepseek_down_gemini_answers(ai):
    state, calls = ai
    state["ds"] = RuntimeError("502")
    state["gemini"] = ["ответ"]
    r = await ai_solver.chat_with_reasoning(HIST)
    assert r["content"].startswith("ответ") and "Gemini" in r["content"] and r["reasoning"] == ""


def test_gemini_errors_marked_transient():
    import httpx
    assert GeminiError("x", transient=True).transient and not GeminiError("x").transient
    # 429 и 5xx временные, 400/403/404 — нет (по коду в _generate)
    src = Path(gemini_solver.__file__).read_text(encoding="utf-8")
    assert "resp.status_code == 429 or resp.status_code >= 500" in src
    assert httpx  # noqa
