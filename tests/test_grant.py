"""Ручные выдачи «Капибары+» (/grant, plus_grant.py), безлимит, своя группа в
лимитах подписки и приветствие «У тебя активна «Капибара+»» (plus_welcome.py)."""
import asyncio
from datetime import date

import pytest

import billing
import config
import plus_grant
import ratelimit
from tests.conftest import STAROSTA_ID
from tests.test_review_bot import send
from tests.test_review_bot import bot, dp  # noqa: F401 — фикстуры

ME, OTHER_UID, LOCAL = 701, 702, -10_000_000_005
OTHER_GROUP = 5001


def _today(monkeypatch, d: date):
    import utils
    box = [d]
    monkeypatch.setattr(utils, "today_msk", lambda: box[0])
    return box


@pytest.fixture
def no_minute_limit(monkeypatch):
    monkeypatch.setattr(ratelimit, "allow", lambda action, uid: True)


def _to(bot, uid):  # noqa: F811
    return [m.text for m in bot.session.named("SendMessage") if m.chat_id == uid]


def test_parse_term():
    p = plus_grant.parse_term
    assert (p("3m"), p("45d"), p("1y"), p("3 мес"), p("2г"), p("10дней"), p("1M")) == (90, 45, 300, 90, 600, 10, 30)
    assert p("0d") is None and p("abc") is None and p("3") is None and p("99999d") is None


@pytest.mark.asyncio
async def test_find_user(db):
    await db.upsert_user(ME, "Vasya_K", "Вася")
    await db.upsert_user(LOCAL, "", "Без Телеграма")                        # аккаунт приложения (VK/Яндекс)
    await db.upsert_user(OTHER_UID, "twin", "Один")
    await db.upsert_user(OTHER_UID + 1, "TWIN", "Другой")
    assert (await plus_grant.find_user("@vasya_k"))["user_id"] == ME        # без учёта регистра
    assert (await plus_grant.find_user("VASYA_K"))["user_id"] == ME
    assert (await plus_grant.find_user(str(ME)))["full_name"] == "Вася"
    assert (await plus_grant.find_user(str(LOCAL)))["user_id"] == LOCAL
    for who, msg in (("@nobody", "Не нашёл"), ("123456", "Нет человека"), ("@twin", "несколько"), ("@!!", "Кого?")):
        with pytest.raises(plus_grant.GrantError, match=msg):
            await plus_grant.find_user(who)


@pytest.mark.asyncio
async def test_extend_adds_to_term_and_off_keeps_paid(db, bot, monkeypatch):  # noqa: F811
    _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "vasya", "Вася")
    assert await billing.grant(ME, 30, "pay") == "2026-11-14"               # купил месяц
    out = await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "3m"])
    assert "до 12.02.2027" in out and "Ему написал" in out                  # +90 после оплаченного
    note = _to(bot, ME)[-1]
    assert "Тебе продлили «Капибару+»: активна до 12.02.2027 — бесплатно" in note
    assert f"{config.AI_SUB_DAILY} вопросов к ИИ в день" in note and "«Подумать ещё»" in note
    assert await billing.grant(ME, 30, "pay") == "2027-03-14"               # купил ещё — после ручных
    out = await plus_grant.command(bot, STAROSTA_ID, ["@vasya"])
    assert "Подписка: до 14.03.2027" in out and "вручную" in out and "оплата" in out

    out = await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "off"])       # ручные 90 — прочь, купленные 60 — нет
    assert "ручные дни сняты, подписка до 14.12.2026" in out
    assert (await billing.status(ME))["paid_until"] == "2026-12-14"
    assert "Снимать нечего" in await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "off"])


@pytest.mark.asyncio
async def test_off_without_paid_ends_now(db, bot, monkeypatch):  # noqa: F811
    _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "", "Вася")
    await plus_grant.command(bot, STAROSTA_ID, [str(ME), "45d"])
    assert (await billing.status(ME))["paid_until"] == "2026-11-29"
    out = await plus_grant.command(bot, STAROSTA_ID, [str(ME), "off", "sub"])
    assert "подписка кончилась" in out and not (await billing.status(ME))["active"]


@pytest.mark.asyncio
async def test_unlimited_bypasses_quota(db, bot, monkeypatch, no_minute_limit):  # noqa: F811
    import ai_quota
    import plans
    day = _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "vasya", "Вася")
    await db.set_user_group(ME, OTHER_GROUP)                                 # чужая группа — проба
    assert await plans.plan_of(ME) == plans.BASE
    out = await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "безлимит"])
    assert "безлимит навсегда" in out
    assert "Тебе выдали безлимит: «Капибара+» навсегда" in _to(bot, ME)[-1]
    assert await plans.plan_of(ME) == plans.UNL and await plans.has_plus(ME)
    for _ in range(config.AI_TRIAL_DAILY + 5):
        assert await ai_quota.gate(ME) is None
    for _ in range(config.SUMMARY_WEEKLY + 2):
        assert await ai_quota.gate(ME, kind="summary") is None
    assert await ai_quota.left(ME) is None
    st = await billing.status(ME)
    assert st["active"] and st["unlimited"] and st["unlimited_until"] is None

    await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "unlimited", "20.10.2026"])   # до дня
    assert await plans.plan_of(ME) == plans.UNL
    day[0] = date(2026, 10, 21)                                              # прошёл — снова проба
    assert await plans.plan_of(ME) == plans.BASE and not await plans.has_plus(ME)
    assert "не в прошлом" in await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "unlimited", "01.01.2020"])

    await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "unlimited"])
    out = await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "off", "unlimited"])
    assert "безлимит снят" in out and await plans.plan_of(ME) == plans.BASE
    for _ in range(config.AI_TRIAL_DAILY):
        await ai_quota.gate(ME)
    assert await ai_quota.gate(ME) == "trial"


@pytest.mark.asyncio
async def test_own_group_gift_has_sub_limits_then_own(db, monkeypatch, no_minute_limit):
    """Своя группа с подарком — лимиты подписки; подарок кончился — свой
    бесплатный лимит группы. Никита — без лимитов, старосты групп — как все."""
    import ai_quota
    import plans
    from database.groups import add_group_admin
    day = _today(monkeypatch, date(2026, 10, 20))
    monkeypatch.setattr(config, "AI_SUB_DAILY", 2)
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 0)
    await db.upsert_user(ME, "", "Вася")
    await db.set_user_group(ME, config.HOME_GROUP_ID)
    assert await plans.plan_of(ME) == plans.SUB
    assert await ai_quota.left(ME) == {"left": 2, "limit": 2}
    assert await ai_quota.gate(ME) is None and await ai_quota.gate(ME) is None
    assert await ai_quota.gate(ME) == "sub"
    day[0] = date(2027, 1, 2)                                                # подарок до 31.12.2026 кончился
    assert await plans.plan_of(ME) == plans.OWN
    for _ in range(5):
        assert await ai_quota.gate(ME) is None                               # AI_DAILY_LIMIT=0 — без лимита
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 6)                         # по умолчанию 20 — бесплатный лимит группы
    assert await ai_quota.gate(ME) is None and await ai_quota.gate(ME) == "day"

    for _ in range(20):
        assert await ai_quota.gate(STAROSTA_ID) is None
    assert await plans.plan_of(STAROSTA_ID) == plans.OWN and await ai_quota.left(STAROSTA_ID) is None

    await db.upsert_user(OTHER_UID, "", "Староста чужой")
    await db.set_user_group(OTHER_UID, OTHER_GROUP)
    await add_group_admin(OTHER_GROUP, OTHER_UID, STAROSTA_ID)
    assert await plans.plan_of(OTHER_UID) == plans.BASE                      # староста группы — как все
    for _ in range(config.AI_TRIAL_DAILY):
        await ai_quota.gate(OTHER_UID)
    assert await ai_quota.gate(OTHER_UID) == "trial"


@pytest.mark.asyncio
async def test_grant_command_only_for_nikita(db, bot, dp, monkeypatch):  # noqa: F811
    _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "vasya", "Вася")
    await db.set_user_group(ME, OTHER_GROUP)
    await send(dp, bot, "/grant @vasya 3m", uid=OTHER_UID)
    assert "только для владельца" in bot.session.texts()[-1]
    assert not (await billing.status(ME))["active"]
    await send(dp, bot, "/grant", uid=STAROSTA_ID)
    assert "<code>/grant @ник 3m</code>" in bot.session.texts()[-1]
    await send(dp, bot, "/grant @vasya 1y", uid=STAROSTA_ID)
    assert "Готово: +300 дн." in bot.session.texts()[-1]
    assert any("Тебе продлили" in t for t in _to(bot, ME))
    await send(dp, bot, "/grant @vasya когда-нибудь", uid=STAROSTA_ID)
    assert "Не понял срок" in bot.session.texts()[-1]
    await send(dp, bot, "/help", uid=STAROSTA_ID)
    assert "/grant" in bot.session.texts()[-1]


@pytest.mark.asyncio
async def test_welcome_once_and_status_line(db, bot, dp, monkeypatch):  # noqa: F811
    import health
    import plus_welcome
    _today(monkeypatch, date(2026, 10, 20))
    await db.upsert_user(ME, "", "Вася")
    await db.set_user_group(ME, config.HOME_GROUP_ID)                        # своя группа — подарок
    await db.upsert_user(OTHER_UID, "", "Чужой")
    await db.set_user_group(OTHER_UID, OTHER_GROUP)

    monkeypatch.setattr(plus_welcome, "AUTO", True)
    for _ in range(2):                                                       # два захода — одно сообщение
        await send(dp, bot, "/help", uid=ME)
        await send(dp, bot, "/help", uid=OTHER_UID)
        await asyncio.gather(*list(plus_welcome._tasks))
    mine = [t for t in _to(bot, ME) if "активна «Капибара+»" in t]
    assert len(mine) == 1 and "У тебя активна «Капибара+» до 31.12.2026 — бесплатно" in mine[0]
    assert not any("активна «Капибара+»" in t for t in _to(bot, OTHER_UID))
    plus_welcome._checked.clear()                                            # перезапуск — отметка в базе
    assert not await plus_welcome.maybe_send(bot, ME)

    await plus_grant.command(bot, STAROSTA_ID, [str(OTHER_UID), "3m"])
    assert not await plus_welcome.maybe_send(bot, OTHER_UID)                 # выдали — уже написали
    await db.upsert_user(OTHER_UID + 1, "", "Ещё")
    await plus_grant.command(bot, STAROSTA_ID, [str(OTHER_UID + 1), "unlimited"])
    assert "Ручные выдачи (/grant): подписок 1 · безлимитов 1" in await health.report()


@pytest.mark.asyncio
async def test_erase_removes_grants(db, bot, monkeypatch):  # noqa: F811
    import privacy
    from database.billing import get_unlimited, grant_log, welcomed
    _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "", "Вася")
    await plus_grant.command(bot, STAROSTA_ID, [str(ME), "unlimited"])
    await plus_grant.command(bot, STAROSTA_ID, [str(ME), "45d"])
    await privacy.erase(ME)
    assert await grant_log(ME) == [] and await get_unlimited(ME) is None and not await welcomed(ME)


@pytest.mark.asyncio
async def test_plus_for_unlimited_has_no_prices_or_pay(db, bot, monkeypatch):  # noqa: F811
    # робот 18.10: у безлимита /plus показывал цены и «Оплатить на сайте»
    from handlers.plus import plus_text
    monkeypatch.setattr(billing, "provider", lambda configured_only=False: "yookassa")
    await db.upsert_user(ME, "vasya", "Вася")
    text, kb = await plus_text(ME)
    assert "₽" in text and any("Оплатить" in b.text for row in kb.inline_keyboard for b in row)
    await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "unlimited"])
    text, kb = await plus_text(ME)
    assert "У тебя безлимит</b> «Капибары+» навсегда" in text
    assert "₽" not in text and "Оплата" not in text
    assert not any("Оплатить" in b.text for row in kb.inline_keyboard for b in row)
    await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "unlimited", "20.12.2099"])
    assert "безлимит</b> «Капибары+» до 20 декабря 2099" in (await plus_text(ME))[0]


@pytest.mark.asyncio
async def test_grant_with_note(db, bot, dp, monkeypatch):  # noqa: F811
    """Никита 18.10: после срока или даты — личная приписка, уходит человеку
    вместе с сообщением о выдаче (курсивом, экранирована) и лежит в журнале."""
    from database.billing import grant_log
    _today(monkeypatch, date(2026, 10, 16))
    await db.upsert_user(ME, "vasya", "Вася")
    out = await plus_grant.command(bot, STAROSTA_ID, "@vasya 3m Спасибо, что помог с <расписанием>!")
    assert "до 13.01.2027" in out and "Ему написал с припиской" in out
    assert "<i>Приписка от Никиты: Спасибо, что помог с &lt;расписанием&gt;!</i>" in out   # Никите — как увидит он
    note = _to(bot, ME)[-1]
    assert "Тебе продлили «Капибару+»: активна до 13.01.2027" in note
    lines = note.split("\n")
    assert lines[2] == "<i>Приписка от Никиты: Спасибо, что помог с &lt;расписанием&gt;!</i>"   # отдельной строкой
    assert (await grant_log(ME, 1))[0]["note"] == "Спасибо, что помог с <расписанием>!"

    await plus_grant.command(bot, STAROSTA_ID, "@vasya 3 мес С первым курсом")       # срок из двух слов
    assert "Приписка от Никиты: С первым курсом" in _to(bot, ME)[-1]
    out = await plus_grant.command(bot, STAROSTA_ID, "@vasya unlimited 31.12.2026 Ты лучший\nправда")
    assert "безлимит до 31.12.2026" in out
    assert "<i>Приписка от Никиты: Ты лучший\nправда</i>" in _to(bot, ME)[-1]    # перенос строки — как написан
    out = await plus_grant.command(bot, STAROSTA_ID, "@vasya безлимит Навсегда твой")   # без даты — тоже приписка
    assert "безлимит навсегда" in out and "Приписка от Никиты: Навсегда твой" in _to(bot, ME)[-1]
    assert "«Навсегда твой»" in await plus_grant.command(bot, STAROSTA_ID, "@vasya")     # видно в журнале
    assert "не в прошлом" in await plus_grant.command(bot, STAROSTA_ID, "@vasya unlimited 01.01.2020 привет")
    assert "длинная" in await plus_grant.command(bot, STAROSTA_ID, "@vasya 1m " + "а" * 700)
    assert "Не понял срок" in await plus_grant.command(bot, STAROSTA_ID, "@vasya Спасибо 3m")

    plain = await plus_grant.command(bot, STAROSTA_ID, ["@vasya", "45d"])            # без приписки — как было
    assert "Ему написал." in plain and "Приписка" not in _to(bot, ME)[-1]
    assert "с припиской" in plus_grant.HELP

    await send(dp, bot, "/grant @vasya 1m Держи\nи учись", uid=STAROSTA_ID)          # команда в боте — с переносом
    assert "<i>Приписка от Никиты: Держи\nи учись</i>" in _to(bot, ME)[-1]
