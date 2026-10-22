"""kap check (tools/env_check.py): итоги проверок и что секреты не печатаются."""

import asyncio

import pytest

from tools import env_check as ec


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("REVIEW_CODE", "PD_FIO", "PD_INN", "PD_EMAIL", "PD_CITY", "BACKUP_KEY", "AI_MAIN",
                 "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET", "VK_CLIENT_ID", "BOT_TOKEN",
                 "ROBOKASSA_LOGIN", "ROBOKASSA_PASS1", "ROBOKASSA_PASS2"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_review_code(clean_env):
    assert ec.check_review_code().mark == ec.OFF
    clean_env.setenv("REVIEW_CODE", "short")
    assert ec.check_review_code().mark == ec.BAD
    clean_env.setenv("REVIEW_CODE", "x" * 12)
    assert ec.check_review_code().mark == ec.OK


def test_requisites(clean_env):
    assert ec.check_requisites().mark == ec.BAD
    for k, v in {"PD_FIO": "Иванов И. И.", "PD_INN": "123", "PD_EMAIL": "a@b.ru", "PD_CITY": "Москва"}.items():
        clean_env.setenv(k, v)
    assert ec.check_requisites().mark == ec.WARN          # ИНН самозанятого — 12 цифр
    clean_env.setenv("PD_INN", "123456789012")
    assert ec.check_requisites().mark == ec.OK


def test_backup_key(clean_env):
    assert ec.check_backup_key().mark == ec.WARN
    clean_env.setenv("BACKUP_KEY", "длинный-ключ-копии-базы")
    assert ec.check_backup_key().mark == ec.OK


def test_ai_main(clean_env):
    assert ec.check_ai_main().mark == ec.OK
    clean_env.setenv("AI_MAIN", "ling")
    assert ec.check_ai_main().mark == ec.BAD


def test_no_bot_token(clean_env):
    rows = asyncio.run(ec.check_telegram())
    assert rows[0][0] == "BOT_TOKEN" and rows[0][1].mark == ec.BAD


def test_robokassa_partial(clean_env):
    clean_env.setenv("ROBOKASSA_LOGIN", "kapibara")
    res = asyncio.run(ec.check_robokassa())
    assert res.mark == ec.BAD and "ROBOKASSA_PASS1" in res.text


@pytest.mark.parametrize("err,mark", [("invalid_grant", ec.OK), ("invalid_client", ec.BAD)])
def test_yandex(clean_env, err, mark):
    clean_env.setenv("YANDEX_CLIENT_ID", "id")
    clean_env.setenv("YANDEX_CLIENT_SECRET", "secret")

    async def probe(url, data):
        return 400, err
    clean_env.setattr(ec, "_oauth_probe", probe)
    assert asyncio.run(ec.check_yandex()).mark == mark


def test_env_file_typo_and_empty(clean_env):
    clean_env.setenv("GEMENI_API_KEY", "x")
    clean_env.setenv("VK_CLIENT_ID", "")
    rows = dict(ec.env_file_problems(["GEMENI_API_KEY", "VK_CLIENT_ID", "BOT_TOKEN"], ec.known_names()))
    assert rows["GEMENI_API_KEY"].mark == ec.BAD           # опечатка
    assert rows["VK_CLIENT_ID"].mark == ec.WARN            # задана пустой
    assert "BOT_TOKEN" not in rows


def test_known_names_cover_code():
    names = ec.known_names()
    for n in ("BOT_TOKEN", "GEMINI_API_KEY", "ROBOKASSA_PASS2", "REVIEW_CODE", "XRAY_CONFIG", "YANDEX_CLIENT_SECRET"):
        assert n in names


def test_render_hides_secrets(clean_env):
    clean_env.setenv("BOT_TOKEN", "123456:SECRET-token-value")
    out = ec.render([("Telegram", [("BOT_TOKEN", ec.Result(ec.BAD, "ошибка 123456:SECRET-token-value"))])])
    assert "SECRET-token-value" not in out and "•••" in out
    assert "Итого: ❌ 1" in out


def test_run_assembles_sections(clean_env):
    """Все живые проверки подменены: run собирает разделы и не падает от сломанной."""
    async def ok_list():
        return [("X", ec.Result(ec.OK, "да"))]

    async def ok():
        return ec.Result(ec.OK, "да")

    async def boom():
        raise RuntimeError("сеть")
    for name in ("check_telegram", "check_openrouter", "check_gemini"):
        clean_env.setattr(ec, name, ok_list)
    for name in ("check_deepseek", "check_proxy", "check_webapp", "check_ical", "check_sdo_cookie", "check_s3",
                 "check_robokassa", "check_yookassa", "check_yandex", "check_apple", "check_fcm", "check_rustore"):
        clean_env.setattr(ec, name, ok)
    clean_env.setattr(ec, "check_apns", boom)
    clean_env.setenv("GEMENI_API_KEY", "x")
    sections = dict(asyncio.run(ec.run(["GEMENI_API_KEY"])))
    assert set(sections) >= {"Telegram", "ИИ", "Оплата", "Пуши", "Файл .env"}
    assert dict(sections["Пуши"])["APNS_*"].mark == ec.BAD
