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
async def test_grant_extends_and_founders_forever(db, monkeypatch, robokassa):
    from database import set_setting
    _today(monkeypatch, date(2026, 10, 16))
    for uid in (ME, FRIEND):
        await db.upsert_user(uid, "", "u")
    assert (await billing.prices(ME))[0] == {"plan": "month", "title": "Месяц", "days": 30, "price": 149,
                                            "full": 249, "founder": True}
    await billing.create(ME, "month", "https://x/done")
    pid = (await _payments(db))[0]
    assert await billing.paid(pid) and not await billing.paid(pid)           # повтор уведомления — не продлевает
    st = await billing.status(ME)
    assert st["active"] and st["until"] == "2026-11-14" and st["founder"]
    assert await billing.grant(ME, 5, "test") == "2026-11-19"                # продление — от конца срока

    await set_setting("plus:stage", "full")                                  # Никита: «249 — я скажу»
    assert [p["price"] for p in await billing.prices(FRIEND)] == [249, 790]  # новым — полная
    _today(monkeypatch, date(2027, 3, 1))                                    # долгий перерыв — цена та же
    assert [p["price"] for p in await billing.prices(ME)] == [149, 649]
    await billing.grant(ME, 30, "pay")
    assert (await billing.status(ME))["founder"]


@pytest.mark.asyncio
async def test_gift_for_own_group(db, monkeypatch):
    import plans
    from database import set_setting
    _today(monkeypatch, date(2026, 10, 20))
    await db.upsert_user(ME, "", "u")

    async def own(uid):
        return uid == ME
    monkeypatch.setattr(plans, "_own", own)
    st = await billing.status(ME)
    assert st["active"] and st["gift"] == billing.GIFT_UNTIL and not st["paid_until"]
    assert await plans.has_plus(ME) and not await plans.has_plus(FRIEND)
    assert await billing.grant(ME, 30, "pay") == "2027-01-30"               # оплата — после подарка
    await set_setting("plus:gift", "off")
    assert not (await billing.status(ME))["gift"]
    _today(monkeypatch, date(2027, 2, 1))
    await set_setting("plus:gift", "2027-01-31")                             # прошёл — не действует
    assert not await billing.gift_for(ME)


@pytest.mark.asyncio
async def test_yookassa_down_falls_back_to_robokassa(db, monkeypatch, robokassa):
    monkeypatch.setattr(billing, "YOOKASSA_SHOP_ID", "shop")
    monkeypatch.setattr(billing, "YOOKASSA_SECRET_KEY", "secret")
    await db.upsert_user(ME, "", "u")
    assert billing.provider() == "yookassa"

    async def down(*a, **k):
        raise billing.PayError("касса не отвечает")
    monkeypatch.setattr(billing, "_yookassa_create", down)
    url = await billing.create(ME, "month", "https://x/done")
    assert url.startswith(billing.ROBOKASSA_URL)
    monkeypatch.setattr(billing, "ROBOKASSA_PASS2", "")                      # Robokassa нет — ошибка как есть
    with pytest.raises(billing.PayError):
        await billing.create(ME, "month", "https://x/done")


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

    assert hook("649.00", "чужой").status_code == 400                        # подпись не та
    assert hook("10.00").status_code == 400                                  # сумма меньше
    assert hook("649.00").text == f"OK{inv}"
    assert hook("649.00").text == f"OK{inv}"                                 # повтор — без второго продления
    st = await billing.status(ME)
    assert st["active"] and st["founder"]                                    # по цене первых — «Основатель»
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
async def test_starosta_switches_and_launch_news(db, bot, dp, monkeypatch):  # noqa: F811
    from database import get_setting
    from tests.conftest import STAROSTA_ID
    from tests.test_review_bot import press
    import scheduler
    monkeypatch.setattr(scheduler, "PACE_SECONDS", 0)
    await send(dp, bot, "/plus stage full", uid=ME)                          # не староста — обычный /plus
    assert await get_setting("plus:stage") is None
    await send(dp, bot, "/plus stage full", uid=STAROSTA_ID)
    assert await get_setting("plus:stage") == "full" and "полная цена" in bot.session.texts()[-1]
    await send(dp, bot, "/plus gift 15.01.2027", uid=STAROSTA_ID)
    assert await billing.gift_until() == "2027-01-15"
    await send(dp, bot, "/plus gift завтра", uid=STAROSTA_ID)
    assert await billing.gift_until() == "2027-01-15" and "Так:" in bot.session.texts()[-1]

    await db.upsert_user(ME, "", "u")
    await send(dp, bot, "/plusnews", uid=STAROSTA_ID)                        # превью, ничего не разослано
    assert "Появилась «Капибара+»" in bot.session.texts()[-2]
    assert await get_setting("plus:announced") is None
    before = len(bot.session.texts())
    await press(dp, bot, "plus:news:go", uid=STAROSTA_ID)
    sent = bot.session.texts()[before:]
    assert any("Появилась «Капибара+»" in t and "uiboshki.ru" in t for t in sent)
    assert await get_setting("plus:announced")


@pytest.mark.asyncio
async def test_launch_text_gift_and_where_to_pay(db, monkeypatch, robokassa):
    import plans
    from handlers.plus import launch_text, plus_text
    await db.upsert_user(ME, "", "u")

    async def own(uid):
        return uid == ME
    monkeypatch.setattr(plans, "_own", own)
    mine, other = await launch_text(ME), await launch_text(FRIEND)
    assert "в подарок до 31 декабря" in mine and "подарок" not in other
    assert "149 ₽" in other and "навсегда" not in other and "так и платит всегда" in other
    assert "на сайте uiboshki.ru" in other and "iPhone" in other
    text, kb = await plus_text(ME)
    assert "подарок твоей группе" in text and "Платить ничего не нужно" in text


@pytest.mark.asyncio
async def test_start_plus_deeplink(db, bot, dp):  # noqa: F811
    await db.upsert_user(ME, "", "u")
    await send(dp, bot, "/start plus", uid=ME)
    assert "Капибара+" in bot.session.texts()[-1]
    await send(dp, bot, "/start plus", uid=FRIEND)                           # новый — сначала приветствие
    assert any("Привет" in t for t in bot.session.texts())


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


async def _invited_and_active(db, inviter, friend):
    """friend пришёл по ссылке inviter и попользовался FRIEND_DAYS дней."""
    from database.billing import ref_code
    await db.upsert_user(friend, "", f"f{friend}")
    assert await referrals.bind(friend, await ref_code(inviter), was_new=True)
    async with aiosqlite.connect(db.DATABASE_PATH) as conn:
        for i in range(referrals.FRIEND_DAYS):
            await conn.execute("INSERT INTO events (user_id, kind, at) VALUES (?, 'open', datetime('now', ?))",
                               (friend, f"+{i} days"))
        await conn.commit()


@pytest.mark.asyncio
async def test_invite_limit_three_friends_for_all_time(db, monkeypatch):
    # Никита 18.10: «максимум 3 человека по приглашению дают подписку» — пригласившему,
    # за всё время; друг свои дни получает всегда, а пригласившему пишем честно
    from database.billing import get_bonuses
    sent = []

    async def notify(_bot, uid, text):
        sent.append((uid, text))
    monkeypatch.setattr(billing, "notify", notify)
    assert referrals.REF_MAX == 3 and not hasattr(referrals, "REF_PERIOD")
    await db.upsert_user(ME, "", "u")
    friends = [FRIEND + i for i in range(4)]
    for f in friends:
        await _invited_and_active(db, ME, f)
        assert await referrals.check(f, bot=object())
    mine = [b for b in await get_bonuses(ME) if b["kind"] == "ref"]
    assert len(mine) == 3 and sum(b["days"] for b in mine) == 3 * referrals.REF_BONUS
    for f in friends:                                                         # четвёртый друг — тоже с днями
        assert [b["days"] for b in await get_bonuses(f)] == [referrals.REF_BONUS]
    to_me = [t for uid, t in sent if uid == ME]
    assert "Это 3-й друг" in to_me[2] and "друзьям дни по-прежнему дают" in to_me[2]
    assert "ему +7 дней" in to_me[3] and "Ты уже позвал 3 друзей — бонус за приглашения закончился" in to_me[3]
    s = await referrals.summary(ME)
    assert (s["ref_max"], s["ref_counted"], s["rewarded"]) == (3, 3, 4)
    assert referrals.invite_line(s).endswith("Ты уже позвал 3 друзей — бонус за приглашения закончился, "
                                             "друзьям дни по-прежнему дают.")
    assert "вам обоим" not in referrals.invite_line(s)
    assert "максимум за 3 друзей, засчитано 0 из 3" in referrals.invite_line({"ref_max": 3, "ref_counted": 0})


@pytest.mark.asyncio
async def test_invite_limit_shown_everywhere(db, bot, dp, client, robokassa):  # noqa: F811
    c, _ = client
    h = _headers_for(ME)
    await db.upsert_user(ME, "", "u")
    inv = c.get("/api/invite", headers=h).json()
    assert (inv["ref_max"], inv["ref_counted"]) == (3, 0)                    # число — с сервера, фронты его не держат
    assert c.get("/api/plus", headers=h).json()["invite"]["ref_max"] == 3
    assert "ref_max" not in c.get("/api/invite", headers={**h, "X-App": "ios"}).json()
    assert "максимум за 3 друзей" in c.get(f"/plus?k={billing.make_key(ME)}").text      # сайт /plus
    import offer_text
    assert any("не больше чем за 3 друзей" in b for sec in offer_text.OFFER["sections"]
               for b in sec["blocks"] if isinstance(b, str))
    await send(dp, bot, "/plus", uid=ME)
    assert "максимум за 3 друзей, засчитано 0 из 3" in bot.session.texts()[-1]
    await send(dp, bot, "/invite", uid=ME)
    assert "максимум за 3 друзей" in bot.session.texts()[-1]
    from handlers.plus import launch_text
    assert "максимум за 3 друзей" in await launch_text(ME)
    for f in range(3):                                                       # лимит выбран
        await _invited_and_active(db, ME, FRIEND + f)
        await referrals.check(FRIEND + f)
    assert c.get("/api/invite", headers=h).json()["ref_counted"] == 3
    await send(dp, bot, "/plus", uid=ME)
    assert "Ты уже позвал 3 друзей — бонус за приглашения закончился" in bot.session.texts()[-1]
    await send(dp, bot, "/invite", uid=ME)
    assert "друзьям дни по-прежнему дают" in bot.session.texts()[-1]
