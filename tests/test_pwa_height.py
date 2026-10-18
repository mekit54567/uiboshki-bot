"""PWA на iPhone с экрана «Домой» (Никита 17.10, скрин): страница под часами,
а iOS отдаёт высоту окна без них — снизу полоса, приложение обрезано. Скрипт
uib-height растягивает окно Flutter на весь экран; в браузере и на Android —
как было."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parent.parent / "app" / "web" / "index.html"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15"


def _run(standalone, ua, inner=(393, 793), screen=(393, 852)):
    script = re.search(r'<script id="uib-height">(.*?)</script>', HTML.read_text(), re.S).group(1)
    js = f"""
      class Element {{}}
      Object.defineProperty(Element.prototype, "clientHeight", {{ configurable: true, get() {{ return this._h; }} }});
      const de = new Element(); de._h = {inner[1]}; de.clientWidth = {inner[0]};
      const styles = [];
      const document = {{
        documentElement: de,
        createElement: () => ({{ textContent: "" }}),
        head: {{ appendChild: (s) => styles.push(s) }},
      }};
      const window = {{ navigator: {{ standalone: {json.dumps(standalone)} }}, addEventListener() {{}} }};
      const navigator = {{ userAgent: {json.dumps(ua)} }};
      const screen = {{ width: {screen[0]}, height: {screen[1]} }};
      {script}
      console.log(JSON.stringify({{ h: de.clientHeight, css: styles.map((s) => s.textContent) }}));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


needs_node = pytest.mark.skipif(not shutil.which("node"), reason="нет node")


@needs_node
def test_iphone_home_screen_fills_whole_screen():
    r = _run(True, IPHONE)
    assert r["h"] == 852
    assert r["css"] == ["body{bottom:auto!important;height:852px!important}"]


@needs_node
def test_iphone_landscape_uses_short_side():
    r = _run(True, IPHONE, inner=(852, 360))
    assert r["h"] == 393


@needs_node
def test_browser_and_android_untouched():
    assert _run(False, IPHONE) == {"h": 793, "css": []}
    assert _run(True, "Mozilla/5.0 (Linux; Android 14)") == {"h": 793, "css": []}
