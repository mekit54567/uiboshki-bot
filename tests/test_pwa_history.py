"""PWA на iPhone (Никита 17.10, видео): свайп «назад» от края уводил iOS в
историю браузера, и экран секунды был чёрным. На iPhone с экрана «Домой»
Flutter не заводит записей в истории — свайп ловит сам Flutter."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parent.parent / "app" / "web" / "index.html"


def _run(standalone):
    script = re.search(r'<script id="uib-history">(.*?)</script>', HTML.read_text(), re.S).group(1)
    js = f"""
      const calls = [];
      const history = {{
        pushState: () => calls.push("push"),
        replaceState: () => calls.push("replace"),
      }};
      const window = {{ navigator: {{ standalone: {json.dumps(standalone)} }}, history }};
      {script}
      window.history.pushState({{}}, "", "/app/");
      console.log(JSON.stringify(calls));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(not shutil.which("node"), reason="нет node")
def test_iphone_home_screen_has_no_browser_history():
    assert _run(True) == ["replace"]


@pytest.mark.skipif(not shutil.which("node"), reason="нет node")
def test_android_and_browser_keep_back_button():
    assert _run(False) == ["push"]
    assert _run(None) == ["push"]
