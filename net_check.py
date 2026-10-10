"""
/netcheck у старосты: кто отвечает серверу бота, каким путём и за сколько.

Нужна для переезда на российский сервер (PLAN.md, «Переезд в Россию»): на
новом сервере одной командой видно, что Telegram и Gemini идут через прокси
и отвечают, а СДО и расписание МИРЭА — напрямую. Платных запросов нет:
к Gemini — подсчёт токенов, к OpenRouter — список моделей.
"""

import asyncio
import time

import httpx

import net

TIMEOUT = 10

# (название, адрес, что считать «не пускает» — коды ответа)
TARGETS = (
    ("Расписание (зеркало)", "https://english.mirea.ru/schedule/api/ical/1/4928", ()),
    ("Расписание (официальное)", "https://schedule-of.mirea.ru/schedule/api/search?limit=1&match=УИБО", ()),
    ("СДО", "https://online-edu.mirea.ru/login/index.php", ()),
    ("OpenRouter", "https://openrouter.ai/api/v1/models", (403, 451)),
    ("Пуши Google (FCM)", "https://fcm.googleapis.com/", (451,)),
    ("Погода", "https://api.open-meteo.com/v1/forecast?latitude=55.67&longitude=37.48&current=temperature_2m", (403, 451)),
    ("VK ID", "https://id.vk.com/", (451,)),
    ("Яндекс ID", "https://oauth.yandex.ru/", (451,)),
)
IP_URL = "https://ipinfo.io/json"


def _route(url: str) -> str:
    return "прокси" if net.via_proxy(url) else "напрямую"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


async def _http(name: str, url: str, blocked_codes: tuple, headers: dict | None = None,
                method: str = "GET", json: dict | None = None) -> dict:
    started = time.monotonic()
    res = {"name": name, "route": _route(url)}
    try:
        async with net.client(timeout=TIMEOUT, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0 uiboshki-netcheck", "Range": "bytes=0-2047",
                                       **(headers or {})}) as c:
            resp = await c.request(method, url, json=json)
    except httpx.HTTPError as e:
        return {**res, "ok": False, "status": 0, "ms": _ms(started), "why": f"не отвечает ({type(e).__name__})"}
    ok = resp.status_code < 500 and resp.status_code not in blocked_codes
    return {**res, "ok": ok, "status": resp.status_code, "ms": _ms(started), "why": "" if ok else f"HTTP {resp.status_code}",
            "body": resp.text[:2000]}


async def _gemini() -> dict:
    from config import GEMINI_API_KEY, GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:countTokens"
    res = await _http("Gemini", url, (), headers={"x-goog-api-key": GEMINI_API_KEY},
                      method="POST", json={"contents": [{"parts": [{"text": "проверка"}]}]})
    if res["status"] and "location is not supported" in res.get("body", "").lower():
        res.update(ok=False, why="Google не пускает страну сервера")
    elif res["status"] in (401, 403) and not GEMINI_API_KEY:
        res.update(ok=True, why="отвечает (ключа нет)")
    elif res["status"] and res["status"] != 200:
        res.update(ok=res["status"] == 429, why=f"HTTP {res['status']}")
    return res


async def _telegram(bot) -> dict:
    proxy, base = net.tg_proxy(), net.telegram_api_base()
    route = "свой адрес Bot API" if base else "прокси" if proxy else "напрямую"
    started = time.monotonic()
    try:
        await asyncio.wait_for(bot.get_me(), TIMEOUT)
    except Exception as e:
        return {"name": "Telegram", "route": route, "ok": False, "status": 0, "ms": _ms(started),
                "why": f"не отвечает ({type(e).__name__})"}
    return {"name": "Telegram", "route": route, "ok": True, "status": 200, "ms": _ms(started), "why": ""}


async def _exit_ip(proxy: str = "") -> str:
    """IP и страна, с которыми сервер выходит в интернет (напрямую или через прокси)."""
    try:
        kw = {"transport": httpx.AsyncHTTPTransport(proxy=proxy)} if proxy else {}
        async with httpx.AsyncClient(timeout=TIMEOUT, **kw) as c:
            data = (await c.get(IP_URL)).json()
        return f"{data.get('ip', '?')} ({data.get('country', '?')})"
    except Exception as e:
        return f"не узнал ({type(e).__name__})"


async def check(bot) -> dict:
    proxy = net.out_proxy()
    results = await asyncio.gather(_telegram(bot), _gemini(), *(_http(*t) for t in TARGETS))
    ips = await asyncio.gather(_exit_ip(), _exit_ip(proxy) if proxy else asyncio.sleep(0, ""))
    return {"results": list(results), "ip": ips[0], "proxy_ip": ips[1], "proxy": net.safe_proxy(proxy),
            "tg_proxy": net.safe_proxy(net.tg_proxy()), "tg_base": net.telegram_api_base()}


def text(rep: dict) -> str:
    lines = ["<b>Сеть сервера бота</b>", f"Выход напрямую: {rep['ip']}"]
    if rep["proxy"]:
        lines.append(f"Прокси {rep['proxy']}: {rep['proxy_ip']}")
    else:
        lines.append("Прокси не задан (OUT_PROXY) — всё напрямую")
    if rep["tg_base"]:
        lines.append(f"Bot API: {rep['tg_base']}")
    elif rep["tg_proxy"] and rep["tg_proxy"] != rep["proxy"]:
        lines.append(f"Telegram через {rep['tg_proxy']}")
    lines.append("")
    for r in rep["results"]:
        icon = "🟢" if r["ok"] else "🔴"
        why = f" · {r['why']}" if r["why"] else ""
        lines.append(f"{icon} {r['name']} — {r['route']}, {r['ms']} мс{why}")
    return "\n".join(lines)
