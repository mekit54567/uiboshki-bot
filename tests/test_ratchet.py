"""tools/ratchet.py: цифры плохих мест в коде могут только уменьшаться."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ratchet", ROOT / "tools" / "ratchet.py")
ratchet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchet)


def _tree(tmp_path, files):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return ratchet.measure(tmp_path)


def test_repo_matches_ceiling():
    import json
    now = ratchet.measure(ROOT)
    ceiling = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))
    assert ratchet.compare(now, ceiling) == ([], []), "python tools/ratchet.py — что изменилось"


def test_counts_broad_and_silent_excepts(tmp_path):
    m = _tree(tmp_path, {"a.py": (
        "try:\n    x = 1\nexcept Exception:\n    pass\n"
        "try:\n    x = 1\nexcept:\n    x = 2\n"
        "try:\n    x = 1\nexcept (ValueError, BaseException):\n    x = 2\n"
        "try:\n    x = 1\nexcept ValueError:\n    pass\n")})
    assert m["broad_except"] == 3
    assert m["silent_except"] == 2


def test_counts_cycles_including_lazy_imports(tmp_path):
    m = _tree(tmp_path, {
        "a.py": "import b\n",
        "b.py": "def f():\n    from a import x\n",       # цикл через импорт в функции
        "c.py": "import a\n",                              # просто зависит — не в клубке
        "handlers/__init__.py": "",
        "handlers/h.py": "from handlers import g\n",
        "handlers/g.py": "import handlers.h\n",
    })
    assert m["cycle_modules"] == 4
    assert m["root_py_files"] == 3


def test_compare_is_a_ratchet():
    ceiling = {"broad_except": 10}
    assert ratchet.compare({"broad_except": 10}, ceiling) == ([], [])
    worse, better = ratchet.compare({"broad_except": 11}, ceiling)
    assert worse and not better
    worse, better = ratchet.compare({"broad_except": 9}, ceiling)
    assert better and not worse                      # лучше — потолок надо опустить
