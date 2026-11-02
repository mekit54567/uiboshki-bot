"""tools/check_imports.py: импорты внутри функций проверяются без запуска кода."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_imports", ROOT / "tools" / "check_imports.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


def _tree(tmp_path, files):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return ci.check(tmp_path)[1]


def test_repo_has_no_broken_imports():
    n, errors = ci.check(ROOT)
    assert n > 100
    assert errors == []


def test_catches_missing_name_in_lazy_import(tmp_path):
    errors = _tree(tmp_path, {
        "a.py": "def f():\n    from b import gone\n    return gone\n",
        "b.py": "def here():\n    pass\n",
    })
    assert errors == ["a.py:2: в b нет имени gone"]


def test_catches_missing_module(tmp_path):
    errors = _tree(tmp_path, {
        "a.py": "def f():\n    import pkg.nope\n",
        "pkg/__init__.py": "",
    })
    assert errors == ["a.py:2: нет модуля pkg.nope"]


def test_accepts_submodules_namespace_and_conditional_names(tmp_path):
    errors = _tree(tmp_path, {
        "a.py": ("from pkg import sub\nfrom web import deps\nfrom web.deps import X\n"
                 "from b import fast\nimport json\n"),
        "pkg/__init__.py": "",
        "pkg/sub.py": "",
        "web/deps.py": "X = 1\n",
        "b.py": "try:\n    from json import loads as fast\nexcept ImportError:\n    fast = None\n",
    })
    assert errors == []
