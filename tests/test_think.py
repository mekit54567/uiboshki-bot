"""«Подумать ещё» (think.py): второй уровень ИИ для «Капибара+» — DeepSeek
через OpenRouter без запасных, свой дневной лимит, попытка не списывается
при сбое, выключатель, кнопка в чате WebApp и в боте, на iPhone — нет."""
import json

import httpx
import pytest

import gemini_solver
import think
from tests.test_review_bot import bot, dp, press, send  # noqa: F401 — фикстуры
from tests.test_webapp_home import _headers_for, client  # noqa: F401 — фикстура

ME, OTHER = 701, 702


@pytest.fixture
def on(monkeypatch):
    import config
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(gemini_solver, "OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(think, "DAILY", 2)


async def _plus(db, uid=ME):
    await db.upsert_user(uid, "", "u")
    await db.set_subscription_until(uid, "2099-01-01")


def _openrouter(monkeypatch, status=200, seen=None):
    def handler(request):
        assert request.url.host == "openrouter.ai"           # Gemini не зовём
        if seen is not None:
            seen.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": {}})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "глубокий ответ"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "cost": 0.0004}})
    real = httpx._client.AsyncClient          # настоящий класс: заглушка могла уже стоять
    monkeypatch.setattr(gemini_solver.httpx, "AsyncClient",
                        lambda *a, **kw: real(*a, transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_solve_uses_model_counts_and_refunds(db, monkeypatch, on):
    await _plus(db)
    seen = []
    _openrouter(monkeypatch, seen=seen)
    q = [{"role": "user", "content": "Что такое NPV?"}]
    answer = await think.solve(ME, q, lectures="=== Лекция 1 ===\nNPV — чистая приведённая стоимость")
    assert answer.startswith("глубокий ответ") and "DeepSeek" in answer
    body = seen[0]
    assert body["model"] == think.MODEL and body["provider"] == {"data_collection": "deny"}   # 152-ФЗ
    assert "Подумать ещё" in body["messages"][0]["content"] and "NPV" in body["messages"][-1]["content"]
    assert await think.left(ME) == 1
    assert "0.000" in await think.status_line() and "1 отв." in await think.status_line()

    _openrouter(monkeypatch, status=503)                      # не ответила — попытку не списываем
    with pytest.raises(think.ThinkError, match="не списана"):
        await think.solve(ME, q)
    assert await think.left(ME) == 1

    _openrouter(monkeypatch)
    await think.solve(ME, q)
    with pytest.raises(think.ThinkError, match="2 в день"):   # свой лимит, даже у подписчика
        await think.solve(ME, q)


@pytest.mark.asyncio
async def test_offer_only_for_plus_not_ios_and_switch(db, monkeypatch, on):
    from database import set_setting
    await _plus(db)
    await db.upsert_user(OTHER, "", "u")
    assert (await think.offer(ME))["left"] == 2
    assert await think.offer(ME, "ios") is None               # iPhone: о платном ни слова
    assert await think.offer(OTHER) is None
    with pytest.raises(think.ThinkError, match="Капибара"):
        await think.solve(OTHER, [{"role": "user", "content": "?"}])
    await set_setting("ai_think", "off")                      # откат одной командой
    assert await think.offer(ME) is None and "выключено" in await think.status_line()


@pytest.mark.asyncio
async def test_day_budget_closes_for_everyone(db, monkeypatch, on):
    from database import set_setting
    from utils import today_msk
    await _plus(db)
    await set_setting(f"ai_think:{today_msk().isoformat()}", json.dumps({"n": {}, "cost": think.DAY_USD}))
    with pytest.raises(think.ThinkError, match="желающих"):
        await think.solve(ME, [{"role": "user", "content": "?"}])


@pytest.mark.asyncio
async def test_webapp_chat_button_and_think_request(db, client, monkeypatch, on):  # noqa: F811
    import ai_quota
    import ai_solver
    c, _ = client
    await _plus(db)

    async def fake_history(history, subject="", backend="gemini", lectures="", extra_system=""):
        return "ответ " + (gemini_solver.forced_model.get() or "ling")

    monkeypatch.setattr(ai_solver, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(ai_solver, "solve_with_history", fake_history)
    q = {"history": [{"role": "user", "content": "что такое NPV и зачем он нужен"}]}
    r = c.post("/api/chat", headers=_headers_for(ME), json=q).json()
    assert r["content"] == "ответ ling" and r["think"] == {"label": "Подумать ещё", "left": 2, "daily": 2}
    assert "think" not in c.post("/api/chat", headers={**_headers_for(ME), "X-App": "ios"}, json=q).json()

    asked = (await ai_quota.today()).get(ME, 0)
    r = c.post("/api/chat", headers=_headers_for(ME), json={**q, "think": True}).json()
    assert r["content"].startswith("ответ " + think.MODEL) and r["think"]["left"] == 1
    assert "<i>↪ «Подумать ещё» — ответил DeepSeek.</i>" in r["html"] and "_↪" not in r["html"]   # курсив, не «_»
    assert (await ai_quota.today()).get(ME, 0) == asked       # в обычный дневной счёт не идёт

    await db.upsert_user(OTHER, "", "u")
    r = c.post("/api/chat", headers=_headers_for(OTHER), json={**q, "think": True})
    assert r.status_code == 403
    r = c.post("/api/chat", headers={**_headers_for(ME), "X-App": "ios"}, json={**q, "think": True})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bot_button_under_answer_and_callback(db, dp, bot, monkeypatch, on):  # noqa: F811
    import handlers.solver as solver
    from tests.test_review_bot import UID
    await _plus(db, UID)
    asked = []

    async def fake_solve_text(text, subject="", backend="gemini", lectures=""):
        return "обычный ответ на вопрос про NPV"

    async def fake_think(uid, question, subject="", lectures="", context=""):
        asked.append(question)
        return "ответ подумав ещё"

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)
    monkeypatch.setattr(think, "solve", fake_think)
    await send(dp, bot, "что такое NPV и как его посчитать")
    marks = bot.session.named("EditMessageReplyMarkup")
    assert marks and marks[-1].reply_markup.inline_keyboard[0][0].callback_data == solver.THINK_CB
    assert "Подумать ещё · 2" in marks[-1].reply_markup.inline_keyboard[0][0].text

    await press(dp, bot, solver.THINK_CB)
    assert asked == [[{"role": "user", "content": "Задание:\nчто такое NPV и как его посчитать"}]]
    assert "ответ подумав ещё" in bot.session.texts()[-1]


@pytest.mark.asyncio
async def test_unlimited_grant_has_no_think_limit(db, monkeypatch, on):
    import plus_grant
    await db.upsert_user(OTHER, "", "u")
    await plus_grant.unlimited(OTHER, None, 1)                # /grant … unlimited
    assert (await think.offer(OTHER))["left"] is None         # кнопка без счётчика
    _openrouter(monkeypatch)
    for _ in range(think.DAILY + 1):
        await think.solve(OTHER, [{"role": "user", "content": "?"}])


@pytest.mark.asyncio
async def test_bot_no_button_when_none_left(db, dp, bot, monkeypatch, on):  # noqa: F811
    # робот 18.10: «Подумать ещё · 0» оставалась под ответом и нажималась
    import handlers.solver as solver
    from database import set_setting
    from tests.test_review_bot import UID
    from utils import today_msk
    await _plus(db, UID)
    await set_setting(f"ai_think:{today_msk().isoformat()}", json.dumps({"n": {str(UID): think.DAILY}}))

    async def fake_solve_text(text, subject="", backend="gemini", lectures=""):
        return "обычный ответ на вопрос про NPV"

    monkeypatch.setattr(solver, "solve_text", fake_solve_text)
    await send(dp, bot, "что такое NPV и как его посчитать")
    assert "обычный ответ" in bot.session.texts()[-1]
    assert not bot.session.named("EditMessageReplyMarkup")
