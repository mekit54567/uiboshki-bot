"""Уведомления нового дизайна (шаг 8, макеты У1 и У2, Никита 11.11): лента
того, что приходило; тихие часы 23:00–07:30 по Москве — пуш и Telegram
молчат, сообщение ждёт в ленте, срочное приходит; «Что присылать» — три
профиля вместо двадцати тумблеров."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from kapibara.core.utils import TZ


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text, **kw):
        self.sent.append((uid, text))


def _at(h, m):
    return lambda: datetime(2026, 10, 8, h, m, tzinfo=TZ)


@pytest.mark.asyncio
async def test_delivered_message_lands_in_inbox(db, monkeypatch):
    from database import inbox, upsert_user
    from kapibara.features.notifications import delivery
    await upsert_user(1, "", "Аня")
    monkeypatch.setattr(delivery, "_now", _at(19, 12))
    bot = Bot()
    await delivery.deliver(bot, 1, "🆕 <b>Новое задание</b>\nКурсовая, глава 1", kind="new_tasks", tab="deadlines",
                           title="Новое задание: Курсовая, глава 1", body="Бизнес-анализ · срок 14 октября")
    assert bot.sent                                           # Telegram как раньше
    [item] = await inbox.items(1)
    assert (item["title"], item["body"], item["tab"], item["kind"]) == (
        "Новое задание: Курсовая, глава 1", "Бизнес-анализ · срок 14 октября", "deadlines", "new_tasks")
    assert item["at"] == "2026-10-08T19:12:00+03:00" and not item["quiet"]
    # без своего заголовка — общий по виду и начало сообщения
    await delivery.deliver(bot, 1, "⏰ <b>Через 10 минут пара</b>\n\nАнализ данных", kind="lesson", tab="today")
    item = (await inbox.items(1))[0]
    assert item["title"] == "Скоро пара" and item["body"] == "⏰ Через 10 минут пара\nАнализ данных"
    assert await inbox.unread(1) == 2


@pytest.mark.asyncio
async def test_quiet_hours_hold_until_morning_but_urgent_comes(db, monkeypatch):
    from database import inbox, set_notify, upsert_user
    from kapibara.features.notifications import delivery
    await upsert_user(1, "", "Аня")
    await set_notify(1, {"quiet": True})
    bot = Bot()
    monkeypatch.setattr(delivery, "_now", _at(23, 40))
    await delivery.deliver(bot, 1, "Новые баллы", kind="grades", tab="sdo")
    assert bot.sent == []                                     # тихо: ни Telegram, ни пуша
    assert (await inbox.items(1))[0]["quiet"] == 1            # но в ленте лежит
    await delivery.deliver(bot, 1, "Тест закрывается через 30 мин", kind="quiz", tab="deadlines", urgent=True)
    await delivery.deliver(bot, 1, "Оплата прошла", kind="plus", tab="more")
    await delivery.deliver(bot, 1, "Завтра 3 пары", kind="evening", tab="today")   # время сводки выбрал сам
    assert len(bot.sent) == 3
    monkeypatch.setattr(delivery, "_now", _at(7, 29))
    await delivery.deliver(bot, 1, "Новое задание", kind="new_tasks")
    assert len(bot.sent) == 3
    monkeypatch.setattr(delivery, "_now", _at(7, 30))       # утро в 07:30 уже приходит
    await delivery.deliver(bot, 1, "Доброе утро", kind="morning", tab="today")
    assert len(bot.sent) == 4
    # тихие часы выключены (по умолчанию) — ночью как раньше
    await set_notify(1, {"quiet": False})
    monkeypatch.setattr(delivery, "_now", _at(2, 0))
    await delivery.deliver(bot, 1, "Новые баллы", kind="grades")
    assert len(bot.sent) == 5


@pytest.mark.asyncio
async def test_inbox_keeps_last_hundred_and_thirty_days(db):
    from database import inbox
    await inbox.add(1, "grades", "старое", "", "sdo", "2026-08-01T10:00:00+03:00")
    for i in range(105):
        await inbox.add(1, "grades", f"#{i}", "", "sdo", "2026-10-08T10:00:00+03:00")
    rows = await inbox.items(1, limit=1000)
    assert len(rows) == 100 and rows[0]["title"] == "#104" and rows[-1]["title"] == "#5"
    await inbox.add(2, "grades", "чужое", "", None, "2026-10-08T10:00:00+03:00")
    assert len(await inbox.items(1, limit=1000)) == 100       # чужая запись мою ленту не трогает


@pytest.mark.asyncio
async def test_erase_removes_inbox(db):
    from database import inbox
    from database.privacy import erase_user
    await inbox.add(1, "grades", "баллы", "Анализ данных: 24 → 28", "sdo", "2026-10-08T10:00:00+03:00")
    done = await erase_user(1)
    assert done.get("inbox") == 1 and await inbox.items(1) == []


def test_inbox_and_profiles_api(db, monkeypatch):
    import asyncio

    import webapp.server as server
    from database import inbox
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data()}
    uid = c.get("/api/me", headers=h).json()["id"]
    asyncio.run(inbox.add(uid, "grades", "В СДО изменились баллы", "Анализ данных: 24 → 28", "sdo",
                          "2026-10-08T07:40:00+03:00"))
    r = c.get("/api/inbox", headers=h).json()
    assert r["unread"] == 1 and r["items"][0]["title"] == "В СДО изменились баллы" and r["items"][0]["tab"] == "sdo"
    assert c.post("/api/inbox/read", headers=h).json() == {"read": 1}
    assert c.get("/api/inbox", headers=h).json()["unread"] == 0

    r = c.get("/api/notify", headers=h).json()
    assert r["profile"] == "daily" and r["quiet_hours"] == {"from": "23:00", "to": "07:30"}
    assert r["prefs"]["quiet"] is False
    c.post("/api/notify", headers=h, json={"subscribed": False})
    r = c.post("/api/notify", headers=h, json={"profile": "important"}).json()
    assert r["profile"] == "important" and r["subscribed"] is True
    p = r["prefs"]
    assert not p["morning"] and not p["weekly"] and (p["remind_first"], p["remind_short"], p["remind_long"]) == (0, 0, 0)
    assert p["deadlines"] and p["grades"] and p["new_tasks"] and p["lessons"]   # смену расписания — присылать
    r = c.post("/api/notify", headers=h, json={"prefs": {"grades": False}}).json()
    assert r["profile"] == "custom"                           # тронул тумблер — «Настроить самому»
    r = c.post("/api/notify", headers=h, json={"profile": "daily", "prefs": {"quiet": True}}).json()
    assert r["profile"] == "daily" and r["prefs"]["quiet"] is True and r["prefs"]["remind_first"] == 60
    assert c.post("/api/notify", headers=h, json={"profile": "всё"}).status_code == 400
