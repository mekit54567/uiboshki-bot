"""Роадмап — что я делаю сейчас и что дальше (Никита 18.10): видят все, кто
поддержал проект любой суммой (донат от DONATE_MIN), — как спасибо, а не
покупка; Никите и старостам-админам — всегда. На iPhone (X-App: ios) роадмапа
нет вовсе, как и доната (App Store 3.1.1).

Пункты — roadmap.json рядом (обновлять вместе с выпусками: вышло — в done,
новое из «Идей в работе» PLAN.md — простыми словами, без внутренней кухни).
Статусы: now — делаю сейчас, next — следующее, idea — попробую, done — недавно вышло.
"""

import json
from pathlib import Path

PATH = Path(__file__).parent / "roadmap.json"
STATUSES = {"now": "Делаю сейчас", "next": "Следующее", "idea": "Попробую", "done": "Недавно вышло"}


def load() -> dict:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    items = [i for i in data["items"] if i.get("status") in STATUSES]
    order = list(STATUSES)
    items.sort(key=lambda i: order.index(i["status"]))
    return {"updated": data.get("updated", ""), "items": items, "statuses": STATUSES}


async def can_see(uid: int) -> bool:
    """Поддержал проект (оплаченный донат) — или это Никита."""
    import config
    from database.billing import has_donated
    return config.is_starosta(uid) or await has_donated(uid)


def text() -> str:
    """Роадмап для бота (HTML Telegram)."""
    from utils import esc
    data = load()
    out = ["🗺 <b>Роадмап Капибары</b>", "<i>Что я делаю сейчас и что дальше. Спасибо, что поддержал!</i>"]
    for status, label in STATUSES.items():
        rows = [i for i in data["items"] if i["status"] == status]
        if not rows:
            continue
        out.append(f"\n<b>{label}</b>")
        out += [f"• <b>{esc(i['title'])}</b> — {esc(i['about'])}" for i in rows]
    if data["updated"]:
        d = data["updated"].split("-")
        out.append(f"\n<i>Обновлено {d[2]}.{d[1]}.{d[0]}</i>")
    return "\n".join(out)
