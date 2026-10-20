"""PWA на /app — веб-сборка Flutter-приложения, как на iPhone (Никита 14.10:
«дизайн у приложений на iPhone и PWA одинаковый»). Сборку кладёт GitHub
Actions (app-web.yml → tools/pwa_build.sh) в webapp/flutter."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
WEB_INDEX = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")


def test_app_serves_flutter_build_only_with_switch(tmp_path, monkeypatch):
    """С 20.10 /app — HTML-версия; веб-сборка Flutter — только откатом
    PWA_ENGINE=flutter (и если сборка есть)."""
    import webapp.server as server
    (tmp_path / "index.html").write_text("<base href=\"/app/\">flutter", encoding="utf-8")
    monkeypatch.setattr(server, "FLUTTER_DIR", tmp_path)
    c = TestClient(server.app)
    monkeypatch.setenv("PWA_ENGINE", "html")
    assert "flutter" not in c.get("/app").text
    monkeypatch.setenv("PWA_ENGINE", "flutter")
    for path in ("/app", "/app/"):
        r = c.get(path)
        assert r.status_code == 200 and "flutter" in r.text and r.headers["cache-control"] == "no-cache"


def test_app_is_html_version_with_versioned_assets(tmp_path, monkeypatch):
    """PWA на HTML (webapp/static/app-html): файлы — полным адресом с меткой
    версии, иначе на /app (без своей папки) они не нашлись бы, а после
    выпуска остались бы старые."""
    import webapp.server as server
    monkeypatch.setenv("PWA_ENGINE", "flutter")
    monkeypatch.setattr(server, "FLUTTER_DIR", tmp_path / "нет")  # сборки нет — всё равно HTML
    c = TestClient(server.app)
    r = c.get("/app")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert re.search(r'src="/app-html/js/core\.js\?v=\w+"', r.text)
    assert re.search(r'href="/app-html/css/app\.css\?v=\w+"', r.text)
    assert 'src="js/' not in r.text and 'href="css/' not in r.text and 'href="fonts/' not in r.text
    for m in re.findall(r'(?:src|href)="(/app-html/[^"?]+)', r.text):
        assert c.get(m).status_code == 200, m


def test_flutter_assets_are_revalidated():
    """У main.dart.js нет метки версии — no-cache, иначе после выпуска старый код."""
    import webapp.server as server
    if not (server.FLUTTER_DIR / "main.dart.js").is_file():
        return
    r = TestClient(server.app).get("/app/main.dart.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"


def test_web_index_moves_old_pwa_login_and_checks_oauth():
    """Вход прежней PWA (uib_token) переезжает в ключ shared_preferences и
    удаляется (иначе «Выйти» вернул бы его); токен VK/Яндекс из адреса — только
    если вход начат в этом браузере (ревью безопасности 09.10)."""
    js = WEB_INDEX.split("<script>")[1].split("</script>")[0]
    assert '"flutter.uib_token"' in js and 'ls.removeItem("uib_token")' in js
    assert "JSON.stringify(old)" in js                        # shared_preferences хранит JSON
    oauth = js.split('location.hash.indexOf("#token=")')[1]
    assert "Date.now() - at < 15 * 60 * 1000" in oauth and "history.replaceState" in oauth
    assert 'register("/sw.js")' in js
    # до запуска Flutter, иначе он прочитает пустой вход
    assert WEB_INDEX.index("flutter.uib_token") < WEB_INDEX.index('src="flutter_bootstrap.js"')
    assert 'href="/manifest.webmanifest"' in WEB_INDEX         # id /app — установленная PWA та же


def test_flutter_does_not_register_its_own_service_worker():
    """У PWA свой /sw.js (оффлайн, пуши) — стандартный загрузчик Flutter
    регистрировал бы ещё flutter_service_worker.js."""
    boot = (ROOT / "app" / "web" / "flutter_bootstrap.js").read_text(encoding="utf-8")
    assert "_flutter.loader.load();" in boot and "serviceWorker" not in boot


def test_build_script_self_hosts_canvaskit():
    """canvaskit — со своего сервера (из России без «КВН»), база — /app/."""
    sh = (ROOT / "tools" / "pwa_build.sh").read_text(encoding="utf-8")
    cmd = next(line for line in sh.splitlines() if line.startswith("flutter build web"))
    assert "--base-href /app/" in cmd and "--no-web-resources-cdn" in cmd and "--dart-define=API=" in cmd
    assert "../webapp/flutter" in sh


def test_sw_caches_app_files():
    sw = (ROOT / "webapp" / "static" / "sw.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/app/")' in sw and "freshFirst(req, SHELL" in sw
    assert re.search(r'url\.pathname === "/app/"', sw)


def test_root_outside_telegram_with_login_opens_app():
    """www.uiboshki.ru вне Telegram: со входом — приложение /app, без — сайт."""
    core = (ROOT / "webapp" / "static" / "js" / "core.js").read_text(encoding="utf-8")
    assert 'location.replace(APP_TOKEN || flutterToken() ? "/app" : "/about")' in core


def test_web_index_push_bridge():
    """Пуши из PWA (5.86): Flutter зовёт window.uibPush (lib/web_push_web.dart);
    iPhone не с экрана «Домой» — подсказка поставить, а не «не поддерживается»."""
    js = WEB_INDEX.split("window.uibPush")[1].split("</script>")[0]
    for name in ("state:", "enable:", "disable:"):
        assert name in js
    assert '"install"' in js and "navigator.standalone" in js
    assert "applicationServerKey" in js and "sub.toJSON()" in js
    dart = (ROOT / "app" / "lib" / "web_push_web.dart").read_text(encoding="utf-8")
    assert all(f"@JS('uibPush.{n}')" in dart for n in ("state", "enable", "disable"))


def test_flutter_assets_gzipped():
    """PWA в Safari (19.10): ~13 МБ при первом открытии — сжимаем. Браузер без
    gzip получает файл как есть; ETag тот же — повторный заход отвечает 304."""
    import webapp.server as server
    f = server.FLUTTER_DIR / "main.dart.js"
    if not f.is_file():
        return
    c = TestClient(server.app)
    r = c.get("/app/main.dart.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip"
    assert r.headers["vary"] == "Accept-Encoding" and r.headers["cache-control"] == "no-cache"
    assert r.content == f.read_bytes()  # httpx распаковал
    assert int(r.headers["content-length"]) < f.stat().st_size / 2
    assert c.get("/app/main.dart.js", headers={"Accept-Encoding": "gzip",
                                               "If-None-Match": r.headers["etag"]}).status_code == 304
    raw = c.get("/app/main.dart.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in raw.headers and raw.content == f.read_bytes()


def test_iphone_draws_at_2x():
    """iPhone 3x → Flutter рисует в 2x: на 56% меньше точек на кадр. Только
    iPhone/iPad и только до запуска Flutter."""
    js = WEB_INDEX.split('<script id="uib-dpr">')[1].split("</script>")[0]
    assert "iPhone|iPod|iPad" in js and 'defineProperty(window, "devicePixelRatio"' in js
    assert "return 2;" in js and "real > 2" in js
    assert WEB_INDEX.index('id="uib-dpr"') < WEB_INDEX.index('src="flutter_bootstrap.js"')
