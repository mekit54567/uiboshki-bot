"""Картинки 1200×630 со стендом сайта:
  • превью ссылки на сайт /about — webapp/static/site/og.jpg (tools/site_og.html);
  • приглашение друга — webapp/static/site/invite.jpg (tools/site_invite.html,
    флаг --invite): приложение в телефоне — в светлой теме (Никита 18.10).

Сервер с WebApp должен быть запущен (стенд или локально):
    python tools/site_og.py http://localhost:8766
    python tools/site_og.py http://localhost:8766 --invite
(свой Chromium — переменная CHROMIUM=/путь/к/chrome).
Страница — стили сайта и живое демо (/about/demo) в телефоне.
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# Светлая тема Telegram (iOS) для демо: заглушка site/demo.js по умолчанию тёмная.
# Подменяем только в браузере снимка — сам демо на сайте остаётся как есть.
LIGHT = ('colorScheme: "light", themeParams: {bg_color: "#f2f2f7", secondary_bg_color: "#ffffff", '
         'section_bg_color: "#ffffff", text_color: "#000000", hint_color: "#8e8e93", '
         'section_separator_color: "#e4e6ea"}')
DARK = 'colorScheme: "dark", themeParams: {}'


def light_demo(js: str) -> str:
    if DARK not in js:
        raise SystemExit("site/demo.js: не нашёл тёмную тему заглушки — поправь tools/site_og.py")
    return js.replace(DARK, LIGHT, 1)


def main(base: str, invite: bool = False):
    page_html = "site_invite.html" if invite else "site_og.html"
    out = "invite.jpg" if invite else "og.jpg"
    html = (ROOT / "tools" / page_html).read_text(encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)   # своя сборка — CHROMIUM=…
        ctx = b.new_context(viewport={"width": 1200, "height": 630})
        if invite:
            def patch(route):
                resp = route.fetch()
                route.fulfill(response=resp, body=light_demo(resp.text()))
            ctx.route(re.compile(r"/site/demo\.js(\?|$)"), patch)     # не demo.json
        pg = ctx.new_page()
        pg.goto(base.rstrip("/") + "/about", wait_until="networkidle")
        pg.set_content(html, wait_until="networkidle")
        pg.wait_for_timeout(3000)                     # демо в iframe дорисовывает главную
        pg.screenshot(path=str(ROOT / "webapp/static/site" / out), type="jpeg", quality=88)
        b.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "http://localhost:8766", invite="--invite" in sys.argv)
