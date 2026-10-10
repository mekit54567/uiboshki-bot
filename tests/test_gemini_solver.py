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


@pytest.mark.asyncio
async def test_rate_limited_model_falls_back(monkeypatch):
    """Основная модель упёрлась в лимит (429) — тот же запрос запасной; запасной
    нет (404) — следующая; кончились все — текст про лимит, а не про 404."""
    calls = []
    replies = {"main": (429, {"error": {}}), "gone": (404, {"error": {}}),
               "spare": (200, {"candidates": [{"content": {"parts": [{"text": "ответ запасной"}]}}]})}

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        calls.append(model)
        status, body = replies[model]
        return httpx.Response(status, json=body)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(gemini_solver.httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini_solver, "GEMINI_MODEL", "main")
    monkeypatch.setattr(gemini_solver, "GEMINI_FALLBACK_MODELS", ["gone", "spare"])
    monkeypatch.setattr(gemini_solver, "_primary_rest_until", 0.0)
    text = await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}])
    assert text == "ответ запасной" and calls == ["main", "gone", "spare"]

    calls.clear()                                              # основная «отдыхает» — сразу запасная,
    assert await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}]) == "ответ запасной"
    assert calls == ["spare"]                                  # пропавшую (404) больше не дёргаем
    gemini_solver._missing.clear()

    calls.clear()                                              # классификатор — без запасных
    with pytest.raises(gemini_solver.GeminiError, match="Лимит"):
        await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}], fallback=False)
    assert calls == ["main"]

    calls.clear()
    monkeypatch.setattr(gemini_solver, "_primary_rest_until", 0.0)
    monkeypatch.setattr(gemini_solver, "GEMINI_FALLBACK_MODELS", ["gone"])
    with pytest.raises(gemini_solver.GeminiError, match="Лимит бесплатного тира") as e:
        await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}])
    assert e.value.transient and calls == ["main", "gone"]

    calls.clear()
    monkeypatch.setattr(gemini_solver, "_primary_rest_until", 0.0)
    replies["main"] = (404, {"error": {}})                     # основная не найдена — сразу ошибка, без перебора
    with pytest.raises(gemini_solver.GeminiError, match="не найдена"):
        await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}])
    assert calls == ["main"]


@pytest.mark.asyncio
async def test_resting_primary_tried_when_spare_is_gone(monkeypatch):
    """10.10: запасной gemini-2.5-flash у Google не стало (404), и после 429
    основная 10 минут «отдыхала» — весь ИИ отвечал «модель не найдена».
    Теперь основная идёт после запасных, а пропавшая запасная запоминается."""
    calls = []
    replies = {"main": (200, {"candidates": [{"content": {"parts": [{"text": "ответ основной"}]}}]}),
               "gone": (404, {"error": {}})}

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        calls.append(model)
        status, body = replies[model]
        return httpx.Response(status, json=body)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(gemini_solver.httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini_solver, "GEMINI_MODEL", "main")
    monkeypatch.setattr(gemini_solver, "GEMINI_FALLBACK_MODELS", ["gone"])
    gemini_solver._rest_primary()                              # основная недавно упёрлась в лимит
    assert await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}]) == "ответ основной"
    assert calls == ["gone", "main"]
    calls.clear()
    assert await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}]) == "ответ основной"
    assert calls == ["main"] and gemini_solver.rest_status() == (0.0, [])   # запасных не осталось
    replies["main"] = (429, {"error": {}})
    with pytest.raises(gemini_solver.GeminiError, match="Лимит"):    # не «модель не найдена»
        await gemini_solver._generate([{"role": "user", "parts": [{"text": "?"}]}])


@pytest.mark.asyncio
async def test_spare_openrouter_model_when_gemini_limited(monkeypatch):
    """10.10, владелец: своя группа — на Gemini, а кончились лимиты у всех её
    моделей — отвечает дешёвая Ling через OpenRouter (тем же запросом, с фото)."""
    calls, sent = [], []

    def handler(request):
        if request.url.host == "openrouter.ai":
            sent.append(json.loads(request.content))
            calls.append("ling")
            return httpx.Response(200, json={"choices": [{"message": {"content": "ответ Ling"},
                                                          "finish_reason": "stop"}]})
        calls.append(request.url.path.split("/models/")[1].split(":")[0])
        return httpx.Response(429, json={"error": {}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(gemini_solver.httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini_solver, "GEMINI_MODEL", "main")
    monkeypatch.setattr(gemini_solver, "GEMINI_FALLBACK_MODELS", ["spare"])
    monkeypatch.setattr(gemini_solver, "OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(gemini_solver, "AI_SPARE_MODEL", "inclusionai/ling-3.0-flash-vl")
    text = await gemini_solver.generate_from_image(b"img", "image/png", "реши", "система")
    assert text == "ответ Ling" and calls == ["main", "spare", "ling"]
    msg = sent[0]
    assert msg["model"] == "inclusionai/ling-3.0-flash-vl" and msg["messages"][0] == {"role": "system", "content": "система"}
    parts = msg["messages"][1]["content"]
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,") and parts[1] == {"type": "text", "text": "реши"}

    calls.clear()                                              # классификатор — без запасных, Ling тоже нет
    with pytest.raises(gemini_solver.GeminiError, match="Лимит"):
        await gemini_solver.generate_text([{"role": "user", "content": "?"}], "s", fallback=False)
    assert "ling" not in calls

    calls.clear()                                              # без ключа OpenRouter — как раньше, текст про лимит
    monkeypatch.setattr(gemini_solver, "AI_SPARE_MODEL", "")
    with pytest.raises(gemini_solver.GeminiError, match="Лимит"):
        await gemini_solver.generate_text([{"role": "user", "content": "?"}], "s")
    assert "ling" not in calls
