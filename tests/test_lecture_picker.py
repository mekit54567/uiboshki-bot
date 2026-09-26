"""
Подбор лекций под вопрос (lecture_picker). После выгрузки СДО у предмета
сотни тысяч символов лекций — целиком на каждый вопрос в чат их не шлём.
"""
import pytest

import lecture_picker as lp


def _ctx(*lectures):
    return "\n\n".join(f"=== {title} ===\n{text}" for title, text in lectures)


LECTURES = _ctx(
    ("Лекция 1. Введение", "Предмет курса, история анализа данных. " + "вода " * 2000),
    ("Лекция 2. Регрессия", "Линейная регрессия, метод наименьших квадратов, коэффициенты. " + "текст " * 2000),
    ("Лекция 3. Кластеризация", "Кластеризация: k-means, центроиды, расстояния. " + "слово " * 2000),
)


def test_short_context_goes_as_is():
    assert lp.pick("=== Л1 ===\nкоротко", "что угодно") == "=== Л1 ===\nкоротко"


def test_picks_matching_lectures_in_original_order():
    out = lp.pick(LECTURES, "Как считать коэффициенты линейной регрессии?", budget=15_000)
    assert "Лекция 2. Регрессия" in out and "Лекция 1" not in out
    both = lp.pick(LECTURES, "регрессия и кластеризация", budget=30_000)
    assert both.index("Лекция 2") < both.index("Лекция 3") and "Лекция 1" not in both


def test_no_match_falls_back_to_first_lectures():
    out = lp.pick(LECTURES, "привет", budget=15_000)
    assert out.startswith("=== Лекция 1. Введение ===") and "Лекция 3" not in out


def test_auto_mode_needs_a_real_match():
    assert lp.pick(LECTURES, "привет, что сдавать на этой неделе?", lp.AUTO_BUDGET, lp.AUTO_MIN_SCORE) == ""
    out = lp.pick(LECTURES, "объясни кластеризацию", lp.AUTO_BUDGET, lp.AUTO_MIN_SCORE)
    assert out.startswith("=== Лекция 3. Кластеризация ===") and "Лекция 2" not in out


@pytest.mark.asyncio
async def test_chat_without_subject_gets_matching_lectures(db, monkeypatch):
    from fastapi.testclient import TestClient

    import ai_solver
    import webapp.server as server
    from tests.test_webapp_auth import _make_init_data

    for i, (title, text) in enumerate([("Лекция 2. Регрессия", "Линейная регрессия, наименьшие квадраты."),
                                       ("Лекция 1. Сети", "Модель OSI, протоколы TCP и UDP.")]):
        fid = await db.add_file(title, ["Анализ данных", "Сети"][i], f"f{i}", f"{i}.pdf", 1)
        await db.save_file_text(fid, text)

    seen = {}

    async def fake_chat(history, subject="", extra_system="", lectures=""):
        seen["lectures"] = lectures
        return {"content": "ок", "reasoning": ""}

    async def no_context(user_id):
        return ""

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", fake_chat)
    monkeypatch.setattr("group_context.build_group_context", no_context)
    client = TestClient(server.app)
    headers = {"X-Telegram-Init-Data": _make_init_data()}

    client.post("/api/chat", json={"history": [{"role": "user", "content": "Что такое линейная регрессия?"}]},
                headers=headers)
    assert "=== Анализ данных: Лекция 2. Регрессия ===" in seen["lectures"] and "OSI" not in seen["lectures"]

    client.post("/api/chat", json={"history": [{"role": "user", "content": "Привет!"}]}, headers=headers)
    assert seen["lectures"] == ""


def test_junk_characters_are_stripped():
    assert lp.pick("=== Л1 ===\nтекст\x00 и \ud835 ещё", "текст") == "=== Л1 ===\nтекст и  ещё"


@pytest.mark.asyncio
async def test_chat_falls_back_without_lectures_and_says_why(db, monkeypatch):
    # живой тест: «Дебет и кредит — что это?» без предмета → «ИИ недоступен»
    from fastapi.testclient import TestClient

    import webapp.server as server
    from gemini_solver import GeminiError
    from tests.test_webapp_auth import _make_init_data

    fid = await db.add_file("Лекция 2. Дебет и кредит", "Учёт", "f", "l.pdf", 1)
    await db.save_file_text(fid, "Дебет и кредит — стороны счёта. Кредит справа, дебет слева.")
    calls = []

    async def flaky_chat(history, subject="", extra_system="", lectures=""):
        calls.append(bool(lectures))
        if lectures:
            raise GeminiError("Gemini не ответил вовремя — попробуй ещё раз")
        return {"content": "Дебет — левая сторона счёта.", "reasoning": ""}

    async def no_context(user_id):
        return ""

    monkeypatch.setattr("ai_solver.chat_with_reasoning", flaky_chat)
    monkeypatch.setattr("group_context.build_group_context", no_context)
    client = TestClient(server.app)
    headers = {"X-Telegram-Init-Data": _make_init_data()}
    data = client.post("/api/chat", json={"history": [{"role": "user", "content": "Дебет и кредит счёта — что это?"}]},
                       headers=headers).json()
    assert calls == [True, False]
    assert "левая сторона" in data["content"] and "ответ без лекций: Gemini не ответил вовремя" in data["content"]

    async def down(*a, **kw):
        raise GeminiError("Gemini: лимит запросов исчерпан")

    monkeypatch.setattr("ai_solver.chat_with_reasoning", down)
    resp = client.post("/api/chat", json={"history": [{"role": "user", "content": "Привет"}]}, headers=headers)
    assert resp.status_code == 502 and "лимит запросов исчерпан" in resp.json()["detail"]
