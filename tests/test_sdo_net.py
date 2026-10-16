"""Предохранитель СДО (16.10): СДО не пускает сервер — запросы к нему падают
сразу, а не висят по 30 с, пока приложение пишет «Сервер не отвечает»."""
import httpx
import pytest

import sdo_net


@pytest.fixture(autouse=True)
def _fresh():
    sdo_net.reset()
    yield
    sdo_net.reset()


def _patch(monkeypatch, handler):
    real = httpx.AsyncClient
    calls = []

    def h(req):
        calls.append(req.url.path)
        return handler(req)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(h), **kw))
    return calls


async def test_no_connect_then_fast_fail(monkeypatch):
    def down(req):
        raise httpx.ConnectTimeout("висит", request=req)

    calls = _patch(monkeypatch, down)
    async with sdo_net.client("c") as c:
        for _ in range(sdo_net.TRIP_AFTER):
            with pytest.raises(httpx.ConnectTimeout):
                await c.get("https://online-edu.mirea.ru/my/")
    assert sdo_net.is_down()
    async with sdo_net.client("c") as c:
        with pytest.raises(httpx.ConnectError):          # тот же тип, что ловят обработчики
            await c.get("https://online-edu.mirea.ru/grade/")
    assert calls == ["/my/"] * sdo_net.TRIP_AFTER         # потом в сеть уже не ходили


async def test_one_failure_does_not_trip(monkeypatch):
    """16.10 (Amvera): одна неудача на залпе запросов выключала СДО всем на 3 минуты."""
    n = {"i": 0}

    def flaky(req):
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ConnectTimeout("разок", request=req)
        return httpx.Response(200, text="ok")

    _patch(monkeypatch, flaky)
    async with sdo_net.client("c") as c:
        with pytest.raises(httpx.ConnectTimeout):
            await c.get("https://online-edu.mirea.ru/my/")
        assert not sdo_net.is_down()
        assert (await c.get("https://online-edu.mirea.ru/my/")).text == "ok"
    assert sdo_net._fails == 0                            # ответ сбросил счёт


async def test_parallel_limit(monkeypatch):
    import asyncio
    now = {"n": 0, "max": 0}
    real = httpx.AsyncClient

    async def h(req):
        now["n"] += 1
        now["max"] = max(now["max"], now["n"])
        await asyncio.sleep(0.01)
        now["n"] -= 1
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(h), **kw))
    async with sdo_net.client("c") as c:
        await asyncio.gather(*(c.get(f"https://online-edu.mirea.ru/{i}") for i in range(20)))
    assert now["max"] <= sdo_net.MAX_PARALLEL


async def test_works_when_up_and_after_window(monkeypatch):
    calls = _patch(monkeypatch, lambda req: httpx.Response(200, text="ok"))
    sdo_net.mark_down()
    monkeypatch.setattr(sdo_net, "_down_until", 0.0)     # окно прошло — снова пробуем
    async with sdo_net.client("c") as c:
        r = await c.get("https://online-edu.mirea.ru/my/")
    assert r.text == "ok" and calls == ["/my/"]
    assert not sdo_net.is_down()


async def test_http_error_does_not_trip(monkeypatch):
    _patch(monkeypatch, lambda req: httpx.Response(502, text="bad gateway"))
    async with sdo_net.client("c") as c:
        r = await c.get("https://online-edu.mirea.ru/my/")
    assert r.status_code == 502 and not sdo_net.is_down()


def test_connect_timeout_is_short():
    c = sdo_net.client("c", timeout=60)
    assert c.timeout.connect == sdo_net.CONNECT_TIMEOUT and c.timeout.read == 60
