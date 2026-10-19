"""
/netcheck у старосты: кто отвечает серверу бота, каким путём и за сколько.

Нужна для переезда на российский сервер (PLAN.md, «Переезд в Россию»): на
новом сервере одной командой видно, что Telegram и Gemini идут через прокси
и отвечают, а СДО и расписание МИРЭА — напрямую. Платных запросов нет:
к Gemini — подсчёт токенов, к OpenRouter — список моделей.
"""

import asyncio
import os
import time
from urllib.parse import urlsplit

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


# 19.10: медленно было всё сразу, и в России тоже (Яндекс 14 с, VK 18 с) —
# сеть это, поиск адресов (DNS) или занятый сервер? Строки ниже отвечают
# одной командой: DNS у каждого адреса отдельно, зависания цикла бота и
# процессор контейнера за время проверки.

async def _resolve(host: str):
    return await asyncio.get_running_loop().getaddrinfo(host, 443)


async def _dns(host: str) -> dict:
    started = time.monotonic()
    try:
        await asyncio.wait_for(_resolve(host), TIMEOUT)
    except Exception as e:
        return {"host": host, "ms": _ms(started), "error": type(e).__name__}
    return {"host": host, "ms": _ms(started), "error": ""}


class _LagMeter:
    """Самое долгое зависание цикла событий, пока идёт проверка."""

    def __init__(self, step: float = 0.1):
        self.step, self.worst, self._task = step, 0.0, None

    async def _run(self):
        while True:
            t = time.monotonic()
            await asyncio.sleep(self.step)
            self.worst = max(self.worst, time.monotonic() - t - self.step)

    def __enter__(self):
        self._task = asyncio.get_running_loop().create_task(self._run())
        return self

    def __exit__(self, *exc):
        self._task.cancel()


CGROUP = "/sys/fs/cgroup"


def _cpu_stat() -> dict:
    """cgroup v2: usage_usec, nr_periods, nr_throttled, throttled_usec; нет — {}."""
    try:
        with open(os.path.join(CGROUP, "cpu.stat")) as f:
            return {k: int(v) for k, v in (line.split() for line in f if line.strip())}
    except (OSError, ValueError):
        return {}


def _cpu_quota() -> float | None:
    """Сколько ядер даёт хостинг (cpu.max «квота период»); без лимита — None."""
    try:
        with open(os.path.join(CGROUP, "cpu.max")) as f:
            quota, period = f.read().split()[:2]
        return None if quota == "max" else int(quota) / int(period)
    except (OSError, ValueError):
        return None


def _cpu(before: dict, after: dict, seconds: float, proc: float) -> dict:
    d = {k: after.get(k, 0) - before.get(k, 0) for k in after}
    return {"quota": _cpu_quota(), "seconds": seconds,
            "busy": d.get("usage_usec", 0) / 1e6 / seconds if after and seconds else None,
            "proc": proc / seconds if seconds else None,
            "throttled": d.get("nr_throttled", 0) / d["nr_periods"] if d.get("nr_periods") else None,
            "throttled_ms": d.get("throttled_usec", 0) // 1000}


def _embedding() -> bool:
    """Своя модель векторов сейчас считает (поток embed занят)."""
    import sys
    le = sys.modules.get("local_embed")
    return bool(le and le._lock.locked())


def _nameservers() -> list[str]:
    try:
        with open("/etc/resolv.conf") as f:
            return [line.split()[1] for line in f if line.startswith("nameserver") and len(line.split()) > 1]
    except OSError:
        return []


async def check(bot) -> dict:
    proxy = net.out_proxy()
    hosts = ["api.telegram.org"] + [urlsplit(u).hostname for _, u, _ in TARGETS]
    embedding = _embedding()
    cpu0, proc0, t0 = _cpu_stat(), time.process_time(), time.monotonic()
    with _LagMeter() as lag:
        results = await asyncio.gather(_telegram(bot), _gemini(), *(_http(*t) for t in TARGETS))
        ips = await asyncio.gather(_exit_ip(), _exit_ip(proxy) if proxy else asyncio.sleep(0, ""))
        dns = await asyncio.gather(*(_dns(h) for h in hosts))     # отдельно от запросов: только поиск адреса
    cpu = _cpu(cpu0, _cpu_stat(), time.monotonic() - t0, time.process_time() - proc0)
    return {"results": list(results), "ip": ips[0], "proxy_ip": ips[1], "proxy": net.safe_proxy(proxy),
            "tg_proxy": net.safe_proxy(net.tg_proxy()), "tg_base": net.telegram_api_base(),
            "dns": list(dns), "nameservers": _nameservers(), "lag": lag.worst, "cpu": cpu,
            "embedding": embedding or _embedding()}


def _server_lines(rep: dict) -> list[str]:
    lines = ["", "<b>Сам сервер</b>"]
    if "dns" in rep:
        slow = [d for d in rep["dns"] if d["error"] or d["ms"] >= 1000]
        worst = max(rep["dns"], key=lambda d: d["ms"], default=None)
        ns = ", ".join(rep.get("nameservers") or []) or "?"
        if worst and not slow:
            lines.append(f"🟢 DNS ({ns}): все адреса за {worst['ms']} мс и быстрее")
        else:
            lines.append(f"🔴 DNS ({ns}) медленный: " + ", ".join(
                f"{d['host']} {d['ms']} мс" + (f" ({d['error']})" if d["error"] else "") for d in slow))
    if "lag" in rep:
        icon = "🔴" if rep["lag"] >= 2 else "🟢"
        lines.append(f"{icon} Самое долгое зависание бота за проверку: {rep['lag']:.1f} с")
    cpu = rep.get("cpu") or {}
    if cpu.get("busy") is not None:
        quota = f"из {cpu['quota']:.2g} ядра" if cpu.get("quota") else "без лимита"
        thr = cpu.get("throttled")
        icon = "🔴" if thr and thr >= 0.2 else "🟢"
        lines.append(f"{icon} Процессор {quota}: занято {cpu['busy']:.2f} ядра (бот — {cpu['proc']:.2f})"
                     + (f", упирался в лимит {thr:.0%} времени" if thr is not None else ""))
    if rep.get("embedding"):
        lines.append("⏳ Во время проверки считались векторы поиска по лекциям")
    return lines


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
    lines += _server_lines(rep)
    return "\n".join(lines)
