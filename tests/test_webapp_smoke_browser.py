"""
Дымовой тест WebApp в настоящем Chromium: главная открывается на тестовой
базе без ошибок JS. Ловит то, что node-проверки (tests/test_webapp_static.py)
не видят: порядок скриптов, обращения к DOM при загрузке, сломанный запуск
из main.js. Telegram — заглушкой window.Telegram.WebApp (скрипт telegram.org
не грузим). Нет Playwright или Chromium (как в CI) — тест пропускается.
"""
import asyncio
import os
import socket

import pytest

from tests.test_webapp_auth import BOT_TOKEN, _make_init_data

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

try:
    from playwright.sync_api import sync_playwright
except Exception:          # нет пакета — пропускаем
    sync_playwright = None

pytestmark = pytest.mark.skipif(sync_playwright is None or not os.path.exists(CHROMIUM),
                                reason="нужны Playwright и Chromium")

TG_STUB = """
window.Telegram = { WebApp: {
  initData: %s, initDataUnsafe: { user: { id: 222, first_name: "Alice" } },
  platform: "tdesktop", colorScheme: "dark", themeParams: {}, version: "7.0",
  isVersionAtLeast: () => false, ready() {}, expand() {}, setHeaderColor() {},
  onEvent() {}, offEvent() {}, openLink() {}, openTelegramLink() {},
  BackButton: { onClick() {}, offClick() {}, show() {}, hide() {} },
  HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
} };
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _browse(url: str, init_data: str):
    """Открыть главную и пройтись по вкладкам; → (ошибки JS, текст карточки сверху).
    Браузер — в своём потоке: у цикла теста запуск подпроцессов не работает."""
    import json
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        # 4xx/5xx API (СДО не подключён и т.п.) Chromium тоже пишет в консоль — это не ошибки JS
        page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
                and errors.append(m.text))
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(TG_STUB % json.dumps(init_data))
        page.goto(url)
        page.wait_for_function("document.querySelectorAll('#daychips button').length === 6")
        page.wait_for_function("document.getElementById('hero').textContent.includes('Повторить')")
        hero = page.inner_text("#hero")
        page.evaluate("document.getElementById('onboard').classList.remove('open')")   # знакомство не мешает
        # первый вход — лист согласия (152-ФЗ): без галочки «Продолжить» неактивна
        page.wait_for_selector("#consent-sheet.open")
        assert page.is_disabled("#pd-go")
        page.click("#consent-sheet .consent-box")
        page.click("#pd-go")
        page.wait_for_selector("#consent-sheet.open", state="hidden")
        for tab in ("search", "chat", "sdo", "today"):
            page.click(f"nav.tabs button[data-tab='{tab}']")
        page.wait_for_timeout(300)
        browser.close()
    return errors, hero


@pytest.mark.asyncio
async def test_home_opens_without_js_errors(db, monkeypatch):
    import bot
    import kapibara.features.weather.forecast
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.deps as deps

    async def mirea_down(*a, **k):
        raise RuntimeError("МИРЭА не отвечает")

    async def no_weather(*a, **k):
        return ""

    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    from kapibara.core import config
    await db.upsert_user(222, "", "Alice")
    await db.set_user_group(222, config.HOME_GROUP_ID)          # группа уже выбрана — лист выбора не мешает
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", mirea_down)
    monkeypatch.setattr(kapibara.features.weather.forecast, "get_weather_for_morning", no_weather)
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        errors, hero = await asyncio.to_thread(_browse, f"http://127.0.0.1:{port}/", _make_init_data())
        assert not errors, errors
        assert "НЕ ЗАГРУЗИЛОСЬ" in hero.upper() and "Повторить" in hero     # МИРЭА лежит — так и пишем
    finally:
        await bot.stop_webapp(server, task)


def _landing(url: str) -> str:
    """Корень в обычном браузере (initData пустой) → адрес, где оказались."""
    import json
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(TG_STUB % json.dumps(""))
        page.goto(url)
        page.wait_for_url("**/about")
        final = page.url
        browser.close()
    return final


@pytest.mark.asyncio
async def test_root_in_plain_browser_goes_to_site(db, monkeypatch):
    """www.uiboshki.ru вне Telegram — сайт /about, а не приложение без входа."""
    import bot
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        final = await asyncio.to_thread(_landing, f"http://127.0.0.1:{port}/")
        assert final.endswith("/about")
    finally:
        await bot.stop_webapp(server, task)


def _pwa(url: str, token: str, standalone: bool = False) -> tuple[bool, bool, list]:
    """/app вне Telegram: (экран «Войти» открыт, главная загрузилась, ошибки JS).
    standalone — как с экрана «Домой» на iPhone; тогда вместо главной — отступ шапки сверху."""
    import json
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(TG_STUB % json.dumps(""))
        if token:
            page.add_init_script(f"localStorage.setItem('uib_token', {json.dumps(token)})")
        if standalone:
            page.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true })")
        page.goto(url)
        page.wait_for_timeout(800)
        login = page.evaluate("document.getElementById('login').classList.contains('open')")
        home = page.evaluate("document.getElementById('greeting') ? document.getElementById('greeting').textContent : ''")
        if standalone:
            home = page.evaluate("parseFloat(getComputedStyle(document.querySelector('header.top')).paddingTop)")
        browser.close()
    return login, (home if standalone else bool(home)), errors


@pytest.mark.asyncio
async def test_pwa_login_screen_and_token(db, monkeypatch):
    """Этап 2: /app вне Telegram — без входа «Войти через Telegram», с токеном — приложение."""
    import bot
    import webapp.deps as deps
    from database.sessions import create_session
    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "", "Alice")
    token = await create_session(222, "test")
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        login, _, errors = await asyncio.to_thread(_pwa, f"http://127.0.0.1:{port}/app", "")
        assert login and not errors, errors
        login, _, errors = await asyncio.to_thread(_pwa, f"http://127.0.0.1:{port}/app", token)
        assert not login and not errors, errors
    finally:
        await bot.stop_webapp(server, task)


@pytest.mark.asyncio
async def test_pwa_home_screen_header_below_clock(db, monkeypatch):
    """Баг (скрин владельца, iPhone 16 Pro): PWA с экрана «Домой» — шапка под часами.
    В режиме standalone шапка отступает как в полном экране Telegram (не меньше 44 + 8)."""
    import bot
    import webapp.deps as deps
    from database.sessions import create_session
    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "", "Alice")
    token = await create_session(222, "test")
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        _, top, errors = await asyncio.to_thread(_pwa, f"http://127.0.0.1:{port}/app", token, True)
        assert not errors, errors
        assert top >= 52
        _, home, _ = await asyncio.to_thread(_pwa, f"http://127.0.0.1:{port}/app", token)
        assert home
    finally:
        await bot.stop_webapp(server, task)


# ── Ночь 09.10: сайт ──
SITE_FIO = "Константинопольский-Великорецкий Александр Владимирович"


def _site_layout(url: str, width: int) -> dict:
    """/about на узком экране: поиск с длинными названиями и расписание преподавателя."""
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(url + "/about")
        page.fill("#schedule-query", "иванов")
        page.wait_for_selector(".search-results button")
        page.click(".search-results button[data-i='1']")
        page.wait_for_selector(".schedule-heading h3")
        res = page.evaluate("""() => {
          const r = (q) => document.querySelector(q).getBoundingClientRect();
          const ph = r('.phone'), ex = r('.demo-expand');
          // слово заголовка (до пробела или дефиса) не рвётся на две строки: один прямоугольник
          const t = document.querySelector('.schedule-heading h3').firstChild, words = [];
          for (const m of t.textContent.matchAll(/[^\\s-]+/g)) {
            const rg = document.createRange(); rg.setStart(t, m.index); rg.setEnd(t, m.index + m[0].length);
            words.push([m[0], rg.getClientRects().length]);
          }
          return {scroll: document.documentElement.scrollWidth, inner: innerWidth, words,
                  expandUnderPhone: ex.left < ph.right && ex.right > ph.left && ex.top < ph.bottom && ex.bottom > ph.top};
        }""")
        browser.close()
    return res


@pytest.mark.asyncio
async def test_site_narrow_layout(db, monkeypatch):
    """Баги сайта на узком экране: длинное название в поиске давало прокрутку
    вбок, кнопка «демо в отдельной вкладке» пряталась под телефоном, фамилия в
    заголовке расписания рвалась посреди слова."""
    import bot
    from kapibara.core import ratelimit
    from kapibara.features.schedule import index as schedule_index
    import webapp.routes.schedule as sched

    async def search(q="", type=0, user=None):
        return {"items": [{"type": 1, "id": 1, "title": "УИБО-03-24", "hint": "Группа"},
                          {"type": 2, "id": 2, "title": SITE_FIO, "hint": "Преподаватель"},
                          {"type": 1, "id": 3, "title": "ОченьДлинноеНазваниеБезПробелов" * 2, "hint": "Группа"}]}

    async def target(t, i, user=None):
        return {"type": t, "id": i, "title": SITE_FIO, "today": "2026-10-09", "stale": False, "weeks": []}

    async def ready():
        return False

    monkeypatch.setattr(sched, "api_search", search)
    monkeypatch.setattr(sched, "api_target", target)
    monkeypatch.setattr(schedule_index, "is_ready", ready)
    ratelimit.reset()
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        for width in (320, 375, 700):
            res = await asyncio.to_thread(_site_layout, f"http://127.0.0.1:{port}", width)
            assert res["scroll"] <= res["inner"], (width, res)
            assert not res["expandUnderPhone"], width
            if width < 700:
                assert all(n == 1 for _, n in res["words"]), (width, res["words"])
    finally:
        await bot.stop_webapp(server, task)
        ratelimit.reset()


# ── Ночь 09.10: зона B ──

def _narrow_phone(url: str, init_data: str):
    """iPhone 320×568 в полном экране Telegram: (ширина страницы с блоком кода
    в чате, низ кнопки «Дальше» в знакомстве)."""
    import json
    stub = (TG_STUB % json.dumps(init_data)).replace('platform: "tdesktop"', 'platform: "ios"') \
        .replace('version: "7.0"', 'version: "8.0", isFullscreen: true, requestFullscreen() {}, '
                 'safeAreaInset: { top: 20, bottom: 0 }, contentSafeAreaInset: { top: 46, bottom: 0 }') \
        .replace("isVersionAtLeast: () => false", "isVersionAtLeast: () => true")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 320, "height": 568})
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(stub)
        page.goto(url)
        page.wait_for_function("document.querySelectorAll('#daychips button').length === 6")
        page.evaluate("document.getElementById('onboard').classList.remove('open'); switchTab('chat');"
                      "appendMsg('assistant', 'код', '', 'Вот:\\n\\n<pre>' + 'x = 1 + '.repeat(60) + '</pre>\\n\\nВсё.')")
        width = page.evaluate("document.documentElement.scrollWidth")
        page.evaluate("showOnboard(0)")
        bottom = page.evaluate("document.querySelector('#onboard .ob-next').getBoundingClientRect().bottom")
        browser.close()
    return width, bottom


@pytest.mark.asyncio
async def test_narrow_phone_chat_code_and_onboarding(db, monkeypatch):
    """Блок кода в ответе ИИ раздвигал страницу вбок; на 320×568 в полном
    экране кнопка «Дальше» знакомства уезжала за нижний край."""
    import bot
    from kapibara.core import config
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.deps as deps

    async def mirea_down(*a, **k):
        raise RuntimeError("МИРЭА не отвечает")

    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", mirea_down)
    await db.upsert_user(222, "", "Alice")
    await db.set_user_group(222, config.HOME_GROUP_ID)
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        width, bottom = await asyncio.to_thread(_narrow_phone, f"http://127.0.0.1:{port}/", _make_init_data())
        assert width <= 320
        assert bottom <= 568
    finally:
        await bot.stop_webapp(server, task)


# ── Ночь 09.10: WebApp, часть A ──

FULLSCREEN_STUB = TG_STUB.replace('platform: "tdesktop"', 'platform: "ios"').replace('version: "7.0"', 'version: "8.0"').replace(
    "isVersionAtLeast: () => false", "isVersionAtLeast: () => true, isFullscreen: true, requestFullscreen() {}, "
    "safeAreaInset: { top: 0, bottom: 0 }, contentSafeAreaInset: { top: 46, bottom: 0 }").replace(
    "onEvent() {}", "onEvent(n, f) { (window.__ev[n] = window.__ev[n] || []).push(f); }")


def _layout(url: str, init_data: str) -> dict:
    """Геометрия на телефоне в полном экране Telegram и на компьютере → словарь замеров."""
    import json
    res = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 320, "height": 568})
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script("window.__ev = {};")
        page.add_init_script(FULLSCREEN_STUB % json.dumps(init_data))
        page.goto(url)
        page.wait_for_function("document.querySelectorAll('#daychips button').length === 6")
        page.evaluate("document.getElementById('onboard').classList.remove('open')")
        # Telegram присылает отступ под полоску «Домой» уже после загрузки
        page.evaluate("Telegram.WebApp.safeAreaInset = {top: 59, bottom: 34}; (__ev.safeAreaChanged || []).forEach(f => f())")
        page.wait_for_timeout(200)
        res["nav"] = page.evaluate("[parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')),"
                                   " document.querySelector('nav.tabs').offsetHeight]")
        page.evaluate("openDeadlinesSeg('dl')")
        page.wait_for_timeout(400)          # пока вкладка въезжает (transform), fixed считается от неё
        res["fab_gap"] = page.evaluate("document.querySelector('nav.tabs').getBoundingClientRect().top"
                                       " - document.getElementById('fab-add').getBoundingClientRect().bottom")
        page.evaluate("openAddSheet()")
        page.wait_for_timeout(300)
        res["sheet_pad"] = page.evaluate("parseFloat(getComputedStyle(document.querySelector('#add-sheet .sheet')).paddingBottom)")
        res["time_over"] = page.evaluate("document.getElementById('nd-time').getBoundingClientRect().right"
                                         " - document.getElementById('nd-subject').getBoundingClientRect().right")
        page.evaluate("closeAddSheet(); switchTab('search')")
        res["search_hscroll"] = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.evaluate("switchTab('today')")
        res["desktop_main"] = page.evaluate("document.querySelector('main').getBoundingClientRect().width")
        browser.close()
    return res


@pytest.mark.asyncio
async def test_layout_safe_area_narrow_and_wide(db, monkeypatch):
    """Ночь 09.10: «＋» дедлайнов вставал на нижнюю панель (отступ пришёл
    safeAreaChanged после загрузки), кнопка листа — на полоску «Домой», поле
    времени вылезало за лист на 320px, «Поиск» ездил вбок, на компьютере всё
    тянулось на 1280px."""
    import bot
    from kapibara.core import config
    import kapibara.features.weather.forecast
    from kapibara.features.schedule import parser as schedule_parser
    import webapp.deps as deps

    async def mirea_down(*a, **k):
        raise RuntimeError("МИРЭА не отвечает")

    async def no_weather(*a, **k):
        return ""

    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "", "Alice")
    await db.set_user_group(222, config.HOME_GROUP_ID)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", mirea_down)
    monkeypatch.setattr(kapibara.features.weather.forecast, "get_weather_for_morning", no_weather)
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        r = await asyncio.to_thread(_layout, f"http://127.0.0.1:{port}/", _make_init_data())
        assert r["nav"][0] == r["nav"][1], r
        assert r["fab_gap"] >= 8, r
        assert r["sheet_pad"] >= 18 + 34, r
        assert r["time_over"] <= 0.5, r
        assert r["search_hscroll"] <= 0, r
        assert r["desktop_main"] <= 680, r
    finally:
        await bot.stop_webapp(server, task)


# ── Ревью безопасности 09.10: токен из адреса ──
def _token_in_url(url: str, token: str, pending: bool) -> bool:
    """Открыть /app#token=… (pending — вход начат в этом браузере) → токен сохранён?"""
    import json
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(TG_STUB % json.dumps(""))
        if pending:
            page.add_init_script("if (!sessionStorage.getItem('x')) { sessionStorage.setItem('x', 1);"
                                 " localStorage.setItem('uib_oauth_at', String(Date.now())); }")
        page.goto(f"{url}#token={token}")
        page.wait_for_timeout(600)
        saved = page.evaluate("localStorage.getItem('uib_token')") == token
        clean = "#token" not in page.url
        browser.close()
    return saved and clean


@pytest.mark.asyncio
async def test_foreign_token_link_is_ignored(db, monkeypatch):
    import bot
    import webapp.deps as deps
    from database.sessions import create_session
    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "", "Alice")
    token = await create_session(222, "test")
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        url = f"http://127.0.0.1:{port}/app"
        assert not await asyncio.to_thread(_token_in_url, url, token, False)   # чужая ссылка — мимо
        assert await asyncio.to_thread(_token_in_url, url, token, True)        # свой вход — принят
    finally:
        await bot.stop_webapp(server, task)


# ── Баг (скрины для поста 23): строка пушей в PWA — над шапкой листа и
#    пропадала после любого тумблера (лист перерисовывается целиком) ──
PUSH_STUB = """
const reg = { pushManager: { getSubscription: async () => null } };
Object.defineProperty(navigator, 'serviceWorker', { value: { ready: Promise.resolve(reg), register: async () => reg } });
window.PushManager = function () {};
window.Notification = { permission: 'default' };
"""


def _push_row(url: str, token: str) -> list:
    """Лист «Уведомления» в PWA: что идёт по порядку до и после тумблера (id или класс)."""
    import json
    order = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.route("https://telegram.org/**", lambda route: route.abort())
        page.add_init_script(TG_STUB % json.dumps(""))
        page.add_init_script(f"localStorage.setItem('uib_token', {json.dumps(token)})")
        page.add_init_script(PUSH_STUB)        # без https service worker не ставится
        page.goto(url)
        page.wait_for_timeout(800)
        kids = """() => [...document.getElementById('notify-body').children].slice(0, 3)
                  .map(e => e.id || e.className)"""
        page.evaluate("openNotify()")
        page.wait_for_selector("#push-row")
        order.append(page.evaluate(kids))
        page.evaluate("toggleNotifyMaster()")
        page.wait_for_timeout(600)
        order.append(page.evaluate(kids))
        order.append(page.evaluate("document.querySelectorAll('#push-row').length"))
        browser.close()
    return order


@pytest.mark.asyncio
async def test_pwa_push_row_under_header(db, monkeypatch):
    import bot
    import webapp.deps as deps
    from database.sessions import create_session
    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "", "Alice")
    token = await create_session(222, "test")
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        before, after, count = await asyncio.to_thread(_push_row, f"http://127.0.0.1:{port}/app", token)
        assert before[:2] == ["sec-hero", "push-row"], before
        assert after[:2] == ["sec-hero", "push-row"], after
        assert count == 1
    finally:
        await bot.stop_webapp(server, task)


def _vote_page(url: str) -> dict:
    """Слепой тест ИИ на телефоне: длинное свёрнуто, «Лучший» уходит на сервер
    и держится после перезагрузки без копии в браузере."""
    out = {"errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(viewport={"width": 390, "height": 760})
        page.on("pageerror", lambda e: out["errors"].append(str(e)))
        page.goto(url)
        out["more"] = page.locator("button.more").count()
        page.click("[data-i='0'][data-j='1'] button")
        page.wait_for_function("document.getElementById('cnt').textContent.includes('выбрано 1')")
        page.wait_for_timeout(300)
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_function("document.querySelector(\"[data-i='0'][data-j='1']\").classList.contains('on')")
        page.click("button.more")
        out["open"] = page.locator(".t.cut").count()
        out["wide"] = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        page.click(".bar button")
        out["res"] = page.inner_text("#res")
        browser.close()
    return out


@pytest.mark.asyncio
async def test_ai_vote_page_keeps_picks_on_server(db, monkeypatch):
    from kapibara.features.ai import bench as ai_bench
    import bot
    import webapp.deps as deps
    from webapp.routes import aitest
    monkeypatch.setattr(deps, "BOT_TOKEN", BOT_TOKEN)
    items = [{"kind": "Конспект", "title": "Лекция 1", "subject": "БД", "answers": [
        {"text": ("длинный конспект\n" * 80) if m == "a/x" else "коротко", "model": m, "cost": 0.001, "secs": 2}
        for m in ("a/x", "b/y")]}]
    key = ai_bench.vote_key(items, {"a/x": "Икс", "b/y": "Игрек"})
    await ai_bench.save(ai_bench.page(items, key["names"]), "vote", key)
    port = _free_port()
    server, task = bot.start_webapp(port)
    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        q = aitest.link("vote").split("/aitest")[1]
        out = await asyncio.to_thread(_vote_page, f"http://127.0.0.1:{port}/aitest{q}")
    finally:
        await bot.stop_webapp(server, task)
    assert not out["errors"], out["errors"]
    assert out["more"] == 1 and out["open"] == 0 and not out["wide"]        # свёрнут только длинный
    assert "Игрек: побед 1" in out["res"]
    assert await ai_bench.vote_picks() == {"0": 1}
