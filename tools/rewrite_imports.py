"""Финал переезда в kapibara/ (docs/adr/0003-safe-moves.md): импорты старых
имён → новые пути, затем переадресации в корне можно удалить.

    python tools/rewrite_imports.py            # переписать файлы
    python tools/rewrite_imports.py --check    # только показать, что осталось

Что меняется (только свои модули из таблицы MOVED, сторонние не трогаем):
    import config                 → from kapibara.core import config
    import gemini_solver as g     → from kapibara.features.ai import gemini as g
    from sdo_parser import a, b   → from kapibara.features.sdo.parser import a, b
    "sdo_parser.fetch" в строке    → "kapibara.features.sdo.parser.fetch"
                                    (monkeypatch.setattr по строке в тестах)
Локальное имя модуля сохраняется (`as`), так что код ниже импорта не меняется.
Таблица MOVED — та же, что была в tests/test_moved_modules.py.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "app", "node_modules", "__pycache__", ".venv", "venv", "pulse_lab_kit"}


def load_moved() -> dict[str, str]:
    """Старое имя → новый путь: по файлам-переадресациям в корне."""
    moved = {}
    for p in sorted(ROOT.glob("*.py")):
        m = re.search(r"^import (kapibara\.[\w.]+) as _m$", p.read_text(encoding="utf-8"), re.M)
        if m and "sys.modules[__name__] = _m" in p.read_text(encoding="utf-8"):
            moved[p.stem] = m.group(1)
    return moved


def files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT)
        if SKIP_DIRS.intersection(rel.parts[:-1]):
            continue
        out.append(p)
    return sorted(out)


def _offset(lines: list[str], lineno: int, col: int) -> int:
    """ast даёт колонку в байтах UTF-8 — переводим в символы строки."""
    line = lines[lineno - 1]
    return sum(len(x) for x in lines[: lineno - 1]) + len(line.encode("utf-8")[:col].decode("utf-8"))


_NAMES: dict[str, set[str]] = {}


def top_names(module: str) -> set[str]:
    """Имена верхнего уровня модуля (функции, классы, переменные, импорты)."""
    if module not in _NAMES:
        path = ROOT.joinpath(*module.split(".")).with_suffix(".py")
        names = set()
        if path.exists():
            for n in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(n.name)
                elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        names |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    names |= {(a.asname or a.name).split(".")[0] for a in n.names}
        _NAMES[module] = names
    return _NAMES[module]


def rewrite(text: str, moved: dict[str, str]) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    edits = []          # (start, end, новый текст)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name in moved for a in node.names):
            indent = " " * node.col_offset
            parts = []
            for a in node.names:
                if a.name in moved:
                    pkg, leaf = moved[a.name].rsplit(".", 1)
                    local = a.asname or a.name
                    parts.append(f"from {pkg} import {leaf}" + ("" if local == leaf else f" as {local}"))
                else:
                    parts.append(f"import {a.name}" + (f" as {a.asname}" if a.asname else ""))
            start = _offset(lines, node.lineno, node.col_offset)
            end = _offset(lines, node.end_lineno, node.end_col_offset)
            edits.append((start, end, ("\n" + indent).join(parts)))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in moved:
            start = _offset(lines, node.lineno, node.col_offset)
            end = _offset(lines, node.end_lineno, node.end_col_offset)
            seg = text[start:end]
            new = re.sub(rf"^from\s+{re.escape(node.module)}\b", f"from {moved[node.module]}", seg, count=1)
            edits.append((start, end, new))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            head, _, rest = node.value.partition(".")
            # только «модуль.имя_в_модуле»: «config.json» или «roadmap.json» — имена файлов, не трогаем
            if head in moved and rest and re.fullmatch(r"[\w.]+", node.value)                     and rest.split(".")[0] in top_names(moved[head]):
                start = _offset(lines, node.lineno, node.col_offset)
                end = _offset(lines, node.end_lineno, node.end_col_offset)
                seg = text[start:end]
                q = seg[0] if seg[0] in "\"'" else None
                if q and seg[-1] == q:
                    edits.append((start, end, q + moved[head] + node.value[len(head):] + q))
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def main(argv: list[str]) -> int:
    moved = load_moved()
    if not moved:
        print("переадресаций в корне нет — переписывать нечего")
        return 0
    changed = 0
    for p in files():
        if p.parent == ROOT and p.stem in moved:
            continue                                     # сама переадресация
        old = p.read_text(encoding="utf-8")
        new = rewrite(old, moved)
        if new != old:
            changed += 1
            if "--check" in argv:
                print(p.relative_to(ROOT).as_posix())
            else:
                p.write_text(new, encoding="utf-8", newline="\n")
    print(f"переадресаций: {len(moved)}, файлов {'к правке' if '--check' in argv else 'переписано'}: {changed}")
    return 1 if ("--check" in argv and changed) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
