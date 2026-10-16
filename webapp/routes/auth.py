"""Вход в приложение без Telegram (этап 2, PLAN.md «Своё приложение»):
PWA и будущее нативное приложение. Telegram в России открывается через
«КВН», поэтому приложение не держится за initData:

  1. POST /api/auth/start — одноразовый код и ссылка t.me/<бот>?start=login_<код>;
  2. в боте: «Войти в приложение на … ?» → «Да, это я» (handlers/start.py);
  3. POST /api/auth/poll {code} — пока «wait»; подтвердил — токен сессии
     устройства (90 дней, продлевается при заходах), код сгорает.

Дальше запросы — с «Authorization: Bearer <токен>» (webapp/deps.py).
«Ещё → Устройства»: список входов, выйти на одном или везде.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


def _device(request: Request) -> str:
    """«Chrome · Android» из User-Agent — чтобы в боте было видно, что за вход."""
    # своё приложение называет себя заголовком X-App (app/lib/api/api.dart): у Dart
    # в User-Agent только «Dart/3», и бот спрашивал «Войти… на устройстве Браузер»
    app = {"ios": "iPhone", "android": "Android"}.get(request.headers.get("x-app", ""))
    if app:
        return f"Капибара · {app}"
    ua = request.headers.get("user-agent", "")
    browser = next((b for b in ("Edg", "YaBrowser", "Chrome", "Firefox", "Safari") if b in ua), "Браузер")
    browser = {"Edg": "Edge", "YaBrowser": "Яндекс Браузер"}.get(browser, browser)
    os_name = next((o for o, k in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                   ("Windows", "Windows"), ("macOS", "Mac OS"), ("Linux", "Linux")) if k in ua), "")
    return f"{browser} · {os_name}" if os_name else browser


def _client_ip(request: Request) -> str:
    from webapp.routes.site import _client_key
    return _client_key(request)


@router.post("/api/auth/start")
async def auth_start(request: Request):
    import ratelimit
    from config import BOT_USERNAME
    from database.sessions import create_login, get_login
    if not ratelimit.allow("auth_start", _client_ip(request)):
        raise HTTPException(429, "Слишком много попыток — подожди минуту")
    code = await create_login(_device(request))
    # pick — число на экране устройства: в боте его надо выбрать из трёх, иначе
    # вход по чужой ссылке подтверждался одним «Да, это я» (ревью безопасности 09.10)
    # tg_link — сразу в приложение Telegram: PWA с экрана «Домой» открывает t.me
    # во встроенном браузере, и после возврата там оставалась белая страница
    return {"code": code, "link": f"https://t.me/{BOT_USERNAME}?start=login_{code}",
            "tg_link": f"tg://resolve?domain={BOT_USERNAME}&start=login_{code}", "expires_in": 600,
            "pick": (await get_login(code))["pick"]}


class PollBody(BaseModel):
    code: str


@router.post("/api/auth/review")
async def auth_review(body: PollBody, request: Request):
    """Демо-вход проверяющих App Store / RuStore по коду REVIEW_CODE
    (review_demo.py): данные — запись стенда, не чьи-то настоящие."""
    import ratelimit
    import review_demo
    if not review_demo.enabled():
        raise HTTPException(404, "Вход по коду выключен")
    if not ratelimit.allow("auth_review", _client_ip(request)):
        raise HTTPException(429, "Слишком много попыток — подожди 10 минут")
    if not review_demo.check_code(body.code[:64]):
        raise HTTPException(403, "Неверный код")
    return {"status": "ok", "token": await review_demo.login(_device(request))}


@router.post("/api/auth/poll")
async def auth_poll(body: PollBody, request: Request):
    from database.sessions import get_login, redeem_login
    login = await get_login(body.code[:64])
    if not login:
        return {"status": "expired"}
    if login["status"] == "no":
        return {"status": "denied"}
    if login["status"] != "ok":
        return {"status": "wait"}
    got = await redeem_login(body.code)
    if not got:
        return {"status": "expired"}
    token, uid = got
    return {"status": "ok", "token": token, "user_id": uid}


@router.get("/api/auth/sessions")
async def auth_sessions(request: Request, user: dict = CurrentUser):
    from database.sessions import list_sessions, token_hash
    current = request.headers.get("authorization", "")[7:].strip()
    items = await list_sessions(user["id"])
    if current:
        from database._conn import connect
        async with connect() as db:
            row = await (await db.execute("SELECT id FROM sessions WHERE token_hash = ?",
                                          (token_hash(current),))).fetchone()
        for it in items:
            it["current"] = bool(row and it["id"] == row[0])
    return {"items": items}


@router.delete("/api/auth/sessions/{session_id}")
async def auth_revoke(session_id: int, user: dict = CurrentUser):
    from database.sessions import revoke_session
    if not await revoke_session(user["id"], session_id=session_id):
        raise HTTPException(404, "Нет такого входа")
    return {"ok": True}


@router.post("/api/auth/logout")
async def auth_logout(request: Request, everywhere: bool = False, user: dict = CurrentUser):
    from database.sessions import revoke_session
    token = request.headers.get("authorization", "")[7:].strip()
    n = await revoke_session(user["id"]) if everywhere else await revoke_session(user["id"], token=token or "-")
    if everywhere:
        # и пуши: отозванное устройство продолжало получать тексты уведомлений
        # (сроки, новые баллы) — ревью безопасности 09.10
        from database.push import delete_user_push_subs
        await delete_user_push_subs(user["id"])
    return {"ok": True, "revoked": n}


# ── Вход через VK ID и Яндекс ID (oauth.py, владелец 08.10) ─────────────────
# Токен получает только тот, кто сам вошёл у провайдера: браузер — во
# фрагменте /app#token=…, приложение — по ссылке ru.uiboshki.app://auth#token=…
# (опрос по коду, как у бота, здесь нельзя: чужую ссылку входа можно прислать
# жертве, и токен её аккаунта ушёл бы тому, кто ждёт код). Привязку к уже
# существующему аккаунту человек подтверждает кнопкой, видя имя аккаунта.

APP_RETURN = "ru.uiboshki.app://auth"


def _provider(provider: str) -> str:
    import oauth
    if provider not in oauth.available():
        raise HTTPException(404, "Такого входа нет")
    return provider


def _redirect_uri(request: Request, provider: str) -> str:
    from webapp import deps
    return (deps.WEBAPP_URL or str(request.base_url)).rstrip("/") + f"/api/auth/{provider}/callback"


def _page(title: str, text: str, extra: str = "", status: int = 200):
    from html import escape
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        # тема телефона (тёмная — не белый экран) и перенос длинных имён без прокрутки вбок
        "<meta name='color-scheme' content='light dark'><title>Капибара</title>"
        "<body style=\"font:16px system-ui;max-width:420px;margin:15vh auto;padding:0 20px;overflow-wrap:anywhere\">"
        f"<h2>{escape(title)}</h2><p>{escape(text)}</p>{extra}</body>", status_code=status)


@router.get("/api/auth/providers")
async def auth_providers():
    """Каким ещё входом можно войти (есть ключи на хостинге); code — вход по
    коду для проверяющих магазинов (review_demo.py)."""
    import oauth
    import review_demo
    return {"items": [{"id": p, "name": oauth.NAMES[p]} for p in oauth.available()],
            "code": review_demo.enabled()}


class OAuthStart(BaseModel):
    client: str = "web"          # web — PWA в браузере, app — своё приложение


async def _oauth_start(provider: str, request: Request, client: str, link_user: int | None) -> dict:
    import oauth
    import ratelimit
    from database.identities import new_state
    if not ratelimit.allow("auth_start", _client_ip(request)):
        raise HTTPException(429, "Слишком много попыток — подожди минуту")
    verifier = oauth.new_verifier()
    state = await new_state(provider, verifier, "", client if client in ("web", "app") else "web", link_user)
    return {"url": oauth.authorize_url(provider, state, verifier, _redirect_uri(request, provider))}


@router.post("/api/auth/{provider}/start")
async def auth_oauth_start(provider: str, body: OAuthStart, request: Request):
    return await _oauth_start(_provider(provider), request, body.client, None)


@router.post("/api/auth/{provider}/link")
async def auth_oauth_link(provider: str, body: OAuthStart, request: Request, user: dict = CurrentUser):
    """Привязать VK/Яндекс к своему аккаунту — чтобы входить и без Telegram."""
    return await _oauth_start(_provider(provider), request, body.client, user["id"])


@router.get("/api/auth/{provider}/callback")
async def auth_oauth_callback(provider: str, request: Request, code: str = "", state: str = "",
                              device_id: str = "", error: str = ""):
    import logging

    import oauth
    from fastapi.responses import RedirectResponse
    from database import get_user, upsert_user
    from database.identities import find_user, link, new_local_user, new_state, take_state
    from database.sessions import create_session
    provider = _provider(provider)
    st = await take_state(state[:64]) if state else None
    if not st or st["provider"] != provider:
        return _page("Ссылка устарела", "Начни вход ещё раз — в приложении.", status=400)
    if error or not code:
        return _page("Вход отменён", "Можно попробовать ещё раз или войти через Telegram.")
    try:
        subject, name = await oauth.profile(provider, code, st["verifier"], _redirect_uri(request, provider),
                                            device_id=device_id, state=state)
    except Exception as e:
        logging.getLogger(__name__).warning(f"вход {provider}: {e}")
        return _page("Не получилось", f"{oauth.NAMES[provider]} не ответил — попробуй через минуту.", status=502)
    owner = await find_user(provider, subject)
    if st["link_user"]:
        if owner and owner != st["link_user"]:
            return _page("Уже привязан", f"Этот {oauth.NAMES[provider]} привязан к другому аккаунту.", status=409)
        # подтверждение кнопкой: видно, к чьему аккаунту привязываешь
        confirm = await new_state(provider, "-", f"{subject}\t{name}", "confirm", st["link_user"])
        who = (await get_user(st["link_user"]) or {}).get("full_name") or "твоему"
        return _page(f"Привязать {oauth.NAMES[provider]}?",
                     f"{name or oauth.NAMES[provider]} → аккаунт «{who}». Потом можно входить и без Telegram.",
                     f"<form method='post' action='/api/auth/{provider}/confirm'><input type='hidden' name='state' "
                     f"value='{confirm}'><button style='font:inherit;padding:12px 20px'>Да, привязать</button></form>")
    if not owner:
        owner = await new_local_user(name or oauth.NAMES[provider])
        await link(provider, subject, owner, name)
    elif name and not (await get_user(owner) or {}).get("full_name"):
        await upsert_user(owner, "", name)
    token = await create_session(owner, f"{_device(request)} · {oauth.NAMES[provider]}")
    target = APP_RETURN if st["client"] == "app" else "/app"
    return RedirectResponse(f"{target}#token={token}", status_code=303)


@router.post("/api/auth/{provider}/confirm")
async def auth_oauth_confirm(provider: str, request: Request):
    import oauth
    from database.identities import find_user, link, take_state
    provider = _provider(provider)
    from urllib.parse import parse_qs
    form = parse_qs((await request.body()).decode(errors="ignore"))     # без python-multipart
    st = await take_state((form.get("state") or [""])[0][:64])
    if not st or st["provider"] != provider or st["client"] != "confirm":
        return _page("Ссылка устарела", "Начни привязку ещё раз.", status=400)
    subject, _, name = st["code"].partition("\t")
    owner = await find_user(provider, subject)
    if owner and owner != st["link_user"]:
        return _page("Уже привязан", f"Этот {oauth.NAMES[provider]} привязан к другому аккаунту.", status=409)
    await link(provider, subject, st["link_user"], name)
    return _page("Готово", f"{oauth.NAMES[provider]} привязан — теперь им можно входить. Вернись в приложение.")


@router.get("/api/auth/identities")
async def auth_identities(user: dict = CurrentUser):
    import oauth
    from database.identities import is_local, list_for
    return {"items": [dict(i, title=oauth.NAMES.get(i["provider"], i["provider"])) for i in await list_for(user["id"])],
            "available": [{"id": p, "name": oauth.NAMES[p]} for p in oauth.available()],
            "telegram": not is_local(user["id"])}


@router.delete("/api/auth/identities/{provider}")
async def auth_unlink(provider: str, user: dict = CurrentUser):
    """Отвязать. Аккаунт без Telegram не может отвязать последний вход."""
    from database.identities import is_local, list_for, unlink
    if is_local(user["id"]) and len(await list_for(user["id"])) <= 1:
        raise HTTPException(400, "Это твой единственный вход — сначала привяжи другой")
    if not await unlink(user["id"], provider):
        raise HTTPException(404, "Не привязан")
    return {"ok": True}
