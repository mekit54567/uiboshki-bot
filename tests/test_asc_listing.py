"""tools/asc_listing.py: токен для App Store Connect и разбор аргументов без сети."""
import sys
from pathlib import Path

import pytest

jwt = pytest.importorskip("jwt")
ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import asc_listing  # noqa: E402


def _p8() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def test_token_claims():
    priv, pub = _p8()
    token = asc_listing.make_token("KEY123", "issuer-1", priv)
    head = jwt.get_unverified_header(token)
    assert head["kid"] == "KEY123" and head["alg"] == "ES256"
    claims = jwt.decode(token, pub, algorithms=["ES256"], audience="appstoreconnect-v1")
    assert claims["iss"] == "issuer-1"
    assert claims["exp"] - claims["iat"] <= 20 * 60


def test_no_keys_is_error(monkeypatch, tmp_path):
    for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8"):
        monkeypatch.delenv(k, raising=False)
    f = tmp_path / "n.md"
    f.write_text("текст", encoding="utf-8")
    assert asc_listing.main(["--version", "2.0.1", "--whats-new", str(f), "--screens", str(tmp_path)]) == 2
