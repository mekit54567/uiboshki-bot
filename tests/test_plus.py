"""«Капибара+» (billing.py, referrals.py, webapp/routes/billing.py, handlers/plus.py):
срок без лета, цена «Основателя», оплата один раз на платёж, подпись ссылки
и уведомлений касс, бонусы за ранг и друга, iOS без подписки, удаление данных."""
import hashlib
from datetime import date

import aiosqlite
import pytest

import billing
import referrals
from tests.test_review_bot import send
from tests.test_review_bot import bot, dp  # noqa: F401 — фикстуры
from tests.test_webapp_home import _headers_for, client  # noqa: F401 — фикстура

ME, FRIEND = 501, 502


@pytest.fixture
def robokassa(monkeypatch):
    monkeypatch.setattr(billing, "ROBOKASSA_LOGIN", "shop")
    monkeypatch.setattr(billing, "ROBOKASSA_PASS1", "p1")
    monkeypatch.setattr(billing, "ROBOKASSA_PASS2", "p2")
    monkeypatch.setattr(billing, "YOOKASSA_SHOP_ID", "")
    import privacy
    for k, v in (("FIO", "Иванов Никита"), ("INN", "123456789012"), ("EMAIL", "a@b.ru")):
        monkeypatch.setattr(privacy, k, v)


def _today(monkeypatch, d: date):
    import utils
    monkeypatch.setattr(utils, "today_msk", lambda: d)


async def _events(db_path, uid, days):
    async with aiosqlite.connect(db_path) as conn:
        for i in range(days):
            await conn.execute("INSERT INTO events (user_id, kind, at) VALUES (?, 'open', datetime('now', ?))",
                               (uid, f"-{i} days"))
        await conn.commit()


def test_summer_does_not_count():
    assert billing.add_days(date(2026, 10, 1), 30) == date(2026, 10, 30)
    assert billing.add_days(date(2027, 6, 21), 30) == date(2027, 9, 20)      # 10 дней июня + 20 сентября
    assert billing.add_days(date(2027, 7, 15), 1) == date(2027, 9, 1)        # куплено летом — с сентября


def test_pay_link_key():
    key = billing.make_key(ME, now=1000)
    assert billing.read_key(key, now=1000) == ME
    assert billing.read_key(key, now=1000 + billing.LINK_TTL + 1) is None    # просрочена
    uid, exp, sig = key.split(".")
    assert billing.read_key(f"{FRIEND}.{exp}.{sig}", now=1000) is None       # чужой id с той же подписью
    assert billing.read_key("мусор", now=1000) is None


@pytest.mark.asyncio
async def test_grant_extends_and_founders(db, monkeypatch, robokassa):
    _today(monkeypatch, date(2026, 10, 16))
    monkeypatch.setattr(billing, "FOUNDERS_LIMIT", 1)
    for uid in (ME, FRIEND):
        await db.upsert_user(uid, "", "u")
    assert (await billing.prices(ME))[0] == {"plan": "month", "title": "Месяц", "days": 30, "price": 149,
                                            "full": 249, "founder": True}
    await billing.create(ME, "month", "https://x/done")
    pid = (await _payments(db))[0]
    assert await billing.paid(pid) and not await billing.paid(pid)           # повтор уведомления — не продлевает
    st = await billing.status(ME)
    assert st["active"] and st["until"] == "2026-11-14" and st["founder"]
    assert (await billing.prices(FRIEND))[0]["price"] == 249                 # место одно — уже занято
    assert await billing.grant(ME, 5, "test") == "2026-11-19"                # продление — от конца срока

    _today(monkeypatch, date(2027, 1, 1))                                    # перерыв больше 30 дней
    assert (await billing.prices(ME))[0]["price"] == 249
    await billing.grant(ME, 30, "pay")
    assert not (await billing.status(ME))["founder"]


async def _payments(db):
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        return [r[0] for r in await (await conn.execute("SELECT id FROM payments ORDER BY created_at")).fetchall()]


@pytest.mark.asyncio
async def test_page_and_robokassa_hook(db, client, monkeypatch, robokassa):  # noqa: F811
    c, _ = client
    await db.upsert_user(ME, "", "u")
    assert c.get("/plus").status_code == 403
    key = billing.make_key(ME)
    page = c.get(f"/plus?k={key}").text
    assert "149 ₽" in page and "/offer" in page
    r = c.post("/plus/pay", data={"k": key, "plan": "semester"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(billing.ROBOKASSA_URL)
    inv = (await _payments(db))[0]

    def hook(out_sum, sig_pass="p2"):
        sig = hashlib.md5(f"{out_sum}:{inv}:{sig_pass}".encode()).hexdigest().upper()
        return c.post("/api/billing/robokassa", data={"OutSum": out_sum, "InvId": inv, "SignatureValue": sig})

    assert hook("790.00", "чужой").status_code == 400                        # подпись не та
    assert hook("10.00").status_code == 400                                  # сумма меньше
    assert hook("790.00").text == f"OK{inv}"
    assert hook("790.00").text == f"OK{inv}"                                 # повтор — без второго продления
    st = await billing.status(ME)
    assert st["active"] and not st["founder"]
    assert c.get(f"/plus/state?k={key}").json()["active"]
    assert c.get("/api/me", headers=_headers_for(ME)).json()["plus"] is True
    assert "Оферта" in c.get("/offer").text


@pytest.mark.asyncio
async def test_yookassa_hook_trusts_only_api(db, client, monkeypatch):  # noqa: F811
    c, _ = client
    await db.upsert_user(ME, "", "u")
    from database.billing import add_payment
    await add_payment("yk-1", "yookassa", ME, "month", 149, 30)
    answers = {"yk-1": "pending"}

    async def check(pid):
        return answers[pid]
    monkeypatch.setattr(billing, "yookassa_check", check)
    hook = {"type": "notification", "event": "payment.succeeded", "object": {"id": "yk-1"}}
    assert c.post("/api/billing/yookassa", json=hook).json() == {"ok": True}
    assert not (await billing.status(ME))["active"]                          # тело сказало «оплачено», ЮKassa — нет
    answers["yk-1"] = "succeeded"
    c.post("/api/billing/yookassa", json=hook)
    assert (await billing.status(ME))["active"]
    assert c.post("/api/billing/yookassa", json={"object": {"id": "чужой"}}).json() == {"ok": True}


@pytest.mark.asyncio
async def test_api_plus_and_ios(db, client, robokassa):  # noqa: F811
    c, _ = client
    h = _headers_for(ME)
    d = c.get("/api/plus", headers=h).json()
    assert not d["hidden"] and d["pay_url"].startswith(billing.site() + "/plus?k=")
    assert d["invite"]["link"].startswith("https://t.me/") and "?start=ref_" in d["invite"]["link"]
    assert "МИРЭА" in d["invite"]["share_text"]
    ios = c.get("/api/plus", headers={**h, "X-App": "ios"}).json()
    assert ios == {"hidden": True}                                            # App Store: ни цен, ни «купить»
    inv = c.get("/api/invite", headers={**h, "X-App": "ios"}).json()
    assert inv["link"] == d["invite"]["link"] and "bonus_days" not in inv     # позвать — можно, про подписку — нет
    assert inv["tg_share"].startswith("https://t.me/share/url?url=https%3A%2F%2Ft.me%2F")
    assert c.get("/api/invite", headers=h).json()["bonus_days"] == referrals.REF_BONUS


@pytest.mark.asyncio
async def test_rank_bonus_needs_real_days(db, client):  # noqa: F811
    c, _ = client
    h = _headers_for(ME)
    c.get("/api/plus", headers=h)
    r = c.post("/api/plus/rank", headers=h, json={"rank": "noon"})
    assert r.status_code == 400 and "7 разных дней" in r.json()["detail"]
    await _events(db.DATABASE_PATH, ME, 7)
    r = c.post("/api/plus/rank", headers=h, json={"rank": "noon"})
    assert r.json()["days"] == 5
    assert c.post("/api/plus/rank", headers=h, json={"rank": "noon"}).status_code == 400   # второй раз нет
    assert c.post("/api/plus/rank", headers=h, json={"rank": "king"}).status_code == 400
    assert (await billing.status(ME))["active"]


@pytest.mark.asyncio
async def test_rank_bonus_waits_for_server_achievements(db, monkeypatch):
    import sys
    import types
    closed = {"v": False}

    async def rank_closed(uid, rank):
        return closed["v"]
    monkeypatch.setitem(sys.modules, "achievements", types.SimpleNamespace(rank_closed=rank_closed))
    await db.upsert_user(ME, "", "u")
    await _events(db.DATABASE_PATH, ME, 1)
    with pytest.raises(referrals.BonusError) as e:
        await referrals.claim_rank(ME, "dawn")
    assert "уже" not in str(e.value) and "нет такого" not in str(e.value)   # приложение спросит снова
    closed["v"] = True
    assert (await referrals.claim_rank(ME, "dawn"))["days"] == 3


@pytest.mark.asyncio
async def test_invite_friend(db, monkeypatch):
    from database.billing import ref_code
    await db.upsert_user(ME, "", "u")
    code = await ref_code(ME)
    assert await ref_code(ME) == code
    assert not await referrals.bind(ME, code, was_new=True)                   # сам себя — нет
    assert not await referrals.bind(FRIEND, code, was_new=False)              # уже был в боте — нет
    assert await referrals.bind(FRIEND, code, was_new=True)
    assert not await referrals.check(FRIEND)                                  # ещё не пользуется
    await _events(db.DATABASE_PATH, FRIEND, 1)
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:                   # три дня после ссылки
        for i in (1, 2):
            await conn.execute("INSERT INTO events (user_id, kind, at) VALUES (?, 'open', datetime('now', ?))",
                               (FRIEND, f"+{i} days"))
        await conn.commit()
    assert await referrals.check_all() == 1
    assert (await billing.status(ME))["active"] and (await billing.status(FRIEND))["active"]
    assert not await referrals.check(FRIEND)                                  # награда — один раз
    assert (await referrals.summary(ME))["rewarded"] == 1


@pytest.mark.asyncio
async def test_invite_deeplink_only_for_new(db, bot, dp):  # noqa: F811
    from database.billing import get_referral, ref_code
    await db.upsert_user(ME, "", "u")
    await db.upsert_user(FRIEND + 1, "", "old")
    code = await ref_code(ME)
    await send(dp, bot, f"/start ref_{code}", uid=FRIEND)
    await send(dp, bot, f"/start ref_{code}", uid=FRIEND + 1)
    assert (await get_referral(FRIEND))["inviter_id"] == ME
    assert await get_referral(FRIEND + 1) is None


@pytest.mark.asyncio
async def test_invite_command_and_inline(db, bot, dp):  # noqa: F811
    await send(dp, bot, "/invite", uid=ME)
    first = [m for n, m in bot.session.calls if n in ("SendPhoto", "SendMessage")][0]
    assert "МИРЭА" in (getattr(first, "caption", None) or getattr(first, "text", ""))
    url = first.reply_markup.inline_keyboard[0][0].url
    assert url.startswith("https://t.me/") and "start=ref_" in url
    await send(dp, bot, "/plus", uid=ME)
    assert "Капибара+" in bot.session.texts()[-1]


@pytest.mark.asyncio
async def test_erase_keeps_payments_without_person(db):
    import privacy
    from database.billing import add_payment, add_referral, get_referral
    await db.upsert_user(ME, "", "u")
    await add_payment("p-1", "robokassa", ME, "month", 249, 30)
    await add_referral(FRIEND, ME)
    await privacy.erase(ME)
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        row = await (await conn.execute("SELECT payer_id, amount FROM payments")).fetchone()
    assert row == (None, 249)                                                 # налоговый учёт — без человека
    assert await get_referral(FRIEND) is None


def test_no_requisites_no_payment(monkeypatch, robokassa):
    import legal_texts
    import privacy
    assert billing.provider() == "robokassa"
    assert "Робокасса" in str(legal_texts.doc("privacy")) and "ЮKassa" not in str(legal_texts.doc("privacy"))
    monkeypatch.setattr(privacy, "INN", "")                                   # оферта без ИНН — оплату не открываем
    assert billing.provider() == "" and billing.provider(configured_only=True) == "robokassa"
    assert billing.missing_requisites() == ["PD_INN"]


@pytest.mark.asyncio
async def test_yookassa_metadata_without_person(db, monkeypatch, robokassa):
    """152-ФЗ: у кассы не должно оставаться id человека — связь только в payments."""
    monkeypatch.setattr(billing, "YOOKASSA_SHOP_ID", "shop")
    monkeypatch.setattr(billing, "YOOKASSA_SECRET_KEY", "key")
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "yk-9", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay"}}

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
    assert await billing.create(ME, "month", "https://x/done") == "https://yoomoney.ru/pay"
    assert str(ME) not in str(sent) and sent["metadata"] == {"plan": "month"}
