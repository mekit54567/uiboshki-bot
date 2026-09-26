"""
Интерфейс WebApp без браузера: index.html разбит на app.css и js/*.js (по
вкладкам), и ошибка в любом из них ломает приложение целиком — у всех и
сразу. Раньше это ловилось только скриншотами. Здесь дешёвые проверки,
которые гоняются в CI: синтаксис JS, что всё подключено и отдаётся, что
id и onclick из разметки существуют, что части не объявляют одно и то же.
"""
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
