"""Тестовый корпус для карты (campus_map.py): tests/data/map/test.json.

Три этажа, коридор посередине, аудитории сверху и снизу, лестница и лифт.
Нужен тестам и стенду, пока нет снимка карты Пульса; в сборку не попадает
(tests/ — в .dockerignore). Запуск: python tools/map_demo.py"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "data" / "map" / "test.json"
W, H, SLOT, ROOM = 1200, 500, 165, 150


def floor(n: int) -> dict:
    rooms, nodes, edges = [], [], []
    corridor = []
    for i in range(6):
        x0 = 120 + i * SLOT
        cx = x0 + ROOM // 2
        corridor.append(f"{n}:c{i}")
        nodes.append({"id": f"{n}:c{i}", "x": cx, "y": 250})
        for side, (y0, y1, dy) in (("t", (60, 210, 210)), ("b", (290, 440, 290))):
            num = i + 1 if side == "t" else i + 7
            kind, name = "room", f"Т-{n}{num:02d}"
            if side == "b" and i == 0:
                kind, name = "stairs", "Лестница"
            elif side == "b" and i == 5:
                kind, name = "lift", "Лифт"
            elif side == "t" and i == 5:
                kind, name = "wc", "Туалет"
            elif n == 1 and side == "b" and i == 3:
                kind, name = "food", "Буфет"
            elif n == 1 and side == "b" and i == 2:
                kind, name = "entrance", "Вход"
            door = f"{n}:{side}{i}"
            nodes.append({"id": door, "x": cx, "y": dy})
            edges.append([door, f"{n}:c{i}"])
            rid = name if kind == "room" else f"{n}-{kind}"
            rooms.append({"id": rid, "name": name, "kind": kind,
                          "shape": [[x0, y0], [x0 + ROOM, y0], [x0 + ROOM, y1], [x0, y1]],
                          "door": door})
    edges += [[a, b] for a, b in zip(corridor, corridor[1:])]
    return {"n": n, "w": W, "h": H, "outline": [[80, 40], [1120, 40], [1120, 460], [80, 460]],
            "rooms": rooms, "nodes": nodes, "edges": edges}


def main():
    floors = [floor(n) for n in (1, 2, 3)]
    links = [{"a": f"{n}:b0", "b": f"{n + 1}:b0", "kind": "stairs"} for n in (1, 2)]
    links += [{"a": f"{n}:b5", "b": f"{n + 1}:b5", "kind": "lift"} for n in (1, 2)]
    data = {"id": "test", "name": "Тестовый корпус", "short": "Т", "address": "тестовые данные",
            "source": "тестовые данные", "scale": 0.05, "floors": floors, "links": links}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
