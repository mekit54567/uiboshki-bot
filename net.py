"""
Исходящие соединения: что идёт через прокси, что напрямую.

Задел под переезд на российский сервер (PLAN.md, «Переезд в Россию»): из
России api.telegram.org режется, а Google (Gemini) не отвечает российским
адресам. Поэтому зарубежные сервисы — через прокси за границей, а СДО,
расписание МИРЭА, VK и Яндекс — напрямую (так быстрее, и МИРЭА видит
российский адрес).

Переменные окружения (пока не заданы — всё как раньше, напрямую):
- `OUT_PROXY` — прокси за границей: `http://логин:пароль@хост:порт` или
  `socks5://…` (socks5h — имена разрешает прокси).
- `PROXY_HOSTS` — каким хостам идти через него, через запятую; поддомены
  тоже. По умолчанию — Gemini и OpenRouter (`DEFAULT_PROXY_HOSTS`).
- `TG_PROXY` — прокси для Telegram, если нужен другой; по умолчанию
  `OUT_PROXY`.
- `TELEGRAM_API_BASE` — свой адрес Bot API вместо api.telegram.org
  (обратный прокси за границей или свой telegram-bot-api).
"""

import os
from urllib.parse import urlsplit

import httpx

DEFAULT_PROXY_HOSTS = ("generativelanguage.googleapis.com", "openrouter.ai")


def out_proxy() -> str:
    return os.getenv("OUT_PROXY", "").strip()


def tg_proxy() -> str:
    return os.getenv("TG_PROXY", "").strip() or out_proxy()


def telegram_api_base() -> str:
    return os.getenv("TELEGRAM_API_BASE", "").strip().rstrip("/")


def proxy_hosts() -> tuple[str, ...]:
    raw = os.getenv("PROXY_HOSTS")
    if raw is None:
        return DEFAULT_PROXY_HOSTS
    return tuple(h.strip().lower().lstrip(".") for h in raw.split(",") if h.strip())


def via_proxy(url: str) -> bool:
    """Пойдёт ли запрос на этот адрес через прокси."""
    if not out_proxy():
        return False
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in proxy_hosts())


def safe_proxy(url: str) -> str:
    """Адрес прокси без логина и пароля — для логов и /netcheck."""
    if not url:
        return ""
    p = urlsplit(url)
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


def client(**kw) -> httpx.AsyncClient:
    """httpx.AsyncClient, у которого хосты из PROXY_HOSTS идут через OUT_PROXY,
    остальные — напрямую. Без OUT_PROXY — обычный клиент."""
    proxy = out_proxy()
    if proxy and "transport" not in kw:
        mounts = dict(kw.pop("mounts", None) or {})
        for h in proxy_hosts():
            transport = httpx.AsyncHTTPTransport(proxy=proxy)
            mounts[f"all://{h}"] = transport
            mounts[f"all://*.{h}"] = transport
        kw["mounts"] = mounts
    return httpx.AsyncClient(**kw)


def tg_session():
    """Сессия aiogram для Bot: прокси и свой адрес Bot API. Без настроек — None
    (aiogram создаст обычную)."""
    proxy, base = tg_proxy(), telegram_api_base()
    if not proxy and not base:
        return None
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.telegram import TelegramAPIServer
    kw = {}
    if proxy:
        kw["proxy"] = proxy
    if base:
        kw["api"] = TelegramAPIServer.from_base(base)
    return AiohttpSession(**kw)
