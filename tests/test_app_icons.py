"""Иконки-картинки приложения (5.84): design/app_icons.json, iOS, Android и
Dart согласованы — всё собирает tools/app_icons.py, тест ловит «забыл
запустить» и ручные правки."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
ICONS = json.loads((ROOT / "design" / "app_icons.json").read_text(encoding="utf-8"))


def cap(n: str) -> str:
    return "Icon" + n[0].upper() + n[1:]


def test_names_unique_and_groups_known():
    names = [i["name"] for i in ICONS["icons"]]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"[a-z][a-z0-9]*", n) for n in names)
    assert {i["group"] for i in ICONS["icons"]} <= set(ICONS["groups"])
    # Хэллоуин — сам 31.10, выбрать нельзя (Никита 13.10)
    assert [i["name"] for i in ICONS["icons"] if i.get("season")] == ["halloween"]


def test_ios_sets_light_and_dark():
    pbx = (APP / "ios" / "Runner.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    lines = re.findall(r'ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = "([^"]*)";', pbx)
    assert lines and len(set(lines)) == 1
    alt = set(lines[0].split())
    for ic in ICONS["icons"]:
        folder = APP / "ios" / "Runner" / "Assets.xcassets" / f"{cap(ic['name'])}.appiconset"
        assert cap(ic["name"]) in alt
        imgs = json.loads((folder / "Contents.json").read_text())["images"]
        light = [i for i in imgs if not i.get("appearances")]
        dark = [i for i in imgs if i.get("appearances")]
        # каждый размер — в светлой и тёмной, файлы на месте
        assert len(light) == len(dark) > 0
        assert {(i["size"], i["idiom"], i["scale"]) for i in light} == {(i["size"], i["idiom"], i["scale"]) for i in dark}
        assert all(i["filename"].startswith("dark-") for i in dark)
        for i in imgs:
            assert (folder / i["filename"]).exists(), i["filename"]


def test_android_aliases_and_pictures():
    manifest = (APP / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    block = manifest[manifest.index("<!-- ART:BEGIN"):manifest.index("<!-- ART:END -->")]
    aliases = re.findall(r'android:name="\.(Icon\w+)"', block)
    want = [x for ic in ICONS["icons"] for x in (cap(ic["name"]), cap(ic["name"]) + "Dark")]
    assert aliases == want
    res = APP / "android" / "app" / "src" / "main" / "res" / "mipmap-xxxhdpi"
    for icon in re.findall(r'android:icon="@mipmap/(\w+)"', block):
        assert (res / f"{icon}.png").exists(), icon
    # список иконок Android берёт из манифеста, а не из своего перечня
    main = next((APP / "android").rglob("MainActivity.kt")).read_text(encoding="utf-8")
    assert "listOf(\"classic\"" not in main


def test_dart_list_matches():
    dart = (APP / "lib" / "theme" / "app_icons_art.dart").read_text(encoding="utf-8")
    assert re.findall(r"AppIcon\._art\('(\w+)'", dart) == [i["name"] for i in ICONS["icons"]]
    for ic in ICONS["icons"]:
        for suf in ("", "_dark"):
            assert (APP / "assets" / "appicons" / f"{ic['name']}{suf}.png").exists()


def test_unlock_rules_valid():
    """unlock (5.91): известные иконки (и нарисованные кодом) и понятные правила."""
    import achievements
    drawn = {"classic", "depth", "indigo", "terracotta", "page", "sunset", "library"}
    names = drawn | {i["name"] for i in ICONS["icons"]}
    for name, rule in ICONS.get("unlock", {}).items():
        assert name in names, name
        assert name != "classic", "обычная иконка всегда открыта"
        kind, _, arg = rule.partition(":")
        assert rule in ("sub", "all", "none") or (kind == "ach" and arg in achievements.IDS) \
            or (kind == "rank" and arg in achievements.RANKS), rule
    dart = (APP / "lib" / "theme" / "app_icons_art.dart").read_text(encoding="utf-8")
    assert dict(re.findall(r"'(\w+)': '([\w:]+)',", dart)) == ICONS.get("unlock", {})
