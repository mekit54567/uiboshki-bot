"""Разведка Пульса (pulse_probe): разбор protobuf без схемы, кадры gRPC-Web,
архив с файлами приложения и ответами методов."""
import io
import struct
import zipfile

import httpx
import pytest

import pulse_probe


def _v(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def _len(field, data):
    return _v(field << 3 | 2) + _v(len(data)) + data


ME = (_len(1, "3f2a-uuid".encode()) + _len(2, _len(1, "Иванов".encode()) + _v(2 << 3) + _v(300))
      + _v(3 << 3 | 1) + struct.pack("<d", 42.5))


def test_decode_and_dump():
    tree = pulse_probe.decode(ME)
    assert tree == [(1, "3f2a-uuid"), (2, [(1, "Иванов"), (2, 300)]), (3, 42.5)]
    assert pulse_probe.dump(tree) == ["1: '3f2a-uuid'", "2 {", "2.1: 'Иванов'", "2.2: 300", "2 }", "3: 42.5"]
    with pytest.raises(ValueError):
        pulse_probe.decode(b"\x0a\x09abc")          # длина больше данных


def test_frames():
    body = pulse_probe.frame(ME) + b"\x80" + struct.pack(">I", 29) + b"grpc-status:0\r\ngrpc-message:"
    msgs, trailer = pulse_probe.unframe(body)
    assert msgs == [ME] and trailer["grpc-status"] == "0"


@pytest.mark.asyncio
async def test_probe(monkeypatch):
    seen = []

    def pulse(request):
        path = request.url.path
        seen.append((request.method, path, request.headers.get("cookie")))
        if path == "/":
            return httpx.Response(200, text='<script type="module" src="/assets/index-a1.js"></script>')
        if path == "/assets/index-a1.js":
            return httpx.Response(200, text='import("./Lessons-b2.js");const m=["assets/shared-c3.js"]')
        if path in ("/assets/Lessons-b2.js", "/assets/shared-c3.js"):
            return httpx.Response(200, text='"rtu_tc.attendance.api.VisitingLogService"')
        if path == "/pulse-info.json":
            return httpx.Response(200, json={"version": "1.9.3"})
        if path.endswith("/GetMeInfo"):
            assert request.headers["pulse-app-version"] == "1.9.3" and request.content == b"\x00\x00\x00\x00\x00"
            return httpx.Response(200, content=pulse_probe.frame(ME) + b"\x80" + struct.pack(">I", 14) + b"grpc-status:0\r\n")
        return httpx.Response(200, headers={"grpc-status": "12", "grpc-message": "unimplemented"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, transport=httpx.MockTransport(pulse), **kw))

    monkeypatch.delenv("PULSE_COOKIE", raising=False)
    data, summary = await pulse_probe.probe()
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert {"site/index.html", "site/assets/index-a1.js", "site/assets/Lessons-b2.js",
            "site/assets/shared-c3.js", "site/pulse-info.json", "calls.txt"} <= set(names)
    assert "PULSE_COOKIE не задана" in summary and not any(m == "POST" for m, _, _ in seen)

    monkeypatch.setenv("PULSE_COOKIE", "sess=abc")
    data, summary = await pulse_probe.probe()
    calls = zipfile.ZipFile(io.BytesIO(data)).read("calls.txt").decode()
    assert "2.1: 'Иванов'" in calls and "grpc-status 12 unimplemented" in calls
    assert f"ответило 1 из {len(pulse_probe.SELF_METHODS)}" in summary
    assert all(c == "sess=abc" for m, _, c in seen if m == "POST")
