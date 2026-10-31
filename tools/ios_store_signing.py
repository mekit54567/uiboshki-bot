"""Подпись iPhone-сборки для App Store — только в CI (app-build.yml, задача ios).

    python tools/ios_store_signing.py <project.pbxproj> --team ABCDE12345 \
        --app-profile "Kapibara App Store" --widget-profile "Kapibara Widget App Store" \
        --notify-profile "Kapibara Notify App Store"

В репозитории проект подписывается автоматически и без команды — так его
собирает AltStore/Sideloadly. Для магазина CI перед сборкой правит копию
проекта на раннере (в git это не попадает):
- у приложения, виджета и расширения пушей (KapibaraNotify) — ручная подпись
  своим профилем (у каждой цели свой App ID, поэтому подпись одной
  настройкой xcodebuild не задать);
- у приложения — права из Runner/RunnerStore.entitlements (там же «Вход
  через Apple» и пуши `aps-environment`: в Runner.entitlements их нет —
  AltStore с ними не ставит);
- только iPhone (TARGETED_DEVICE_FAMILY = 1): иначе App Store требует
  скриншоты iPad, а на iPad приложение всё равно откроется в режиме iPhone.
"""

import argparse
import re
import sys
from pathlib import Path

APP_ID = "ru.uiboshki.app"
WIDGET_ID = "ru.uiboshki.app.KapibaraWidget"
NOTIFY_ID = "ru.uiboshki.app.KapibaraNotify"
STORE_ENTITLEMENTS = "Runner/RunnerStore.entitlements"
IDENTITY = "Apple Distribution"

_BLOCK = re.compile(r"(buildSettings = \{\n)(.*?)(\n\t\t\t\};)", re.S)


def _set(body: str, key: str, value: str) -> str:
    """Поставить ключ в блоке buildSettings (заменить или дописать)."""
    line = re.compile(r"^(\t+)" + re.escape(key) + r" = .*?;$", re.M)
    if line.search(body):
        return line.sub(lambda m: f"{m.group(1)}{key} = {value};", body)
    indent = re.match(r"\t+", body).group(0) if body.strip() else "\t\t\t\t"
    return body + f"\n{indent}{key} = {value};"


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def patch(text: str, team: str, app_profile: str, widget_profile: str, notify_profile: str) -> str:
    if not re.fullmatch(r"[A-Z0-9]{10}", team):
        raise ValueError(f"Team ID — 10 латинских букв и цифр, а не {team!r}")
    profiles = {APP_ID: app_profile, WIDGET_ID: widget_profile, NOTIFY_ID: notify_profile}
    seen = dict.fromkeys(profiles, 0)

    def one(m: re.Match) -> str:
        body = m.group(2)
        bid = re.search(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", body)
        bid = bid.group(1).strip('"') if bid else None
        if bid not in seen:
            return m.group(0)
        seen[bid] += 1
        body = _set(body, "CODE_SIGN_STYLE", "Manual")
        body = _set(body, "DEVELOPMENT_TEAM", team)
        body = _set(body, "CODE_SIGN_IDENTITY", _q(IDENTITY))
        body = _set(body, '"CODE_SIGN_IDENTITY[sdk=iphoneos*]"', _q(IDENTITY))
        body = _set(body, "PROVISIONING_PROFILE_SPECIFIER", _q(profiles[bid]))
        body = _set(body, "TARGETED_DEVICE_FAMILY", "1")
        if bid == APP_ID:
            body = _set(body, "CODE_SIGN_ENTITLEMENTS", STORE_ENTITLEMENTS)
        return m.group(1) + body + m.group(3)

    out = _BLOCK.sub(one, text)
    if not all(seen.values()):
        raise ValueError(f"в проекте не нашлись цели: {[k for k, v in seen.items() if not v]}")
    # уровень проекта тоже: иначе цели без своей настройки соберутся и под iPad
    return out.replace('TARGETED_DEVICE_FAMILY = "1,2";', "TARGETED_DEVICE_FAMILY = 1;")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pbxproj", type=Path)
    ap.add_argument("--team", required=True)
    ap.add_argument("--app-profile", required=True)
    ap.add_argument("--widget-profile", required=True)
    ap.add_argument("--notify-profile", required=True)
    a = ap.parse_args(argv)
    a.pbxproj.write_text(
        patch(a.pbxproj.read_text(encoding="utf-8"), a.team, a.app_profile, a.widget_profile,
              a.notify_profile),
        encoding="utf-8",
    )
    print(f"подпись для App Store: команда {a.team}, профили «{a.app_profile}», "
          f"«{a.widget_profile}» и «{a.notify_profile}»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
