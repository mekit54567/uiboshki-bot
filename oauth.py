"""Вход через VK ID и Яндекс ID (владелец 08.10): для тех, у кого нет или
не открывается Telegram, и чтобы вход не зависел только от него.

Как и вход через бота, поверх одноразового кода auth_logins:
  1. POST /api/auth/<провайдер>/start → ссылка на VK/Яндекс и код входа;
  2. человек входит там, провайдер возвращает его на /api/auth/<провайдер>/callback;
  3. бот узнаёт его id у провайдера → свой человек (привязан раньше) или
     новый аккаунт без Telegram → код входа подтверждён;
  4. PWA/приложение получает токен тем же /api/auth/poll.

Ключи — VK_CLIENT_ID (+ VK_CLIENT_SECRET, необязательно: VK ID работает с
PKCE) и YANDEX_CLIENT_ID + YANDEX_CLIENT_SECRET в переменных хостинга. Нет ключа —
кнопки нет. Сеть — только через _post/_get (тесты подменяют).
"""

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx

NAMES = {"vk": "VK ID", "yandex": "Яндекс ID"}


def _cfg(provider: str) -> tuple[str, str]:
    p = provider.upper()
    return os.getenv(f"{p}_CLIENT_ID", ""), os.getenv(f"{p}_CLIENT_SECRET", "")


def available() -> list[str]:
    """Провайдеры, для которых на хостинге есть ключи (Яндексу нужен и секрет)."""
    out = []
    for p in NAMES:
        cid, secret = _cfg(p)
        if cid and (secret or p == "vk"):
            out.append(p)
    return out


def new_verifier() -> str:
    return secrets.token_urlsafe(48)


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorize_url(provider: str, state: str, verifier: str, redirect_uri: str) -> str:
    cid, _ = _cfg(provider)
    if provider == "vk":
        return "https://id.vk.com/authorize?" + urlencode({
            "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri, "state": state,
            "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
            "scope": "vkid.personal_info"})
    return "https://oauth.yandex.ru/authorize?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri, "state": state,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256", "force_confirm": "no"})


class OAuthError(Exception):
    pass


async def _post(url: str, data: dict, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, data=data, headers=headers or {})
    if r.status_code >= 400:
        raise OAuthError(f"{url}: {r.status_code}")
    return r.json()


async def _get(url: str, headers: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers)
    if r.status_code >= 400:
        raise OAuthError(f"{url}: {r.status_code}")
    return r.json()


async def profile(provider: str, code: str, verifier: str, redirect_uri: str,
                  device_id: str = "", state: str = "") -> tuple[str, str]:
    """Код от провайдера → (id человека у провайдера, имя)."""
    cid, secret = _cfg(provider)
    if provider == "vk":
        tok = await _post("https://id.vk.com/oauth2/auth", {
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_id": cid, "device_id": device_id, "redirect_uri": redirect_uri, "state": state,
            **({"client_secret": secret} if secret else {})})
        if not tok.get("access_token"):
            raise OAuthError(f"VK: {tok.get('error_description') or tok.get('error') or 'нет токена'}")
        info = (await _post("https://id.vk.com/oauth2/user_info",
                            {"client_id": cid, "access_token": tok["access_token"]})).get("user") or {}
        uid = str(info.get("user_id") or tok.get("user_id") or "")
        name = " ".join(x for x in (info.get("first_name"), info.get("last_name")) if x)
    else:
        tok = await _post("https://oauth.yandex.ru/token", {
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_id": cid, "client_secret": secret})
        if not tok.get("access_token"):
            raise OAuthError(f"Яндекс: {tok.get('error_description') or tok.get('error') or 'нет токена'}")
        info = await _get("https://login.yandex.ru/info?format=json",
                          {"Authorization": f"OAuth {tok['access_token']}"})
        uid = str(info.get("id") or "")
        name = info.get("real_name") or info.get("display_name") or ""
    if not uid:
        raise OAuthError(f"{NAMES[provider]}: не отдал id")
    return uid, name.strip()[:100]
