"""Основная иконка Капибары — «Мел» (5.117.12, Никита 28.10: «сделать Мел
базовой везде»).

    python tools/base_icon.py

Берёт design/base_icon/light.png (квадрат, лучше 1024) и раскладывает:
iOS AppIcon.appiconset (все размеры и 1024 для App Store), Android
ic_launcher во всех плотностях, PWA (webapp/static/pwa, app/web/icons),
значки вкладки браузера. Прежняя синяя капибара на мяче один раз уезжает в
альтернативную иконку «Первая» (IconOriginal.appiconset, ic_launcher_original)
— повторный запуск её не трогает.
"""
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
SRC = ROOT / "design" / "base_icon" / "light.png"
RES = APP / "android" / "app" / "src" / "main" / "res"
XCASSETS = APP / "ios" / "Runner" / "Assets.xcassets"
ANDROID = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
# (путь, размер); маска PWA обрезает до круга 80 % — капибара и так в центре
WEB = [
    (ROOT / "webapp" / "static" / "pwa" / "apple-touch-icon.png", 180),
    (ROOT / "webapp" / "static" / "pwa" / "icon-192.png", 192),
    (ROOT / "webapp" / "static" / "pwa" / "icon-512.png", 512),
    (ROOT / "webapp" / "static" / "pwa" / "maskable-512.png", 512),
    (ROOT / "webapp" / "static" / "img" / "capy" / "icon-64.png", 64),
    (ROOT / "webapp" / "static" / "site" / "favicon.png", 64),
    (APP / "web" / "favicon.png", 32),
    (APP / "web" / "icons" / "Icon-192.png", 192),
    (APP / "web" / "icons" / "Icon-512.png", 512),
    (APP / "web" / "icons" / "Icon-maskable-192.png", 192),
    (APP / "web" / "icons" / "Icon-maskable-512.png", 512),
]


def source() -> Image.Image:
    img = Image.open(SRC).convert("RGB")  # App Store: 1024 без прозрачности
    w, h = img.size
    if w != h:
        m = min(w, h)
        img = img.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
    return img


def save(img: Image.Image, px: int, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((px, px), Image.LANCZOS).save(path, optimize=True)


def keep_original():
    """Прежняя основная → «Первая» (один раз, пока её нет)."""
    old = XCASSETS / "AppIcon.appiconset"
    new = XCASSETS / "IconOriginal.appiconset"
    if not new.exists():
        new.mkdir()
        images = []
        for i in json.loads((old / "Contents.json").read_text(encoding="utf-8"))["images"]:
            if i["idiom"] == "ios-marketing":
                continue  # 1024 альтернативной иконке не нужен
            shutil.copy(old / i["filename"], new / i["filename"])
            images.append(i)
        new.joinpath("Contents.json").write_text(
            json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
            encoding="utf-8",
        )
    for dens in ANDROID:
        dst = RES / f"mipmap-{dens}" / "ic_launcher_original.png"
        if not dst.exists():
            shutil.copy(RES / f"mipmap-{dens}" / "ic_launcher.png", dst)


def build():
    keep_original()
    big = source()
    folder = XCASSETS / "AppIcon.appiconset"
    for i in json.loads((folder / "Contents.json").read_text(encoding="utf-8"))["images"]:
        px = round(float(i["size"].split("x")[0]) * int(i["scale"][0]))
        save(big, px, folder / i["filename"])
    for dens, px in ANDROID.items():
        save(big, px, RES / f"mipmap-{dens}" / "ic_launcher.png")
    for path, px in WEB:
        save(big, px, path)


if __name__ == "__main__":
    build()
