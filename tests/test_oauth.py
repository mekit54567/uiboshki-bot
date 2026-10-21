"""Вход через VK ID и Яндекс ID (владелец 08.10): новый аккаунт без Telegram,
повторный вход, приложение, привязка к аккаунту с подтверждением, чужая
привязка, отвязка последнего входа, рассылки без Telegram — только пушем."""
from urllib.parse import parse_qs, urlsplit

import pytest

import oauth
from tests.test_auth_sessions import client  # noqa: F401 — фикстура

TG_USER = 777


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("VK_CLIENT_ID", "vk-app")
    monkeypatch.setenv("YANDEX_CLIENT_ID", "ya-app")
    monkeypatch.setenv("YANDEX_CLIENT_SECRET", "ya-secret")
    who = {"subject": "vk-1", "name": "Аня Петрова"}

    async def profile(provider, code, verifier, redirect_uri, device_id="", state=""):
        assert code == "good" and verifier and redirect_uri.endswith(f"/api/auth/{provider}/callback")
        return who["subject"], who["name"]

    monkeypatch.setattr(oauth, "profile", profile)
    return who


def _start(c, provider="vk", client_kind="web", headers=None):
    res = c.post(f"/api/auth/{provider}/{'link' if headers else 'start'}", json={"client": client_kind},
                 headers=headers or {})
    assert res.status_code == 200, res.text
    q = parse_qs(urlsplit(res.json()["url"]).query)
    return q["state"][0], q


def _token(location: str) -> str:
    return location.split("#token=", 1)[1]


def test_no_keys_no_buttons(db, client, monkeypatch):  # noqa: F811
    for k in ("VK_CLIENT_ID", "YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    assert client.get("/api/auth/providers").json() == {"items": [], "code": False, "apple": False}
    assert client.post("/api/auth/vk/start", json={}).status_code == 404


@pytest.mark.asyncio
async def test_login_creates_account_without_telegram(db, client, keys):  # noqa: F811
    from database.identities import LOCAL_BASE
    assert [p["id"] for p in client.get("/api/auth/providers").json()["items"]] == ["vk", "yandex"]
    state, q = _start(client)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["vk-app"]   # PKCE
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}&device_id=d1", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"].startswith("/app#token=")
    me = client.get("/api/me", headers={"Authorization": f"Bearer {_token(res.headers['location'])}"}).json()
    assert me["id"] <= LOCAL_BASE and me["first_name"] == "Аня"
    assert me["group"] is None                                               # дальше — «Из какой ты группы?»
    again = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    assert again.status_code == 400                                          # state — один раз

    state, _ = _start(client, client_kind="app")
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    assert res.headers["location"].startswith("ru.uiboshki.app://auth#token=")   # своё приложение
    me2 = client.get("/api/me", headers={"Authorization": f"Bearer {_token(res.headers['location'])}"}).json()
    assert me2["id"] == me["id"]                                             # тот же человек

    # PWA на HTML (/app-html/) — назад туда же, а не в прежнюю сборку на /app (Никита 20.10)
    state, _ = _start(client, client_kind="html")
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    assert res.headers["location"].startswith("/app-html/#token=")

    keys.update(subject="vk-2", name="Боря")
    state, _ = _start(client)
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    me3 = client.get("/api/me", headers={"Authorization": f"Bearer {_token(res.headers['location'])}"}).json()
    assert me3["id"] < me["id"]                                              # новый — следующий номер


@pytest.mark.asyncio
async def test_link_needs_confirmation_and_owner(db, client, keys):  # noqa: F811
    from database.sessions import create_session
    await db.upsert_user(TG_USER, "anya", "Аня Петрова")
    h = {"Authorization": f"Bearer {await create_session(TG_USER, 'Phone')}"}
    state, _ = _start(client, headers=h)
    page = client.get(f"/api/auth/vk/callback?code=good&state={state}")
    assert "Да, привязать" in page.text and "Аня Петрова" in page.text       # видно, к чьему аккаунту
    confirm = page.text.split("name='state' value='", 1)[1].split("'", 1)[0]
    assert "Готово" in client.post("/api/auth/vk/confirm", content=f"state={confirm}",
                                   headers={"Content-Type": "application/x-www-form-urlencoded"}).text
    assert client.post("/api/auth/vk/confirm", content=f"state={confirm}").status_code == 400   # один раз

    state, _ = _start(client)                                                # теперь вход через VK — в тот же аккаунт
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    assert client.get("/api/me", headers={"Authorization": f"Bearer {_token(res.headers['location'])}"}
                      ).json()["id"] == TG_USER
    items = client.get("/api/auth/identities", headers=h).json()
    assert [i["provider"] for i in items["items"]] == ["vk"] and items["telegram"]

    await db.upsert_user(TG_USER + 1, "", "Чужой")
    h2 = {"Authorization": f"Bearer {await create_session(TG_USER + 1, 'Phone')}"}
    state, _ = _start(client, headers=h2)
    assert client.get(f"/api/auth/vk/callback?code=good&state={state}").status_code == 409   # уже чужой
    assert client.delete("/api/auth/identities/vk", headers=h).json() == {"ok": True}  # у кого есть Telegram — можно


@pytest.mark.asyncio
async def test_local_user_keeps_last_login_and_gets_push_only(db, client, keys, monkeypatch):  # noqa: F811
    import delivery
    state, _ = _start(client, provider="yandex")
    res = client.get(f"/api/auth/yandex/callback?code=good&state={state}", follow_redirects=False)
    h = {"Authorization": f"Bearer {_token(res.headers['location'])}"}
    uid = client.get("/api/me", headers=h).json()["id"]
    assert client.delete("/api/auth/identities/yandex", headers=h).status_code == 400   # последний вход
    assert client.post("/api/files/1/send", headers=h).status_code == 400              # «В Telegram» — нет

    pushed = []

    async def push(user_id, kind, html, tab=None):
        pushed.append(user_id)
        return 1

    class NoBot:
        async def send_message(self, *a, **k):
            raise AssertionError("в Telegram без Telegram")

    monkeypatch.setattr(delivery, "push", push)
    assert await delivery.deliver(NoBot(), uid, "утро", kind="morning") is None
    assert pushed == [uid]


def test_cancel_and_stale(db, client, keys):  # noqa: F811
    state, _ = _start(client)
    assert "отменён" in client.get(f"/api/auth/vk/callback?error=access_denied&state={state}").text
    assert client.get("/api/auth/vk/callback?code=good&state=чужой").status_code == 400


@pytest.mark.asyncio
async def test_app_gets_one_time_code_not_token(db, client, keys):  # noqa: F811
    """Своё приложение с challenge: в ru.uiboshki.app://auth — одноразовый код,
    токен — только в обмен на секрет приложения (аудит 21.10, R8, RFC 8252)."""
    verifier = oauth.new_verifier()
    res = client.post("/api/auth/vk/start", json={"client": "app", "challenge": oauth._challenge(verifier)})
    state = parse_qs(urlsplit(res.json()["url"]).query)["state"][0]
    res = client.get(f"/api/auth/vk/callback?code=good&state={state}", follow_redirects=False)
    loc = res.headers["location"]
    assert loc.startswith("ru.uiboshki.app://auth#code=") and "token" not in loc
    code = loc.split("#code=", 1)[1]
    # перехватчик ссылки без секрета — мимо, и код сгорел
    assert client.post("/api/auth/exchange", json={"code": code, "verifier": "чужой"}).status_code == 400
    assert client.post("/api/auth/exchange", json={"code": code, "verifier": verifier}).status_code == 400

    res = client.post("/api/v1/auth/vk/start", json={"client": "app", "challenge": oauth._challenge(verifier)})
    state = parse_qs(urlsplit(res.json()["url"]).query)["state"][0]
    code = client.get(f"/api/auth/vk/callback?code=good&state={state}",
                      follow_redirects=False).headers["location"].split("#code=", 1)[1]
    r = client.post("/api/v1/auth/exchange", json={"code": code, "verifier": verifier})
    assert r.status_code == 200
    me = client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["first_name"] == "Аня"
    assert client.post("/api/auth/exchange", json={"code": code, "verifier": verifier}).status_code == 400  # один раз
    # код входа — не код обмена: state начатого входа на обмен не годится
    state, _ = _start(client, client_kind="app")
    assert client.post("/api/auth/exchange", json={"code": state, "verifier": verifier}).status_code == 400
    assert client.post("/api/auth/vk/start", json={"client": "app", "challenge": "коротко"}).status_code == 400
