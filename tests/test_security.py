"""Безопасность: ключ из секретной фразы с переходом без потерь, лимиты частоты."""
import pytest

import ratelimit
import sdo_accounts


def test_passphrase_key_and_rotation(monkeypatch):
    monkeypatch.delenv("SDO_CRYPT_KEY", raising=False)
    monkeypatch.delenv("SDO_CRYPT_PASSPHRASE", raising=False)
    old = sdo_accounts.encrypt("cookie-old-0123456789")          # ключ от токена бота
    monkeypatch.setenv("SDO_CRYPT_PASSPHRASE", "капибара катит мяч")
    assert sdo_accounts.key_source() == "passphrase"
    assert sdo_accounts.decrypt(old) == "cookie-old-0123456789"   # старое читается
    assert sdo_accounts.needs_rotation(old)                       # и будет перешифровано
    new = sdo_accounts.encrypt("cookie-old-0123456789")
    assert not sdo_accounts.needs_rotation(new)
    monkeypatch.setenv("SDO_CRYPT_PASSPHRASE", "другая фраза")
    assert sdo_accounts.decrypt(new) is None                      # без фразы не прочитать


@pytest.mark.asyncio
async def test_rotate_all_on_new_key(db, monkeypatch):
    """152-ФЗ, 16.10: задали отдельный ключ — при запуске все входы (и
    устаревшие) перешифровываются, не дожидаясь проверки; /status больше не
    предупреждает про ключ от BOT_TOKEN."""
    import health
    from database import get_sdo_sessions, save_sdo_session, set_sdo_status
    monkeypatch.delenv("SDO_CRYPT_KEY", raising=False)
    monkeypatch.delenv("SDO_CRYPT_PASSPHRASE", raising=False)
    await save_sdo_session(1, sdo_accounts.encrypt("cookie-one-0123456789"))
    await save_sdo_session(2, sdo_accounts.encrypt("cookie-two-0123456789"))
    await set_sdo_status(2, "expired")
    assert "ключом от BOT_TOKEN" in await health.report()
    assert await sdo_accounts.rotate_all() == {"rotated": 0, "unreadable": 0}

    monkeypatch.setenv("SDO_CRYPT_KEY", "-" * 43 + "=")            # 32 байта в base64 — годный ключ Fernet
    assert await sdo_accounts.rotate_all() == {"rotated": 2, "unreadable": 0}
    rows = await get_sdo_sessions("ok") + await get_sdo_sessions("expired")
    assert all(not sdo_accounts.needs_rotation(r["cookie_enc"]) for r in rows)
    assert {sdo_accounts.decrypt(r["cookie_enc"]) for r in rows} == {"cookie-one-0123456789", "cookie-two-0123456789"}
    assert "ключом от BOT_TOKEN" not in await health.report()
    monkeypatch.setenv("BOT_TOKEN", "другой")                      # токен бота больше не нужен для куки
    monkeypatch.setattr(sdo_accounts, "BOT_TOKEN", "другой")
    assert sdo_accounts.decrypt(rows[0]["cookie_enc"]) is not None


def test_rate_limit():
    ratelimit.reset()
    assert all(ratelimit.allow("submit", 1) for _ in range(6))
    assert not ratelimit.allow("submit", 1)
    assert ratelimit.allow("submit", 2)                            # у каждого свой счётчик
    ratelimit.reset()


def test_ratelimit_forgets_stale_keys(monkeypatch):
    """Ключи-IP с сайта не копятся вечно: при переполнении отжившие выкидываются."""
    ratelimit.reset()
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 10)
    clock = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock[0])
    for i in range(11):
        assert ratelimit.allow("site_search", -i - 1)
    clock[0] += 61
    assert ratelimit.allow("site_search", -100) and len(ratelimit._hits) == 1
    ratelimit.reset()


@pytest.mark.asyncio
async def test_ai_daily_limit_switch(db, monkeypatch):
    """AI_DAILY_LIMIT: 0 — без дневного лимита (но счёт идёт — для /stats);
    задан — после N вопросов за календарный день МСК «day»; старосте не
    действует; счёт в базе — деплой его не обнуляет; новый день — заново."""
    import ai_quota
    import config
    import database.homework
    from datetime import date
    from tests.conftest import STAROSTA_ID
    day = [date(2026, 10, 6)]
    monkeypatch.setattr("utils.today_msk", lambda: day[0])
    monkeypatch.setattr(ratelimit, "allow", lambda action, uid: True)      # минутный — не о том
    await db.upsert_user(555, "u", "U")
    await db.set_user_group(555, config.HOME_GROUP_ID)                     # своя группа — тариф own
    for _ in range(5):
        assert await ai_quota.gate(555) is None                            # по умолчанию выключен
    assert (await ai_quota.today())[555] == 5
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 6)
    assert await ai_quota.gate(555) is None and await ai_quota.gate(555) == "day"
    assert "6 в сутки" in ai_quota.text("day") and ai_quota.text("day", capital=True).startswith("На сегодня")
    assert await ai_quota.gate(555, day=False) is None                     # классификатор — не в счёт
    for _ in range(8):
        assert await ai_quota.gate(STAROSTA_ID) is None
    assert database.homework                                               # счёт в settings, не в памяти
    day[0] = date(2026, 10, 7)
    assert await ai_quota.gate(555) is None                                # новый день — заново
