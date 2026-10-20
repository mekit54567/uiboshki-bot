"""Пуши (этап 2 (г)): веб-пуши PWA (ключ VAPID, подписка браузера) и пуши
своего приложения (токен FCM/RuStore/APNs и ключ шифрования, app_push.py)."""

import base64
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webapp.deps import CurrentUser

router = APIRouter()


@router.get("/api/push/key")
async def push_key(user: dict = CurrentUser):
    import webpush
    return {"key": webpush.public_key_b64()}


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSub(BaseModel):
    endpoint: str
    keys: PushKeys


@router.post("/api/push/subscribe")
async def push_subscribe(body: PushSub, request: Request, user: dict = CurrentUser):
    from database.push import save_push_sub
    from webapp.routes.auth import _device
    if not push_host_ok(body.endpoint) or len(body.endpoint) > 1000:
        raise HTTPException(400, "не похоже на подписку браузера")
    await save_push_sub(user["id"], body.endpoint, body.keys.p256dh[:200], body.keys.auth[:100], _device(request))
    return {"ok": True}


# Куда браузеры принимают пуши (Chrome/Edge/Яндекс — FCM, Firefox — Mozilla,
# Safari — Apple). Любой другой https-адрес — отказ: сервер не шлёт POST куда
# попало (ревью безопасности 09.10).
PUSH_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com")


def push_host_ok(endpoint: str) -> bool:
    from urllib.parse import urlsplit
    u = urlsplit(endpoint)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


class PushOff(BaseModel):
    endpoint: str


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(body: PushOff, user: dict = CurrentUser):
    from database.push import delete_push_sub
    return {"ok": True, "removed": await delete_push_sub(body.endpoint, user["id"])}


# ── Пуши своего приложения (app_push.py): токен устройства + его ключ AES ────

APP_TOKEN_RE = re.compile(r"^[A-Za-z0-9:_\-.+/=]{16,4096}$")
APNS_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64,200}$")     # идёт в адрес запроса к Apple — только hex


@router.get("/api/push/app")
async def app_push_config(user: dict = CurrentUser):
    """Какие каналы включены на сервере: нет ни одного — тумблера в приложении нет."""
    import app_push
    return {"platforms": app_push.platforms(), "version": app_push.VERSION}


class AppPushSub(BaseModel):
    platform: str
    token: str
    key: str


def _check_token(platform: str, token: str):
    from database.app_push import PLATFORMS
    if platform not in PLATFORMS:
        raise HTTPException(400, "неизвестный сервис пушей")
    if not (APNS_TOKEN_RE if platform == "apns" else APP_TOKEN_RE).match(token):
        raise HTTPException(400, "не похоже на токен устройства")


@router.post("/api/push/app/subscribe")
async def app_push_subscribe(body: AppPushSub, request: Request, user: dict = CurrentUser):
    import app_push
    import sdo_accounts
    from database.app_push import save_app_push
    from webapp.routes.auth import _device
    _check_token(body.platform, body.token)
    key = app_push.parse_key(body.key)
    if key is None:
        raise HTTPException(400, "ключ — 32 байта в base64")
    await save_app_push(user["id"], body.platform, body.token,
                        sdo_accounts.encrypt(base64.b64encode(key).decode()), _device(request))
    return {"ok": True, "enabled": app_push.enabled(body.platform)}


class AppPushOff(BaseModel):
    platform: str
    token: str


@router.post("/api/push/app/unsubscribe")
async def app_push_unsubscribe(body: AppPushOff, user: dict = CurrentUser):
    from database.app_push import delete_app_push
    return {"ok": True, "removed": await delete_app_push(body.platform, body.token, user["id"])}
