"""Выбор модели ИИ (ai_bench.py, /aitest): список моделей у OpenRouter,
бюджет, автопроверки, судья, таблица «балл · цена», слепое голосование и
подписанные ссылки на страницы."""
import base64
import json
import re

import pytest
from fastapi.testclient import TestClient

import ai_bench


def _m(mid, pin, pout, ctx=128_000, image=False, out=("text",)):
    """Модель в формате /api/v1/models; цены — $ за 1 млн токенов."""
    return {"id": mid, "name": f"Vendor: {mid.split('/')[-1]}", "context_length": ctx,
            "pricing": {"prompt": str(pin / 1e6), "completion": str(pout / 1e6)},
            "architecture": {"input_modalities": ["text"] + (["image"] if image else []),
                             "output_modalities": list(out)}}


CATALOG = {"data": [
    _m("google/gemini-3.1-flash-lite-preview", 0.25, 1.5, image=True),   # закрыта аккаунту (регион)
    _m("openai/gpt-oss-120b", 0.04, 0.17), _m("anthropic/claude-haiku-5.5", 0.1, 0.5),
    _m("qwen/qwen3.7-flash", 0.03, 0.13),
    _m("deepseek/deepseek-v4.1-flash-0901", 0.3, 1.2),                  # кандидат — по началу id
    _m("deepseek/deepseek-v4-pro", 0.4, 1.2),                           # судья
    _m("cheap/a", 0.01, 0.02), _m("cheap/b", 0.02, 0.04), _m("cheap/c", 0.03, 0.05), _m("cheap/d", 0.04, 0.06),
    _m("mid/x", 0.2, 0.8), _m("dear/y", 2.0, 8.0),                      # дороже потолка входа
    _m("free/z:free", 0, 0), _m("cheap/a:batch", 0.005, 0.01), _m("~cheap/latest", 0.01, 0.02),
    _m("small/ctx", 0.01, 0.01, ctx=8000), _m("img/gen", 0.01, 0.01, out=("image",)),
    _m("router/auto", -1, -1),
]}


def test_pick_takes_candidates_and_cheap_spread_skipping_odd_and_closed(monkeypatch):
    models = ai_bench.parse_models(CATALOG)
    got = ai_bench.pick(models, limit=6)
    assert got[:2] == ["qwen/qwen3.7-flash", "deepseek/deepseek-v4.1-flash-0901"]     # PINNED первыми
    assert len(got) == 6 and "dear/y" not in got
    assert not any(i.split("/")[0] in ("google", "openai", "anthropic") for i in got)  # закрыты аккаунту
    assert not any(":" in i or i.startswith("~") or i in ("small/ctx", "img/gen", "router/auto") for i in got)
    assert sum(i.startswith("cheap/") for i in got) <= ai_bench.PER_VENDOR             # не больше трёх от одного
    assert "mid/x" in got                                                               # и не только самые дешёвые
    assert models["qwen/qwen3.7-flash"]["name"] == "qwen3.7-flash"


def test_fit_budget_drops_most_expensive_but_keeps_pinned():
    models = ai_bench.parse_models(CATALOG)
    tasks = [{"kind": "Вопрос", "system": "", "user": "x" * 30_000, "out": 700, "judge_context": "x" * 30_000}]
    ids = ["deepseek/deepseek-v4.1-flash-0901", "cheap/a", "mid/x"]
    kept, dropped, cost = ai_bench.fit_budget(ids, models, tasks, models["deepseek/deepseek-v4-pro"], 0.011)
    assert dropped == ["mid/x"] and kept == ["deepseek/deepseek-v4.1-flash-0901", "cheap/a"]
    kept, dropped, _ = ai_bench.fit_budget(ids, models, tasks, None, 0)
    assert kept == ["deepseek/deepseek-v4.1-flash-0901"]                              # кандидат из плана — всегда


def test_checks_catch_rule_breaks():
    assert ai_bench.checks("x² + √y [1] по лекции [2]", "Вопрос", 3) == []
    assert ai_bench.checks("Ответ по формуле дроби $\\frac{a}{b}$ [7]", "Вопрос", 3) == ["LaTeX", "выдуманные [n]"]
    assert ai_bench.checks("# Итог\nответ без ссылок", "Вопрос", 2) == ["заголовки #", "без ссылок [n]"]
    assert ai_bench.checks("The answer is simple and clear", "Конспект") == ["не по-русски"]
    assert ai_bench.checks("Вот код:\n```python\nprint('hello world from python')\n```", "Вопрос") == []


def test_parse_scores_tolerates_noise():
    assert ai_bench.parse_scores('Итог: ```json\n{"A": 8, "b": "6", "C": 15, "Z": 3}\n```', "ABC") == \
        {"A": 8, "B": 6, "C": 10}
    assert ai_bench.parse_scores("не знаю", "AB") == {}


def test_table_scores_errors_as_zero_and_marks_pareto():
    def ans(score, cost, error=False, intent=None):
        return {"score": score, "cost": cost, "secs": 2.0, "error": error, "flags": [], "intent": intent}
    tasks = [
        {"kind": "Вопрос", "answers": {"a/good": ans(9, 0.001), "b/cheap": ans(7, 0.0001), "c/bad": ans(6, 0.002)}},
        {"kind": "Вопрос", "answers": {"a/good": ans(9, 0.001), "b/cheap": ans(None, 0, error=True),
                                        "c/bad": ans(6, 0.002)}},
        {"kind": "Намерение", "want": "files", "answers": {"a/good": ans(None, 0, intent="files"),
                                                            "b/cheap": ans(None, 0, intent="none"),
                                                            "c/bad": ans(None, 0, intent="files")}},
    ]
    rows = {r["id"]: r for r in ai_bench.table(tasks, ["a/good", "b/cheap", "c/bad"], {})}
    assert rows["b/cheap"]["q_score"] == 3.5 and rows["b/cheap"]["errors"] == 1        # ошибка — 0 баллов
    assert rows["a/good"]["q_rub"] == 85.0 and rows["a/good"]["intent"] == 100
    assert rows["a/good"]["star"] and rows["b/cheap"]["star"] and not rows["c/bad"]["star"]


@pytest.fixture
async def group_data(db):
    from database._conn import connect
    async with connect() as c:
        await c.execute("INSERT INTO solver_history (user_id, task_text, answer, subject) VALUES "
                        "(1, 'Как считать NPV инвестиционного проекта?', 'x', 'Финансы')")
        await c.commit()
    fid = await db.add_file("Лекция 1", "Финансы", "tg", "l1.pdf", 1)
    await db.save_file_text(fid, "Дисконтирование денежных потоков. " * 400)


def _fake_openrouter(monkeypatch, calls, judge_calls, left=5.0):
    async def fake_get(client, key, path):
        assert path == "/models"
        return CATALOG

    async def fake_balance(client, key):
        return left

    async def fake_ask(client, key, model, system, user, max_tokens, temperature=None):
        if system == ai_bench.JUDGE_SYSTEM:
            judge_calls.append(user)
            letters = re.findall(r"=== Ответ ([A-H]) ===", user)
            return {"text": json.dumps({x: 8 if "qwen" in user.split(f"Ответ {x} ===")[1][:40] else 5
                                        for x in letters}), "cost": 0.01, "secs": 1, "error": False}
        calls.append(model)
        import intent_router
        text = "files" if system == intent_router.SYSTEM_PROMPT else f"ответ {model} по лекции"
        return {"text": text, "cost": 0.001, "secs": 0.5, "error": False}

    monkeypatch.setattr(ai_bench, "SAMPLE_QUESTIONS", [])                   # только вопрос из истории
    monkeypatch.setattr(ai_bench, "_get", fake_get)
    monkeypatch.setattr(ai_bench, "balance", fake_balance)
    monkeypatch.setattr(ai_bench, "ask", fake_ask)


async def test_screen_on_group_data(group_data, monkeypatch):
    calls, judge_calls = [], []
    _fake_openrouter(monkeypatch, calls, judge_calls)
    plan = await ai_bench.prepare("k", ["qwen/qwen3.7-flash", "cheap/a", "нет/такой"])
    assert plan["ids"] == ["qwen/qwen3.7-flash", "cheap/a"] and plan["judge"] == "deepseek/deepseek-v4-pro"
    assert "Нет у OpenRouter или закрыто аккаунту: нет/такой" in plan["text"] and "на счёте $5.00" in plan["text"]
    html, summary = await ai_bench.screen("k", plan)
    n_tasks = 2 + len(ai_bench.INTENT_CASES)                                 # вопрос, конспект, намерения
    assert len(calls) == 2 * n_tasks and len(judge_calls) == 2               # судья — по разу на вопрос и конспект
    assert "Отбор готов: 2 моделей" in summary and "qwen3.7-flash (8.0" in summary
    assert "★ qwen3.7-flash" in html and "qwen/qwen3.7-flash" in html and "ответ cheap/a по лекции" in html
    assert "нужно schedule_today" in html                                    # ошибки классификатора — списком
    await ai_bench.save(html, "report")
    assert await ai_bench.load("report") == html and await ai_bench.load("vote") is None
    text = ai_bench.report_text(html, cut=10)                                # коротко — для Claude по ссылке
    assert "<" not in text and "★ qwen3.7-flash | 8.0" in text and "нужно schedule_today" in text
    assert "ответ chea…" in text and "ответ cheap/a по лекции" not in text    # ответы — началом
    text = ai_bench.report_text(html, cut=10, full="QWEN3.7")                # одну модель — целиком
    assert "ответ qwen/qwen3.7-flash по лекции" in text and "ответ cheap/a по лекции" not in text


async def test_budget_follows_account_balance(group_data, monkeypatch):
    _fake_openrouter(monkeypatch, [], [], left=0.0)
    plan = await ai_bench.prepare("k")
    assert plan["ids"] == ["qwen/qwen3.7-flash", "deepseek/deepseek-v4.1-flash-0901"]   # остались только PINNED
    assert "Не влезли в бюджет $0.00" in plan["text"]


async def test_vote_hides_models_until_reveal(group_data, monkeypatch):
    calls = []
    _fake_openrouter(monkeypatch, calls, [])
    plan = await ai_bench.prepare("k", ["qwen/qwen3.7-flash", "cheap/a"], intents=False)
    html, summary = await ai_bench.vote("k", plan)
    assert len(calls) == 4 and "1 вопросов и 1 конспектов × 2 модели" in summary
    visible = re.sub(r'atob\("[^"]+"\)|<div class="t">.*?</div>', "", html)
    assert "qwen3.7-flash" not in visible and "Ответ 2" in html             # имён моделей не видно
    secret = json.loads(base64.b64decode(re.search(r'atob\("([^"]+)"\)', html).group(1)))
    assert set(secret["names"]) == {"qwen/qwen3.7-flash", "cheap/a"}          # ключ — для «Показать модели»
    assert plan["key"] == secret and len(secret["blocks"]) == 2               # тот же ключ — серверу


async def test_vote_picks_live_on_server(db, monkeypatch):
    """Выбор в слепом тесте — на сервере по той же подписанной ссылке (на
    iPhone копировать итог неудобно), итог текстом — &view=result для Claude."""
    import webapp.server as server
    from webapp import deps
    from webapp.routes import aitest
    monkeypatch.setattr(deps, "BOT_TOKEN", "123:abc")
    monkeypatch.setattr(deps, "WEBAPP_URL", "https://www.uiboshki.ru")
    items = [{"kind": k, "title": f"задача {k}", "subject": "БД", "answers": [
        {"text": "ответ", "model": m, "cost": 0.001, "secs": 2.0} for m in ("a/x", "b/y")]}
        for k in ("Вопрос", "Конспект")]
    key = ai_bench.vote_key(items, {"a/x": "Икс", "b/y": "Игрек"})
    await ai_bench.save(ai_bench.page(items, key["names"]), "vote", key)
    q = aitest.link("vote").split("uiboshki.ru/aitest")[1]
    c = TestClient(server.app)
    assert c.get("/aitest/pick" + q).json() == {"picks": {}}
    assert c.post("/aitest/pick" + q, json={"i": 0, "j": 1}).json() == {"picks": {"0": 1}}
    assert c.post("/aitest/pick" + q, json={"i": 1, "j": 0}).json() == {"picks": {"0": 1, "1": 0}}
    assert c.post("/aitest/pick" + q, json={"i": 1, "j": -1}).json() == {"picks": {"0": 1}}   # снять
    assert c.post("/aitest/pick" + q, json={"i": 5, "j": 0}).status_code == 400
    assert c.post("/aitest/pick" + q, json={"i": 0, "j": 2}).status_code == 400
    assert c.post("/aitest/pick" + q.replace("sig=", "sig=0"), json={"i": 0, "j": 0}).status_code == 404
    report_q = aitest.link("report").split("uiboshki.ru/aitest")[1]
    assert c.post("/aitest/pick" + report_q, json={"i": 0, "j": 0}).status_code == 404     # подпись отбора не годится
    r = c.get("/aitest" + q + "&view=result")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "выбрано 1 из 2" in r.text and "Игрек (b/y): побед 1 (вопрос 1, конспект 0)" in r.text
    assert "1. Вопрос · БД · задача Вопрос → Игрек" in r.text and "2. Конспект · БД · задача Конспект → не выбран" in r.text
    assert "Слепой тест ИИ" in c.get("/aitest" + q).text                     # без view — сама страница
    await ai_bench.save("<body><h1>Отбор</h1><div class=\"t\">длинный ответ</div></div></body>", "report")
    text = c.get("/aitest" + report_q + "&view=text")
    assert text.headers["content-type"].startswith("text/plain") and text.text == "Отбор\nдлинный ответ\n"
    await ai_bench.save(ai_bench.page(items, key["names"]), "vote", key)
    assert c.get("/aitest/pick" + q).json() == {"picks": {}}                 # новый тест — выбор с нуля


async def test_page_links_are_signed_per_kind(db, monkeypatch):
    import webapp.server as server
    from webapp import deps
    from webapp.routes import aitest
    monkeypatch.setattr(deps, "BOT_TOKEN", "123:abc")
    monkeypatch.setattr(deps, "WEBAPP_URL", "https://www.uiboshki.ru")
    path = aitest.link("report").split("uiboshki.ru")[1]
    assert path.startswith("/aitest?k=report&exp=")
    c = TestClient(server.app)
    assert c.get(path).status_code == 404                                     # страницы ещё нет
    await ai_bench.save("<p>отбор</p>", "report")
    r = c.get(path)
    assert r.status_code == 200 and "отбор" in r.text and r.headers["cache-control"] == "no-store"
    assert c.get(path.replace("sig=", "sig=0")).status_code == 404            # чужая подпись
    assert c.get(path.replace("k=report", "k=vote")).status_code == 404       # подпись — на свою страницу
    assert c.get("/aitest").status_code == 404


async def test_current_gemini_joins_by_own_key(group_data, monkeypatch):
    """OpenRouter закрывает аккаунту Google — нынешняя Gemini идёт в отбор своим
    ключом, бесплатно; обрыв по лимиту токенов отмечается."""
    import config
    import gemini_solver
    calls, gemini_calls = [], []
    _fake_openrouter(monkeypatch, calls, [])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g")

    async def fake_generate(history, system, **kw):
        gemini_calls.append(kw)
        return "ответ Gemini [1]" + gemini_solver.TRUNCATED_NOTE

    monkeypatch.setattr(gemini_solver, "generate_text", fake_generate)
    plan = await ai_bench.prepare("k")
    assert plan["ids"][0] == ai_bench.GEMINI_DIRECT
    plan["ids"] = plan["ids"][:2]
    html, _ = await ai_bench.screen("k", plan)
    assert len(gemini_calls) == len(plan["tasks"]) and gemini_calls[-1]["temperature"] == 0  # намерения — без фантазии
    assert all(kw["fallback"] is False for kw in gemini_calls)               # мерка — сама Gemini, не Ling
    assert "наш ключ, бесплатно · сейчас у нас" in html and "обрыв" in html
    assert "ответ Gemini [1]" in html and "ответ обрезан" not in html


async def test_questions_skip_photos_and_fill_with_samples(db, monkeypatch):
    """Чат WebApp вопросы не хранит, а в истории решалки их мало — добираем
    примерами; задачи с фото (в истории только подпись) не берём."""
    from database._conn import connect
    async with connect() as c:
        await c.executemany("INSERT INTO solver_history (user_id, task_text, answer, subject) VALUES (1, ?, 'x', ?)",
                            [("[фото] реши задачу с картинки", "Математика"),
                             ("Как считать NPV инвестиционного проекта?", "Финансы")])
        await c.commit()
    monkeypatch.setattr(ai_bench, "QUESTIONS", 4)
    got = await ai_bench._questions()
    assert got[0] == ("Как считать NPV инвестиционного проекта?", "Финансы")
    assert [q for q, _ in got[1:]] == ai_bench.SAMPLE_QUESTIONS[:3]
    assert not any(q.startswith("[фото]") for q, _ in got)


async def test_lectures_one_per_subject_preferring_lectures(db):
    """Первый отбор взял последние 300 файлов — все одного предмета, конспект
    вышел один. Теперь — по предмету на лекцию, сначала файлы типа «лекция»."""
    text = "Текст лекции про учёт и анализ. " * 300
    old = await db.add_file("Лекция 1", "Анализ данных", "tg1", "a.pdf", 1, category="lecture")
    await db.save_file_text(old, text)
    for i in range(3):
        fid = await db.add_file(f"Доп {i}", "Учёт", f"tg{i + 2}", f"u{i}.pdf", 1, category="other")
        await db.save_file_text(fid, text)
    lec = await db.add_file("Лекция 2", "Учёт", "tg9", "u.pdf", 1, category="lecture")
    await db.save_file_text(lec, text)
    got = await ai_bench._lectures(4)
    assert sorted((x["subject"], x["title"]) for x in got) == [("Анализ данных", "Лекция 1"), ("Учёт", "Лекция 2")]


def test_pareto_ignores_free_baseline():
    rows = [{"id": ai_bench.GEMINI_DIRECT, "q_score": 10, "q_rub": 0.0},
            {"id": "a/cheap", "q_score": 8, "q_rub": 3.0}, {"id": "b/dear", "q_score": 7, "q_rub": 9.0}]
    assert ai_bench.pareto(rows) == {"a/cheap"}


async def test_judge_retries_unparsed_answer(monkeypatch):
    replies = iter(["думаю…", '{"A": 7}'])

    async def fake_ask(client, key, model, system, user, max_tokens, temperature=None):
        return {"text": next(replies), "cost": 0.01, "secs": 1, "error": False}

    monkeypatch.setattr(ai_bench, "ask", fake_ask)
    task = {"judge_context": "Вопрос: x"}
    got = await ai_bench.judge_task(None, "k", "j", task, {"m/one": {"text": "ответ", "error": False}})
    assert got == {"m/one": 7} and task["judge_cost"] == 0.02


async def test_gemini_retries_on_limit(monkeypatch):
    import gemini_solver
    calls = []

    async def flaky(history, system, **kw):
        calls.append(1)
        if len(calls) < 3:
            raise gemini_solver.GeminiError("Лимит запросов (HTTP 429)")
        return "ответ"

    monkeypatch.setattr(gemini_solver, "generate_text", flaky)
    monkeypatch.setattr(ai_bench, "GEMINI_WAIT", 0)
    res = await ai_bench.ask_gemini("s", "u", 100)
    assert res["text"] == "ответ" and not res["error"] and len(calls) == 3
