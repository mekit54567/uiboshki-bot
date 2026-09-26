"""
Решалка целиком на Gemini (Groq удалён): формат запроса generateContent,
история диалога, фото, фолбэк /solve_ds без ключа DeepSeek, понятные ошибки
вместо сырого httpx-исключения, классификатор намерений. Сеть — через
httpx.MockTransport: реальный httpx-клиент, подменён только транспорт.
"""
import base64
import json

import httpx
import pytest

import ai_solver
import gemini_solver
import intent_router


@pytest.fixture
def gemini(monkeypatch):
    """Перехватывает запросы к Gemini. requests — что ушло, reply — что ответить."""
    state = {"requests": [], "reply": (200, {"candidates": [{"content": {"parts": [{"text": "Ответ модели"}]}}]})}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        status, body = state["reply"]
        return httpx.Response(status, json=body)

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(gemini_solver.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(gemini_solver, "GEMINI_MODEL", "gemini-test")
    return state


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.mark.asyncio
async def test_solve_text_goes_to_gemini_with_key_in_header(gemini):
    answer = await ai_solver.solve_text("2 + 2 = ?", "Математика")
    assert answer == "Ответ модели"

    req = gemini["requests"][0]
    assert req.url.path.endswith("/models/gemini-test:generateContent")
    assert req.headers["x-goog-api-key"] == "test-gemini-key"
    assert "test-gemini-key" not in str(req.url)  # ключ не в URL — иначе утёк бы в текст ошибки

    body = _body(req)
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Задание:\n2 + 2 = ?"}]}]
    assert "«Математика»" in body["systemInstruction"]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_dialog_history_maps_assistant_to_model(gemini):
    history = [
        {"role": "user", "content": "Задание:\nреши x+1=3"},
        {"role": "assistant", "content": "x = 2"},
        {"role": "user", "content": "а почему?"},
    ]
    await ai_solver.solve_with_history(history, "Математика")
    roles = [c["role"] for c in _body(gemini["requests"][0])["contents"]]
    assert roles == ["user", "model", "user"]


@pytest.mark.asyncio
async def test_deepseek_without_key_falls_back_to_gemini(gemini, monkeypatch):
    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "")
    assert await ai_solver.solve_text("задача", backend="deepseek") == "Ответ модели"
    assert len(gemini["requests"]) == 1


@pytest.mark.asyncio
async def test_unknown_backend_like_old_groq_goes_to_gemini(gemini):
    # В FSM-состоянии у кого-то после деплоя может остаться backend="groq".
    assert await ai_solver.solve_text("задача", backend="groq") == "Ответ модели"


@pytest.mark.asyncio
async def test_photo_and_ocr_send_inline_image(gemini):
    img = b"\xff\xd8fake-jpeg"
    await ai_solver.solve_image(img, subject="Экономика")
    await ai_solver.extract_text_from_image(img)

    for req in gemini["requests"]:
        parts = _body(req)["contents"][0]["parts"]
        assert parts[0]["inlineData"] == {"mimeType": "image/jpeg", "data": base64.b64encode(img).decode()}
    assert _body(gemini["requests"][1])["generationConfig"]["temperature"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [
    (429, "Лимит бесплатного тира Gemini исчерпан"),
    (404, "Модель gemini-test не найдена"),
    (403, "проверь GEMINI_API_KEY"),
    (500, "HTTP 500"),
])
async def test_http_errors_become_readable_and_keep_key_secret(gemini, status, expected):
    gemini["reply"] = (status, {"error": {"message": "whatever"}})
    with pytest.raises(gemini_solver.GeminiError) as exc:
        await ai_solver.solve_text("задача")
    assert expected in str(exc.value)
    assert "test-gemini-key" not in str(exc.value)


@pytest.mark.asyncio
async def test_empty_answer_is_an_error_not_blank_message(gemini):
    gemini["reply"] = (200, {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]})
    with pytest.raises(gemini_solver.GeminiError, match="SAFETY"):
        await ai_solver.solve_text("задача")


@pytest.mark.asyncio
async def test_missing_key_is_readable(gemini, monkeypatch):
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "")
    with pytest.raises(gemini_solver.GeminiError, match="GEMINI_API_KEY не настроен"):
        await ai_solver.solve_text("задача")
    assert gemini["requests"] == []


@pytest.mark.asyncio
async def test_lecture_solver_still_works_through_shared_call(gemini):
    answer = await gemini_solver.solve_with_lecture_context("задание", "Матан", "=== Лекция 1 ===\nтекст")
    assert answer == "Ответ модели"
    text = _body(gemini["requests"][0])["contents"][0]["parts"][0]["text"]
    assert "=== Лекция 1 ===" in text and "задание" in text


# ── Классификатор намерений ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classifier_uses_gemini(gemini):
    gemini["reply"] = (200, {"candidates": [{"content": {"parts": [{"text": "deadlines_list\n"}]}}]})
    assert await intent_router.classify_intent("какие дедлайны на неделе") == "deadlines_list"
    body = _body(gemini["requests"][0])
    assert "maxOutputTokens" not in body["generationConfig"]  # см. комментарий в classify_intent


@pytest.mark.asyncio
async def test_classifier_skips_long_task_text_to_save_quota(gemini):
    long_task = "Найдите производную функции f(x) = " + "x^2 + " * 100 + "1"
    assert await intent_router.classify_intent(long_task) == "none"
    assert gemini["requests"] == []


@pytest.mark.asyncio
async def test_classifier_fails_safe_on_quota(gemini):
    gemini["reply"] = (429, {"error": {}})
    assert await intent_router.classify_intent("когда следующая пара") == "none"
