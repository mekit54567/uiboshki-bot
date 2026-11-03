"""Храповик качества кода (CI: «python tools/ratchet.py»).

Плохих мест в коде много (широкие except, клубок импортов, плоский корень),
и чинить всё разом опасно для прода. Поэтому CI запоминает текущие цифры в
tools/ratchet.json и пускает их только вниз, как храповик крутится в одну
сторону:
  - стало больше — CI красный: новый код должен быть чище старого;
  - стало меньше — тоже красный, пока не обновишь потолок
    («python tools/ratchet.py --update» и закоммить ratchet.json), иначе
    следующий PR мог бы молча вернуть цифру назад.

Что считаем (код сервера: корень, kapibara/, handlers/, database/, webapp/):
  broad_except   — except Exception / BaseException / голый except;
  silent_except  — обработчик, в котором только pass (ошибка пропадает);
  cycle_modules  — модули, сцепленные взаимными импортами в клубок
                   (с импортами внутри функций);
  root_py_files  — .py в корне репозитория (план — пакет kapibara/);
  ruff_debt      — замечания Ruff из RUFF_DEBT по всему репозиторию: правила,
                   которые ловят баги, но в старом коде ещё есть (ревью 03.11).
                   Правило дошло до нуля — переносим в select в ruff.toml,
                   тогда CI красный от первого же нового случая.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tools" / "ratchet.json"
SERVER_DIRS = ("kapibara", "handlers", "database", "webapp")

# B — bugbear (замыкание на переменной цикла, raise без from, zip без strict…),
# ASYNC — блокирующие вызовы внутри async (бот замирает для всех), SIM/C4/PERF/UP
# — лишний и устаревший код. ASYNC109 (параметр timeout у async-функции) — не баг.
RUFF_DEBT = ["B", "ASYNC", "SIM", "PERF", "UP"]
RUFF_DEBT_IGNORE = ["ASYNC109"]


def ruff_debt(root: Path) -> int:
    out = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--select", ",".join(RUFF_DEBT),
         "--ignore", ",".join(RUFF_DEBT_IGNORE), "--exit-zero", "--output-format", "json", "--no-cache"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    return len(json.loads(out.stdout or "[]"))


def server_files(root: Path) -> list[Path]:
    files = list(root.glob("*.py"))
    for d in SERVER_DIRS:
        files += [p for p in (root / d).rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(files)


def module_name(p: Path, root: Path) -> str:
    parts = list(p.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_broad(h: ast.ExceptHandler) -> bool:
    if h.type is None:
        return True
    types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return any(isinstance(t, ast.Name) and t.id in ("Exception", "BaseException") for t in types)


def _cycle_modules(graph: dict[str, set[str]]) -> int:
    """Сколько модулей сидит в компонентах сильной связности размером > 1 (Тарьян)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    total = 0
    counter = 0
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))

    def visit(v: str) -> None:
        nonlocal counter, total
        index[v] = low[v] = counter
        counter += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            size = 0
            while True:
                w = stack.pop()
                on.discard(w)
                size += 1
                if w == v:
                    break
            if size > 1:
                total += size

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return total


def _redirect_target(p: Path) -> str | None:
    """«import kapibara.x.y as _m; sys.modules[__name__] = _m» → kapibara.x.y."""
    text = p.read_text(encoding="utf-8")
    if "sys.modules[__name__]" not in text:
        return None
    tree = ast.parse(text)
    imported = {a.asname: a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names if a.asname}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and ast.unparse(n.targets[0]) == "sys.modules[__name__]"                 and isinstance(n.value, ast.Name):
            return imported.get(n.value.id)
    return None


def measure(root: Path) -> dict[str, int]:
    files = server_files(root)
    names = {module_name(p, root): p for p in files}
    # Переехавший модуль (ADR 0003): старое имя — переадресация на новое, в
    # графе это один и тот же модуль
    redirect = {n: t for n, p in names.items() if (t := _redirect_target(p))}
    for n in redirect:
        names.pop(n)
    broad = silent = 0
    graph: dict[str, set[str]] = {n: set() for n in names}

    def target(name: str) -> str | None:
        # самый длинный свой модуль-префикс: «database.users» → database.users, иначе database
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            cand = redirect.get(cand, cand)
            if cand in names:
                return cand
        return None

    for name, p in names.items():
        tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
        is_pkg = p.name == "__init__.py"
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if _is_broad(node):
                    broad += 1
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    silent += 1
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if (t := target(a.name)) and t != name:
                        graph[name].add(t)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = name.split(".") if is_pkg else name.split(".")[:-1]
                    base = base[: len(base) - (node.level - 1)]
                    mod = ".".join(base + ([node.module] if node.module else []))
                else:
                    mod = node.module or ""
                for a in node.names:
                    t = target(f"{mod}.{a.name}") or target(mod)
                    if t and t != name:
                        graph[name].add(t)
    return {
        "broad_except": broad,
        "silent_except": silent,
        "cycle_modules": _cycle_modules(graph),
        "root_py_files": len(list(root.glob("*.py"))),
        "ruff_debt": ruff_debt(root),
    }


def compare(now: dict[str, int], ceiling: dict[str, int]) -> tuple[list[str], list[str]]:
    """(стало хуже, стало лучше — потолок надо опустить)"""
    worse = [f"{k}: {now[k]} > потолка {ceiling[k]}" for k in now if k in ceiling and now[k] > ceiling[k]]
    better = [f"{k}: {now[k]} < потолка {ceiling[k]}" for k in now if k in ceiling and now[k] < ceiling[k]]
    worse += [f"{k}: нет в tools/ratchet.json" for k in now if k not in ceiling]
    return worse, better


def main(argv: list[str]) -> int:
    now = measure(ROOT)
    if "--update" in argv:
        BASELINE.write_text(json.dumps(now, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("потолок обновлён:", now)
        return 0
    ceiling = json.loads(BASELINE.read_text(encoding="utf-8"))
    worse, better = compare(now, ceiling)
    for k, v in now.items():
        print(f"{k}: {v} (потолок {ceiling.get(k, '—')})")
    if worse:
        print("\n❌ Стало хуже — новый код должен быть не хуже старого:\n  " + "\n  ".join(worse))
        print("Узкий тип ошибки вместо except Exception, лог вместо pass, импорт без нового цикла.")
        print("ruff_debt — что именно: ruff check . --select " + ",".join(RUFF_DEBT) + " --ignore " + ",".join(RUFF_DEBT_IGNORE))
        return 1
    if better:
        print("\n✅ Стало лучше:\n  " + "\n  ".join(better))
        print("Опусти потолок: python tools/ratchet.py --update и закоммить tools/ratchet.json")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
