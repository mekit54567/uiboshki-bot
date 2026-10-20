"""Картинки 1200×630 со стендом сайта:
  • превью ссылки на сайт /about — webapp/static/site/og.jpg (tools/site_og.html).
    С 19.10 og.jpg — картинка, которую Никита сделал в ChatGPT: снимок отсюда
    её перезапишет, поэтому только с флагом --og (запасной вариант);
  • приглашение друга — webapp/static/site/invite.jpg (tools/site_invite.html,
    флаг --invite): приложение в телефоне — в светлой теме (Никита 18.10).

Сервер с WebApp должен быть запущен (стенд или локально):
    python tools/site_og.py http://localhost:8766 --invite
    python tools/site_og.py http://localhost:8766 --og       # перезапишет og.jpg от ChatGPT
(свой Chromium — переменная CHROMIUM=/путь/к/chrome).
Страница — стили сайта и живое демо (/about/demo) в телефоне.
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# С 5.104 демо на сайте — само приложение (веб-сборка Flutter): тему оно берёт
# из системы (prefers-color-scheme), её и задаём браузеру снимка —
# приглашение светлое, превью сайта тёмное.


def main(base: str, invite: bool = False):
    page_html = "site_invite.html" if invite else "site_og.html"
    out = "invite.jpg" if invite else "og.jpg"
    html = (ROOT / "tools" / page_html).read_text(encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)   # своя сборка — CHROMIUM=…
        ctx = b.new_context(viewport={"width": 1200, "height": 630},
                            color_scheme="light" if invite else "dark")
        pg = ctx.new_page()
        pg.goto(base.rstrip("/") + "/about", wait_until="networkidle")
        pg.set_content(html, wait_until="networkidle")
        pg.wait_for_timeout(6000)                     # приложение в iframe запускается и рисует главную
        pg.screenshot(path=str(ROOT / "webapp/static/site" / out), type="jpeg", quality=88)
        b.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--invite" not in sys.argv and "--og" not in sys.argv:
        raise SystemExit("--invite — картинка приглашения; --og — превью сайта (заменит og.jpg от ChatGPT)")
    main(args[0] if args else "http://localhost:8766", invite="--invite" in sys.argv)
