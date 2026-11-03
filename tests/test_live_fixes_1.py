"""Правки по живому тесту 02.10: пара → сразу «Текущий контроль» (без
экрана предмета), листы прокручиваются, капибара в пустом поиске,
клавиатуру убирает «Ввод» и нажатие мимо поля, понятный текст знакомства."""
from pathlib import Path
import re

JS = "webapp/static/js/"


def _src(name):
    return Path(JS + name).read_text(encoding="utf-8")


def _body(src, name):
    start = src.index(f"function {name}(")
    return src[start:src.index("\n}\n", start)]


def test_lesson_opens_tk_directly():
    body = _body(_src("sdo.js"), "openLessonSdo")
    assert "openTk()" in body and 'showSdoView("tk")' in body
    assert "await openSubject" not in body        # раньше: экран предмета, ожидание, потом ТК


def test_sheets_scroll():
    css = Path("webapp/static/app.css").read_text(encoding="utf-8")
    sheet = re.search(r"\.sheet \{([^}]*)\}", css).group(1)
    assert "overflow-y: auto" in sheet and "max-height" in sheet


def test_empty_search_capybara_and_keyboard():
    assert 'capyEmpty("Ничего не нашлось"' in _src("search.js")
    core = _src("core.js")
    assert "blur()" in core and '"touchstart"' in core
    assert 'id="target-search" enterkeyhint="search"' in Path("webapp/static/index.html").read_text(encoding="utf-8")


def test_onboarding_search_text():
    more = _src("more.js")
    assert "Пары любого преподавателя, группы или аудитории МИРЭА" in more
    assert "сразу в её баллы" not in more


def test_tab_switch_hides_keyboard():
    core = _src("core.js")
    assert "blur()" in _body(core, "switchTab")
    assert '.closest(".tabs")' in core
