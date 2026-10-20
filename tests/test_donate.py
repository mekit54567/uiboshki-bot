"""«Поддержать проект» (Никита 18.10): донат той же кассой на сайте — своя
таблица donations, дней подписки не даёт, на iPhone скрыт, без реквизитов
закрыт, уведомления касс отличают его от подписки, человеку — спасибо,
Никите — строка в чат и в /status."""
import hashlib
from urllib.parse import parse_qs, urlparse

import aiosqlite
import pytest

import billing
import config
from tests.conftest import STAROSTA_ID
from tests.test_plus import robokassa  # noqa: F401 — фикстура
from tests.test_review_bot import press, send
from tests.test_review_bot import bot, dp  # noqa: F401 — фикстуры
from tests.test_webapp_home import _headers_for, client  # noqa: F401 — фикстура

ME = 601


async def _rows(db, table):
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await conn.execute(f"SELECT * FROM {table} ORDER BY created_at")).fetchall()]


def _to(bot, uid):  # noqa: F811
    return [m.text for m in bot.session.named("SendMessage") if m.chat_id == uid]


def test_amounts():
    assert billing.donate_amount("300") == 300 and billing.donate_amount(" 1 000 ₽") == 1000
    for bad in ("", "abc", "49", "15001", "-5", None):
        with pytest.raises(billing.PayError):
            billing.donate_amount(bad)
    assert billing.DONATE_AMOUNTS == (100, 300, 500) and billing.DONATE_MIN == 50


@pytest.mark.asyncio
async def test_robokassa_donation_gives_no_days(db, bot, client, monkeypatch, robokassa):  # noqa: F811
    c, _ = client
    monkeypatch.setattr(config, "STAROSTA_ID", STAROSTA_ID)
    await db.upsert_user(ME, "vasya", "Вася")
    url = await billing.create_donation(ME, 300, "https://x/done")
    q = parse_qs(urlparse(url).query)
    assert url.startswith(billing.ROBOKASSA_URL) and q["OutSum"] == ["300.00"]
    assert q["Description"] == ["Добровольная поддержка проекта «Капибара»"]          # позиция в чеке
    don = await _rows(db, "donations")
    assert [(d["payer_id"], d["amount"], d["status"]) for d in don] == [(ME, 300, "pending")]
    assert await _rows(db, "payments") == []                                          # не подписка
    inv = don[0]["id"]

    def hook(out_sum):
        sig = hashlib.md5(f"{out_sum}:{inv}:p2".encode()).hexdigest()
        return c.post("/api/billing/robokassa", data={"OutSum": out_sum, "InvId": inv, "SignatureValue": sig})

    assert hook("50.00").status_code == 400                                          # сумма меньше
    assert hook("300.00").text == f"OK{inv}"
    st = await billing.status(ME)
    assert not st["active"] and not st["paid_until"]                                  # дней подписки — ноль
    assert (await _rows(db, "donations"))[0]["status"] == "succeeded"
    assert not await billing.settle(inv, bot)                                         # повтор — без второго спасибо

    inv2 = (parse_qs(urlparse(await billing.create_donation(ME, "500", "https://x")).query))["InvId"][0]
    assert await billing.settle(inv2, bot)
    thanks = _to(bot, ME)[-1]
    assert "Спасибо за поддержку! 500 ₽" in thanks and "Это не подписка" in thanks
    owner = _to(bot, STAROSTA_ID)[-1]
    assert "Поддержка проекта: 500 ₽ от Вася @vasya" in owner and "Всего: 2 · 800 ₽" in owner
    assert not (await billing.status(ME))["active"]

    import health
    assert "Поддержка проекта (/donate): 2 · 800 ₽, за 30 дней — 2 · 800 ₽" in await health.report()


@pytest.mark.asyncio
async def test_yookassa_hook_tells_donation_from_sub(db, client, monkeypatch):  # noqa: F811
    c, _ = client
    await db.upsert_user(ME, "", "u")
    from database.billing import add_donation, add_payment, get_donation
    await add_donation("yk-d1", "yookassa", ME, 300)
    await add_donation("yk-d2", "yookassa", ME, 100)
    await add_payment("yk-s1", "yookassa", ME, "month", 149, 30)
    answers = {"yk-d1": "pending", "yk-d2": "canceled", "yk-s1": "succeeded"}

    async def check(pid):
        return answers[pid]
    monkeypatch.setattr(billing, "yookassa_check", check)

    def hook(pid):
        return c.post("/api/billing/yookassa", json={"event": "payment.succeeded", "object": {"id": pid}}).json()

    assert hook("yk-d1") == {"ok": True}
    assert (await get_donation("yk-d1"))["status"] == "pending"                       # телу не верим
    answers["yk-d1"] = "succeeded"
    hook("yk-d1")
    assert (await get_donation("yk-d1"))["status"] == "succeeded"
    assert not (await billing.status(ME))["active"]                                   # донат — без дней
    hook("yk-d2")
    assert (await get_donation("yk-d2"))["status"] == "canceled"
    hook("yk-s1")                                                                     # подписка — как была
    assert (await billing.status(ME))["active"]


@pytest.mark.asyncio
async def test_api_donate_hidden_on_iphone_and_closed_without_requisites(db, client, monkeypatch, robokassa):  # noqa: F811
    import privacy
    c, _ = client
    h = _headers_for(ME)
    d = c.get("/api/donate", headers=h).json()
    assert not d["hidden"] and d["url"].startswith(billing.site() + "/donate?k=")
    assert d["amounts"] == [100, 300, 500] and d["min"] == 50 and "не подписка" in d["note"]
    assert c.get("/api/plus", headers=h).json()["donate_url"].startswith(billing.site() + "/donate?k=")
    assert c.get("/api/donate", headers={**h, "X-App": "ios"}).json() == {"hidden": True}   # App Store
    assert c.get("/api/plus", headers={**h, "X-App": "ios"}).json() == {"hidden": True}

    monkeypatch.setattr(privacy, "INN", "")                                           # без реквизитов — закрыто
    assert c.get("/api/donate", headers=h).json()["url"] == ""
    assert c.get("/api/plus", headers=h).json()["donate_url"] == ""
    with pytest.raises(billing.PayError):
        await billing.create_donation(ME, 300, "https://x")
    key = billing.make_key(ME)
    assert "совсем скоро" in c.get(f"/donate?k={key}").text
    assert c.post("/donate/pay", data={"k": key, "amount": "300"}, follow_redirects=False).status_code == 400


@pytest.mark.asyncio
async def test_donate_page(db, client, robokassa):  # noqa: F811
    c, _ = client
    await db.upsert_user(ME, "", "u")
    assert c.get("/donate").status_code == 403 and "/donate" in c.get("/donate").text
    key = billing.make_key(ME)
    page = c.get(f"/donate?k={key}").text
    assert "<h1>Поддержать проект</h1>" in page and "Это не подписка — просто спасибо" in page and "роадмап" in page
    assert all(f"{a}&nbsp;₽" in page for a in (100, 300, 500)) and 'name="own"' in page and "/offer" in page
    r = c.post("/donate/pay", data={"k": key, "amount": "own", "own": "250"}, follow_redirects=False)
    assert r.status_code == 303 and "OutSum=250.00" in r.headers["location"]
    r = c.post("/donate/pay", data={"k": key, "amount": "own", "own": "10"}, follow_redirects=False)
    assert r.status_code == 400 and "от 50" in r.text
    assert c.post("/donate/pay", data={"k": "чужой", "amount": "300"}).status_code == 403
    assert c.get(f"/donate/done?k={key}").status_code == 200
    assert c.get(f"/donate/state?k={key}").json() == {"paid": False, "amount": 0}
    inv = (await _rows(db, "donations"))[-1]["id"]
    await billing.settle(inv)
    assert c.get(f"/donate/state?k={key}").json() == {"paid": True, "amount": 250}
    assert c.get("/donate/state?k=битый").status_code == 403
    assert "Поддержка проекта" in c.get("/offer").text                                # раздел в оферте


@pytest.mark.asyncio
async def test_yookassa_donation_metadata_without_person(db, monkeypatch, robokassa):  # noqa: F811
    monkeypatch.setattr(billing, "YOOKASSA_SHOP_ID", "shop")
    monkeypatch.setattr(billing, "YOOKASSA_SECRET_KEY", "key")
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "yk-d9", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay"}}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, json, headers):
            sent.update(json)
            return Resp()

    monkeypatch.setattr(billing, "_yk_client", lambda: Client())
    await db.upsert_user(ME, "", "u")
    assert await billing.create_donation(ME, 100, "https://x/done") == "https://yoomoney.ru/pay"
    assert str(ME) not in str(sent) and sent["metadata"] == {"kind": "donation"}
    assert sent["description"] == billing.DONATE_TITLE and sent["amount"]["value"] == "100.00"
    assert [d["id"] for d in await _rows(db, "donations")] == ["yk-d9"] and await _rows(db, "payments") == []


@pytest.mark.asyncio
async def test_bot_donate(db, bot, dp, robokassa):  # noqa: F811
    await db.upsert_user(ME, "", "u")
    await send(dp, bot, "/donate", uid=ME)
    m = bot.session.named("SendMessage")[-1]
    assert "Поддержать проект" in m.text and "не подписка — просто спасибо" in m.text and "/roadmap" in m.text
    assert m.reply_markup.inline_keyboard[0][0].url.startswith(billing.site() + "/donate?k=")
    await send(dp, bot, "/plus", uid=ME)
    kb = bot.session.named("SendMessage")[-1].reply_markup.inline_keyboard
    assert any(b.callback_data == "plus:donate" for row in kb for b in row)
    await press(dp, bot, "plus:donate", uid=ME)
    assert "Поддержать проект" in bot.session.texts()[-1]
    await send(dp, bot, "/start donate", uid=ME)
    assert "Поддержать проект" in bot.session.texts()[-1]
    await send(dp, bot, "/help", uid=ME)
    assert "/donate" in bot.session.texts()[-1]


@pytest.mark.asyncio
async def test_bot_donate_closed_without_requisites(db, bot, dp, monkeypatch, robokassa):  # noqa: F811
    import privacy
    monkeypatch.setattr(privacy, "INN", "")
    await send(dp, bot, "/donate", uid=ME)
    m = bot.session.named("SendMessage")[-1]
    assert "совсем скоро" in m.text and m.reply_markup is None


@pytest.mark.asyncio
async def test_erase_keeps_donations_without_person(db):
    import privacy
    from database.billing import add_donation
    await db.upsert_user(ME, "", "u")
    await add_donation("d-1", "robokassa", ME, 300)
    await privacy.erase(ME)
    rows = await _rows(db, "donations")
    assert [(r["payer_id"], r["amount"]) for r in rows] == [(None, 300)]               # налоговый учёт — без человека


@pytest.mark.asyncio
async def test_roadmap_for_supporters(db, bot, dp, client, robokassa):  # noqa: F811
    """Роадмап (Никита 18.10) — тем, кто поддержал проект любой суммой, как спасибо;
    до доната — замок и ссылка на донат; на iPhone — нет вовсе (как и доната)."""
    import roadmap
    c, _ = client
    h = _headers_for(ME)
    await db.upsert_user(ME, "", "u")
    d = c.get("/api/roadmap", headers=h).json()
    assert d["locked"] and d["donate_url"].startswith(billing.site() + "/donate?k=") and "items" not in d
    assert c.get("/api/roadmap", headers={**h, "X-App": "ios"}).json() == {"hidden": True}
    await send(dp, bot, "/roadmap", uid=ME)
    m = bot.session.named("SendMessage")[-1]
    assert "открывается тем, кто поддержал" in m.text and m.reply_markup.inline_keyboard[0][0].url

    inv = parse_qs(urlparse(await billing.create_donation(ME, 50, "https://x")).query)["InvId"][0]
    assert not (await roadmap.can_see(ME))                                            # ещё не оплачен
    assert await billing.settle(inv, bot)
    assert "/roadmap" in _to(bot, ME)[-1]                                             # в спасибо — где роадмап
    d = c.get("/api/roadmap", headers=h).json()
    assert not d["locked"] and d["items"] and set(d["statuses"]) == {"now", "next", "idea", "done"}
    order = [i["status"] for i in d["items"]]
    assert order == sorted(order, key=list(roadmap.STATUSES).index)                    # сейчас → дальше → вышло
    await send(dp, bot, "/roadmap", uid=ME)
    assert "Роадмап Капибары" in bot.session.texts()[-1] and "Делаю сейчас" in bot.session.texts()[-1]
    assert await roadmap.can_see(STAROSTA_ID)                                         # Никите — всегда


def test_roadmap_file_is_valid():
    import roadmap
    data = roadmap.load()
    assert data["updated"] and all(i["title"] and i["about"] for i in data["items"])
    assert len(roadmap.text()) < 4096


def test_robokassa_returns_to_own_page(robokassa):  # noqa: F811
    """Success URL в кабинете Robokassa один (/plus/done), поэтому донат
    возвращает на «спасибо» сам — SuccessUrl2, отказ — FailUrl2; оба в подписи."""
    url = billing.robokassa_url(7, 300, "x", "https://x/donate/done?k=K")
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["SuccessUrl2"] == "https://x/donate/done?k=K" and q["SuccessUrl2Method"] == "GET"
    assert q["FailUrl2"] == "https://x/donate?k=K" and q["FailUrl2Method"] == "GET"
    want = hashlib.md5("shop:300.00:7:https://x/donate/done?k=K:GET:https://x/donate?k=K:GET:p1".encode())
    assert q["SignatureValue"] == want.hexdigest()
    plain = {k: v[0] for k, v in parse_qs(urlparse(billing.robokassa_url(7, 300, "x")).query).items()}
    assert "SuccessUrl2" not in plain and plain["SignatureValue"] == hashlib.md5(b"shop:300.00:7:p1").hexdigest()
