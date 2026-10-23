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
    assert "=== [1] Анализ данных: Лекция 2. Регрессия ===" in seen["lectures"] and "OSI" not in seen["lectures"]

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
    assert "левая сторона" in data["content"] and "ответил без лекций" in data["content"] and "Gemini" not in data["content"]

    async def down(*a, **kw):
        raise GeminiError("Gemini: лимит запросов исчерпан")

    monkeypatch.setattr("ai_solver.chat_with_reasoning", down)
    resp = client.post("/api/chat", json={"history": [{"role": "user", "content": "Привет"}]}, headers=headers)
    # без названия провайдера и кода — «Повторить» (Никита 21.10: «причём тут Gemini?»)
    detail = resp.json()["detail"]
    assert resp.status_code == 502 and "Gemini" not in detail and "Повторить" in detail


def test_typo_in_question_still_finds_lecture():
    # живой тест: «Дебит и кредит эт что?» — в лекциях «дебет»
    ctx = _ctx(("Лекция 1. Учёт", "Дебет и кредит — стороны счёта. " + "учёт " * 3000),
               ("Лекция 2. Налоги", "НДС и налог на прибыль. " + "налог " * 3000))
    out = lp.pick(ctx, "Дебит и кредит эт что?", lp.AUTO_BUDGET, lp.AUTO_MIN_SCORE)
    assert out.startswith("=== Лекция 1. Учёт ===") and "Лекция 2" not in out


def test_auto_mode_takes_lectures_of_one_subject():
    # живой тест: вопрос про оценку бизнеса без предмета — в «📖» оказались
    # «Практика 1» анализа данных и ПР по ООАиП, по паре общих слов
    ctx = _ctx(("ФХД: Лекция 5. Оценка стоимости бизнеса", "Стоимость бизнеса, мультипликаторы P/E, дисконтирование денежных потоков. " * 50),
               ("ФХД: Лекция 6. Рентабельность", "Рентабельность и стоимость капитала, денежные потоки. " * 50),
               ("Анализ данных: Практика 1", "Денежные потоки в таблице, стоимость ячейки. " * 50),
               ("ООАиП: ПР1", "Стоимость объекта класса, потоки ввода. " * 50))
    out = lp.pick(ctx, "как считать стоимость бизнеса через денежные потоки и мультипликаторы",
                  lp.AUTO_BUDGET, lp.AUTO_MIN_SCORE, True)
    assert "=== ФХД: Лекция 5" in out and "=== ФХД: Лекция 6" in out
    assert "Анализ данных" not in out and "ООАиП" not in out


def test_subject_scores_and_wants_course():
    ctx = _ctx(("Учет: Лекция 3. Баланс", "Баланс предприятия, актив и пассив. " * 20),
               ("ФХД: Лекция 3. Анализ баланса", "Анализ баланса предприятия, ликвидность. " * 20),
               ("ООАиП: Лекция 1", "Классы и объекты. " * 20))
    ranked = lp.subject_scores(ctx, "что было в лекции про баланс предприятия")
    assert {s for s, _ in ranked[:2]} == {"Учет", "ФХД"} and "ООАиП" not in dict(ranked)
    assert lp.wants_course("объясни 3 лекцию") and lp.wants_course("что препод говорил на паре")
    assert not lp.wants_course("что такое NPV")


@pytest.mark.asyncio
async def test_chat_asks_subject_when_lecture_question_is_ambiguous(db, monkeypatch):
    # вопрос явно про лекции, а подходят два предмета — не отвечаем наугад
    from fastapi.testclient import TestClient
    import ai_solver
    import webapp.server as server
    from database import add_file, save_file_text
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    for subj in ("Учет", "ФХД"):
        fid = await add_file("Лекция 3", subj, "TG" + subj, "l3.pdf", 0)
        await save_file_text(fid, "Баланс предприятия, актив и пассив. " * 20)

    async def no_ai(*a, **kw):
        raise AssertionError("должен переспросить предмет, а не звать ИИ")

    monkeypatch.setattr(ai_solver, "chat_with_reasoning", no_ai)
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c, headers = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    data = c.post("/api/chat", headers=headers, json={"history": [
        {"role": "user", "content": "объясни баланс предприятия из 3 лекции"}], "subject": ""}).json()
    assert sorted(data["choose"]) == ["Учет", "ФХД"]
