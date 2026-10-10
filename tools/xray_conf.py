"""
Конфиг Xray для прокси бота за границей (переезд в Россию, PLAN.md).

На сервере рядом с ботом запускается Xray (docker/start.sh), бот ходит
через него: `OUT_PROXY=http://127.0.0.1:10809` (net.py решает, что через
прокси, а что напрямую — маршрутизация в Xray не нужна).

`XRAY_CONFIG` (секрет в настройках хостинга, не в репозитории) — одно из:
- ссылка `vless://…`, `trojan://…` (как в приложении VPN);
- JSON конфига Xray из приложения — из него берётся только исходящий
  прокси (outbound), остальное (логи телефона, правила, DNS) не нужно;
- то же в base64.

    python tools/xray_conf.py /tmp/xray.json   — записать конфиг, код 0
"""

import base64
import binascii
import json
import os
import sys
from urllib.parse import parse_qs, unquote, urlsplit

HTTP_PORT = 10809
SOCKS_PORT = 10808
PROXY_PROTOCOLS = ("vless", "vmess", "trojan", "shadowsocks")


def _decode(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith(("{", "vless://", "trojan://")):
        return raw
    try:
        return base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError):
        return raw


def _stream(q: dict, host: str) -> dict:
    def g(k, d=""):
        return q.get(k, [d])[0]
    network = g("type", "tcp")
    security = g("security", "none")
    s: dict = {"network": network, "security": security}
    if security == "tls":
        s["tlsSettings"] = {"serverName": g("sni", host), "fingerprint": g("fp", "chrome")}
        if g("alpn"):
            s["tlsSettings"]["alpn"] = g("alpn").split(",")
    elif security == "reality":
        s["realitySettings"] = {"serverName": g("sni"), "fingerprint": g("fp", "chrome"), "publicKey": g("pbk"),
                                "shortId": g("sid"), "spiderX": g("spx")}
    if network == "ws":
        s["wsSettings"] = {"path": g("path", "/"), "headers": {"Host": g("host")} if g("host") else {}}
    elif network == "grpc":
        s["grpcSettings"] = {"serviceName": g("serviceName")}
    elif network in ("xhttp", "splithttp"):
        s["xhttpSettings"] = {"path": g("path", "/"), "host": g("host")}
    return s


def outbound_from_link(link: str) -> dict:
    u = urlsplit(link)
    q = parse_qs(u.query)
    host, port = u.hostname, u.port or 443
    if u.scheme == "vless":
        user = {"id": unquote(u.username or ""), "encryption": q.get("encryption", ["none"])[0]}
        if q.get("flow", [""])[0]:
            user["flow"] = q["flow"][0]
        settings = {"vnext": [{"address": host, "port": port, "users": [user]}]}
    elif u.scheme == "trojan":
        settings = {"servers": [{"address": host, "port": port, "password": unquote(u.username or "")}]}
        q.setdefault("security", ["tls"])
    else:
        raise ValueError(f"ссылка {u.scheme}:// не поддержана — пришли JSON конфига")
    return {"tag": "proxy", "protocol": u.scheme, "settings": settings, "streamSettings": _stream(q, host)}


def outbound_from_json(conf: dict) -> dict:
    outs = conf.get("outbounds") or []
    for o in outs:
        if o.get("tag") == "proxy" and o.get("protocol") in PROXY_PROTOCOLS:
            return {**o, "tag": "proxy"}
    for o in outs:
        if o.get("protocol") in PROXY_PROTOCOLS:
            return {**o, "tag": "proxy"}
    raise ValueError("в конфиге нет исходящего прокси (vless, vmess, trojan, shadowsocks)")


def build(raw: str) -> dict:
    text = _decode(raw)
    outbound = outbound_from_json(json.loads(text)) if text.startswith("{") else outbound_from_link(text)
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "http", "listen": "127.0.0.1", "port": HTTP_PORT, "protocol": "http"},
            {"tag": "socks", "listen": "127.0.0.1", "port": SOCKS_PORT, "protocol": "socks",
             "settings": {"udp": False}},
        ],
        "outbounds": [outbound],
    }


def main(path: str) -> int:
    raw = os.getenv("XRAY_CONFIG", "")
    if not raw.strip():
        return 1
    try:
        conf = build(raw)
    except Exception as e:      # без значения ключа в логе
        print(f"XRAY_CONFIG не разобрался: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conf, f)
    out = conf["outbounds"][0]
    print(f"Xray: {out['protocol']} через {out.get('streamSettings', {}).get('security', '?')}, "
          f"http 127.0.0.1:{HTTP_PORT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/xray.json"))
