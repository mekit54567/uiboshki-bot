"""Сайт-презентация /about (webapp/routes/site.py): страница, приложение в
демо-режиме (без SDK Telegram, на записанных тестовых данных) и живой поиск
расписания МИРЭА без входа — с ограничением частоты по IP."""
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SITE = Path(__file__).parent.parent / "webapp" / "static" / "site"


def _client():
    import webapp.server as server
    return TestClient(server.app)


def test_about_page_and_demo():
    c = _client()
    r = c.get("/about")
    assert r.status_code == 200 and "Капибара" in r.text and "Его сделали студенты, а не университет" in r.text and "__BOT__" not in r.text and 'src="/about/demo"' in r.text
    # стили и скрипт — с меткой версии (кэш на год, после обновления — новая ссылка)
    import re as _re
    for rel in ("site/site.css", "site/site.js"):
        m = _re.search(rf'"/({rel}\?v=\w+)"', r.text)
        assert m, rel
        assert "immutable" in c.get("/" + m.group(1)).headers["cache-control"]
    # превью ссылки в Telegram — абсолютный адрес картинки, сама картинка есть
    assert '<meta property="og:image" content="http' in r.text and "__BASE__" not in r.text
    assert c.get("/site/og.jpg").content[:3] == b"\xff\xd8\xff"
    # демо — само приложение (веб-сборка Flutter, Никита 19.10): заглушка
    # demo-app.js — первым скриптом, до base href и запуска Flutter
    import webapp.server as server
    if (server.FLUTTER_DIR / "index.html").is_file():
        app_demo = c.get("/about/demo").text
        assert "/site/demo-app.js?v=" in app_demo and "flutter_bootstrap.js" in app_demo
        assert app_demo.index("demo-app.js") < app_demo.index("<base") < app_demo.index("<script>")
    demo = c.get("/about/demo/tg").text
    assert '<base href="/">' in demo and "site/demo.js?v=" in demo
    assert "telegram.org/js/telegram-web-app.js" not in demo                 # без настоящего SDK
    assert demo.index("site/demo.js") < demo.index("js/core.js")              # заглушка — до приложения
    for f in ("site/site.css", "site/site.js", "site/demo.js", "site/demo-app.js", "site/demo.json", "site/capy.svg",
              "site/fonts/serif-cyrillic.woff2", "site/fonts/sans-latin.woff2"):
        assert c.get("/" + f).status_code == 200, f
    # всё, что ищет site.js по id, есть на странице; шрифты — из /site/fonts
    import re
    js = c.get("/site/site.js").text
    for el in set(re.findall(r'\$\("([\w-]+)"\)', js)):
        assert f'id="{el}"' in r.text, el
    css = c.get("/site/site.css").text
    assert "/assets/" not in css and css.count("url('/site/fonts/") == 4


def test_site_scripts_parse_and_demo_data_is_complete():
    for f in ("site.js", "demo.js", "demo-app.js"):
        subprocess.run(["node", "--check", str(SITE / f)], check=True)
    # демо приложения: вход «demo» — только в своём localStorage в памяти (сайт и
    # PWA /app — один адрес: настоящий вход в /app демо трогать не должно),
    # без service worker; запросы приложения идут на /api/v1/…
    app_demo = (SITE / "demo-app.js").read_text(encoding="utf-8")
    assert 'Object.defineProperty(window, "localStorage"' in app_demo
    assert "serviceWorker.register = " in app_demo and "/api\\/v1\\/" in app_demo
    # iOS: в iframe прокручивается body внутри экрана фиксированной высоты, а не
    # окно — иначе на коротком дне нижняя панель уезжала вверх (живой тест 04.10)
    demo = (SITE / "demo.js").read_text(encoding="utf-8")
    assert "html{height:100%;overflow:hidden}" in demo and "body{height:100%;overflow-y:auto" in demo
    assert "window.scrollTo = function" in demo and '"scrollY"' in demo
    fx = json.loads((SITE / "demo.json").read_text(encoding="utf-8"))["fx"]
    # то, что приложение спрашивает при открытии, есть в записи
    for key in ("GET /api/me", "GET /api/today", "GET /api/deadlines", "GET /api/files", "GET /api/sdo/grades",
                "GET /api/sdo/status", "POST /api/chat"):
        assert key in fx, key
    assert fx["GET /api/optional"]["pending"] == []                           # без вопроса про военку поверх главной
    course = fx["GET /api/sdo/grades"]["courses"][0]["id"]
    assert fx[f"GET /api/sdo/grades/{course}"]["goal"]["tk"]
    # ссылки на картинки слайдов из ответа ИИ — существуют
    for k, v in fx.items():
        if k.startswith("GET /api/files/") and "/page/" in k:
            assert (SITE.parent / v["image"]).exists(), v["image"]


@pytest.mark.asyncio
async def test_public_search_and_target(db, monkeypatch):
    import ratelimit
    import schedule_index
    import webapp.routes.schedule as sched

    async def search(q, types, limit=30):
        return [{"id": 4928, "title": "УИБО-03-24", "type": 1}]

    async def ready():
        return True

    async def target(target_type, target_id, user):
        assert user == {"id": 0}
        return {"type": 1, "id": 4928, "title": "УИБО-03-24", "pinned": False, "today": "2026-10-08",
                "weeks": [{"days": []}] * 8, "stale": None}

    async def title(t, i):
        return "УИБО-03-24" if (t, i) == (1, 4928) else None

    monkeypatch.setattr(schedule_index, "search", search)
    monkeypatch.setattr(schedule_index, "get_title", title)
    monkeypatch.setattr(schedule_index, "is_ready", ready)
    monkeypatch.setattr(sched, "api_target", target)
    ratelimit.reset()
    c = _client()
    r = c.get("/about/api/search?q=УИБО")
    assert r.status_code == 200 and r.json()["items"][0]["id"] == 4928      # без initData
    t = c.get("/about/api/target/1/4928").json()
    assert "pinned" not in t and len(t["weeks"]) == 2
    codes = [c.get("/about/api/target/1/4928", headers={"X-Forwarded-For": "1.2.3.4"}).status_code for _ in range(16)]
    assert codes[:15] == [200] * 15 and codes[15] == 429                       # по IP
    assert c.get("/about/api/target/1/4928", headers={"X-Forwarded-For": "5.6.7.8"}).status_code == 200
    # начало X-Forwarded-For подставляет посетитель — лимит по адресу, который дописал прокси
    ratelimit.reset()
    codes = [c.get("/about/api/target/1/4928", headers={"X-Forwarded-For": f"8.8.{i}.1, 1.2.3.4, 10.0.0.7"}).status_code
             for i in range(16)]
    assert codes[15] == 429
    # и на всех посетителей вместе — потолок
    ratelimit.reset()
    monkeypatch.setitem(ratelimit.LIMITS, "site_all", (3, 60))
    codes = [c.get("/about/api/search?q=УИБО", headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(4)]
    assert codes == [200, 200, 200, 429]
    # отбитые лимитом одного адреса запросы общий потолок не тратят
    ratelimit.reset()
    monkeypatch.setitem(ratelimit.LIMITS, "site_all", (17, 60))   # 15 по IP + 1 — при старом порядке было бы 19
    for _ in range(19):
        c.get("/about/api/target/1/4928", headers={"X-Forwarded-For": "7.7.7.7"})
    assert c.get("/about/api/search?q=УИБО", headers={"X-Forwarded-For": "6.6.6.6"}).status_code == 200
    # случайный id — не в справочнике: 404 без похода в МИРЭА
    ratelimit.reset()
    assert c.get("/about/api/target/1/99999").status_code == 404
    # справочник ещё не собран — поиск шёл запасным официальным: его результат открывается

    async def not_ready():
        return False

    monkeypatch.setattr(schedule_index, "is_ready", not_ready)
    assert c.get("/about/api/target/1/99999").status_code == 200
    ratelimit.reset()


def test_site_dark_theme_is_fresh():
    """Тёмная тема сайта — генерируется из светлой (tools/site_dark.py). Поменял
    стили — запусти скрипт, иначе тёмная тема разойдётся со светлой."""
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("site_dark", root / "tools" / "site_dark.py")
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)
    css = sd.CSS.read_text(encoding="utf-8")
    light = css[:css.index(sd.START)].rstrip() + "\n"
    assert sd.build(light) in css, "запусти python tools/site_dark.py"
    assert "white-space" not in sd.build(light)                  # не цвет
    assert sd.flip("#f8f6f0") < "#3" and sd.flip("#282720") > "#c"   # бумага темнеет, чернила светлеют


def test_root_has_site_link_preview(monkeypatch):
    """Ссылка www.uiboshki.ru в Telegram — превью сайта, а не пустое приложение:
    бот превью не выполняет JS-переход на /about, теги нужны на самом корне."""
    import webapp.deps as deps
    monkeypatch.setattr(deps, "WEBAPP_URL", "https://www.uiboshki.ru")
    r = _client().get("/")
    assert r.status_code == 200 and "js/core.js" in r.text                    # это всё ещё приложение
    assert '<meta property="og:image" content="https://www.uiboshki.ru/site/og.jpg?v=' in r.text and "__OGV__" not in r.text
    assert '<meta property="og:url" content="https://www.uiboshki.ru/about">' in r.text
    assert "__BASE__" not in r.text and r.text.index("og:title") < r.text.index("</head>")


def test_app_has_site_link_preview(monkeypatch):
    """Ссылка uiboshki.ru/app из /help — превью Капибары, а не старое «УИБО-бот»:
    у /app своих og-тегов не было, Telegram держал давнее превью (Никита 20.10)."""
    import webapp.deps as deps
    monkeypatch.setattr(deps, "WEBAPP_URL", "https://www.uiboshki.ru")
    r = _client().get("/app")
    assert r.status_code == 200
    assert '<meta property="og:title" content="Капибара' in r.text
    assert '<meta property="og:image" content="https://www.uiboshki.ru/site/og.jpg?v=' in r.text
    assert '<meta property="og:url" content="https://www.uiboshki.ru/app">' in r.text
    assert r.text.count('<meta name="description"') == 1 and "__BASE__" not in r.text
    assert "УИБО-бот" not in r.text
