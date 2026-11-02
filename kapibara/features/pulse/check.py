"""
Пускает ли pulse.mirea.ru (посещаемость по датам) запросы с сервера бота.
Пульс прикрыт DDoS-Guard: из облака разработки он отвечал 403 «geoblocked»,
а у владельца через немецкий VPN открывается — режут, похоже, адреса
дата-центров. Сервер бота — тоже дата-центр, поэтому проверяем прямо оттуда
(/pulsecheck у старосты и кнопка в листе «СДО»).
"""

import time

import httpx

PULSE_URL = "https://pulse.mirea.ru/"


async def check() -> dict:
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}) as c:
            resp = await c.get(PULSE_URL)
    except httpx.HTTPError as e:
        return {"ok": False, "status": 0, "why": f"не отвечает ({type(e).__name__})", "ms": int((time.monotonic() - started) * 1000)}
    body = resp.text[:4000].lower()
    blocked = resp.status_code in (403, 451) or "geoblock" in body or "has restricted access" in body
    why = ("пускает" if not blocked else
           "блокирует (DDoS-Guard не пускает адрес сервера)" if "ddos-guard" in body else f"блокирует (HTTP {resp.status_code})")
    return {"ok": not blocked, "status": resp.status_code, "why": why, "ms": int((time.monotonic() - started) * 1000)}


def text(res: dict) -> str:
    icon = "🟢" if res["ok"] else "🔴"
    return f"{icon} Пульс МИРЭА с сервера бота: {res['why']}\nHTTP {res['status']} · {res['ms']} мс"
