"""
Интерфейс WebApp без браузера: index.html разбит на app.css и js/*.js (по
вкладкам), и ошибка в любом из них ломает приложение целиком — у всех и
сразу. Раньше это ловилось только скриншотами. Здесь дешёвые проверки,
которые гоняются в CI: синтаксис JS, что всё подключено и отдаётся, что
id и onclick из разметки существуют, что части не объявляют одно и то же.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS_FILES = re.findall(r'<script src="(js/[\w-]+\.js)"></script>', HTML)
JS = {name: (STATIC / name).read_text(encoding="utf-8") for name in JS_FILES}
ALL_JS = "\n".join(JS.values())


def test_all_parts_are_wired_in_order():
    assert JS_FILES[0] == "js/core.js" and JS_FILES[-1] == "js/main.js"
    assert sorted(JS_FILES) == sorted(f"js/{p.name}" for p in (STATIC / "js").glob("*.js"))
    assert '<link rel="stylesheet" href="app.css">' in HTML
    assert "<script>" not in HTML and "<style>" not in HTML      # больше ничего не встроено


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
@pytest.mark.parametrize("name", JS_FILES)
def test_js_syntax(name):
    res = subprocess.run(["node", "--check", str(STATIC / name)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_index_versions_assets_and_they_are_served():
    import webapp.server as server
    client = TestClient(server.app)
    page = client.get("/")
    assert page.status_code == 200 and page.headers["cache-control"] == "no-cache"
    urls = re.findall(r'(?:src|href)="((?:js/[\w-]+\.js|app\.css)\?v=[0-9a-f]{10})"', page.text)
    assert len(urls) == len(JS_FILES) + 1
    for url in urls:
        assert client.get("/" + url).status_code == 200


def test_ids_used_in_js_exist():
    ids_in_html = set(re.findall(r'\bid="([\w-]+)"', HTML))
    ids_made_by_js = set(re.findall(r'\bid=\\?"([\w-]+)\\?"', ALL_JS)) | set(re.findall(r'\.id\s*=\s*"([\w-]+)"', ALL_JS))
    used = set(re.findall(r'getElementById\("([\w-]+)"\)', ALL_JS))
    used |= set(re.findall(r'querySelector(?:All)?\("#([\w-]+)', ALL_JS))
    missing = used - ids_in_html - ids_made_by_js
    assert not missing, f"в разметке нет элементов: {sorted(missing)}"


def test_onclick_handlers_are_defined():
    defined = set(re.findall(r'^(?:async\s+)?function\s+(\w+)\s*\(', ALL_JS, re.M))
    called = set(re.findall(r'onclick="(\w+)\(', HTML))
    assert called - defined == set(), f"нет функций: {sorted(called - defined)}"


def test_no_part_redeclares_anothers_globals():
    seen = {}
    for name, text in JS.items():
        for kind, ident in re.findall(r'^(?:async\s+)?(function|const|let|var)\s+(\w+)', text, re.M):
            assert ident not in seen, f"{ident} объявлен и в {seen[ident]}, и в {name}"
            seen[ident] = name


def test_sdo_pips_fill_from_left():
    # живой скрин 01.10: «1 из 4 закрыто» подсвечивало последнее деление (закрытые карточки идут в конце)
    assert "i < closed" in JS["js/sdo.js"]


def test_icons_used_are_drawn():
    # свои иконки (js/icons.js) вместо эмодзи: каждая, что зовётся из JS или
    # разметки, нарисована — иначе на её месте пустое место
    drawn = set(re.findall(r"^\s+(\w+): '", JS["js/icons.js"], re.M))
    drawn |= set(re.findall(r'<symbol id="i-(\w+)"', JS["js/icons.js"]))     # отдельные символы (капибара)
    used = set(re.findall(r'icon\("(\w+)"', ALL_JS)) | set(re.findall(r'href="#i-(\w+)"', HTML))
    look = JS["js/sdo.js"].split("const WORK_LOOK = {", 1)[1].split("};", 1)[0]
    used |= set(re.findall(r'\["(\w+)", "', look))
    cats = JS["js/files.js"].split("const CAT_ICONS = {", 1)[1].split("};", 1)[0]
    used |= set(re.findall(r': "(\w+)"', cats))
    missing = {u for u in used if u not in drawn and u not in ("ok", "bad", "warn", "")}
    assert not missing, f"не нарисованы: {sorted(missing)}"


def test_tab_bar_and_menu_use_own_icons():
    nav = HTML[HTML.index('<nav class="tabs">'):HTML.index("</nav>")]
    menu = HTML[HTML.index('id="more-menu"'):HTML.index('id="sdo-sheet"')]
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    assert not emoji.search(nav) and not emoji.search(menu)


def test_theme_follows_telegram_live():
    # тема Telegram меняется без перезапуска приложения — перекрашиваемся сразу
    core = JS["js/core.js"]
    assert 'tg.onEvent("themeChanged", applyTheme)' in core
    assert "dataset.theme" in core
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ':root[data-theme="light"]' in css and "var(--switch-off)" in css


def test_onboarding_once_and_not_on_deep_links():
    more, main = JS["js/more.js"], JS["js/main.js"]
    assert "CloudStorage" in more and "onboarded_v1" in more        # один раз, и на другом телефоне тоже
    assert "if (!deepLink) maybeOnboard();" in main                 # из уведомления — без знакомства
    assert 'id="onboard"' in HTML


def test_happy_empty_states_with_capybara():
    assert "function capyEmpty(" in JS["js/core.js"]
    for f in ("js/deadlines.js", "js/home.js", "js/files.js", "js/sdo.js", "js/search.js"):
        assert "capyEmpty(" in JS[f], f


def test_telegram_back_closes_sheets_first():
    main = JS["js/main.js"]
    assert "closeTopSheet" in main and "MutationObserver" in main
    assert "NESTED().forEach(fn => tg.BackButton.offClick(fn))" in main     # без двойного «назад»


def test_whats_new_once_per_release():
    more = JS["js/more.js"]
    assert "const NEWS = {" in more and 'cloudFlag("news_seen", NEWS.id)' in more
    assert "if (firstVisit) { cloudFlag(\"news_seen\", NEWS.id); return; }" in more   # новичку — только знакомство
    assert 'id="news-sheet"' in HTML


def test_home_starts_instantly_from_saved_day():
    # Мгновенный старт: сводка «сегодня» за этот же день — из памяти телефона,
    # свежая — следом; имя — сразу из Telegram; пары сегодня — без /api/day.
    home = JS["js/home.js"]
    assert "readHomeSnap()" in home and "saveHomeSnap()" in home
    assert "snap.today.date === isoDate(new Date())" in home          # только за сегодня
    assert "tg.initDataUnsafe.user" in home
    assert "renderDay(list, todayData)" in home


# ── Дизайн-ревью, пункты 1–5 (v5.5.0) ──────────────────────────────────────

CSS = (STATIC / "app.css").read_text(encoding="utf-8")


def test_chat_opens_at_last_message():
    # п. 1: чат с историей открывался сверху, на самых старых сообщениях
    assert "scrollChatToEnd()" in JS["js/core.js"].split("function switchTab")[1].split("\n}\n")[0]
    chat = JS["js/chat.js"]
    assert "function scrollChatToEnd()" in chat and "if (!chatLog.length) return;" in chat


def test_security_says_starosta_sees_who():
    # п. 2: с v5.1.0 староста видит в /stats, кто пользуется, — экран «Безопасность» говорит об этом
    assert "Староста видит, кто именно" in JS["js/more.js"]


def test_light_theme_text_is_darker():
    # п. 3: в светлой теме зелёные/оранжевые надписи читались плохо — тексту свои цвета
    assert not re.search(r"(?<![-\w])color: var\(--(ok|warn|accent-2|danger)\)", CSS)
    light = CSS.split(':root[data-theme="light"] { --switch-off')[1].split("}")[0]
    for var in ("--ok-text", "--warn-text", "--accent-2-text", "--danger-text"):
        assert var in light


def test_sdo_legend_lists_every_colour_in_bars():
    # п. 4: в полосках пять цветов, в легенде было три
    sdo = JS["js/sdo.js"]
    assert "legendHtml(list)" in sdo and '"трудовая деятельность"' in sdo and '"достижения"' in sdo


def test_search_filters_stay_in_one_row():
    # п. 5: «Аудитории» на узком iPhone уезжали на вторую строку
    assert re.search(r"#target-types \{ flex-wrap: nowrap; overflow-x: auto;", CSS)


# ── Дизайн-ревью, пункты 6–10 (v5.6.0) ─────────────────────────────────────

def test_target_down_screen_has_retry():
    # п. 6: «МИРЭА лежит» — было голой строкой; теперь капибара и «Повторить»
    search = JS["js/search.js"]
    assert "function retryTarget()" in search and 'onclick="retryTarget()"' in search
    assert "capyEmpty(\"Сайт МИРЭА сейчас не отвечает\"" in search
    assert 'id="target-stale"' in HTML and "data.stale" in search


def test_sdo_texts_are_human():
    # п. 7: статусы Moodle по-английски и «нужно 0» у закрытых предметов
    sdo = JS["js/sdo.js"]
    assert "function humanStatus(" in sdo and "Сдано, ждёт оценки" in sdo
    assert "function gotText(" in sdo and "зачёт уже есть" in sdo


def test_done_group_has_chevron_not_hint():
    # п. 8: «Выполнено · N ›» вместо «нажми, чтобы вернуть»
    dl = JS["js/deadlines.js"]
    assert "done-chev" in dl and "— нажми, чтобы вернуть</span>" not in dl
    assert "details.done-group[open] .done-chev" in CSS


def test_header_only_on_today():
    # п. 9: шапка с приветствием — только на «Сегодня», на остальных вкладках место контенту
    assert 'classList.toggle("compact-head", name !== "today")' in JS["js/core.js"]
    assert "body.compact-head header.top { display: none; }" in CSS


def test_home_pills_scroll_in_one_row():
    # п. 10: плашки над главной — одной строкой с прокруткой вбок
    assert 'id="pill-row"' in HTML and "pill-row" in JS["js/home.js"]
    assert re.search(r"\.pill-row \{[^}]*overflow-x: auto;", CSS)
    assert ".pill-row > div { flex: none;" in CSS


def test_new_chat_stays_open_after_restart():
    # «＋ Новый» — при следующем заходе открывается он (даже пустой), а не прошлый
    chat = JS["js/chat.js"]
    assert 'CHAT_CUR_KEY = "chats.current"' in chat and 'cur === "new"' in chat
    for fn in ("function newChat", "function switchChat", "function saveChatLog", "function deleteChat"):
        assert "rememberChat()" in chat.split(fn)[1].split("\n}\n")[0], fn


# ── Дизайн-ревью, п. 14 ──

def test_file_summary_pills_and_hint():
    # п. 14: у файла с текстом была крошечная книжка — не понимали, что будет конспект
    files = JS["js/files.js"]
    card = files.split("function fileCard(")[1].split("\n}\n")[0]
    assert '<span class="fpill txt">' in card and "есть текст</span>" in card
    assert '<span class="fpill sum">' in card and "конспект</span>" in card
    assert 'class="badge' not in card
    assert re.search(r"\.file-card \.fpill \{[^}]*border-radius: 999px;[^}]*white-space: nowrap;", CSS)
    assert re.search(r"\.file-card \.fpill\.txt \{[^}]*color: var\(--accent-2-text\)", CSS)
    assert re.search(r"\.file-card \.fpill\.sum \{[^}]*color: #fff;[^}]*linear-gradient", CSS)
    # подсказка — над списком, а не под ним (видна и в папке предмета)
    view = HTML.split('id="view-files"')[1].split("</section>")[0]
    assert "Нажми на файл с пометкой — ИИ сделает конспект" in view and "/upload" in view
    assert view.index('id="files-hint"') < view.index('id="file-list"')


# ── Дизайн-ревью, п. 15 ──
# Даты по-человечески: «чт, 8 окт · через 6 дн.» вместо голых «8.10» и «к 09.10».

def test_human_dates_one_helper_everywhere():
    assert "function humanDate(" in JS["js/core.js"]
    for f in ("js/deadlines.js", "js/home.js", "js/more.js", "js/sdo.js"):
        assert "humanDate(" in JS[f], f
    # старые голые форматы «d.mm» и «к dd.mm» больше не собираются
    assert '"." + String(d.getMonth() + 1).padStart(2, "0")' not in ALL_JS
    assert "'<span class=\"chip warn\">к ' + h.lesson_date.slice(8, 10)" not in ALL_JS
    assert 'split("-").reverse().slice(0, 2).join(".")' not in ALL_JS
    assert 'return +p[2] + "." + p[1]' not in ALL_JS                    # ось графика баллов


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_human_date_output():
    core = JS["js/core.js"]
    code = core[core.index("const MONTHS_SHORT"):core.index("async function sendToChat(")]
    cases = [
        ("2026-09-26", "23:59", "сегодня · 23:59"),
        ("2026-09-27", "09:00", "завтра · 09:00"),
        ("2026-09-25", "", "вчера"),
        ("2026-10-01", "23:59", "чт, 1 окт · через 5 дн."),       # 23:59 у дальних — не пишем
        ("2026-10-01", "18:00", "чт, 1 окт · через 5 дн. · 18:00"),
        ("2026-10-03", "", "сб, 3 окт · через неделю"),
        ("2026-12-14", "", "пн, 14 дек"),                          # дальше месяца — без «через»
        ("2026-09-22", "", "вт, 22 сен · 4 дн. назад"),
        ("2026-05-01", "", "пт, 1 мая"),
    ]
    script = code + "\nconst c = " + json.dumps([[d, t] for d, t, _ in cases]) + ";\n" + \
        'console.log(JSON.stringify(c.map(([d, t]) => humanDate(d, { time: t, today: "2026-09-26" }))));'
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [want for _, _, want in cases]


# ── Дизайн-ревью, п. 16 ──

def _quick_dates_on(*days):
    """Прогоняет quickDates из deadlines.js в node на заданных датах (Y, M, D)."""
    import json
    home, dl, core = JS["js/home.js"], JS["js/deadlines.js"], JS["js/core.js"]
    src = "\n".join([
        re.search(r"function isoDate\(d\) \{.*?\n\}", home, re.S).group(0),
        re.search(r"const MONTHS_SHORT = .*?;", core).group(0),     # п. 15 перенёс в core.js
        re.search(r"const QD_DOW = .*?;", dl).group(0),
        re.search(r"function quickDates\(now\) \{.*?\n\}", dl, re.S).group(0),
        "console.log(JSON.stringify(%s.map(([y, m, d]) => quickDates(new Date(y, m - 1, d)))));"
        % json.dumps(days),
    ])
    res = subprocess.run(["node", "-e", src], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


# ── Дизайн-ревью, п. 17 ──
def _sdo_js(expr):
    # histScale и historyCard из sdo.js — в node, результат выражения как JSON
    import json
    sdo = JS["js/sdo.js"]
    fns = "".join(re.search(r"function %s\(.*?\n}\n" % n, sdo, re.S).group(0)
                  for n in ("fmtNum", "histScale", "historyCard"))
    core = JS["js/core.js"]       # подписи оси — словами (п. 15): MONTHS_SHORT и humanDate из core.js
    dates = "\n".join([re.search(r"const MONTHS_SHORT = .*?;", core).group(0),
                       re.search(r"const WEEKDAYS_SHORT = .*?;", core).group(0)] +
                      [re.search(r"function %s\(.*?\n}\n" % n, core, re.S).group(0) for n in ("isoDays", "humanDate")])
    code = "function escapeHtml(s){return String(s)}" + dates + fns + "console.log(JSON.stringify(" + expr + "))"
    res = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_quick_dates_next_monday_without_duplicates():
    # пт 2 окт 2026, вс 4 окт, пн 5 окт, ср 30 дек (переход года)
    fri, sun, mon, dec = _quick_dates_on((2026, 10, 2), (2026, 10, 4), (2026, 10, 5), (2026, 12, 30))
    assert [q["label"] for q in fri] == ["Сегодня", "Завтра", "Пн, 5 окт", "Через неделю"]
    assert [q["date"] for q in fri] == ["2026-10-02", "2026-10-03", "2026-10-05", "2026-10-09"]
    assert sun[2] == {"label": "Пт, 9 окт", "date": "2026-10-09"}       # пн = завтра — берём пятницу
    assert mon[2] == {"label": "Пт, 9 окт", "date": "2026-10-09"}       # пн через неделю — тоже пятница
    assert dec[2] == {"label": "Пн, 4 янв", "date": "2027-01-04"}
    for row in (fri, sun, mon, dec):
        assert len({q["date"] for q in row}) == 4                         # без двух одинаковых дат


def test_quick_dates_in_deadline_sheet():
    sheet = HTML[HTML.index('id="add-sheet"'):HTML.index('id="file-sheet"')]
    assert sheet.index('id="nd-quick"') < sheet.index('class="row2"')
    dl = JS["js/deadlines.js"]
    assert "renderQuickDates();" in dl[dl.index("function openAddSheet("):]   # и для нового, и для правки
    assert 'getElementById("nd-date").addEventListener("input", syncQuickDates)' in dl
    pick = dl[dl.index("function pickQuickDate("):dl.index("function syncQuickDates(")]
    assert "haptic()" in pick
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    block = css[css.index("Дизайн-ревью, п. 16"):]
    assert "flex-wrap: nowrap" in block and "overflow-x: auto" in block


# ── Дизайн-ревью, п. 19 ──

def test_sdo_without_login_explains_what_it_gives():
    # без своего входа экран СДО не пустой: 4 пункта «что даёт вход» перед кнопкой
    sdo = JS["js/sdo.js"]
    body = sdo[sdo.index("function sdoNeedConnect("):]
    body = body[:body.index("\n}\n")]
    assert "SDO_PERKS.map(" in body and body.index("sdo-perks") < body.index("openSdoSheet()")
    perks = sdo[sdo.index("const SDO_PERKS = ["):sdo.index("];", sdo.index("const SDO_PERKS = ["))]
    for ic in ("cap", "checkCircle", "upload", "bell"):
        assert '["' + ic + '", ' in perks, ic
    assert "до 3 файлов" in perks                       # как sdo_submit.MAX_FILES
    assert "устарел" in body and "Подключить заново" in body   # «вход устарел» — тот же экран
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".sdo-perk .sec-ic" in css and "var(--accent)" in css[css.index(".sdo-perk .sec-ic"):]


# ── Дизайн-ревью, п. 20 ──
def test_onboarding_tells_about_ai_and_summaries():
    # знакомство рассказывает про главное: ИИ по лекциям группы и конспекты
    more = JS["js/more.js"]
    block = more[more.index("const ONBOARD = ["):more.index("let onboardStep")]
    slides = re.findall(r'\{ ic: "(\w+)", cls: "([\w-]+)"', block)
    assert 4 <= len(slides) <= 5, slides
    assert ("sparkle", "t-ai") in slides and ("bookOpen", "t-summary") in slides
    assert "лекциям вашей группы" in block and "из какой взял" in block and "по фото" in block
    assert "Конспект один на всю группу" in block
    assert slides[-1][0] == "search"                                  # последним — как было
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for _, cls in slides:
        assert ".ob-ic." + cls + " {" in css, cls
    # точки и «Дальше/Начать» — по числу слайдов, флаг прежний (кто прошёл — не увидит снова)
    assert "ONBOARD.map((_, j) =>" in more and more.count("i < ONBOARD.length - 1") == 2
    assert 'const ONBOARD_KEY = "onboarded_v1";' in more


# ── Дизайн-ревью, п. 12 ──
# На главной плитка «Поиск» дублировала вкладку внизу — вместо неё «Баллы СДО»:
# сколько предметов закрыто (те же цифры, что в hero экрана СДО) и какой ближе.

def _home_bento():
    start = HTML.index('<div class="bento"')
    return HTML[start:HTML.index('<h2 class="section">', start)]


def test_home_tile_sdo_instead_of_search():
    bento = _home_bento()
    assert "Поиск" not in bento and "switchTab('search')" not in bento
    assert "Баллы СДО" in bento and 'onclick="openSdo()"' in bento
    assert 'id="home-sdo-big"' in bento and 'id="home-sdo-sub"' in bento
    nav = HTML[HTML.index('<nav class="tabs">'):HTML.index("</nav>")]
    assert 'data-tab="search"' in nav                       # поиск остался во вкладке


def test_home_sdo_tile_shares_logic_and_loads_after_home():
    home, sdo, main = JS["js/home.js"], JS["js/sdo.js"], JS["js/main.js"]
    # подсчёт один — в sdo.js, и экран СДО, и плитка берут его
    assert "sdoSummary(list)" in sdo and "sdoSummary(" in home
    assert "c.closed).length" not in home
    # журнал — общим фоновым запросом, после главной; последнее — из памяти сразу
    assert "loadToday().then(loadSdoTile)" in main and "renderSdoTile(readSdoTile())" in main
    assert "fetchSdoGrades()" in home and "await fetchSdoGrades()" in sdo
    assert "updateSdoTile(sdoData)" in sdo                   # открыл СДО — плитка тоже свежая


def _js_fn(src, name):
    return re.search(r"(?:async )?function %s\(.*?\n}\n" % name, src, re.S).group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_home_sdo_tile_renders_states():
    import json
    home, sdo = JS["js/home.js"], JS["js/sdo.js"]
    courses = [
        {"title": "Физическая культура и спорт", "closed": True, "need": 0},
        {"title": "Основы предпринимательской деятельности [II.25-26]", "closed": False, "need": 4.5},
        {"title": "Анализ данных", "closed": False, "need": 12},
    ]
    code = (
        "const els = {'home-sdo-big': {}, 'home-sdo-sub': {}};"
        "const document = {getElementById: id => els[id]};"
        "const store = {}; const localStorage = {getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; }};"
        "const icon = n => '<svg ' + n + '>'; const escapeHtml = s => String(s);"
        "let sdoData = null; let api = () => Promise.reject(new Error('подключи СДО, чтобы видеть свои баллы'));"
        'const SDO_TILE_KEY = "home.sdoTile"; let sdoGradesReq = null;'
        + "".join(_js_fn(sdo, n) for n in ("fmtNum", "sdoSummary", "shortCourse", "fetchSdoGrades"))
        + "".join(_js_fn(home, n) for n in ("tileFromGrades", "renderSdoTile", "updateSdoTile", "readSdoTile", "loadSdoTile"))
        + "const out = [];"
        + "updateSdoTile({courses: %s});" % json.dumps(courses, ensure_ascii=False)
        + "out.push(els['home-sdo-big'].textContent, els['home-sdo-sub'].innerHTML, readSdoTile().closed);"
        + "loadSdoTile().then(() => { out.push(els['home-sdo-sub'].textContent, readSdoTile().state);"
        + "  api = () => Promise.reject(new Error('ошибка сети')); delete store['home.sdoTile'];"
        + "  return loadSdoTile(); }).then(() => { out.push(els['home-sdo-sub'].textContent); console.log(JSON.stringify(out)); });"
    )
    res = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    big, sub, closed, off_sub, off_state, err_sub = json.loads(res.stdout)
    assert big == "1 из 3" and closed == 1                   # как «Закрыто … 1 из 3» на экране СДО
    assert sub == "ближе всего: Основы предпринимательской…, ещё&nbsp;4,5"
    assert off_sub == "Подключи СДО — увидишь баллы и сколько до зачёта" and off_state == "off"
    assert err_sub == "нажми, чтобы открыть"                 # сеть упала, сохранённого нет


def _js_arg(x):
    import json
    return json.dumps(x, ensure_ascii=False)


EXAM_MARKS = [{"at": 40, "label": "3"}, {"at": 60, "label": "4"}, {"at": 80, "label": "5"}]
CREDIT_MARKS = [{"at": 40, "label": "зачёт"}]


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_history_scale_up_to_next_threshold():
    # баллы 10–50 на шкале 0–130 лежали внизу: верх — ближайший порог с запасом
    s = _sdo_js("histScale([12, 20, 28], %s, 130)" % _js_arg(EXAM_MARKS))
    assert (s["lo"], s["hi"], s["goal"]) == (0, 50, 40) and [m["at"] for m in s["marks"]] == [40]
    s = _sdo_js("histScale([18, 33], %s, 130)" % _js_arg(CREDIT_MARKS))
    assert (s["lo"], s["hi"], s["goal"]) == (0, 50, 40)
    # все точки высоко — низ чуть ниже минимума, пройденный порог тоже в шкале
    s = _sdo_js("histScale([45, 55], %s, 130)" % _js_arg(EXAM_MARKS))
    assert (s["goal"], s["hi"]) == (60, 75) and 0 < s["lo"] < 45
    assert [m["at"] for m in s["marks"]] == [40, 60]
    # выше всех порогов — до максимума БРС
    s = _sdo_js("histScale([82, 95], %s, 130)" % _js_arg(EXAM_MARKS))
    assert s["hi"] == 130 and s["goal"] is None and s["lo"] < 82
    s = _sdo_js("histScale([41, 44], %s, 130)" % _js_arg(CREDIT_MARKS))
    assert (s["lo"], s["hi"]) == (0, 130)
    # ровная линия на нуле и на максимуме — шкала не схлопывается
    assert _sdo_js("histScale([0, 0], %s, 130).hi" % _js_arg(EXAM_MARKS)) == 50
    s = _sdo_js("histScale([130, 130], %s, 130)" % _js_arg(EXAM_MARKS))
    assert s["hi"] == 130 and s["lo"] < 130


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_history_card_threshold_labels_and_last_value():
    c = {"max": 130, "marks": EXAM_MARKS, "history": {"week_delta": 8, "points": [
        ["2026-09-10", 12], ["2026-09-20", 20], ["2026-10-01", 28.5]]}}
    html = _sdo_js("historyCard(%s)" % _js_arg(c))
    assert "на «3» · 40" in html and " goal" in html               # порог-цель — пунктир с подписью
    assert "на «4»" not in html                                     # вне шкалы — без линии
    assert 'class="hist-val' in html and ">28,5<" in html          # последнее значение у точки
    assert 'class="hist-y top">50<' in html and 'class="hist-y bot">0<' in html   # ось подписана
    assert "url(#hist-fill)" in html and "linearGradient" in html
    assert ".hist-plot .hist-area { fill: url(#hist-fill); }" in CSS
    # одна точка — подсказка без графика, нет истории — ничего
    one = {**c, "history": {"week_delta": None, "points": [["2026-10-01", 5]]}}
    assert "График появится" in _sdo_js("historyCard(%s)" % _js_arg(one))
    assert _sdo_js("historyCard(%s)" % _js_arg({**c, "history": {"points": []}})) == ""


# ── Дизайн-ревью, п. 18 ──

def _more_menu():
    return HTML[HTML.index('<div class="more-grid">'):HTML.index('id="sdo-sheet"')]


def test_more_menu_ten_tiles_with_actions():
    # 11 плиток: «План» (автопилот), прежние 6 + ДЗ, «Что нового», «Канал бота», «Написать нам»
    menu = _more_menu()
    labels = re.findall(r'<span class="lbl">([^<]+)</span>', menu)
    assert labels == ["План", "Файлы", "Дедлайны", "ДЗ", "Календарь", "Уведомления", "Безопасность",
                      "Ярлык", "Что нового", "Канал бота", "Написать нам"]
    for call in ("openHomework()", "showWhatsNew()", "openConfigLink(CHANNEL_URL)", "openConfigLink(CONTACT_URL)"):
        assert f'toggleMore(false); {call}"' in menu, call
    assert 'href="#i-send"' in menu and 'href="#i-message"' in menu and 'href="#i-sparkle"' in menu
    # ДЗ — функцией, а не кликом по кнопке сегмента
    dl = JS["js/deadlines.js"]
    assert "function setDlSeg(seg)" in dl and "function openHomework()" in dl
    assert 'openDeadlinesSeg("hw")' in dl and ".click()" not in dl.split("function openDeadlinesSeg")[1]


def test_more_menu_links_from_config():
    # ссылки из config.py; не задана — тост «Скоро», t.me — внутри Telegram
    core, more = JS["js/core.js"], JS["js/more.js"]
    assert "const CHANNEL_URL = APP_CONFIG.channel" in core and "const CONTACT_URL = APP_CONFIG.contact" in core
    fn = more.split("function openConfigLink(url)")[1].split("\n}\n")[0]
    assert 'if (!url) { showToast("Скоро"); return; }' in fn
    assert "tg.openTelegramLink(url)" in fn and "openLink(url)" in fn


def test_more_menu_four_per_row_last_row_centered():
    # 4 в ряд, неполный последний ряд — по центру при любом числе плиток (flex-wrap)
    block = CSS.split("/* ── Дизайн-ревью, п. 18 ── */")[1]
    assert re.search(r"\.more-grid \{[^}]*display: flex; flex-wrap: wrap; justify-content: center;", block)
    assert "flex: 0 0 calc((100% - 3 * 8px) / 4)" in block
    assert re.search(r"\.more-grid \.sq \{[^}]*border-radius: 18px", block)
    for t in ("t-hw", "t-news", "t-channel", "t-contact"):
        assert f".more-grid .sq.{t} {{ background:" in block, t


def test_more_menu_opens_with_cascade_and_respects_reduced_motion():
    block = CSS.split("/* ── Дизайн-ревью, п. 18 ── */")[1]
    assert ".more-backdrop.open .more-grid button { animation: moreTileIn" in block
    assert "animation-delay: calc(40ms + var(--i, 0) * 25ms)" in block
    assert ".more-backdrop.open .more-pop { animation: moreSheetIn" in block
    reduced = block.split("@media (prefers-reduced-motion: reduce)")[1]
    assert ".more-backdrop.open .more-grid button" in reduced and "animation: none" in reduced
    # номер плитки для задержки ставится при каждом открытии
    toggle = JS["js/more.js"].split("function toggleMore(show)")[1].split("\n}\n")[0]
    assert 'b.style.setProperty("--i", i)' in toggle


# ── Сдача: что принимает задание (живой случай 02.10 — только ZIP) ──

def test_submit_sheet_shows_accepted_types():
    more = JS["js/more.js"]
    open_ = more.split("async function openSubmit(")[1].split("\n}\n")[0]
    assert "loadSubmitRules(submitting)" in open_
    assert '"/api/sdo/submit-rules?cmid="' in more and "input.accept = rules.accepted.join" in more
    render = more.split("function renderSubmit(")[1].split("\n}\n")[0]
    assert render.count("submitRulesHtml()") == 2                      # и до выбора файлов, и после
    change = more.split('getElementById("submit-file").addEventListener("change"')[1].split("\n});\n")[0]
    assert "submitExtOk(" in change and "submitMaxMb()" in change      # чужой тип отсекаем до загрузки
    assert re.search(r"\.sub-rules \{[^}]*border-radius", CSS) and ".sub-rules .exts span.ext" in CSS


# ── Листы смахиваются вниз (владелец: «Что нового» не смахивался) ──

def test_sheets_close_by_swipe_down():
    core = JS["js/core.js"]
    assert 'closest(".sheet-backdrop.open .sheet")' in core
    assert "d.sheet.scrollTop > 0" in core                         # прокрутка листа — не свайп
    assert 'closeSheet(d.sheet.closest(".sheet-backdrop").id)' in core
    assert "{ passive: false }" in core and "e.preventDefault()" in core   # фон под листом не листается
