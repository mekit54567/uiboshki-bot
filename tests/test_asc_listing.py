"""tools/asc_listing.py: токен для App Store Connect и разбор аргументов без сети."""
import sys
from pathlib import Path
from unittest.mock import Mock

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


@pytest.mark.parametrize(("folder", "display_type"), [
    ("appstore-6.9", "APP_IPHONE_67"),
    ("appstore-6.3", "APP_IPHONE_61"),
])
def test_upload_uses_apple_display_type(monkeypatch, tmp_path, folder, display_type):
    for name in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8"):
        monkeypatch.setenv(name, "test")
    monkeypatch.setattr(asc_listing, "make_token", Mock(return_value="token"))
    monkeypatch.setattr(asc_listing, "find_app", Mock(return_value="app"))
    monkeypatch.setattr(asc_listing, "ensure_version", Mock(return_value="version"))
    monkeypatch.setattr(asc_listing, "set_whats_new", Mock(return_value=[{"id": "ru"}]))
    monkeypatch.setattr(asc_listing, "png_or_jpg_size", Mock(return_value=asc_listing.SETS[folder][1]))
    upload = Mock()
    monkeypatch.setattr(asc_listing, "upload_set", upload)
    note = tmp_path / "note.md"
    note.write_text("Что нового", encoding="utf-8")
    (tmp_path / folder).mkdir()
    shot = tmp_path / folder / "1-today.jpg"
    shot.touch()

    assert asc_listing.main(["--version", "2.0.1", "--whats-new", str(note), "--screens", str(tmp_path)]) == 0
    assert upload.call_args.args[1:] == ("ru", display_type, [shot])


def test_attach_build_only_for_requested_ios_version():
    asc = Mock(dry=False)
    asc.get.return_value = [{"id": "processed-build"}]
    asc.call.return_value = {"data": None}

    asc_listing.attach_build(asc, "app-id", "version-id", "2.0.1", "369")

    asc.get.assert_called_once_with("/v1/builds", **{
        "filter[app]": "app-id", "filter[preReleaseVersion.platform]": "IOS",
        "filter[preReleaseVersion.version]": "2.0.1", "filter[version]": "369",
        "filter[processingState]": "VALID", "filter[expired]": "false",
    })
    asc.call.assert_called_with("PATCH", "/v1/appStoreVersions/version-id/relationships/build",
                                json={"data": {"type": "builds", "id": "processed-build"}})
