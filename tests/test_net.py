"""
Исходящие соединения под переезд в Россию (net.py, net_check.py): без
переменных — всё как раньше; с OUT_PROXY — через прокси только Gemini,
OpenRouter и хосты из PROXY_HOSTS, МИРЭА — напрямую; Telegram — через
TG_PROXY / TELEGRAM_API_BASE; Gemini из страны без доступа — сразу запасная.
"""
import json

import httpx
import pytest

import gemini_solver
import net
import net_check


@pytest.fixture
def no_proxy_env(monkeypatch):
    for k in ("OUT_PROXY", "PROXY_HOSTS", "TG_PROXY", "TELEGRAM_API_BASE",
              "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(k, raising=False)     # системные прокси машины тестов — не наши


def test_without_env_everything_direct(no_proxy_env):
    assert not net.via_proxy("https://generativelanguage.googleapis.com/v1beta/models")
    assert net.tg_session() is None
    c = net.client(timeout=5)
    assert isinstance(c, httpx.AsyncClient) and not any(c._mounts.values())


def test_proxy_only_for_listed_hosts(no_proxy_env, monkeypatch):
    monkeypatch.setenv("OUT_PROXY", "http://user:secret@1.2.3.4:3128")
    assert net.via_proxy("https://generativelanguage.googleapis.com/v1beta/x")
    assert net.via_proxy("https://openrouter.ai/api/v1/chat/completions")
    assert not net.via_proxy("https://online-edu.mirea.ru/my/")
    assert not net.via_proxy("https://english.mirea.ru/schedule/api/ical/1/4928")
    assert not net.via_proxy("https://evilopenrouter.ai/")          # не поддомен
    monkeypatch.setenv("PROXY_HOSTS", "openrouter.ai, googleapis.com")
    assert net.via_proxy("https://fcm.googleapis.com/fcm/send")     # поддомен
    assert net.safe_proxy(net.out_proxy()) == "http://1.2.3.4:3128"  # без пароля


async def test_client_routes_through_proxy(no_proxy_env, monkeypatch):
    monkeypatch.setenv("OUT_PROXY", "http://1.2.3.4:3128")
    async with net.client(timeout=5) as c:
        def transport(url):
            return c._transport_for_url(httpx.URL(url))
        assert transport("https://generativelanguage.googleapis.com/x") is not c._transport
        assert transport("https://online-edu.mirea.ru/x") is c._transport
    # подменённый транспорт (тесты) — без прокси
    mock = httpx.MockTransport(lambda r: httpx.Response(200))
    async with net.client(transport=mock) as c:
        assert not any(c._mounts.values())


async def test_tg_session(no_proxy_env, monkeypatch):
    monkeypatch.setenv("OUT_PROXY", "socks5://1.2.3.4:1080")
    s = net.tg_session()
    assert s.proxy == "socks5://1.2.3.4:1080"
    await s.close()
    monkeypatch.setenv("TG_PROXY", "http://5.6.7.8:3128")
    monkeypatch.setenv("TELEGRAM_API_BASE", "https://tg.example.ru/")
    s = net.tg_session()
    assert s.proxy == "http://5.6.7.8:3128"
    assert s.api.api_url("T", "getMe") == "https://tg.example.ru/botT/getMe"
    await s.close()


async def test_gemini_geoblock_goes_to_spare(monkeypatch):
    """Из России Gemini отвечает 400 «User location is not supported» — не
    перебираем все модели Gemini, а сразу отвечает запасная через OpenRouter."""
    calls = []

    def handler(request):
        if request.url.host == "openrouter.ai":
            calls.append("ling")
            return httpx.Response(200, json={"choices": [{"message": {"content": "ответ Ling"}}]})
        calls.append(request.url.path.split("/models/")[1].split(":")[0])
        return httpx.Response(400, json={"error": {"code": 400, "status": "FAILED_PRECONDITION",
                                                   "message": "User location is not supported for the API use."}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(gemini_solver, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini_solver, "GEMINI_MODEL", "main")
    monkeypatch.setattr(gemini_solver, "GEMINI_FALLBACK_MODELS", ["spare"])
    monkeypatch.setattr(gemini_solver, "OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(gemini_solver, "AI_SPARE_MODEL", "inclusionai/ling-3.0-flash-vl")
    assert await gemini_solver.generate_text([{"role": "user", "content": "?"}], "s") == "ответ Ling"
    assert calls == ["main", "ling"]

    monkeypatch.setattr(gemini_solver, "AI_SPARE_MODEL", "")      # без запасной — понятный текст
    with pytest.raises(gemini_solver.GeminiError, match="прокси"):
        await gemini_solver.generate_text([{"role": "user", "content": "?"}], "s")


async def test_netcheck_report(no_proxy_env, monkeypatch):
    def handler(request):
        host = request.url.host
        if host == "ipinfo.io":
            return httpx.Response(200, json={"ip": "203.0.113.5", "country": "US"})
        if host == "generativelanguage.googleapis.com":
            body = json.loads(request.content)
            assert body["contents"][0]["parts"][0]["text"] == "проверка"
            return httpx.Response(400, json={"error": {"message": "User location is not supported for the API use."}})
        if host == "schedule-of.mirea.ru":
            raise httpx.ConnectTimeout("timeout")
        return httpx.Response(200, text="ok")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, **{**kw, "transport": httpx.MockTransport(handler)}))

    class FakeBot:
        async def get_me(self):
            return {"id": 1}

    rep = await net_check.check(FakeBot())
    by = {r["name"]: r for r in rep["results"]}
    assert by["Telegram"]["ok"] and by["Telegram"]["route"] == "напрямую"
    assert not by["Gemini"]["ok"] and "страну" in by["Gemini"]["why"]
    assert not by["Расписание (официальное)"]["ok"]
    assert by["СДО"]["ok"] and by["СДО"]["route"] == "напрямую"
    text = net_check.text(rep)
    assert "203.0.113.5 (US)" in text and "Прокси не задан" in text and "🔴 Gemini" in text
