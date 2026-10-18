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


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_desktop_leaves_fullscreen_phone_enters_it():
    # «Open» в списке чатов Telegram Desktop открывал главное приложение бота на
    # весь монитор (режим из BotFather), закрыть было нечем (владелец, 09.10).
    # Desktop при запуске говорит isFullscreen = false — выходим всё равно.
    got = _front("js/core.js", ["fitFullscreen"], "", """
      const run = (platform, isFullscreen) => {
        const log = [];
        tg = { platform: platform, isFullscreen: isFullscreen,
               requestFullscreen: () => log.push("request"), exitFullscreen: () => log.push("exit") };
        fitFullscreen();
        return log.join(",");
      };
      console.log(JSON.stringify([run("tdesktop", false), run("tdesktop", true), run("macos", false),
        run("weba", false), run("webk", false), run("ios", false), run("ios", true), run("android", false),
        run("android_x", false), run("unknown", false)]));
    """)
    assert got == ["exit", "exit", "exit", "exit", "exit", "request", "", "request", "", ""]
    # события полного экрана и отступов — на всех платформах, а не только на телефоне
    core = JS["js/core.js"]
    setup = core.split('if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0")) {')[1].split("\n}\n")[0]
    assert 'tg.onEvent("fullscreenChanged", syncFullscreen)' in setup and "fitFullscreen();" in setup


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
        # баллов на «3» хватает, но зачтено меньше 75 % работ — не автомат (владелец, 06.10)
        {"title": "Экономика", "closed": True, "auto": False, "works_need": 1, "need": 15},
    ]
    code = (
        "const els = {'home-sdo-big': {}, 'home-sdo-sub': {}};"
        "const document = {getElementById: id => els[id]};"
        "const store = {}; const localStorage = {getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; }};"
        "const icon = n => '<svg ' + n + '>'; const escapeHtml = s => String(s);"
        "let sdoData = null; let api = () => Promise.reject(new Error('подключи СДО, чтобы видеть свои баллы'));"
        'const SDO_TILE_KEY = "home.sdoTile"; let sdoGradesReq = null;'
        + "".join(_js_fn(sdo, n) for n in ("fmtNum", "sdoSummary", "autoWorksText", "shortCourse", "fetchSdoGrades"))
        + "".join(_js_fn(home, n) for n in ("plural", "tileFromGrades", "renderSdoTile", "updateSdoTile", "readSdoTile", "loadSdoTile"))
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
    assert big == "1 из 4" and closed == 1                   # как «На автомат … 1 из 4» на экране СДО
    # подпись — что это за число: «2 из 9» без неё было непонятно (владелец, 06.10)
    assert sub == "предметов на автомат · ближе всего: Экономика — зачесть ещё 1 работу"
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


def test_more_menu_tiles_with_actions():
    # 12 плиток — три ровных ряда: прежние 6 + ДЗ, «Что нового», «Канал и связь», «Группа», «Позвать»,
    # «Капибара+». Никита 18.10: нового ряда под «Капибару+» не надо — «Канал бота» и «Написать нам»
    # сошлись в одну плитку с листом (как «Новости и связь» в приложении)
    menu = _more_menu()
    labels = re.findall(r'<span class="lbl">([^<]+)</span>', menu)
    assert labels == ["Файлы", "Дедлайны", "ДЗ", "Календарь", "Уведомления", "Безопасность",
                      "Установить", "Что нового", "Канал и связь", "Моя группа", "Позвать", "Капибара+"]
    assert len(labels) % 4 == 0                                              # без неполного ряда
    for call in ("openHomework()", "showWhatsNew()", "openLinks()", "shareBot()", "openGroup()", "openPlus()"):
        assert f'toggleMore(false); {call}"' in menu, call
    assert 'href="#i-send"' in menu and 'href="#i-sparkle"' in menu
    # обе ссылки — в листе, ничего не потерялось
    fn = JS["js/more.js"].split("function openLinks()")[1].split("\n}\n")[0]
    assert "openConfigLink(CHANNEL_URL)" in fn and "openConfigLink(CONTACT_URL)" in fn
    assert 'row("send", "Канал бота"' in fn and 'row("message", "Написать нам"' in fn
    assert 'id="links-sheet"' in HTML and 'id="links-body"' in HTML
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


# ── Ревью фронта: гонки и состояние ────────────────────────────────────────
# Функции из js/*.js гоняются в node с заглушками DOM; api() — управляемый:
# каждый вызов — промис, который тест сам разрешает (calls[i].res / .rej) в
# нужном порядке — так воспроизводится «старый ответ пришёл после нового».

FRONT_PRELUDE = r"""
const els = {};
function mkEl(id) {
  const cls = new Set();
  return { id: id, innerHTML: "", textContent: "", value: "", disabled: false, style: {}, dataset: {}, isConnected: true,
    classList: { add: c => cls.add(c), remove: (...c) => c.forEach(x => cls.delete(x)), contains: c => cls.has(c),
      toggle: (c, on) => { if (on === undefined) on = !cls.has(c); if (on) cls.add(c); else cls.delete(c); return on; } },
    remove() {}, focus() {}, blur() {}, scrollIntoView() {} };
}
const document = { getElementById: id => els[id] || (els[id] = mkEl(id)), querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, body: mkEl("body"), documentElement: mkEl("html"), activeElement: null };
const window = { scrollTo() {} };
let tg = null;
const haptic = () => {};
const icon = n => "[" + n + "]";
const escapeHtml = s => String(s == null ? "" : s);
const toasts = [];
const showToast = t => { toasts.push(t); };
const calls = [];
function api(path, opts) {
  return new Promise((res, rej) => calls.push({ path: path, body: opts && opts.body ? JSON.parse(opts.body) : null, res: res, rej: rej }));
}
const tick = () => new Promise(r => setTimeout(r, 0));
const requestAnimationFrame = f => f();
function backLog() {
  const log = [];
  tg = { BackButton: { onClick: f => log.push("on:" + f.name), offClick: f => log.push("off:" + f.name),
                       show: () => log.push("show"), hide: () => log.push("hide") } };
  return log;
}
"""


def _front(js_file, names, stubs, code):
    """Функции names из js_file + заглушки → node; code — тело async-функции,
    печатает результат console.log(JSON.stringify(...))."""
    src = "".join(_js_fn(JS[js_file], n) for n in names)
    script = FRONT_PRELUDE + stubs + "\n" + src + "\n(async () => {\n" + code + \
        "\n})().catch(e => { console.error(e && e.stack || e); process.exit(1); });"
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


SDO_STUBS = """
let sdoData = null, sdoCourse = null, sdoView = "sdo", sdoCourseReq = 0, sdoTask = null, sdoTaskReq = 0, tkFilter = "all";
const shown = [];
function showSdoView(n) { sdoView = n; }
function renderSubject() { shown.push("subject:" + sdoCourse.id); }
function renderTk() { shown.push("tk:" + sdoCourse.id); }
function renderPos() {}
function renderTask() { shown.push("task:" + sdoTask.cmid); }
"""

node = pytest.mark.skipif(not shutil.which("node"), reason="нужен node")


@node
def test_sdo_old_answer_does_not_replace_newer_subject_or_task():
    # находка 1: ответ по предмету A пришёл после B — «Сдать» и отметка лекции уходили в A
    course, subj_body, task, task_body, shown = _front("js/sdo.js", ["openSubject", "openTask"], SDO_STUBS, """
      openSubject(1); openSubject(2);
      calls[1].res({ id: 2 }); await tick();
      calls[0].res({ id: 1 }); await tick();
      const course = sdoCourse.id;
      openSubject(3); openSubject(4);
      calls[3].res({ id: 4 }); await tick();
      calls[2].rej(new Error("сеть")); await tick();            // ошибка старого — тоже мимо
      const subjBody = document.getElementById("subject-body").innerHTML;
      openTask({ cmid: 10, name: "A" }); openTask({ cmid: 20, name: "B" });
      calls[5].res({ cmid: 20 }); await tick();
      calls[4].res({ cmid: 10 }); await tick();
      const task = sdoTask.cmid;
      openTask({ cmid: 30, name: "C" }); openTask({ cmid: 40, name: "D" });
      calls[7].res({ cmid: 40 }); await tick();
      calls[6].rej(new Error("сеть")); await tick();
      console.log(JSON.stringify([course, subjBody, task, document.getElementById("task-body").innerHTML, shown]));
    """)
    assert course == 2 and "Не загрузилось" not in subj_body
    assert task == 20 and "Не загрузилось" not in task_body
    assert "subject:1" not in shown and "task:10" not in shown


@node
def test_sdo_back_from_tk_draws_subject():
    # находка 8: ТК открыт с пары на главной (мимо экрана предмета) — «Назад» показывал старый предмет
    view, shown = _front("js/sdo.js", ["sdoBack"], SDO_STUBS, """
      sdoView = "tk"; sdoCourse = { id: 7 }; sdoBack();
      const view = sdoView;
      sdoView = "pos"; sdoCourse = null; sdoBack();             // предмета нет — без падения
      console.log(JSON.stringify([view, shown]));
    """)
    assert view == "subject" and shown == ["subject:7"]


@node
def test_submit_result_of_old_task_only_toasts():
    # находка 2: результат сдачи A рисовался на листе задания B
    renders, toasts, cmid = _front("js/more.js", ["sendSubmission"], """
      let submitting;
      const renders = [];
      function renderSubmit(state) { renders.push((state || "form") + ":" + submitting.item.subject); }
      function refreshTk() {}
      function loadSdoStatus() {}
    """, """
      submitting = { item: { subject: "A", cmid: 1 }, files: [{ name: "a.pdf", data: "x" }] };
      const p = sendSubmission();
      submitting = { item: { subject: "B", cmid: 2 }, files: [] };    // открыли «Сдать» у другого
      calls[0].res({ status: "ok" }); await p;
      submitting = { item: { subject: "C", cmid: 3 }, files: [] };
      const p2 = sendSubmission();
      submitting = { item: { subject: "D", cmid: 4 }, files: [] };
      calls[1].rej(new Error("СДО упал")); await p2;
      const p3 = sendSubmission(); calls[2].res({}); await p3;      // своё задание — лист как раньше
      console.log(JSON.stringify([renders, toasts, calls[0].body.cmid]));
    """)
    assert renders == ["sending:A", "sending:C", "sending:D", "done:D"]
    assert toasts == ["✓ «A» сдано", "⚠️ «C» не сдано: СДО упал"] and cmid == 1


CHAT_STUBS = """
const CHATS_KEY = "chats.v1", CHAT_CUR_KEY = "chats.current";
let chats = [], chatId = null, chatLog = [], pendingAttachment = null;
const store = {};
const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
const shownMsgs = [];
function appendMsg(role, content) { shownMsgs.push(role + ":" + content); return mkEl("bubble"); }
function typingBubble() { return { remove() {} }; }
function addQuickReplies() {}
function dropQuickReplies() {}
function askSubject() {}
function clearAttachment() {}
function renderChat() {}
function scrollChatToEnd() {}
function syncNavHeight() {}
let thinkOffer = null, thinkArmed = false;
"""
CHAT_FNS = ["rememberChat", "chatTitle", "saveChatLog", "chatLogOf", "newChat", "switchChat", "historyOf",
            "requestAnswer", "sendChat", "thinkAgain", "setThinkOffer", "renderThinkToggle", "toggleThink"]


@node
def test_chat_think_toggle_before_question_is_one_shot():
    # Никита 18.10: «Подумать» — выбрать до ответа. Включил — вопрос уходит
    # с think_first, переключатель сам выключается; кончилось — серый;
    # с вложением — нельзя; не подписчик — переключателя нет
    first, second, html_on, html_off, html_zero, html_att, html_none, armed_zero = _front(
        "js/chat.js", CHAT_FNS, CHAT_STUBS, """
      const box = document.getElementById("think-toggle");
      setThinkOffer({ label: "Подумать ещё", left: 2, daily: 10 });
      toggleThink();
      const htmlOn = box.innerHTML;
      const input = document.getElementById("chat-input");
      input.value = "что такое NPV?"; const p = sendChat();
      const htmlOff = box.innerHTML;
      calls[0].res({ content: "глубоко", html: "глубоко", think: { label: "Подумать ещё", left: 0, daily: 10 } }); await p;
      const htmlZero = box.innerHTML;
      toggleThink();
      const armedZero = thinkArmed;
      input.value = "а пример?"; const p2 = sendChat();
      calls[1].res({ content: "пример", html: "пример" }); await p2;
      setThinkOffer({ label: "Подумать ещё", left: 3, daily: 10 });
      pendingAttachment = { name: "a.jpg" }; renderThinkToggle(); toggleThink();
      const htmlAtt = box.innerHTML + "|" + thinkArmed;
      pendingAttachment = null;
      setThinkOffer(null);
      console.log(JSON.stringify([calls[0].body, calls[1].body, htmlOn, htmlOff, htmlZero, htmlAtt, box.innerHTML,
                                  armedZero]));
    """)
    assert first["think_first"] is True and [m["content"] for m in first["history"]] == ["что такое NPV?"]
    assert "think_first" not in second                       # одноразовый: следующий — обычный
    assert 'class="think-toggle on"' in html_on and 'aria-pressed="true"' in html_on and "Подумать · 2" in html_on
    assert 'class="think-toggle"' in html_off and "disabled" not in html_off
    assert "Подумать · 0" in html_zero and "disabled" in html_zero and not armed_zero
    assert "disabled" in html_att and html_att.endswith("|false")
    assert html_none == ""


@node
def test_chat_think_first_survives_subject_choice():
    # «объясни 3 лекцию» с «Подумать»: сервер спросил предмет — повтор уходит тоже «подумав»
    first, again = _front("js/chat.js", CHAT_FNS + ["askAgain"], CHAT_STUBS.replace("function askSubject() {}", """
      function askSubject(entry, att) { setTimeout(() => askAgain(entry, att), 0); }
    """), """
      setThinkOffer({ label: "Подумать ещё", left: 2, daily: 10 });
      toggleThink();
      document.getElementById("chat-input").value = "объясни 3 лекцию"; const p = sendChat();
      calls[0].res({ content: "По какому предмету?", choose: ["Экономика"] }); await p; await tick();
      calls[1].res({ content: "ответ", html: "ответ" }); await tick();
      console.log(JSON.stringify([calls[0].body.think_first, calls[1].body.think_first]));
    """)
    assert first is True and again is True


@node
def test_chat_think_again_resends_question_without_old_answer():
    # «Подумать ещё»: тот же вопрос без прошлого ответа, новый ответ — под ним;
    # дальше в истории из двух ответов подряд уходит только последний
    think_body, shown, next_hist = _front("js/chat.js", CHAT_FNS, CHAT_STUBS, """
      const q = { role: "user", content: "что такое NPV?" };
      chatLog.push(q); saveChatLog();
      const p = requestAnswer(q, null);
      calls[0].res({ content: "коротко", html: "коротко", think: { label: "Подумать ещё", left: 3 } }); await p;
      const p2 = thinkAgain();
      calls[1].res({ content: "глубже", html: "глубже", think: { label: "Подумать ещё", left: 2 } }); await p2;
      const e = { role: "user", content: "а пример?" };
      chatLog.push(e); requestAnswer(e, null);
      console.log(JSON.stringify([calls[1].body, shownMsgs, calls[2].body.history.map(m => m.content)]));
    """)
    assert think_body["think"] is True and [m["content"] for m in think_body["history"]] == ["что такое NPV?"]
    assert shown == ["assistant:коротко", "assistant:глубже"]
    assert next_hist == ["что такое NPV?", "глубже", "а пример?"]


@node
def test_chat_answer_goes_to_its_own_chat():
    # находка 3: «＋ Новый» во время ожидания — ответ ИИ попадал в новый чат
    in_new, shown, log, same = _front("js/chat.js", CHAT_FNS, CHAT_STUBS, """
      const q = { role: "user", content: "что такое NPV?" };
      chatLog.push(q); saveChatLog();
      const first = chatId;
      const p = requestAnswer(q, null);
      newChat();
      calls[0].res({ content: "ответ про NPV", html: "ответ про NPV" }); await p;
      const inNew = chatLog.length, shownNow = shownMsgs.slice();
      switchChat(chats.findIndex(c => c.id === first));
      console.log(JSON.stringify([inNew, shownNow, chatLog.map(m => m.content), chatId === first]));
    """)
    assert in_new == 0 and shown == []
    assert log == ["что такое NPV?", "ответ про NPV"] and same


@node
def test_chat_enter_does_not_send_second_question_while_waiting():
    # находка 12: Enter отправлял второй вопрос, пока первый без ответа
    n, left, n2 = _front("js/chat.js", CHAT_FNS, CHAT_STUBS, """
      const input = document.getElementById("chat-input");
      input.value = "первый"; const p = sendChat();
      input.value = "второй"; sendChat();
      const n = calls.length, left = input.value;
      calls[0].res({ content: "ок", html: "ок" }); await p;
      const p2 = sendChat(); const n2 = calls.length;
      calls[1].res({ content: "ок2", html: "ок2" }); await p2;
      console.log(JSON.stringify([n, left, n2]));
    """)
    assert (n, left, n2) == (1, "второй", 2)          # текст не пропал — уйдёт следующим


@node
def test_chat_remembers_attached_document_text():
    # находка 13: со следующего сообщения ИИ забывал вложенный файл
    first, second, saved = _front("js/chat.js", CHAT_FNS, CHAT_STUBS, """
      const e1 = { role: "user", content: "Разбери этот файл.", att: { name: "a.txt" } };
      chatLog.push(e1); saveChatLog();
      const p1 = requestAnswer(e1, { name: "a.txt", mime: "text/plain", data: "eA==" });
      calls[0].res({ content: "Разобрал", html: "Разобрал", file_text: "=== Файл «a.txt» ===\\nNPV — это" }); await p1;
      const e2 = { role: "user", content: "а что в конце?" };
      chatLog.push(e2);
      requestAnswer(e2, null);
      console.log(JSON.stringify([calls[0].body.history, calls[1].body, JSON.parse(store["chats.v1"])[0].log[0].file_text]));
    """)
    assert first == [{"role": "user", "content": "Разбери этот файл."}]         # сам файл — вложением
    assert second["history"][0]["content"] == "Разбери этот файл.\n\n=== Файл «a.txt» ===\nNPV — это"
    assert "attachment" not in second and second["history"][-1]["content"] == "а что в конце?"
    assert saved.endswith("NPV — это")                                           # и после перезапуска


@node
def test_home_reloads_today_after_midnight():
    # находка 4: главная за вчера — «На сегодня всё · завтра в 9:00» о сегодняшней паре
    res = _front("js/home.js", ["mskToday", "checkTodayFresh"], """
      let todayData = { date: "2026-10-02" }, weekOffset = 3, todayCheckedAt = 0, loads = 0;
      function loadToday() { loads++; }
    """, """
      const at = iso => { Date.now = () => Date.parse(iso); };
      const out = [];
      at("2026-10-02T20:59:00Z"); out.push(checkTodayFresh(), loads);          // 23:59 МСК — ещё сегодня
      at("2026-10-02T21:01:00Z"); out.push(checkTodayFresh(), loads, weekOffset);  // 00:01 МСК — новый день
      out.push(checkTodayFresh());                                              // сразу ещё раз — не спамим
      at("2026-10-02T21:02:30Z"); out.push(checkTodayFresh(), loads);           // через минуту — снова
      todayData.date = "2026-10-03"; out.push(checkTodayFresh());
      console.log(JSON.stringify(out));
    """)
    assert res == [False, 0, True, 1, 0, False, True, 2, False]
    home = JS["js/home.js"]
    assert "checkTodayFresh()" in _js_fn(home, "refreshStatuses")
    assert 'document.addEventListener("visibilitychange"' in home and 'tg.onEvent("activated", refreshStatuses)' in home


@node
def test_home_hero_says_schedule_failed():
    # находка 5: schedule_ok=false — было крупно «Сегодня пар нет — отдыхай»
    failed, calm = _front("js/home.js", ["renderHero", "heroFailed"], "let todayData;", """
      const hero = document.getElementById("hero");
      todayData = { schedule_ok: false, lessons: [], tomorrow_first: null }; renderHero();
      const failed = [hero.className, hero.innerHTML];
      todayData = { schedule_ok: true, lessons: [], tomorrow_first: null }; renderHero();
      console.log(JSON.stringify([failed, [hero.className, hero.innerHTML]]));
    """)
    assert failed[0] == "hero err" and "не загрузилось" in failed[1] and 'onclick="loadToday()"' in failed[1]
    assert "отдыхай" not in failed[1] and "пар нет" not in failed[1]
    assert calm[0] == "hero calm" and "отдыхай" in calm[1]
    assert ".hero.err {" in CSS and ".hero .h-retry {" in CSS


@node
def test_home_cold_start_error_still_draws_day_chips():
    # находка 14: /api/today упал на холодном старте без снимка — полоски дней не было
    chips, cls, html = _front("js/home.js", ["loadToday", "heroFailed"], """
      let todayData = null, chipsDate = null, chips = 0;
      const weekCache = {};
      function setGreeting() {}
      function readHomeSnap() { return null; }
      function renderToday() {}
      function saveHomeSnap() {}
      function rerenderToday() {}
      function renderDayChips() { chips++; chipsDate = todayData ? todayData.date : null; }
    """, """
      const p = loadToday(); await tick();
      calls.find(c => c.path === "/api/me").res({ first_name: "Никита" });
      calls.find(c => c.path === "/api/today").rej(new Error("сеть")); await p;
      const hero = document.getElementById("hero");
      console.log(JSON.stringify([chips, hero.className, hero.innerHTML]));
    """)
    assert chips == 1 and cls == "hero err" and "Повторить" in html and "сеть" in html


@node
def test_selecting_day_ignores_buttons_of_old_strip():
    # находка 10: после пересоздания полоски пары старой кнопки вставали в другую неделю
    rendered, html = _front("js/home.js", ["selectDay"], """
      let todayData = null;
      const dayCache = {}, rendered = [];
      function renderDay(list, d) { rendered.push(d.date); }
      function loadLessonScores() {}
      function scrollToWeek() {}
      const btn = d => { const b = mkEl(d); b.dataset.date = d; return b; };
    """, """
      let strip = [btn("2026-10-05"), btn("2026-10-06")];
      document.querySelectorAll = () => strip;
      const old = strip[1];
      selectDay(old, true);                                  // пары вт грузятся…
      strip = [btn("2026-10-12")]; old.isConnected = false;  // …а неделю уже листнули
      selectDay(strip[0], true);
      calls[1].res({ date: "2026-10-12", lessons: [] }); await tick();
      calls[0].res({ date: "2026-10-06", lessons: [] }); await tick();
      const b3 = btn("2026-10-13"); strip = [b3]; selectDay(b3, true);
      b3.isConnected = false; strip = [btn("2026-10-20")]; selectDay(strip[0], true);
      calls[3].res({ date: "2026-10-20", lessons: [] }); await tick();
      calls[2].rej(new Error("сеть")); await tick();         // ошибка старого — тоже мимо
      console.log(JSON.stringify([rendered, document.getElementById("day-lessons").innerHTML]));
    """)
    assert rendered == ["2026-10-12", "2026-10-20"] and "Не загрузилось" not in html


@node
def test_notify_fast_taps_keep_every_day():
    # находка 6: Пн-Вт-Ср подряд — часть нажатий терялась (POST нёс устаревший список)
    res = _front("js/more.js", ["saveNotify", "toggleNotifyDay"], """
      let notifyState = { subscribed: true, prefs: { morning_days: [0, 1, 2] } };
      let notifyQueue = Promise.resolve(), notifyPending = 0, renders = 0;
      function renderNotify() { renders++; }
    """, """
      toggleNotifyDay("morning_days", 3);
      toggleNotifyDay("morning_days", 4);                      // второе — до ответа на первое
      const now = notifyState.prefs.morning_days.slice(), drawn = renders;
      await tick();
      const inFlight = calls.length;
      calls[0].res({ subscribed: true, prefs: { morning_days: [0, 1, 2, 3] } }); await tick();
      const second = calls[1].body.prefs.morning_days, mid = notifyState.prefs.morning_days.slice();
      calls[1].res({ subscribed: true, prefs: { morning_days: [0, 1, 2, 3, 4] } }); await tick();
      console.log(JSON.stringify([now, drawn, inFlight, second, mid, notifyState.prefs.morning_days]));
    """)
    full = [0, 1, 2, 3, 4]
    assert res == [full, 2, 1, full, full, full]        # сразу у себя, запросы — по одному


@node
def test_file_from_link_resets_file_search():
    # находка 7: источник из ответа ИИ при открытом поиске по файлам — «Файл не найден»
    toasts, query, subject, box = _front("js/files.js", ["openFileFromLink"], """
      let fileQuery = "лекция", fileSubject = null, fileCat = "", fileIndex = {}, fileSearchTimer = null;
      function switchTab() {}
      async function loadFiles(q) { if (q !== undefined) fileQuery = q; fileIndex = fileQuery ? {} : { 5: { id: 5, subject: "Анализ данных" } }; }
      function renderFiles() {}
    """, """
      document.getElementById("file-search").value = "лекция";
      await openFileFromLink(5);
      console.log(JSON.stringify([toasts, fileQuery, fileSubject, document.getElementById("file-search").value]));
    """)
    assert (toasts, query, subject, box) == ([], "", "Анализ данных", "")


@node
def test_old_target_error_does_not_cover_newer_one():
    # находка 11: ошибка запроса по Иванову перерисовывала открытого после него Петрова
    cur, html = _front("js/search.js", ["openTarget"], """
      const TARGET_KIND = { 1: ["users", "Группа"], 2: ["user", "Преподаватель"], 3: ["door", "Аудитория"] };
      let targetCurrent = null, targetData = null, targetWeekIdx = 0, pinnedTargets = [];
      function rememberTarget() {}
      function isPinned() { return false; }
      function setPinButton() {}
      function openNextLessonDay() {}
      function renderTargetWeek() { document.getElementById("target-lessons").innerHTML = "неделя " + targetCurrent.title; }
      const capyEmpty = t => t;
    """, """
      openTarget(2, 1, "Иванов"); openTarget(2, 2, "Петров");
      calls[1].res({ pinned: false, weeks: [] }); await tick();
      calls[0].rej(new Error("сеть")); await tick();
      console.log(JSON.stringify([targetCurrent.title, document.getElementById("target-lessons").innerHTML]));
    """)
    assert (cur, html) == ("Петров", "неделя Петров")


@node
def test_switch_tab_takes_target_back_handler_off():
    # находка 15: closeTarget оставался на «Назад» и закрывал скрытый экран поиска из чата
    away, back = _front("js/core.js", ["switchTab"], """
      function loadDeadlines() {} function loadFiles() {} function renderRecent() {}
      function loadPins() { return Promise.resolve(); } function syncNavHeight() {} function scrollChatToEnd() {}
      function closeFolder() {} function sdoBack() {} function closeTarget() {}
    """, """
      const log = backLog();
      document.getElementById("target-view").style.display = "block";
      switchTab("chat"); const away = log.splice(0);
      switchTab("search"); const back = log.splice(0);
      console.log(JSON.stringify([away, back]));
    """)
    assert "off:closeTarget" in away and "on:closeTarget" not in away and away[-1] == "hide"
    assert back[-2:] == ["on:closeTarget", "show"] and back.index("off:closeTarget") < back.index("on:closeTarget")


@node
def test_back_button_restored_on_attendance_screen():
    # находка 9: после меню «Ещё» на экране «Посещения» пропадала «Назад» Telegram
    main = JS["js/main.js"]
    fn = re.search(r"  function restoreBack\(\) \{.*?\n  \}\n", main, re.S).group(0)
    script = FRONT_PRELUDE + "function sdoBack() {} function closeTarget() {} function syncFileBack() {}\n" + fn + """
      const log = backLog();
      document.querySelector = s => s === ".view.active" ? { id: "view-pos" } : null;
      restoreBack();
      console.log(JSON.stringify(log));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["off:sdoBack", "on:sdoBack", "show"]
    # те же экраны СДО, что подсвечивают вкладку в switchTab
    tabs = re.search(r'\["sdo", ((?:"\w+", )*"\w+")\]\.includes\(name\)', JS["js/core.js"]).group(1)
    for v in re.findall(r'"(\w+)"', tabs):
        assert '"view-' + v + '"' in fn, v


def test_own_remind_time_is_moscow():
    # находка 16: поле своего времени напоминания — время сервера (МСК), а не телефона
    remind = _js_fn(JS["js/deadlines.js"], "renderRemind")
    assert 'type="datetime-local"' in remind and "по Москве" in remind


def test_onclick_built_in_js_call_defined_functions():
    # находка 17: onclick-строки, собранные в JS (markLecture, openTk('todo'), tapWork, setGoal…),
    # не проверялись — опечатка в имени ломала кнопку молча
    defined = set(re.findall(r'^(?:async\s+)?function\s+(\w+)\s*\(', ALL_JS, re.M))
    builtins = {"String", "Number", "JSON", "event", "this"}
    called = set()
    # onclick="…" внутри строк JS: всё до закрывающей кавычки атрибута, со всеми вызовами в нём
    for chunk in re.findall(r'onclick=\\?"(.*?)\\?"', ALL_JS):
        called |= set(re.findall(r'(?<![\w.])([A-Za-z_]\w*)\s*\(', chunk))
    # готовые обработчики строкой, которые подставляются в onclick: "openTk('todo')", 'openPos()'
    called |= set(re.findall(r'''["'](\w+)\((?:\\?'\w*\\?')?\)["']''', ALL_JS))
    assert {"markLecture", "tapWork", "setGoal", "openTk", "openPos", "openSubject"} <= called
    missing = called - defined - builtins
    assert not missing, f"нет функций: {sorted(missing)}"


def test_share_bot_sends_site_link():
    # «Позвать» — пересылка в Telegram ссылки на сайт /about с подписью
    fn = JS["js/more.js"].split("function shareBot()")[1].split("\n}\n")[0]
    assert 'location.origin + "/about"' in fn and "t.me/share/url?url=" in fn and "tg.openTelegramLink(url)" in fn


@pytest.mark.asyncio
async def test_sdo_guide_link_from_published_post(db, monkeypatch):
    """Экран «Подключить СДО» — ссылка на гайд в канале: номер сообщения из
    channel:published, канал из CHANNEL_URL; не выпущен — кнопки нет."""
    import config
    import webapp.server as server
    from channel_posts import mark_published
    monkeypatch.setattr(config, "CHANNEL_URL", "https://t.me/uiboshki_dev")
    assert await server._guide_link() == ""
    await mark_published(server.GUIDE_SLUG, [23])
    assert await server._guide_link() == "https://t.me/uiboshki_dev/23"
    monkeypatch.setattr(config, "CHANNEL_URL", "@uiboshki_dev")
    assert await server._guide_link() == "https://t.me/uiboshki_dev/23"
    assert "(GUIDE_URL ?" in JS["js/more.js"] and "const GUIDE_URL = APP_CONFIG.guide" in JS["js/core.js"]
    assert (server.STATIC_DIR.parent.parent / "channel" / "posts" / server.GUIDE_SLUG).is_dir()


# ── Ночь 09.10: Капибара везде ──
def test_more_install_sheet_tells_about_pwa():
    """«Ещё → Установить» — лист про Telegram, PWA (uiboshki.ru/app), компьютер
    и своё приложение, а не только ярлык Telegram (владелец, 09.10)."""
    assert 'toggleMore(false); openPlatforms()"' in _more_menu()
    assert 'id="platforms-sheet"' in HTML and 'id="platforms-body"' in HTML
    js = JS["js/more.js"]
    body = js.split("function openPlatforms()")[1].split("async function copyAppLink")[0]
    for text in ("uiboshki.ru/app", "Telegram", "На компьютере", "Android и iPhone", "addToHome()", "copyAppLink()"):
        assert text in body, text
    assert 'APP_URL = "https://www.uiboshki.ru/app"' in js
    assert "laptop:" in JS["js/icons.js"]
    assert 'id: "v5.50"' in js and "uiboshki.ru/app" in js.split("const NEWS")[1].split("};")[0]

# ── Ночь 09.10: сайт ──
def test_site_dark_spinner_keeps_accent():
    """Тёмная тема сайта: «border:1px solid …» в тёмном правиле .spinner сбрасывал
    border-top-color:var(--accent) — спиннер «Ищем в расписании…» был ровным
    кольцом без бегущего куска. Генератор повторяет цвет стороны после рамки."""
    import importlib.util
    root = STATIC.parent.parent
    spec = importlib.util.spec_from_file_location("site_dark", root / "tools" / "site_dark.py")
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)
    out = sd.build(".spinner{display:inline-block;border:1px solid #bdb7aa;border-top-color:var(--accent);width:13px}")
    assert re.search(r"\.spinner\{border:1px solid #[0-9a-f]{6};border-top-color:var\(--accent\)\}", out), out
    css = (STATIC / "site" / "site.css").read_text(encoding="utf-8")
    assert ".spinner{border:1px solid #60594a;border-top-color:var(--accent)}" in css
    # номера возможностей 01–04 одной ширины — заголовки не пляшут на пару пикселей
    assert ".feature-number{font-variant-numeric:tabular-nums}" in css


def test_server_pages_wrap_long_text():
    """Страницы, которые сервер отдаёт сам: длинное имя аккаунта VK/Яндекс и
    длинный вопрос/код в слепом тесте ИИ не дают прокрутки вбок на телефоне;
    страница входа — в теме телефона (тёмная — не белый экран)."""
    import ai_bench
    from webapp.routes.auth import _page
    html = _page("Привязать VK ID?", "А" * 200).body.decode()
    assert "overflow-wrap:anywhere" in html and "name='color-scheme' content='light dark'" in html
    page = ai_bench.page([{"kind": "Вопрос", "title": "x" * 300, "subject": "", "answers": [
        {"text": "```\n" + "1" * 300 + "\n```", "model": m, "cost": 0, "secs": 1} for m in "ab"]}], {"a": "A", "b": "B"})
    assert "h2{font-size:16px;margin:4px 0 10px;overflow-wrap:anywhere}" in page and ".t pre{white-space:pre-wrap}" in page


def test_demo_news_seen_follows_current_release():
    """Демо на сайте: «Что нового» не всплывает — прочитан текущий NEWS.id, а не
    зашитый номер (после смены id на v5.50 лист вылез поверх демо)."""
    demo = (STATIC / "site" / "demo.js").read_text(encoding="utf-8")
    assert 'news_seen: "v' not in demo and "NEWS.id" in demo


# ── Ночь 09.10: зона B (СДО, файлы, чат, «Ещё» и листы) ──

def _night_b_css():
    return CSS.split("Ночь 09.10: СДО, файлы, чат, листы")[1]


def test_chat_code_block_scrolls_inside_bubble():
    # блок кода в ответе ИИ раздвигал страницу вбок (320px: ширина 1149px)
    rule = re.search(r"\.msg pre \{([^}]*)\}", _night_b_css()).group(1)
    assert "overflow-x: auto" in rule and "max-width: 100%" in rule
    # и без лишних пустых строк вокруг блока
    assert r'html.replace(/\n*(<pre>[\s\S]*?<\/pre>)\n*/g, "$1")' in JS["js/chat.js"]


def test_no_emoji_in_reasoning_summary():
    # «Ход мыслей» был с эмодзи мозга — в интерфейсе эмодзи не используем
    assert ".think summary::before { content: none; }" in _night_b_css()


def test_subject_category_name_not_under_bar():
    # 320px: «Посещаемость» налезала на мини-полоску — полоска сжимается, а не имя
    css = _night_b_css()
    assert ".cat-row .nm { min-width: auto; }" in css
    assert re.search(r"\.cat-row \.mb \{[^}]*flex: 0 1 70px", css)


def test_long_subject_back_button_one_line():
    # «‹ Анализ и диагностика финансово-хозяйственной…» шёл тремя строками по центру
    rule = re.search(r"#tk-back, #pos-back \{([^}]*)\}", _night_b_css()).group(1)
    assert "text-overflow: ellipsis" in rule and "white-space: nowrap" in rule and "text-align: left" in rule


def test_fullscreen_sheets_clear_home_bar_and_top_buttons():
    # полный экран Telegram: env() там 0 — низ листа (кнопка «Загрузить в СДО»)
    # уходил под полоску «Домой», верх длинного листа — под кнопки Telegram
    rule = re.search(r"html\.fullscreen \.sheet \{([^}]*)\}", _night_b_css()).group(1)
    assert "var(--safe-bottom" in rule and "var(--safe-top" in rule
    # своя max-height у листа «Безопасность» (с id) перебивала бы правило
    assert "#security-sheet .sheet { max-height" not in CSS
    # открытый лист затемняет и полосу под часами (светлая тема — белая полоса)
    assert "html.fullscreen body:has(.sheet-backdrop.open, .more-backdrop.open)::before { display: none; }" in CSS


def test_onboarding_fits_short_screen():
    # 320×568 в полном экране: «Дальше» уезжало за нижний край
    css = _night_b_css()
    assert ".onboard { overflow-y: auto; }" in css and "@media (max-height: 640px)" in css


# ── Ночь 09.10: WebApp, часть A ──

def test_search_filters_do_not_push_page_sideways():
    # строка фильтров поиска уходила вправо на 18px при отступе main 14px —
    # вся вкладка «Поиск» прокручивалась вбок на 4px (стенд, все размеры)
    main_pad = re.search(r"\n  main \{ padding: \d+px (\d+)px", CSS).group(1)
    m = re.search(r"#target-types \{[^}]*margin-right: -(\d+)px; padding-right: (\d+)px", CSS)
    assert m and m.group(1) == m.group(2) == main_pad


def test_deadline_sheet_date_and_time_share_row():
    # 320px: поле времени вылезало за край листа «Новый дедлайн»
    assert re.search(r"\.sheet \.row2 > \* \{ flex: 1 1 0; min-width: 0; \}", CSS)


def test_calm_hero_text_clears_capybara():
    # «завтра в 14:20»: название пары и преподаватель уезжали под капибару
    assert re.search(r"\.hero\.calm \.h-title, \.hero\.calm \.h-meta \{ padding-right: 5\dpx; \}", CSS)


def test_sheets_respect_telegram_safe_area():
    # полный экран Telegram: env() пуст — кнопка листа стояла на полоске «Домой»
    rule = re.search(r"html\.fullscreen \.sheet \{(.*?)\}", CSS, re.S).group(1)
    assert "var(--safe-bottom" in rule and "var(--safe-top" in rule


def test_nav_height_follows_tab_bar_size():
    # safeAreaChanged приходит после загрузки — --nav-h оставался старым,
    # «＋» дедлайнов вставал на нижнюю панель
    core = JS["js/core.js"]
    assert re.search(r"new ResizeObserver\(\(\) => \{[^}]*syncNavHeight\(\)[^}]*\}\)\s*\.observe\(document\.querySelector\(\"nav\.tabs\"\), \{ box: \"border-box\" \}\)", core)


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_home_deadline_tile_cuts_on_word_with_ellipsis():
    # плитка «Дедлайны»: было «Лабораторная работа 3 · Анализ и диагнос · просрочен»
    fn = re.search(r"function shortText\(s, max\) \{.*?\n\}", JS["js/home.js"], re.S).group(0)
    assert "shortText(dl.soon[0].subject, 40)" in JS["js/home.js"]
    src = fn + "\nconsole.log(JSON.stringify([" \
        "shortText('Лабораторная работа 3 · Анализ и диагностика финансово-хозяйственной', 40)," \
        "shortText('Курсовая: глава 1', 40), shortText('', 40)]));"
    res = subprocess.run(["node", "-e", src], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["Лабораторная работа 3 · Анализ и…", "Курсовая: глава 1", ""]


def test_wide_screen_keeps_phone_column():
    # PWA на компьютере: пары и нижняя панель растягивались на все 1280px
    block = CSS.split("@media (min-width: 720px)")[1]
    for sel in ("header.top, main { max-width: var(--col)", "nav.tabs { padding-left: calc(var(--col-side)",
                ".sheet { max-width: var(--col)", ".fab { right: calc(var(--col-side)"):
        assert sel in block


def test_target_week_arrows_off_until_weeks_loaded():
    # экран «МИРЭА не отвечает»: стрелки недели горели, а нажатие ничего не делало
    fn = JS["js/search.js"].split("async function openTarget(")[1].split("const data = await api(")[0]
    assert 'getElementById("tw-prev").disabled = document.getElementById("tw-next").disabled = true' in fn


# ── Ревью безопасности 09.10: токен из адреса — только своему входу ──
def test_token_from_url_only_after_own_oauth_start():
    """/app#token=<чужой> по присланной ссылке переключал человека в чужой аккаунт.
    Токен из адреса берётся, только если startOAuth начат в этом браузере."""
    core = JS["js/core.js"]
    head = core.split("const APP_TOKEN")[0]
    assert "if (oauthPending()) saveToken(" in head
    assert 'localStorage.setItem("uib_oauth_at"' in core.split("async function startOAuth")[1].split("\n}\n")[0]


def test_pwa_login_shows_pick_number():
    """Вход через бота: экран «Войти» показывает число, которое надо нажать в Telegram."""
    body = JS["js/core.js"].split("function showPending")[1].split("\n}\n")[0]
    assert "login-pick" in body and "p.pick" in body
    assert ".login-pick" in CSS


def test_pwa_login_opens_telegram_directly_and_survives_restart():
    """PWA с экрана «Домой»: t.me открывался во встроенном браузере, после
    «Да, это я» вместо числа — белая страница, и так по кругу (Никита, 14.10).
    На телефоне в режиме приложения — tg://, начатый вход переживает перезапуск."""
    core = JS["js/core.js"]
    open_bot = core.split("function openBot")[1].split("\n}\n")[0]
    assert "STANDALONE_PHONE && p.tg" in open_bot and "location.href = p.tg" in open_bot
    start = core.split("async function startLogin")[1].split("async function pollLogin")[0]
    assert "res.tg_link" in start and "savePending(p)" in start and "openBot(p)" in start
    assert "window.open(res.link" not in start
    show = core.split("function showLogin")[1].split("\n}\n")[0]
    assert "readPending()" in show and "showPending(pending)" in show
    poll = core.split("async function pollLogin")[1].split("\n}\n")[0]
    assert poll.count("savePending(null)") == 2          # вошёл или код сгорел — забыть
    assert ".login-web" in CSS


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_plus_sheet_invite_limit_from_server():
    # Никита 18.10: «максимум 3 человека по приглашению дают подписку» — число с сервера (ref_max)
    import json
    more = JS["js/more.js"]
    fn = re.search(r"function inviteText\(.*?\n}\n", more, re.S).group(0)

    def run(inv):
        res = subprocess.run(["node", "-e", fn + "console.log(JSON.stringify(inviteText(%s)))" % _js_arg(inv)],
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        return json.loads(res.stdout)
    base = {"friend_days": 3, "bonus_days": 7, "came": 2}
    t = run({**base, "ref_max": 3, "ref_counted": 1})
    assert "вам обоим +7 дней" in t and "максимум за 3 друзей, засчитано 1 из 3" in t
    t = run({**base, "ref_max": 3, "ref_counted": 3})
    assert t.startswith("Ты уже позвал 3 друзей — бонус за приглашения закончился, друзьям дни по-прежнему дают")
    assert "вам обоим" not in t
    assert "максимум" not in run(base)                                       # старый сервер — без лимита
    assert "3" not in fn.replace("inv.", "")                                  # тройку фронт у себя не держит
    assert "secItem(\"users\", \"Позови друга\", inviteText(inv))" in more


def test_plus_sheet_early_supporter_label():
    # Никита 18.10: метка оплативших по цене первых — «Early Supporter», латиницей
    more = JS["js/more.js"]
    assert "<i>Early Supporter</i>" in more and "У тебя метка Early Supporter" in more
    assert "Основател" not in more


def test_plus_sheet_price_on_one_line_and_no_double_dot():
    # робот-скриншотер 18.10: «649 ₽» переносился, у рангов «14 дн..»
    assert re.search(r"\.plus-price b \{[^}]*white-space: nowrap", CSS)
    more = JS["js/more.js"]
    assert '" дн."' in more and 'ranks + ".")' not in more


def test_plus_tag_whole_and_invite_own_icon():
    # робот 18.10: «Early Supporter» ломался пополам на две строки; у «Позвать» был значок «Моей группы»
    assert re.search(r"\.plus-price i \{[^}]*display: inline-block;[^}]*white-space: nowrap", CSS)
    assert "&nbsp;₽</s>" in JS["js/more.js"]
    assert re.search(r'shareBot\(\)"><span class="sq t-share"><svg class="ico" aria-hidden="true"><use href="#i-invite"/>',
                     HTML)
    assert "  invite: '" in JS["js/icons.js"]


def test_think_note_wraps_not_cut():
    # робот 18.10: «следующий вопрос решит DeepS…» обрезалось — подсказка переносится, а не режется
    rule = re.search(r"\.think-note \{([^}]*)\}", CSS).group(1)
    assert "nowrap" not in rule and "ellipsis" not in rule
