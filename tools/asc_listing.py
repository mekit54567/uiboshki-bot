"""Выгрузка карточки версии в App Store Connect через API, без отправки на проверку.

    python tools/asc_listing.py --version 2.0.1 --whats-new docs/store/whats-new-2.0.1.md \
        --screens docs/store/screens/framed [--dry-run]

Что делает (всё — в версии iOS, «Подготовка к отправке»; «Add for Review» не нажимает):
1. находит приложение по bundle id ru.uiboshki.app, находит версию или создаёт её
   (выпуск вручную);
2. прописывает «Что нового» в локали ru (и во всех остальных, что уже есть у версии);
3. для каждой папки скринов (appstore-6.9, appstore-6.3) очищает набор нужного размера
   и заливает файлы по порядку 1…N.
4. с --build-number выбирает указанную обработанную сборку iOS для этой версии.

Ключ — те же секреты, что у загрузки в TestFlight: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8
(переменные окружения; значения в логи не пишутся). Версия 2.0.1 появится в списке,
когда Apple обработает билд, но саму версию можно создать и раньше.
"""
import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

import httpx
import jwt

API = "https://api.appstoreconnect.apple.com"
BUNDLE_ID = "ru.uiboshki.app"
# App Store Connect использует старые идентификаторы размеров по API.
SETS = {
    "appstore-6.9": ("APP_IPHONE_67", (1320, 2868)),
    "appstore-6.3": ("APP_IPHONE_61", (1206, 2622)),
}


class AscError(RuntimeError):
    pass


def make_token(key_id: str, issuer: str, p8: str) -> str:
    now = int(time.time())
    payload = {"iss": issuer, "iat": now, "exp": now + 15 * 60, "aud": "appstoreconnect-v1"}
    return jwt.encode(payload, p8, algorithm="ES256", headers={"kid": key_id, "typ": "JWT"})


class Asc:
    def __init__(self, token: str, dry: bool = False):
        self.http = httpx.Client(base_url=API, timeout=60, headers={"Authorization": f"Bearer {token}"})
        self.dry = dry

    def call(self, method: str, path: str, **kw) -> dict:
        if self.dry and method != "GET":
            print(f"[dry-run] {method} {path}")
            return {"data": {"id": "DRY"}}
        r = self.http.request(method, path, **kw)
        if r.status_code >= 300:
            raise AscError(f"{method} {path} → {r.status_code}: {r.text[:600]}")
        return r.json() if r.content else {}

    def get(self, path: str, **params) -> list[dict]:
        return self.call("GET", path, params=params).get("data", [])


def find_app(asc: Asc) -> str:
    apps = asc.get("/v1/apps", **{"filter[bundleId]": BUNDLE_ID})
    if not apps:
        raise AscError(f"приложение {BUNDLE_ID} не найдено")
    return apps[0]["id"]


def ensure_version(asc: Asc, app_id: str, version: str) -> str:
    found = asc.get(f"/v1/apps/{app_id}/appStoreVersions",
                    **{"filter[versionString]": version, "filter[platform]": "IOS"})
    if found:
        state = found[0]["attributes"].get("appStoreState")
        print(f"версия {version} уже есть, состояние: {state}")
        return found[0]["id"]
    body = {"data": {"type": "appStoreVersions",
                     "attributes": {"platform": "IOS", "versionString": version, "releaseType": "MANUAL"},
                     "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}}
    vid = asc.call("POST", "/v1/appStoreVersions", json=body)["data"]["id"]
    print(f"создана версия {version}")
    return vid


def set_whats_new(asc: Asc, version_id: str, text: str) -> list[dict]:
    locs = asc.get(f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")
    if not locs:
        body = {"data": {"type": "appStoreVersionLocalizations",
                         "attributes": {"locale": "ru", "whatsNew": text},
                         "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}}}}
        loc = asc.call("POST", "/v1/appStoreVersionLocalizations", json=body)["data"]
        print("создана локаль ru, «Что нового» записано")
        return [loc]
    for loc in locs:
        body = {"data": {"type": "appStoreVersionLocalizations", "id": loc["id"], "attributes": {"whatsNew": text}}}
        asc.call("PATCH", f"/v1/appStoreVersionLocalizations/{loc['id']}", json=body)
        print(f"«Что нового» записано в локаль {loc['attributes'].get('locale')}")
    return locs


def png_or_jpg_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def upload_set(asc: Asc, loc_id: str, display_type: str, files: list[Path]) -> None:
    sets = asc.get(f"/v1/appStoreVersionLocalizations/{loc_id}/appScreenshotSets")
    cur = next((s for s in sets if s["attributes"].get("screenshotDisplayType") == display_type), None)
    if cur:
        for shot in asc.get(f"/v1/appScreenshotSets/{cur['id']}/appScreenshots"):
            asc.call("DELETE", f"/v1/appScreenshots/{shot['id']}")
        set_id = cur["id"]
    else:
        body = {"data": {"type": "appScreenshotSets", "attributes": {"screenshotDisplayType": display_type},
                         "relationships": {"appStoreVersionLocalization": {"data": {"type": "appStoreVersionLocalizations", "id": loc_id}}}}}
        set_id = asc.call("POST", "/v1/appScreenshotSets", json=body)["data"]["id"]
    for f in files:
        data = f.read_bytes()
        body = {"data": {"type": "appScreenshots", "attributes": {"fileName": f.name, "fileSize": len(data)},
                         "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": set_id}}}}}
        shot = asc.call("POST", "/v1/appScreenshots", json=body)["data"]
        if asc.dry:
            continue
        for op in shot["attributes"]["uploadOperations"]:
            chunk = data[op["offset"]: op["offset"] + op["length"]]
            headers = {h["name"]: h["value"] for h in op["requestHeaders"]}
            r = httpx.request(op["method"], op["url"], content=chunk, headers=headers, timeout=120)
            if r.status_code >= 300:
                raise AscError(f"загрузка части {f.name}: {r.status_code}")
        done = {"data": {"type": "appScreenshots", "id": shot["id"],
                         "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}}
        asc.call("PATCH", f"/v1/appScreenshots/{shot['id']}", json=done)
        print(f"  {display_type}: {f.name} загружен")


def attach_build(asc: Asc, app_id: str, version_id: str, version: str, number: str) -> None:
    builds = asc.get("/v1/builds", **{
        "filter[app]": app_id,
        "filter[preReleaseVersion.platform]": "IOS",
        "filter[preReleaseVersion.version]": version,
        "filter[version]": number,
        "filter[processingState]": "VALID",
        "filter[expired]": "false",
    })
    if len(builds) != 1:
        raise AscError(f"ожидалась одна обработанная сборка iOS {version} ({number}), найдено: {len(builds)}")
    build_id = builds[0]["id"]
    path = f"/v1/appStoreVersions/{version_id}/relationships/build"
    current = asc.call("GET", path).get("data")
    if not current or current["id"] != build_id:
        asc.call("PATCH", path, json={"data": {"type": "builds", "id": build_id}})
    print(f"сборка iOS {version} ({number}) {'выбрана или будет выбрана' if asc.dry else 'выбрана'}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--whats-new", required=True, type=Path)
    ap.add_argument("--screens", required=True, type=Path)
    ap.add_argument("--build-number")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    key_id, issuer, p8 = (os.environ.get(k, "") for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_P8"))
    if not (key_id and issuer and p8):
        print("нет ASC_KEY_ID / ASC_ISSUER_ID / ASC_KEY_P8", file=sys.stderr)
        return 2
    asc = Asc(make_token(key_id, issuer, p8), a.dry_run)
    text = a.whats_new.read_text(encoding="utf-8").strip()
    if not text or len(text) > 4000:
        print("«Что нового»: пусто или длиннее 4000 знаков", file=sys.stderr)
        return 2
    try:
        app_id = find_app(asc)
        version_id = ensure_version(asc, app_id, a.version)
        if version_id == "DRY":   # версии ещё нет, дальше без неё нечего проверять
            print(f"пробный прогон: ключ и приложение найдены, версию {a.version} создам при настоящем запуске")
            return 0
        locs = set_whats_new(asc, version_id, text)
        for folder, (display_type, size) in SETS.items():
            files = sorted(p for p in (a.screens / folder).glob("*.jpg"))
            if not files:
                print(f"{folder}: файлов нет, пропускаю")
                continue
            bad = [p.name for p in files if png_or_jpg_size(p) != size]
            if bad:
                print(f"{folder}: размер не {size[0]}×{size[1]}: {', '.join(bad)}", file=sys.stderr)
                return 2
            for loc in locs:
                try:
                    upload_set(asc, loc["id"], display_type, files)
                except AscError as e:
                    if folder != "appstore-6.3":   # 6,9″ обязателен, 6,3″ Apple умеет делать из него сам
                        raise
                    print(f"{folder}: не залился ({e}); 6,9″ достаточно, продолжаю", file=sys.stderr)
        if a.build_number:
            attach_build(asc, app_id, version_id, a.version, a.build_number)
    except (AscError, httpx.HTTPError) as e:
        print(f"ошибка: {e}", file=sys.stderr)
        return 1
    print("готово: на проверку НЕ отправлено, это делает Никита в App Store Connect")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
