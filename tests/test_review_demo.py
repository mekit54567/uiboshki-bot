"""Демо-вход проверяющих App Store / RuStore (review_demo.py): код из
REVIEW_CODE → сессия демо-аккаунта, ответы — запись стенда со сдвигом на
текущую неделю, настоящие данные и обработчики не трогаются."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import review_demo
from utils import TZ

CODE = "kapibara-review-2026"


@pytest.fixture
def client(db, monkeypatch):
    import config
    import ratelimit
    import webapp.server as server
    monkeypatch.setattr(config, "REVIEW_CODE", CODE)
    ratelimit.reset()
    return TestClient(server.app, headers={"User-Agent": "Dart/3", "X-App": "ios"})


def _login(client) -> dict:
    r = client.post("/api/v1/auth/review", json={"code": CODE})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_code_login_and_flag(client):
    assert client.get("/api/auth/providers").json()["code"] is True
    assert client.post("/api/auth/review", json={"code": "не тот код"}).status_code == 403
    h = _login(client)
    assert h["Authorization"].startswith("Bearer rv.")
    me = client.get("/api/v1/me", headers=h).json()
    assert me["group"]["name"] == "УИБО-03-24"


def test_off_without_code(db, monkeypatch):
    import config
    import webapp.server as server
    monkeypatch.setattr(config, "REVIEW_CODE", "")
    c = TestClient(server.app)
    assert c.get("/api/auth/providers").json()["code"] is False
    assert c.post("/api/auth/review", json={"code": ""}).status_code == 404


def test_short_code_is_ignored(monkeypatch):
    import importlib

    import config
    monkeypatch.setenv("REVIEW_CODE", "123")
    try:
        assert importlib.reload(config).REVIEW_CODE == ""
    finally:
        monkeypatch.delenv("REVIEW_CODE")
        importlib.reload(config)


def test_attempts_are_limited(client):
    codes = [client.post("/api/auth/review", json={"code": f"x{i}"}).status_code for i in range(6)]
    assert codes[-1] == 429


def test_forged_rv_token_is_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer rv.fake"})
    assert r.status_code == 401


def test_delete_and_logout_keep_demo_account(client):
    h = _login(client)
    assert client.post("/api/me/delete", json={"confirm": True}, headers=h).json() == {"ok": True}
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 200      # тот же вход живёт дальше


def test_week_shift_keeps_weekdays():
    assert review_demo.shift_days(date(2026, 10, 8)) == 0
    assert review_demo.shift_days(date(2026, 11, 22)) == 42          # воскресенье — та же неделя
    assert review_demo.shift_days(date(2026, 11, 23)) == 49


def test_answers_follow_today():
    now = datetime(2026, 11, 24, 11, 0, tzinfo=TZ)                   # вторник, через 7 недель
    st, day = review_demo.answer("GET", "/api/day", "date=2026-11-27", b"", now)
    assert st == 200 and day["date"] == "2026-11-27" and day["label"] == "27 ноября"
    assert day["weekday"] == "Пятница" and day["lessons"]
    assert day["lessons"][0]["start_iso"].startswith("2026-11-27T")

    st, week = review_demo.answer("GET", "/api/week", "start=2026-11-23", b"", now)
    assert week["days"][0]["date"] == "2026-11-23" and week["week"] == 13

    today = review_demo.today_view(now)
    assert today["date"] == "2026-11-24" and today["weekday"] == "Вторник"
    assert today["now"].startswith("2026-11-24T11:00")
    assert all(x["status"] in ("now", "past", "later") for x in today["lessons"])
    soon = today["deadlines"]["soon"][0]
    assert soon["days"] == (date.fromisoformat(soon["due_date"]) - now.date()).days

    _, grades = review_demo.answer("GET", "/api/sdo/grades/18672", "", b"", now)
    text = str(grades)
    assert "15 октября 2026" not in text and "четверг, 3 декабря 2026" in text


def test_unknown_answers_like_fake_api():
    now = datetime(2026, 10, 8, 10, 0, tzinfo=TZ)
    assert review_demo.answer("GET", "/api/nothing", "", b"", now) == (200, {"ok": True})
    assert review_demo.answer("POST", "/api/sdo/submit", "", b"", now)[1]["status"]


def test_real_users_are_not_intercepted(client, monkeypatch):
    """Обычный вход (не rv.) идёт в настоящие обработчики."""
    r = client.get("/api/me", headers={"Authorization": "Bearer obychny-token"})
    assert r.status_code == 401 and "сессия" in r.json()["detail"]


# ── ИИ-чат демо: настоящая модель по демо-данным ─────────────────────────

@pytest.fixture
def model(monkeypatch):
    """Подменённая модель: запоминает историю и системный контекст, отвечает
    разным текстом на разные вопросы (со ссылкой [1], если есть лекции)."""
    import ai_solver
    import group_context
    import semantic_search
    calls = []

    async def fake(history, subject="", extra_system="", lectures=""):
        calls.append({"history": [dict(m) for m in history], "context": extra_system, "lectures": lectures})
        q = history[-1]["content"]
        return {"content": f"Ответ на «{q}»" + (" [1]" if lectures else ""), "reasoning": ""}

    async def forbidden(*a, **k):
        raise AssertionError("демо-чат не должен звать настоящие данные")
    monkeypatch.setattr(ai_solver, "chat_with_reasoning", fake)
    monkeypatch.setattr(group_context, "build_group_context", forbidden)
    monkeypatch.setattr(semantic_search, "search", forbidden)
    return calls


def _ask(client, h, *questions, **extra):
    history = []
    for q in questions:
        history.append({"role": "user", "content": q})
        r = client.post("/api/v1/chat", json={"history": history, **extra}, headers=h)
        if r.status_code != 200:
            return r
        history.append({"role": "assistant", "content": r.json()["content"]})
    return r


def test_demo_chat_asks_real_model(client, model):
    h = _login(client)
    fixture = review_demo.fixtures()["POST /api/chat"]
    a = _ask(client, h, "привет").json()
    b = _ask(client, h, "что у меня завтра?").json()
    assert a["html"] != b["html"] and fixture["html"] not in (a["html"], b["html"])
    assert set(a) >= {"content", "html", "reasoning"}
    assert [c["history"][-1]["content"] for c in model] == ["привет", "что у меня завтра?"]
    assert "sources" not in a                                   # болтовня — без лекций и плашек

    kpi = _ask(client, h, "привет", "чем метрика отличается от KPI?").json()
    assert len(model[-1]["history"]) == 3                       # история дошла до модели
    assert "Метрика — измеримый показатель" in model[-1]["lectures"]
    assert kpi["sources"] and kpi["sources"][0]["id"] == 4
    assert set(kpi["sources"][0]) == {"n", "id", "title", "page", "kind", "label"}
    page = client.get(f"/api/v1/files/4/page/{kpi['sources'][0]['page']}", headers=h).json()
    assert page["id"] == 4 and page["text"]


async def test_demo_context_from_fixtures_not_db(client, model):
    from database import add_deadline
    from utils import today_msk
    await add_deadline("Настоящий дедлайн из базы", "", today_msk().isoformat(), "23:59", 1)
    h = _login(client)
    assert _ask(client, h, "что сдавать?").status_code == 200
    ctx = model[-1]["context"]
    assert "Настоящий дедлайн" not in ctx
    assert "Моделирование бизнес-процессов" in ctx and "Баллы БРС" in ctx
    assert "Ближайшие дедлайны" in ctx or "дедлайнов на ближайшие" in ctx
    import ai_quota
    assert await ai_quota.today() == {}                         # счёт людей не тронут


def test_demo_chat_model_error_gives_fixture(client, monkeypatch):
    import ai_solver

    async def broken(*a, **k):
        raise RuntimeError("модель упала")
    monkeypatch.setattr(ai_solver, "chat_with_reasoning", broken)
    h = _login(client)
    r = _ask(client, h, "чем метрика отличается от KPI?")
    assert r.status_code == 200
    assert r.json()["html"] == review_demo.fixtures()["POST /api/chat"]["html"]


def test_demo_chat_limits_and_think(client, model, monkeypatch):
    import ratelimit
    h = _login(client)
    r = client.post("/api/chat", json={"history": [{"role": "user", "content": "x"}], "think": True}, headers=h)
    assert r.status_code == 403
    monkeypatch.setitem(ratelimit.LIMITS, "ai", (1000, 60))
    codes = [_ask(client, h, f"вопрос {i}").status_code for i in range(review_demo.DEMO_AI_DAILY + 1)]
    assert codes[:-1] == [200] * review_demo.DEMO_AI_DAILY and codes[-1] == 429
    detail = _ask(client, h, "ещё").json()["detail"]
    assert "кончились" in detail and "подписк" not in detail


def test_trial_text_on_ios_without_subscription():
    import ai_quota
    assert "подписк" in ai_quota.text("trial")
    assert "подписк" not in ai_quota.text("trial", app="ios")
    assert "подписк" not in ai_quota.text("trial", app="IOS")
