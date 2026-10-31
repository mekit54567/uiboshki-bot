"""Сборки для магазинов (docs/store/): подпись iPhone для App Store только в
CI и только с секретами, «Вход через Apple» — только в магазинной сборке,
Android — APK и AAB с номером сборки из запуска."""
import plistlib
from pathlib import Path

import pytest
import yaml

from tools import ios_store_signing as sign

ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "app" / "ios"
PBXPROJ = IOS / "Runner.xcodeproj" / "project.pbxproj"
WF = ROOT / ".github" / "workflows" / "app-build.yml"


def _ent(name):
    return plistlib.loads((IOS / "Runner" / name).read_bytes())


def test_apple_signin_only_in_store_entitlements():
    """AltStore с правами applesignin и aps-environment не ставит — они только в RunnerStore."""
    alt, store = _ent("Runner.entitlements"), _ent("RunnerStore.entitlements")
    assert "com.apple.developer.applesignin" not in alt
    assert store["com.apple.developer.applesignin"] == ["Default"]
    assert store["aps-environment"] == "production" and "aps-environment" not in alt
    # всё остальное (App Group для виджета) — как в обычной сборке
    only_store = {"com.apple.developer.applesignin", "aps-environment"}
    assert {k: v for k, v in store.items() if k not in only_store} == alt


def test_patch_signs_app_and_extensions_with_own_profiles():
    out = sign.patch(PBXPROJ.read_text(encoding="utf-8"), "ABCDE12345", "Kap App", "Kap Widget", "Kap Notify")
    blocks = [b for _, b, _ in sign._BLOCK.findall(out)]
    app = [b for b in blocks if f"PRODUCT_BUNDLE_IDENTIFIER = {sign.APP_ID};" in b]
    widget = [b for b in blocks if f"PRODUCT_BUNDLE_IDENTIFIER = {sign.WIDGET_ID};" in b]
    notify = [b for b in blocks if f"PRODUCT_BUNDLE_IDENTIFIER = {sign.NOTIFY_ID};" in b]
    assert len(app) == 3 and len(widget) == 3 and len(notify) == 3  # Debug, Release, Profile
    for b in app:
        assert 'PROVISIONING_PROFILE_SPECIFIER = "Kap App";' in b
        assert "CODE_SIGN_ENTITLEMENTS = Runner/RunnerStore.entitlements;" in b
    for b in widget:
        assert 'PROVISIONING_PROFILE_SPECIFIER = "Kap Widget";' in b
        assert "CODE_SIGN_ENTITLEMENTS = KapibaraWidget/KapibaraWidget.entitlements;" in b
        assert b.count("CODE_SIGN_STYLE") == 1           # заменён, не продублирован
    for b in notify:
        assert 'PROVISIONING_PROFILE_SPECIFIER = "Kap Notify";' in b
        assert "CODE_SIGN_ENTITLEMENTS = KapibaraNotify/KapibaraNotify.entitlements;" in b
    for b in app + widget + notify:
        assert "CODE_SIGN_STYLE = Manual;" in b and "DEVELOPMENT_TEAM = ABCDE12345;" in b
        assert '"CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "Apple Distribution";' in b
    assert '"1,2"' not in out                            # только iPhone
    assert "PRODUCT_BUNDLE_IDENTIFIER = ru.uiboshki.app.RunnerTests;" in out


def test_patch_rejects_bad_team():
    with pytest.raises(ValueError):
        sign.patch(PBXPROJ.read_text(encoding="utf-8"), "abc", "a", "b", "c")


def test_repo_project_stays_unsigned_for_altstore():
    """В git проект без команды и без applesignin — так его ставит AltStore."""
    text = PBXPROJ.read_text(encoding="utf-8")
    assert "RunnerStore.entitlements" not in text
    assert "DEVELOPMENT_TEAM" not in text


def test_workflow_builds_store_files():
    text = WF.read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    assert "flutter build appbundle" in text and "flutter build apk" in text
    assert "tools/ios_store_signing.py" in text and "flutter build ipa" in text
    names = [s.get("name", "") for s in wf["jobs"]["ios"]["steps"]]
    assert any("без подписи" in n for n in names)        # без секретов CI зелёный
    inputs = wf[True]["workflow_dispatch"]["inputs"]     # yaml: «on» → True
    assert set(inputs) >= {"version", "testflight"}


def test_notify_extension_is_built_and_embedded():
    """Расширение KapibaraNotify расшифровывает пуш на iPhone: цель в проекте,
    вложена в приложение и подписывается в обеих сборках."""
    text = PBXPROJ.read_text(encoding="utf-8")
    assert "NotificationService.swift in Sources */," in text
    assert "KapibaraNotify.appex in Embed Foundation Extensions */," in text
    assert text.count("PRODUCT_BUNDLE_IDENTIFIER = ru.uiboshki.app.KapibaraNotify;") == 3
    info = plistlib.loads((IOS / "KapibaraNotify" / "Info.plist").read_bytes())
    assert info["NSExtension"]["NSExtensionPointIdentifier"] == "com.apple.usernotifications.service"
    wf = WF.read_text(encoding="utf-8")
    assert "PlugIns/KapibaraNotify.appex" in wf and "IOS_PROFILE_NOTIFY" in wf
