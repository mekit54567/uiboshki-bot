"""Роадмап — что я делаю сейчас и что дальше (Никита 18.10): видят все, кто
поддержал проект любой суммой (донат от DONATE_MIN), — как спасибо, а не
покупка; Никите и старостам-админам — всегда. На iPhone (X-App: ios) роадмапа
нет вовсе, как и доната (App Store 3.1.1).

Пункты — roadmap.json рядом (обновлять вместе с выпусками: вышло — в done,
новое из «Идей в работе» PLAN.md — простыми словами, без внутренней кухни).
Статусы: now — делаю сейчас, next — следующее, idea — попробую, done — вышло,
failed — не получилось.

Номера (Никита 20.10): edition — номер роадмапа; пункт с from = номер, где его
обещал, — в «итогах» нового номера: вышло, не вышло или в работе, «Сделано N из
M». post — пост в канале разработки, как сделано или почему не вышло: имя папки
из channel/posts (ссылку берём из выпущенных) или готовая ссылка t.me. Страница —
/roadmap?k=<личный ключ> (webapp/routes/roadmap_page.py), бот и приложения
ведут туда.
"""

import json
from pathlib import Path

PATH = Path(__file__).parent / "roadmap.json"
STATUSES = {"now": "Делаю сейчас", "next": "Следующее", "idea": "Попробую", "done": "Вышло",
            "failed": "Не получилось"}
RESULT = ("done", "failed", "now")       # чем кончились пункты прошлого номера


def load() -> dict:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    items = [i for i in data["items"] if i.get("status") in STATUSES]
    order = list(STATUSES)
    items.sort(key=lambda i: order.index(i["status"]))
    return {"edition": data.get("edition", 1), "updated": data.get("updated", ""), "items": items,
            "statuses": STATUSES}


def results(data: dict) -> list[dict]:
    """Пункты прошлого номера — итоги: вышло, потом не вышло, потом в работе."""
    prev = [i for i in data["items"] if i.get("from") and i["from"] < data["edition"] and i["status"] in RESULT]
    return sorted(prev, key=lambda i: RESULT.index(i["status"]))


def score(data: dict) -> tuple[int, int]:
    """«Сделано N из M» по итогам прошлого номера."""
    res = results(data)
    return sum(i["status"] == "done" for i in res), len(res)


async def with_links(data: dict) -> dict:
    """post → ссылка: готовая https — как есть, имя поста — t.me/<канал>/<id>
    из выпущенных (не выпущен или канал без @имени — без ссылки)."""
    import channel_posts
    done = await channel_posts.published()
    for i in data["items"]:
        post = (i.get("post") or "").strip()
        link = post if post.startswith("https://") else ""
        if post and not link and done.get(post, {}).get("ids"):
            link = channel_posts.post_link(channel_posts.target(post) or "", done[post]["ids"][0])
        i["link"] = link
    return data


def page_link(uid: int) -> str:
    """Личная ссылка на страницу роадмапа — тот же ключ, что у /plus и /donate."""
    import billing
    return f"{billing.site()}/roadmap?k={billing.make_key(uid)}"


async def can_see(uid: int) -> bool:
    """Поддержал проект (оплаченный донат) — или это Никита."""
    import config
    from database.billing import has_donated
    return config.is_starosta(uid) or await has_donated(uid)


def text() -> str:
    """Роадмап для бота (HTML Telegram) — коротко; красиво — на странице."""
    from utils import esc
    data = load()
    done, total = score(data)
    out = [f"🗺 <b>Роадмап Капибары №{data['edition']}</b>", "<i>Что я делаю сейчас и что дальше.</i>"]
    if total:
        out.append(f"Из прошлого роадмапа сделано <b>{done} из {total}</b>.")
    for status, label in STATUSES.items():
        rows = [i for i in data["items"] if i["status"] == status]
        if not rows:
            continue
        out.append(f"\n<b>{label}</b>")
        out += [f"• <b>{esc(i['title'])}</b> — {esc(i['about'])}" for i in rows]
    if data["updated"]:
        d = data["updated"].split("-")
        out.append(f"\n<i>Обновлено {d[2]}.{d[1]}.{d[0]}. Спасибо за поддержку!</i>")
    return "\n".join(out)
