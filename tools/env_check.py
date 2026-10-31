"""
`kap check` на сервере: проходит по переменным бота и показывает, что
работает (✅), что нет (❌ и почему), что не задано (⚪).

Повод (22.10): Kapi ИИ ответил запасной Gemini, потому что Ling молчал, а
узнать, какой ключ живой, было нечем. Где можно — живой лёгкий запрос к
сервису (ИИ — вопрос на пару токенов, кассы и входы — заведомо пустой
запрос, по ответу видно, приняли ли ключ). Значения секретов не печатаются:
только имя и итог, весь вывод ещё и вычищается от них (`_scrub`).

Запуск — `kap check` (внутри работающего контейнера: те же переменные и тот
же VPN, что у бота), или `python -m tools.env_check` из корня репозитория.
Имена из файла `.env`, которых код не знает (опечатка), — `KAP_ENV_NAMES`.
"""

import asyncio
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import net  # noqa: E402

TIMEOUT = 15
ROOT = Path(__file__).resolve().parent.parent

OK, BAD, WARN, OFF, NOTE = "✅", "❌", "⚠️", "⚪", "🔹"   # NOTE — задано, живой проверки нет


@dataclass
class Result:
    mark: str
    text: str


def env(name: str) -> str:
    return os.getenv(name, "").strip()


def _err(e: Exception) -> str:
    return f"не отвечает ({type(e).__name__})"


def _client(**kw) -> httpx.AsyncClient:
    return net.client(timeout=TIMEOUT, **kw)


# ── Telegram ────────────────────────────────────────────────────────────────

async def check_telegram() -> list[tuple[str, Result]]:
    if not env("BOT_TOKEN"):
        return [("BOT_TOKEN", Result(BAD, "не задан — бот не запустится"))]
    from aiogram import Bot
    from aiogram.exceptions import TelegramUnauthorizedError
    bot = Bot(token=env("BOT_TOKEN"), session=net.tg_session())
    out = []
    try:
        try:
            me = await asyncio.wait_for(bot.get_me(), TIMEOUT)
        except TelegramUnauthorizedError:
            return [("BOT_TOKEN", Result(BAD, "Telegram не принял токен (отозван в BotFather?)"))]
        except Exception as e:
            return [("BOT_TOKEN", Result(BAD, f"Telegram {_err(e)}"))]
        out.append(("BOT_TOKEN", Result(OK, f"бот @{me.username}")))
        want = env("BOT_USERNAME").lstrip("@")
        if want and want.lower() != (me.username or "").lower():
            out.append(("BOT_USERNAME", Result(BAD, f"@{want}, а токен от @{me.username} — ссылки t.me будут вести не туда")))
        elif want:
            out.append(("BOT_USERNAME", Result(OK, "совпадает с ботом")))
        out.append(("STAROSTA_ID", await _starosta(bot)))
        for name in ("CHANNEL_ID", "LOGIN_CHANNEL"):
            out.append((name, await _channel(bot, me.id, env(name))))
        out.append(("GROUP_CHAT_ID", await _group_chat(bot)))
    finally:
        await bot.session.close()
    return out


async def _starosta(bot) -> Result:
    raw = env("STAROSTA_ID")
    if not raw or raw == "0":
        return Result(BAD, "не задан — команды старосты никому не доступны")
    ids = [p.strip() for p in raw.split(",") if p.strip()]
    bad = []
    for i in ids:
        try:
            await asyncio.wait_for(bot.get_chat(int(i)), TIMEOUT)
        except ValueError:
            return Result(BAD, "не число (нужен id из Telegram, через запятую)")
        except Exception:
            bad.append(i)
    if bad:
        return Result(WARN, f"бот не видит {len(bad)} из {len(ids)} (не нажимали /start в боте?)")
    return Result(OK, f"бот видит {'всех ' + str(len(ids)) if len(ids) > 1 else 'аккаунт'}")


async def _channel(bot, bot_id: int, raw: str) -> Result:
    if not raw:
        return Result(OFF, "не задан")
    chat = raw if raw.lstrip("-").isdigit() else "@" + raw.split("/")[-1].lstrip("@")
    try:
        await asyncio.wait_for(bot.get_chat(chat), TIMEOUT)
        member = await asyncio.wait_for(bot.get_chat_member(chat, bot_id), TIMEOUT)
    except Exception as e:
        return Result(BAD, f"бот не видит канал ({type(e).__name__})")
    if member.status not in ("administrator", "creator"):
        return Result(BAD, "бот в канале не админ — постить не сможет")
    return Result(OK, "канал есть, бот — админ")


async def _group_chat(bot) -> Result:
    raw = env("GROUP_CHAT_ID")
    if not raw or raw == "0":
        return Result(OFF, "не задан (лента «Подслушано» выключена)")
    try:
        await asyncio.wait_for(bot.get_chat(int(raw)), TIMEOUT)
    except ValueError:
        return Result(BAD, "не число")
    except Exception as e:
        return Result(BAD, f"бот не видит чат ({type(e).__name__})")
    return Result(OK, "бот видит чат")


# ── ИИ ──────────────────────────────────────────────────────────────────────

PING = "Ответь одним словом: ок"


async def _openrouter_chat(model: str, deny: bool = False) -> Result:
    payload = {"model": model, "messages": [{"role": "user", "content": PING}], "max_tokens": 16}
    if deny:
        payload["provider"] = {"data_collection": "deny"}
    try:
        async with _client() as c:
            r = await c.post("https://openrouter.ai/api/v1/chat/completions", json=payload,
                             headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"})
    except httpx.HTTPError as e:
        return Result(BAD, f"{model}: {_err(e)}")
    if r.status_code == 200:
        return Result(OK, f"{model} отвечает")
    why = _or_error(r)
    if r.status_code == 429:
        return Result(WARN, f"{model}: лимит (429), ключ рабочий{why}")
    return Result(BAD, f"{model}: HTTP {r.status_code}{why}")


def _or_error(r: httpx.Response) -> str:
    try:
        msg = (r.json().get("error") or {}).get("message", "")
    except ValueError:
        msg = ""
    return f" — {msg[:120]}" if msg else ""


async def check_openrouter() -> list[tuple[str, Result]]:
    if not env("OPENROUTER_API_KEY"):
        return [("OPENROUTER_API_KEY", Result(OFF, "не задан — Ling и «Подумать ещё» выключены"))]
    try:
        async with _client() as c:
            r = await c.get("https://openrouter.ai/api/v1/key",
                            headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"})
    except httpx.HTTPError as e:
        return [("OPENROUTER_API_KEY", Result(BAD, _err(e) + " — VPN (XRAY_CONFIG) работает?"))]
    if r.status_code in (401, 403):
        return [("OPENROUTER_API_KEY", Result(BAD, f"OpenRouter не принял ключ (HTTP {r.status_code})"))]
    if r.status_code != 200:
        return [("OPENROUTER_API_KEY", Result(BAD, f"HTTP {r.status_code}"))]
    data = r.json().get("data") or {}
    left = data.get("limit_remaining")
    usage = data.get("usage")
    money = f", осталось ${left:.2f}" if isinstance(left, (int, float)) else ""
    spent = f", потрачено ${usage:.2f}" if isinstance(usage, (int, float)) else ""
    out = [("OPENROUTER_API_KEY", Result(OK, f"ключ принят{spent}{money}"))]
    spare = os.getenv("AI_SPARE_MODEL", "inclusionai/ling-3.0-flash-vl").strip()
    out.append(("AI_SPARE_MODEL", await _openrouter_chat(spare) if spare
                else Result(OFF, "пусто — Ling выключен, всё идёт в Gemini")))
    think = os.getenv("AI_THINK_MODEL", "deepseek/deepseek-v4.1-flash").strip()
    out.append(("AI_THINK_MODEL", await _openrouter_chat(think, deny=True)))
    return out


async def check_gemini() -> list[tuple[str, Result]]:
    if not env("GEMINI_API_KEY"):
        return [("GEMINI_API_KEY", Result(OFF, "не задан — запасного ИИ нет"))]
    models = [os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()]
    fallback = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-2.5-flash")
    models += [m.strip() for m in fallback.split(",") if m.strip() and m.strip() not in models]
    lines = []
    for m in models:
        lines.append(await _gemini_one(m))
    name_ok = [r for r in lines if r.mark in (OK, WARN)]
    if not name_ok:
        mark = BAD
    elif any(r.mark != OK for r in lines):
        mark = WARN
    else:
        mark = OK
    return [("GEMINI_API_KEY", Result(mark, "; ".join(r.text for r in lines)))]


async def _gemini_one(model: str) -> Result:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": PING}]}], "generationConfig": {"maxOutputTokens": 16}}
    try:
        async with _client() as c:
            r = await c.post(url, json=body, headers={"x-goog-api-key": env("GEMINI_API_KEY")})
    except httpx.HTTPError as e:
        return Result(BAD, f"{model}: {_err(e)}")
    if r.status_code == 200:
        return Result(OK, f"{model} отвечает")
    text = r.text.lower()
    if "location is not supported" in text:
        return Result(BAD, f"{model}: Google не пускает страну сервера — VPN (XRAY_CONFIG)?")
    if r.status_code == 429:
        return Result(WARN, f"{model}: лимит (429)")
    if r.status_code == 404:
        return Result(BAD, f"{model}: такой модели у Google нет")
    if r.status_code in (400, 401, 403):
        return Result(BAD, f"{model}: ключ не принят (HTTP {r.status_code})")
    return Result(BAD, f"{model}: HTTP {r.status_code}")


async def check_deepseek() -> Result:
    if not env("DEEPSEEK_API_KEY"):
        return Result(OFF, "не задан")
    try:
        async with _client() as c:
            r = await c.get("https://api.deepseek.com/user/balance",
                            headers={"Authorization": f"Bearer {env('DEEPSEEK_API_KEY')}"})
    except httpx.HTTPError as e:
        return Result(BAD, _err(e))
    if r.status_code != 200:
        return Result(BAD, f"ключ не принят (HTTP {r.status_code})")
    return Result(OK if r.json().get("is_available") else WARN,
                  "ключ принят" + ("" if r.json().get("is_available") else ", но баланс пуст"))


def check_ai_main() -> Result:
    v = os.getenv("AI_MAIN", "all").strip().lower()
    if v not in ("all", "plus", "me", "gemini"):
        return Result(BAD, f"«{v}» — бывает all, plus, me или gemini")
    return Result(OK, f"{v} (переключает /aimain, в базе может стоять другое)")


# ── Сеть ────────────────────────────────────────────────────────────────────

async def check_proxy() -> Result:
    proxy = net.out_proxy()
    if not env("XRAY_CONFIG") and not proxy:
        return Result(OFF, "не задан — всё напрямую (Gemini из России не пустит)")
    if not proxy:
        return Result(BAD, "XRAY_CONFIG есть, а прокси не поднялся (ссылка битая? смотри kap logs)")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, proxy=proxy) as c:
            data = (await c.get("https://ipinfo.io/json")).json()
    except Exception as e:
        return Result(BAD, f"VPN {_err(e)}")
    country = data.get("country", "?")
    want = env("PROXY_COUNTRY")
    if want and want.upper() not in (country.upper(), _country_code(want)):
        return Result(WARN, f"выход через {country}, а PROXY_COUNTRY = {want} (в политике будет не та страна)")
    return Result(OK, f"выход через {country}")


def _country_code(name: str) -> str:
    return {"латвия": "LV", "германия": "DE", "нидерланды": "NL", "финляндия": "FI",
            "эстония": "EE", "литва": "LT", "польша": "PL", "швеция": "SE"}.get(name.strip().lower(), "")


async def check_webapp() -> Result:
    url = env("WEBAPP_URL").rstrip("/")
    if not url:
        return Result(BAD, "не задан — Mini App, ссылки на сайт и картинки постов не работают")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(f"{url}/api/meta")
    except httpx.HTTPError as e:
        return Result(BAD, f"{url} {_err(e)}")
    if r.status_code != 200:
        return Result(BAD, f"{url}/api/meta — HTTP {r.status_code}")
    return Result(OK, f"сайт отвечает, версия {r.json().get('version', '?')}")


async def check_ical() -> Result:
    url = os.getenv("ICAL_URL", "https://english.mirea.ru/schedule/api/ical/1/4928").strip()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers={"Range": "bytes=0-1023"})
    except httpx.HTTPError as e:
        return Result(BAD, f"календарь {_err(e)}")
    if r.status_code >= 400 or "BEGIN:VCALENDAR" not in r.text:
        return Result(BAD, f"не календарь (HTTP {r.status_code})")
    name = re.search(r"X-WR-CALNAME:([^\r\n]+)", r.text)
    return Result(OK, f"календарь {name.group(1).strip() if name else 'есть'}")


# ── СДО и шифрование ────────────────────────────────────────────────────────

async def check_sdo_cookie() -> Result:
    cookie = env("SDO_SESSION_COOKIE")
    if not cookie:
        return Result(OFF, "не задана — общий синк дедлайнов не идёт")
    import sdo_accounts
    try:
        alive = await sdo_accounts.check(cookie)
    except Exception as e:
        return Result(WARN, f"СДО {_err(e)} — сам вход не проверить")
    return Result(OK, "СДО пускает") if alive else Result(BAD, "СДО не пускает — кука протухла, нужна новая")


def check_crypt_key() -> Result:
    if not env("SDO_CRYPT_KEY") and not env("SDO_CRYPT_PASSPHRASE"):
        return Result(WARN, "не задан — входы СДО шифруются ключом от BOT_TOKEN")
    import sdo_accounts
    if env("SDO_CRYPT_KEY") and not sdo_accounts._key_ok(env("SDO_CRYPT_KEY")):
        return Result(BAD, "SDO_CRYPT_KEY — не ключ Fernet (44 знака base64)")
    probe = sdo_accounts.decrypt(sdo_accounts.encrypt("проверка"))
    return Result(OK, "шифрует и расшифровывает") if probe == "проверка" else Result(BAD, "не расшифровывает своё")


def check_backup_key() -> Result:
    v = env("BACKUP_KEY")
    if not v:
        return Result(WARN, "не задан — ночная копия базы уходит в Telegram без шифрования")
    import backup
    key = backup.backup_key()
    raw = backup.encrypt(b"probe", key)
    if backup.decrypt(raw, key) != b"probe":
        return Result(BAD, "не расшифровывает своё")
    if len(v) < 16:
        return Result(WARN, f"короткий ({len(v)} знаков) — лучше 16+")
    return Result(OK, "копия шифруется")


async def check_s3() -> Result:
    names = ("BACKUP_S3_BUCKET", "BACKUP_S3_KEY_ID", "BACKUP_S3_SECRET")
    have = [n for n in names if env(n)]
    if not have:
        return Result(OFF, "не задано (копия — в Telegram, решение 19.10)")
    if len(have) < 3:
        return Result(BAD, "нужны все три: " + ", ".join(n for n in names if n not in have) + " не заданы")
    import s3_store
    try:
        code, _ = await s3_store.get("kap-check/no-such-file")
    except Exception as e:
        return Result(BAD, f"S3 {_err(e)}")
    if code in (200, 404):
        return Result(OK, "ключи приняты")
    return Result(BAD, f"S3 не пускает (HTTP {code}: ключ, секрет или бакет)")


# ── Касса ───────────────────────────────────────────────────────────────────

async def check_robokassa() -> Result:
    names = ("ROBOKASSA_LOGIN", "ROBOKASSA_PASS1", "ROBOKASSA_PASS2")
    have = [n for n in names if env(n)]
    if not have:
        return Result(OFF, "не задана")
    if len(have) < 3:
        return Result(BAD, ", ".join(n for n in names if n not in have) + " не заданы")
    login, inv = env("ROBOKASSA_LOGIN"), "1"
    sig = hashlib.md5(f"{login}:{inv}:{env('ROBOKASSA_PASS2')}".encode()).hexdigest()
    url = "https://auth.robokassa.ru/Merchant/WebService/Service.asmx/OpStateExt"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, params={"MerchantLogin": login, "InvoiceID": inv, "Signature": sig})
    except httpx.HTTPError as e:
        return Result(BAD, f"Robokassa {_err(e)}")
    code = re.search(r"<Code>(\d+)</Code>", r.text)
    test = " (тестовый режим ROBOKASSA_TEST=1)" if env("ROBOKASSA_TEST") == "1" else ""
    if not code:
        return Result(WARN, f"непонятный ответ (HTTP {r.status_code}){test}")
    c_ = code.group(1)
    if c_ in ("0", "3"):
        return Result(OK, f"логин и пароль 2 приняты{test}; пароль 1 проверит только оплата")
    if c_ == "1":
        why = "в тестовом режиме тут нужны боевые пароли — после одобрения проверь ещё раз" if test else "пароль 2 не тот"
        return Result(BAD if not test else WARN, f"подпись не сошлась: {why}{test}")
    if c_ == "2":
        return Result(WARN, f"магазин не найден или ещё не активирован (ждём одобрения?){test}")
    return Result(WARN, f"Robokassa ответила кодом {c_}{test}")


async def check_yookassa() -> Result:
    if not env("YOOKASSA_SHOP_ID") and not env("YOOKASSA_SECRET_KEY"):
        return Result(OFF, "не задана")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get("https://api.yookassa.ru/v3/me",
                            auth=(env("YOOKASSA_SHOP_ID"), env("YOOKASSA_SECRET_KEY")))
    except httpx.HTTPError as e:
        return Result(BAD, f"ЮKassa {_err(e)}")
    if r.status_code != 200:
        return Result(BAD, f"не приняла (HTTP {r.status_code})")
    if env("YOOKASSA_SECRET_KEY").startswith("test_"):
        return Result(WARN, "ключи приняты, магазин тестовый: деньги не списываются, платить может только Никита")
    return Result(OK, "ключи приняты")


def check_requisites() -> Result:
    names = ("PD_FIO", "PD_INN", "PD_EMAIL", "PD_CITY")
    missing = [n for n in names if not env(n)]
    if missing:
        return Result(BAD, "не заданы " + ", ".join(missing) + " — оплата закрыта, в политике пусто")
    if not re.fullmatch(r"\d{12}", env("PD_INN")):
        return Result(WARN, "PD_INN — у самозанятого 12 цифр")
    if "@" not in env("PD_EMAIL"):
        return Result(WARN, "PD_EMAIL без @")
    return Result(OK, "все четыре заданы")


# ── Входы ───────────────────────────────────────────────────────────────────

async def _oauth_probe(url: str, data: dict) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(url, data=data)
    try:
        return r.status_code, str(r.json().get("error", ""))
    except ValueError:
        return r.status_code, ""


async def check_yandex() -> Result:
    cid, secret = env("YANDEX_CLIENT_ID"), env("YANDEX_CLIENT_SECRET")
    if not cid and not secret:
        return Result(OFF, "не задан — кнопки входа нет")
    if not (cid and secret):
        return Result(BAD, "нужны оба: YANDEX_CLIENT_ID и YANDEX_CLIENT_SECRET")
    # заведомо неверный код: «invalid_grant» — приложение и секрет приняты
    try:
        code, err = await _oauth_probe("https://oauth.yandex.ru/token", {
            "grant_type": "authorization_code", "code": "0000000", "client_id": cid, "client_secret": secret})
    except httpx.HTTPError as e:
        return Result(BAD, f"Яндекс {_err(e)}")
    if err == "invalid_grant":
        return Result(OK, "приложение и секрет приняты")
    if err == "invalid_client":
        return Result(BAD, "Яндекс не узнал приложение или секрет")
    return Result(WARN, f"ответ {code} {err}".strip())


def check_vk() -> Result:
    if not env("VK_CLIENT_ID"):
        return Result(OFF, "не задан — кнопки входа нет")
    if not env("VK_CLIENT_ID").isdigit():
        return Result(BAD, "VK_CLIENT_ID — должно быть число (id приложения)")
    return Result(NOTE, "задан; VK проверяет только при настоящем входе — войди разок в /app")


async def check_apple() -> Result:
    names = ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY")
    have = [n for n in names if env(n)]
    if not have:
        return Result(OFF, "не задан — кнопки «Войти через Apple» нет")
    if len(have) < 3:
        return Result(BAD, ", ".join(n for n in names if n not in have) + " не заданы")
    import apple_signin
    try:
        secret = apple_signin.client_secret()
    except Exception as e:
        return Result(BAD, f"APPLE_PRIVATE_KEY не читается ({type(e).__name__}) — нужен .p8 целиком")
    try:
        code, err = await _oauth_probe(apple_signin.TOKEN_URL, {
            "client_id": apple_signin.client_id(), "client_secret": secret,
            "code": "kapcheck", "grant_type": "authorization_code"})
    except httpx.HTTPError as e:
        return Result(BAD, f"Apple {_err(e)}")
    if err == "invalid_grant":
        return Result(OK, "ключ и команда приняты")
    if err == "invalid_client":
        return Result(BAD, "Apple не принял ключ (APPLE_KEY_ID, TEAM_ID или CLIENT_ID не те)")
    return Result(WARN, f"ответ {code} {err}".strip())


def check_review_code() -> Result:
    v = env("REVIEW_CODE")
    if not v:
        return Result(OFF, "не задан — входа для проверяющих магазинов нет")
    if len(v) < 12:
        return Result(BAD, f"{len(v)} знаков, нужно от 12 — кнопки не будет")
    return Result(OK, "задан, длина подходит")


# ── Пуши ────────────────────────────────────────────────────────────────────

async def check_fcm() -> Result:
    if not env("FCM_SERVICE_ACCOUNT"):
        return Result(OFF, "не задан — пушей на Android через Google нет")
    import app_push
    acc = app_push._fcm_account()
    if acc is None:
        return Result(BAD, "не JSON сервисного аккаунта Firebase (или нет полей)")
    try:
        token = await app_push._fcm_access(acc)
    except Exception as e:
        return Result(BAD, f"Google не выдал доступ ({type(e).__name__})")
    return Result(OK, f"проект {acc['project_id']}, доступ выдан") if token else Result(BAD, "Google не выдал доступ")


async def check_rustore() -> Result:
    have = [n for n in ("RUSTORE_PROJECT_ID", "RUSTORE_SERVICE_TOKEN") if env(n)]
    if not have:
        return Result(OFF, "не задан — пушей через RuStore нет")
    if len(have) < 2:
        return Result(BAD, "нужны оба: RUSTORE_PROJECT_ID и RUSTORE_SERVICE_TOKEN")
    import app_push
    try:
        code, body = await app_push._request(
            app_push.RUSTORE_URL.format(project=env("RUSTORE_PROJECT_ID")),
            json_body={"message": {"token": "kap-check", "data": {"v": "0"}}},
            headers={"Authorization": f"Bearer {env('RUSTORE_SERVICE_TOKEN')}"})
    except Exception as e:
        return Result(BAD, f"RuStore {_err(e)}")
    if code in (401, 403):
        return Result(BAD, f"RuStore не принял токен или проект (HTTP {code})")
    if code in (400, 404) or code < 300:
        return Result(OK, "токен принят (пробный пуш на несуществующее устройство отклонён, как надо)")
    return Result(WARN, f"RuStore ответил HTTP {code}")


async def check_apns() -> Result:
    if not env("APNS_KEY_ID") and not env("APNS_PRIVATE_KEY"):
        return Result(OFF, "не задан — пушей на iPhone нет")
    import app_push
    if not app_push._apns_ok():
        return Result(BAD, "нужны APNS_KEY_ID, APNS_PRIVATE_KEY и APNS_TEAM_ID (или APPLE_TEAM_ID)")
    try:
        app_push._apns_jwt["value"] = ""
        jwt = app_push.apns_jwt()
    except Exception as e:
        return Result(BAD, f"APNS_PRIVATE_KEY не читается ({type(e).__name__})")
    sandbox = env("APNS_SANDBOX") in ("1", "true", "yes")
    host = app_push.APNS_SANDBOX_HOST if sandbox else app_push.APNS_HOST
    try:
        code, body = await app_push._request(
            f"{host}/3/device/{'0' * 64}", json_body={"aps": {"alert": "kap check"}}, http2=True,
            headers={"authorization": f"bearer {jwt}", "apns-push-type": "alert",
                     "apns-topic": env("APNS_TOPIC") or "ru.uiboshki.app"})
    except Exception as e:
        return Result(BAD, f"Apple {_err(e)}")
    reason = str(body.get("reason", ""))
    if reason in ("BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"):
        return Result(OK, "ключ принят" + (" (песочница)" if sandbox else ""))
    if reason in ("InvalidProviderToken", "ExpiredProviderToken", "MissingProviderToken"):
        return Result(BAD, f"Apple не принял ключ ({reason})")
    return Result(WARN, f"Apple ответил {code} {reason}".strip())


def check_vapid() -> Result:
    if not env("VAPID_PRIVATE_KEY"):
        return Result(NOTE, "не задан — ключ веб-пушей берётся от BOT_TOKEN (сменишь токен — подписки слетят)")
    import webpush
    try:
        webpush.private_key()
    except Exception as e:
        return Result(BAD, f"не читается ({type(e).__name__})")
    return Result(OK, "ключ читается")


# ── Прочее ──────────────────────────────────────────────────────────────────

def check_embed() -> Result:
    raw = os.getenv("EMBED_PROVIDER", "gemini").strip()
    import local_embed
    key = raw[len("local:"):] if raw.startswith("local:") else raw
    if key not in ("gemini", *local_embed.MODELS):
        return Result(BAD, f"«{raw}» — нет такой модели, поиск уйдёт в Gemini")
    return Result(OK, key)


def check_hosting() -> Result:
    import privacy
    h = privacy._host()
    if h["name"] != "Amvera" and h["org"] == h["name"]:
        return Result(BAD, f"юрлица хостинга {h['name']} нет ни в коде, ни в HOSTING_ORG — в политике пусто")
    if env("HOSTING_ORG") and privacy.HOSTS.get(env("HOSTING").lower(), {}).get("org"):
        return Result(NOTE, "задан, но не нужен: юрлицо хостинга уже в коде (privacy.HOSTS)")
    return Result(OK, f"в политике — {h['name']}")


def _numbers() -> list[tuple[str, Result]]:
    out = []
    for name in ("AI_DAILY_LIMIT", "AI_SUB_DAILY", "AI_THINK_DAILY", "AI_TRIAL_DAILY", "AI_TRIAL_DAY_TOTAL",
                 "SUMMARY_WEEKLY", "SDO_SYNC_INTERVAL_HOURS", "STARS_RUB", "STARS_MARKUP", "AI_THINK_DAY_USD",
                 "USD_RUB", "AITEST_BUDGET_USD"):
        v = env(name)
        if not v:
            continue
        try:
            float(v)
        except ValueError:
            out.append((name, Result(BAD, "не число — бот может не запуститься")))
    return out


# ── Опечатки и пустые строки в .env ─────────────────────────────────────────

SKIP_UNKNOWN = {"PATH", "HOME", "HOSTNAME", "LANG", "TZ", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE"}


def known_names() -> set[str]:
    """Все имена В_ВЕРХНЕМ_РЕГИСТРЕ, которые встречаются в коде строкой."""
    names = {"VK_CLIENT_ID", "VK_CLIENT_SECRET", "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET"}
    pat = re.compile(r"[\"']([A-Z][A-Z0-9_]{2,})[\"']")
    for p in ROOT.rglob("*.py"):
        if any(part in ("tests", ".git", "node_modules", "app") for part in p.relative_to(ROOT).parts[:-1]):
            continue
        try:
            names.update(pat.findall(p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    for sh in (ROOT / "docker" / "start.sh", ROOT / "Dockerfile"):
        if sh.exists():
            names.update(re.findall(r"\$\{?([A-Z][A-Z0-9_]{2,})", sh.read_text(encoding="utf-8", errors="ignore")))
    return names


def env_file_problems(names: list[str], known: set[str]) -> list[tuple[str, Result]]:
    out = []
    for name in sorted(set(names) - known - SKIP_UNKNOWN):
        out.append((name, Result(BAD, "код такую переменную не знает — опечатка?")))
    for name in sorted(set(names)):
        if name in os.environ and not os.environ[name].strip():
            out.append((name, Result(WARN, "задана пустой — это не то же, что «не задана»; лучше закомментировать #")))
    return out


# ── Сборка ──────────────────────────────────────────────────────────────────

async def _one(name: str, coro) -> tuple[str, Result]:
    try:
        res = await coro if asyncio.iscoroutine(coro) else coro
    except Exception as e:   # одна сломанная проверка не валит остальные
        res = Result(BAD, f"проверка упала ({type(e).__name__})")
    return name, res


async def _safe_list(fn) -> list[tuple[str, Result]]:
    try:
        return await fn()
    except Exception as e:
        return [(fn.__name__.replace("check_", "").upper(), Result(BAD, f"проверка упала ({type(e).__name__})"))]


def _sync(fn) -> Result:
    try:
        return fn()
    except Exception as e:
        return Result(BAD, f"проверка упала ({type(e).__name__})")


async def run(env_names: list[str] | None = None) -> list[tuple[str, list[tuple[str, Result]]]]:
    tg, oroute, gem, rest = await asyncio.gather(
        _safe_list(check_telegram), _safe_list(check_openrouter), _safe_list(check_gemini),
        asyncio.gather(
            _one("DEEPSEEK_API_KEY", check_deepseek()), _one("XRAY_CONFIG", check_proxy()),
            _one("WEBAPP_URL", check_webapp()), _one("ICAL_URL", check_ical()),
            _one("SDO_SESSION_COOKIE", check_sdo_cookie()), _one("BACKUP_S3_*", check_s3()),
            _one("ROBOKASSA_*", check_robokassa()), _one("YOOKASSA_*", check_yookassa()),
            _one("YANDEX_CLIENT_*", check_yandex()), _one("APPLE_*", check_apple()),
            _one("FCM_SERVICE_ACCOUNT", check_fcm()), _one("RUSTORE_*", check_rustore()),
            _one("APNS_*", check_apns())))
    r = dict(rest)
    sections = [
        ("Telegram", tg),
        ("ИИ", oroute + gem + [("DEEPSEEK_API_KEY", r["DEEPSEEK_API_KEY"]), ("AI_MAIN", _sync(check_ai_main))]),
        ("Сеть и сайт", [("XRAY_CONFIG", r["XRAY_CONFIG"]), ("WEBAPP_URL", r["WEBAPP_URL"]),
                         ("ICAL_URL", r["ICAL_URL"])]),
        ("СДО и шифрование", [("SDO_SESSION_COOKIE", r["SDO_SESSION_COOKIE"]),
                              ("SDO_CRYPT_KEY", _sync(check_crypt_key)), ("BACKUP_KEY", _sync(check_backup_key)),
                              ("BACKUP_S3_*", r["BACKUP_S3_*"])]),
        ("Оплата", [("ROBOKASSA_*", r["ROBOKASSA_*"]), ("YOOKASSA_*", r["YOOKASSA_*"]),
                    ("PD_*", _sync(check_requisites))]),
        ("Входы", [("YANDEX_CLIENT_*", r["YANDEX_CLIENT_*"]), ("VK_CLIENT_ID", _sync(check_vk)),
                   ("APPLE_*", r["APPLE_*"]), ("REVIEW_CODE", _sync(check_review_code))]),
        ("Пуши", [("FCM_SERVICE_ACCOUNT", r["FCM_SERVICE_ACCOUNT"]), ("RUSTORE_*", r["RUSTORE_*"]),
                  ("APNS_*", r["APNS_*"]), ("VAPID_PRIVATE_KEY", _sync(check_vapid))]),
        ("Прочее", [("EMBED_PROVIDER", _sync(check_embed)), ("HOSTING", _sync(check_hosting))] + _numbers()),
    ]
    if env_names:
        problems = env_file_problems(env_names, known_names())
        if problems:
            sections.append(("Файл .env", problems))
    return sections


SECRET_HINTS = ("TOKEN", "KEY", "SECRET", "PASS", "COOKIE", "CONFIG", "CODE", "ACCOUNT", "PROXY")


def _scrub(text: str) -> str:
    """Страховка: ни одно значение секрета не уходит в вывод, даже из текста ошибки."""
    for name, value in os.environ.items():
        v = value.strip()
        if len(v) >= 6 and any(h in name for h in SECRET_HINTS) and v in text:
            text = text.replace(v, "•••")
    return text


def render(sections) -> str:
    lines, count = [], {}
    for title, rows in sections:
        lines.append(f"\n{title}")
        for name, res in rows:
            lines.append(f"  {res.mark} {name} — {res.text}")
            count[res.mark] = count.get(res.mark, 0) + 1
    total = ", ".join(f"{m} {count[m]}" for m in (OK, WARN, BAD, NOTE, OFF) if count.get(m))
    lines.append(f"\nИтого: {total}")
    lines.append(f"{OK} работает  {WARN} работает с оговоркой  {BAD} не работает  "
                 f"{NOTE} задано, живой проверки нет  {OFF} не задано")
    return _scrub("\n".join(lines))


def main():
    names = [n for n in os.getenv("KAP_ENV_NAMES", "").split() if n]
    print("Проверяю переменные бота (секунд 10–20)…", flush=True)
    print(render(asyncio.run(run(names))))


if __name__ == "__main__":
    main()
