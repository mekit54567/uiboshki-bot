"""Экспериментальный вход в Пульс: журнал разведки с телефона → архив старосте."""
import base64
import io
import json
import zipfile

import pulse_lab
import pulse_probe
from tests.test_pulse_probe import ME


def _jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.c2lnbmF0dXJlLXNpZ25hdHVyZQ"


TOKEN = _jwt({"exp": 1_800_000_600, "iat": 1_800_000_000, "iss": "https://sso.mirea.ru/realms/x",
              "email": "ivanov@edu.mirea.ru", "name": "Иванов Иван"})


def _report():
    return {
        "login": {"age_min": 3},
        "pages": ["/", "/lessons/visiting-logs"],
        "storage": {"local": {"oidc.user": TOKEN, "theme": "dark"}, "session": {}},
        "calls": [{
            "kind": "xhr", "method": "POST", "status": 200, "ms": 120,
            "url": "https://pulse.mirea.ru/rtu_tc.rtu_attend.app.UserService/GetMeInfo",
            "req_headers": {"authorization": "Bearer " + TOKEN, "content-type": "application/grpc-web+proto"},
            "resp_headers": {"content-type": "application/grpc-web+proto", "grpc-status": "0"},
            "req": base64.b64encode(pulse_probe.frame()).decode(),
            "resp": base64.b64encode(pulse_probe.frame(ME)).decode(),
        }],
    }


def test_secrets_never_leave_and_lifetime_stays():
    data, summary = pulse_lab.build(_report())
    z = zipfile.ZipFile(io.BytesIO(data))
    everything = "".join(z.read(n).decode() for n in z.namelist())
    assert TOKEN not in everything and "ivanov@edu.mirea.ru" not in everything
    rep = json.loads(z.read("report.json"))
    auth = rep["calls"][0]["req_headers"]["authorization"]
    assert auth["redacted"] and auth["scheme"] == "Bearer" and auth["jwt"]["lifetime_min"] == 10.0
    assert rep["storage"]["local"]["oidc.user"]["jwt"]["iss"].startswith("https://sso.mirea.ru")
    assert rep["storage"]["local"]["theme"] == "dark"
    calls = z.read("calls.txt").decode()
    assert "ответ | 2.1: 'Иванов'" in calls and "GetMeInfo" in z.read("methods.txt").decode()
    assert "1 запросов" in summary


def test_endpoint_only_for_starosta(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.conftest import STAROSTA_ID
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    sent = []

    class Bot:
        async def send_document(self, chat_id, doc, caption=""):
            sent.append((chat_id, doc.filename, caption))

    monkeypatch.setattr("webapp.deps.tg_bot", lambda: Bot())
    c = TestClient(server.app)
    other = {"X-Telegram-Init-Data": _make_init_data(user={"id": 222, "first_name": "U"})}
    me = {"X-Telegram-Init-Data": _make_init_data(user={"id": STAROSTA_ID, "first_name": "N"})}
    assert c.post("/api/pulse/lab", headers=other, json=_report()).status_code == 403
    assert c.get("/api/me", headers=other).json()["lab"] is False
    assert c.get("/api/me", headers=me).json()["lab"] is True
    r = c.post("/api/pulse/lab", headers=me, json=_report())
    assert r.status_code == 200 and r.json()["sent"]
    assert sent[0][0] == STAROSTA_ID and sent[0][1].startswith("pulse-lab-")
    assert c.post("/api/pulse/lab", headers=me, content=b"[1]").status_code == 400
    assert c.get("/api/pulse/lab/kit", headers=other).status_code == 403
    assert isinstance(c.get("/api/pulse/lab/kit", headers=me).json(), dict)


def test_kit_from_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pulse_lab, "KIT_PATH", str(tmp_path / "kit.json"))
    assert pulse_lab.kit() == {}
    (tmp_path / "kit.json").write_text('{"seeds": ["/services"], "wait_sec": 6, "evil": 1}')
    (tmp_path / "hook.js").write_text("(function(){})()")
    (tmp_path / "evil.js").write_text("x")
    assert pulse_lab.kit() == {"seeds": ["/services"], "wait_sec": 6, "hook": "(function(){})()"}


def test_shipped_hook():
    """31.10: встроенный перехват не писал ответы «LeSSOns…» (ловил «sso» как вход)."""
    import re
    hook = pulse_lab.kit()["hook"]
    assert "window.__capy.v === 2" in hook
    authy = re.search(r"var AUTHY = /(.+)/i;", hook).group(1).replace("\\/", "/")
    for url in ("https://pulse.mirea.ru/rtu_tc.attendance.api.LessonService/GetAvailableLessonsOfVisitingLogs",
                "https://pulse.mirea.ru/rtu_tc.not_scheduled_lessons.api.StudentLanguageService/GetStudentLanguageState"):
        assert not re.search(authy, url, re.I)
    assert re.search(authy, "https://sso.mirea.ru/realms/x/protocol/openid-connect/token", re.I)


def test_body_limit_fits_journal():
    """31.10: журнал после обхода 40 страниц упёрся в общий предел 1 МБ (413)."""
    from webapp.server import body_limit
    assert body_limit("/api/v1/pulse/lab") == pulse_lab.MAX_BODY
    assert body_limit("/api/v1/pulse/lab/kit") == pulse_lab.MAX_BODY
    assert body_limit("/api/v1/me") == 1024 * 1024
