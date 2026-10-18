"""Карта корпусов (5.100.4, Никита 18.10): планы этажей, поиск аудитории и
маршрут между аудиториями — экран «Ещё → Карта» в приложении и PWA (не
вкладкой: «бонтяйство»). Данные — снимок карты Пульса РТУ МИРЭА (подпись
источника — на экране), переведённый в свой формат; пока снимка нет — только
тестовый корпус в tests/data/map (в сборку не попадает), и экрана у людей нет.

Свой формат — файл <id>.json на корпус в MAP_DIR (по умолчанию map_data/):

  {"id": "v-78", "name": "Вернадского, 78", "short": "В-78", "address": "…",
   "source": "Пульс РТУ МИРЭА", "scale": 0.05,       # метров в единице плана
   "floors": [{"n": 2, "w": 1200, "h": 600,
               "outline": [[x, y], …],               # контур этажа
               "rooms": [{"id": "А-223", "name": "А-223", "kind": "room",
                          "shape": [[x, y], …], "door": "2:d223"}],
               "nodes": [{"id": "2:d223", "x": …, "y": …}],   # точки коридоров и двери
               "edges": [["2:d223", "2:c4"], …]}],
   "links": [{"a": "2:s1", "b": "3:s1", "kind": "stairs"}]}   # лестницы и лифты

kind комнаты — KINDS (аудитория, туалет, столовая, лестница, лифт, вход,
прочее). Маршрут — Дейкстра по точкам: коридор — расстояние в метрах,
переход между этажами — FLOOR_COST (лифт — ещё и ожидание). Включение —
MAP=1/0 на сервере (по умолчанию включено, если есть данные): /api/meta
features.map, без него плитки «Карта» нет."""

import heapq
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

KINDS = ("room", "wc", "food", "stairs", "lift", "entrance", "other")
# метров «пешком» за этаж: лестница — пролёт, лифт — ещё и ожидание
FLOOR_COST = {"stairs": 12.0, "lift": 25.0}
WALK_MPS = 1.2
SOURCE = "Пульс РТУ МИРЭА"


def _dir() -> Path:
    return Path(os.getenv("MAP_DIR") or Path(__file__).with_name("map_data"))


def enabled() -> bool:
    return os.getenv("MAP", "1") != "0" and bool(campuses())


def forget():
    _load.cache_clear()


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, dict]:
    out = {}
    root = Path(path)
    if root.is_dir():
        for f in sorted(root.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            out[data["id"]] = data
    return out


def _all() -> dict[str, dict]:
    return _load(str(_dir()))


def campuses() -> list[dict]:
    """Список корпусов: id, название, этажи, источник — без планов."""
    return [{"id": c["id"], "name": c["name"], "short": c.get("short", c["name"]), "address": c.get("address", ""),
             "source": c.get("source", SOURCE), "floors": [f["n"] for f in c["floors"]]}
            for c in _all().values()]


def campus(cid: str) -> dict | None:
    return _all().get(cid)


# ── Поиск аудитории ──────────────────────────────────────────────────────────

_LAT = str.maketrans("abcehkmoptxy", "авсенкмортху")   # латиница, похожая на кириллицу


def norm(s: str) -> str:
    """«а223», «A-223», «а 223» → «а223»: без регистра, дефисов и пробелов."""
    return re.sub(r"[\s\-–—._]+", "", s.lower().replace("ё", "е")).translate(_LAT)


def find(q: str, limit: int = 20) -> list[dict]:
    """Аудитории по началу названия во всех корпусах; точное совпадение — первым."""
    key = norm(q)
    if not key:
        return []
    hits = []
    for c in _all().values():
        for f in c["floors"]:
            for r in f["rooms"]:
                n = norm(r["name"])
                if n.startswith(key) or (len(key) >= 3 and key in n):
                    hits.append((n != key, len(n), r["name"], {"campus": c["id"], "short": c.get("short", ""),
                                                             "floor": f["n"], "id": r["id"], "name": r["name"],
                                                             "kind": r.get("kind", "room")}))
    hits.sort(key=lambda h: h[:3])
    return [h[3] for h in hits[:limit]]


# ── Маршрут ──────────────────────────────────────────────────────────────────

def _floor_of(node: str) -> int:
    return int(node.split(":", 1)[0])


def _graph(c: dict):
    pos: dict[str, tuple[float, float]] = {}
    adj: dict[str, list[tuple[str, float, str | None]]] = {}
    scale = float(c.get("scale", 1))
    for f in c["floors"]:
        for n in f["nodes"]:
            pos[n["id"]] = (n["x"], n["y"])
            adj.setdefault(n["id"], [])
        for a, b in f["edges"]:
            d = math.dist(pos[a], pos[b]) * scale
            adj[a].append((b, d, None))
            adj[b].append((a, d, None))
    for link in c.get("links", []):
        a, b, kind = link["a"], link["b"], link.get("kind", "stairs")
        d = FLOOR_COST.get(kind, FLOOR_COST["stairs"]) * abs(_floor_of(a) - _floor_of(b))
        adj[a].append((b, d, kind))
        adj[b].append((a, d, kind))
    return pos, adj


def _room(c: dict, rid: str) -> tuple[int, dict] | None:
    for f in c["floors"]:
        for r in f["rooms"]:
            if r["id"] == rid:
                return f["n"], r
    return None


def route(cid: str, src: str, dst: str, lift: bool = False) -> dict | None:
    """Путь от двери src до двери dst (id аудиторий) → {"meters", "minutes",
    "legs": [{"floor", "points"}], "steps": [{"kind", "from", "to"}]} или None.
    lift — ехать на лифте, а не по лестнице, где можно."""
    c = campus(cid)
    a, b = c and _room(c, src), c and _room(c, dst)
    if not a or not b or not a[1].get("door") or not b[1].get("door"):
        return None
    pos, adj = _graph(c)
    start, goal = a[1]["door"], b[1]["door"]
    best = {start: 0.0}
    prev: dict[str, tuple[str, str | None]] = {}
    heap = [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == goal:
            break
        if d > best.get(u, math.inf):
            continue
        for v, w, kind in adj.get(u, []):
            if kind and lift != (kind == "lift"):
                w *= 3        # не тот способ — только если другого нет
            nd = d + w
            if nd < best.get(v, math.inf):
                best[v], prev[v] = nd, (u, kind)
                heapq.heappush(heap, (nd, v))
    if goal not in best:
        return None
    path, kinds = [goal], []
    while path[-1] != start:
        u, kind = prev[path[-1]]
        kinds.append(kind)
        path.append(u)
    path.reverse()
    kinds.reverse()
    legs, steps = [], []
    for i, node in enumerate(path):
        fl = _floor_of(node)
        if not legs or legs[-1]["floor"] != fl:
            if legs:
                steps.append({"kind": kinds[i - 1] or "stairs", "from": legs[-1]["floor"], "to": fl})
            legs.append({"floor": fl, "points": []})
        legs[-1]["points"].append(list(pos[node]))
    # проехал этаж насквозь (одна точка на лестнице) — один переход «с 1 на 3»
    i = 1
    while i < len(legs) - 1:
        if len(legs[i]["points"]) == 1 and steps[i - 1]["kind"] == steps[i]["kind"]:
            steps[i - 1]["to"] = steps.pop(i)["to"]
            legs.pop(i)
        else:
            i += 1
    # длина — только пешком (переходы между этажами — в steps)
    scale = float(c.get("scale", 1))
    meters = sum(math.dist(p, q) * scale for leg in legs for p, q in zip(leg["points"], leg["points"][1:]))
    seconds = meters / WALK_MPS + sum(30 if s["kind"] == "lift" else 15 * abs(s["to"] - s["from"]) for s in steps)
    return {"from": {"id": src, "name": a[1]["name"], "floor": a[0]}, "to": {"id": dst, "name": b[1]["name"],
                                                                          "floor": b[0]},
            "meters": round(meters), "minutes": max(1, round(seconds / 60)), "legs": legs, "steps": steps}


# ── Проверка данных (снимок Пульса → свой формат) ────────────────────────────

def check(c: dict) -> list[str]:
    """Что не так с корпусом: пустой список — можно класть в MAP_DIR."""
    errs = []
    nodes = {n["id"] for f in c.get("floors", []) for n in f.get("nodes", [])}
    for f in c.get("floors", []):
        for n in f.get("nodes", []):
            if _floor_of(n["id"]) != f["n"]:
                errs.append(f"точка {n['id']} не с этажа {f['n']}")
        for a, b in f.get("edges", []):
            if a not in nodes or b not in nodes:
                errs.append(f"переход {a}–{b}: нет точки")
        for r in f.get("rooms", []):
            if r.get("kind", "room") not in KINDS:
                errs.append(f"{r['id']}: вид {r.get('kind')}")
            if len(r.get("shape", [])) < 3:
                errs.append(f"{r['id']}: контур")
            if r.get("door") and r["door"] not in nodes:
                errs.append(f"{r['id']}: дверь {r['door']} не на графе")
    for link in c.get("links", []):
        if link["a"] not in nodes or link["b"] not in nodes:
            errs.append(f"лестница {link['a']}–{link['b']}: нет точки")
    if not errs:   # все двери аудиторий связаны между собой
        _, adj = _graph(c)
        doors = [r["door"] for f in c["floors"] for r in f["rooms"] if r.get("door")]
        if doors:
            seen, todo = {doors[0]}, [doors[0]]
            while todo:
                for v, _, _ in adj[todo.pop()]:
                    if v not in seen:
                        seen.add(v)
                        todo.append(v)
            errs += [f"{d}: не дойти" for d in doors if d not in seen]
    return errs
