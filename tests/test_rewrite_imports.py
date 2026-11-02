"""tools/rewrite_imports.py: импорты старых имён → kapibara/, имена файлов не трогаем."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("rewrite_imports", ROOT / "tools" / "rewrite_imports.py")
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)

MOVED = {"config": "kapibara.core.config", "gemini_solver": "kapibara.features.ai.gemini"}


def test_imports_keep_local_name():
    src = "import config\nimport gemini_solver as g\nfrom config import BOT_TOKEN\n\n\ndef f():\n    import gemini_solver\n"
    assert ri.rewrite(src, MOVED) == (
        "from kapibara.core import config\nfrom kapibara.features.ai import gemini as g\n"
        "from kapibara.core.config import BOT_TOKEN\n\n\ndef f():\n    from kapibara.features.ai import gemini as gemini_solver\n")


def test_patch_strings_but_not_file_names():
    src = 'p("config.BOT_TOKEN")\nopen("config.json")\nx = "гемини: gemini_solver.py"\n'
    out = ri.rewrite(src, MOVED)
    assert '"kapibara.core.config.BOT_TOKEN"' in out
    assert '"config.json"' in out and "gemini_solver.py" in out
