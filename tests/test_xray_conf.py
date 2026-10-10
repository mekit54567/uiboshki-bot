"""Конфиг Xray для прокси бота (tools/xray_conf.py): из ссылки vless:// или
JSON приложения берётся только исходящий прокси, логи телефона и правила
отбрасываются; наружу — http и socks на 127.0.0.1. Ключи — выдуманные."""
import base64
import json

import pytest

from tools import xray_conf

UUID = "00000000-1111-2222-3333-444444444444"


def test_vless_reality_link():
    link = (f"vless://{UUID}@example.org:443?type=tcp&security=reality&sni=www.example.com&fp=firefox"
            "&pbk=PUBKEY&sid=ab12&flow=xtls-rprx-vision#Латвия")
    conf = xray_conf.build(link)
    out = conf["outbounds"][0]
    assert out["protocol"] == "vless" and out["tag"] == "proxy"
    user = out["settings"]["vnext"][0]["users"][0]
    assert user == {"id": UUID, "encryption": "none", "flow": "xtls-rprx-vision"}
    assert out["settings"]["vnext"][0]["address"] == "example.org"
    r = out["streamSettings"]["realitySettings"]
    assert r["publicKey"] == "PUBKEY" and r["shortId"] == "ab12" and r["serverName"] == "www.example.com"
    assert {i["port"] for i in conf["inbounds"]} == {10809, 10808}
    assert all(i["listen"] == "127.0.0.1" for i in conf["inbounds"])


def test_app_json_keeps_only_proxy_outbound():
    app = {"log": {"access": "/private/var/mobile/x/access.log", "loglevel": "Debug"},
           "routing": {"rules": [{"domain": ["geosite:private"], "outboundTag": "direct"}]},
           "outbounds": [{"protocol": "freedom", "tag": "direct"},
                         {"protocol": "vless", "tag": "proxy",
                          "settings": {"vnext": [{"address": "example.org", "port": 443, "users": [{"id": UUID}]}]},
                          "streamSettings": {"network": "tcp", "security": "tls"}}]}
    for raw in (json.dumps(app), base64.b64encode(json.dumps(app).encode()).decode()):
        conf = xray_conf.build(raw)
        assert conf["log"] == {"loglevel": "warning"} and "routing" not in conf
        assert [o["protocol"] for o in conf["outbounds"]] == ["vless"]


def test_bad_config_does_not_leak(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XRAY_CONFIG", json.dumps({"outbounds": [{"protocol": "freedom"}]}))
    assert xray_conf.main(str(tmp_path / "x.json")) == 2
    monkeypatch.setenv("XRAY_CONFIG", f"vless://{UUID}@example.org:443?security=tls&sni=example.org")
    assert xray_conf.main(str(tmp_path / "x.json")) == 0
    assert UUID not in capsys.readouterr().err                # ключ в логи не попадает
    with pytest.raises(ValueError):
        xray_conf.build("ss://abc@example.org:8388")
