"""Проверка своих импортов без запуска кода (CI: «python tools/check_imports.py»).

В коде ~800 импортов внутри функций (так разрывают циклы между модулями).
Обычный импорт модуля их не выполняет, а тесты доходят не до всех веток, так
что опечатка в таком импорте или переименованная функция всплывает только в
проде, когда ветка сработает. Здесь читаем каждый файл (ast) и для каждого
`import x` / `from x import y`, где x — наш модуль, проверяем: модуль есть,
и имя y в нём определено (функция, класс, переменная, импорт) или это
подмодуль пакета. Сторонние библиотеки не проверяем — их ловит сборка образа.

Выход: 0 — всё сходится, 1 — список «файл:строка: что не так».
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Не код сервера: приложение Flutter, сборки, служебное
SKIP_DIRS = {".git", "app", "node_modules", "__pycache__", ".venv", "venv", "pulse_lab_kit"}


def py_files(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if SKIP_DIRS.intersection(rel.parts[:-1]):
            continue
        out.append(p)
    return sorted(out)


def module_name(p: Path, root: Path) -> str:
    parts = list(p.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class Module:
    def __init__(self, path: Path, tree: ast.Module):
        self.path = path
        self.is_package = path.name == "__init__.py"
        self.names: set[str] = set()
        self.star = False           # from x import * / globals() — имён не знаем, не проверяем
        for node in tree.body:
            self._collect(node)

    def _collect(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        self.names.add(n.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    self.star = True
                else:
                    self.names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            # имена, заданные под if/try на верхнем уровне (запасной импорт и т.п.)
            for field in ("body", "orelse", "finalbody", "handlers"):
                for child in getattr(node, field, []) or []:
                    self._collect(child)
        elif isinstance(node, ast.ExceptHandler):
            for child in node.body:
                self._collect(child)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) \
                    and getattr(f.value.func, "id", "") == "globals":
                self.star = True    # globals().update(...)


def check(root: Path) -> tuple[int, list[str]]:
    """(сколько файлов, ошибки)"""
    files = py_files(root)
    trees: dict[str, tuple[Path, ast.Module]] = {}
    for p in files:
        trees[module_name(p, root)] = (p, ast.parse(p.read_text(encoding="utf-8"), str(p)))
    mods = {name: Module(p, t) for name, (p, t) in trees.items()}
    # Папки без __init__.py (webapp/) — пакеты-пространства имён: только подмодули
    for name in list(mods):
        parts = name.split(".")
        for i in range(1, len(parts)):
            pkg = ".".join(parts[:i])
            if pkg not in mods:
                ns = Module(root.joinpath(*parts[:i], "__init__.py"), ast.Module(body=[], type_ignores=[]))
                mods[pkg] = ns
    ours = {name.split(".")[0] for name in mods}

    def resolve(cur: str, cur_pkg: bool, level: int, module: str | None) -> str:
        if not level:
            return module or ""
        base = cur.split(".") if cur_pkg else cur.split(".")[:-1]
        base = base[: len(base) - (level - 1)]
        return ".".join(base + ([module] if module else []))

    errors = []
    for name, (path, tree) in trees.items():
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in ours and a.name not in mods:
                        errors.append(f"{rel}:{node.lineno}: нет модуля {a.name}")
            elif isinstance(node, ast.ImportFrom):
                target = resolve(name, mods[name].is_package, node.level, node.module)
                if not target or target.split(".")[0] not in ours:
                    continue
                if target not in mods:
                    errors.append(f"{rel}:{node.lineno}: нет модуля {target}")
                    continue
                m = mods[target]
                if m.star:
                    continue
                for a in node.names:
                    if a.name == "*" or a.name in m.names:
                        continue
                    if m.is_package and f"{target}.{a.name}" in mods:
                        continue
                    errors.append(f"{rel}:{node.lineno}: в {target} нет имени {a.name}")
    return len(files), errors


def main() -> int:
    n, errors = check(ROOT)
    for e in errors:
        print(e)
    print(f"проверено файлов: {n}, ошибок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
