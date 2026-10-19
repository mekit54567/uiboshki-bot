"""Переезд на свой сервер Timeweb Cloud (19.10: Amvera час висела на запуске
контейнера): docker compose с Caddy, автообновление из ветки, перенос базы
из S3, хостинг в текстах политики — из переменной HOSTING."""
import gzip
import os
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

DIR = Path(__file__).resolve().parent.parent / "deploy" / "timeweb"


def test_compose_runs_bot_from_repo_with_db_on_local_disk():
    c = yaml.safe_load((DIR / "docker-compose.yml").read_text())
    bot = c["services"]["bot"]
    assert bot["build"] == "../.." and (DIR / "../../Dockerfile").resolve().exists()
    assert bot["environment"]["HOSTING"] == "timeweb"
    assert bot["environment"]["DATABASE_PATH"].startswith("/data/")
    assert "/opt/kapibara/data:/data" in bot["volumes"]
    assert bot["env_file"] == "/opt/kapibara/.env"
    assert set(c["services"]["caddy"]["ports"]) == {"80:80", "443:443"}


def test_caddy_serves_domain_and_only_meta_by_ip():
    text = (DIR / "Caddyfile").read_text()
    assert "www.uiboshki.ru {" in text and "reverse_proxy bot:8080" in text
    by_ip = text.split("http:// {", 1)[1]
    assert "handle /api/meta" in by_ip and "respond" in by_ip      # по IP — только проверка, без входа


def test_scripts_are_valid_shell():
    for name in ("setup.sh", "update.sh", "kap"):
        subprocess.run(["sh", "-n", str(DIR / name)], check=True)
    setup = (DIR / "setup.sh").read_text()
    assert '[ ! -f "$ROOT/.env" ]' in setup                  # повторный запуск не затирает переменные
    assert "dockerhub.timeweb.cloud" in setup
    update = (DIR / "update.sh").read_text()
    assert "/opt/kapibara/branch" in update
    # «уже обновлено» — по отметке удачного запуска, а не по HEAD: упавшая сборка повторится
    assert '"$(git rev-parse HEAD)"' not in update
    assert update.index("up -d --build") < update.index('echo "$NEW" > "$DONE"')
    assert update.index("flock -w") < update.index("git fetch -q")            # руками и по таймеру — не вместе
    timer = (DIR / "kapibara-update.timer").read_text()
    assert "OnUnitActiveSec=1min" in timer


def test_env_example_has_no_empty_optional_values():
    # «ИМЯ=» без значения — это «задано пустым»: BOT_USERNAME= сломал бы ссылки t.me/
    required = {"BOT_TOKEN", "STAROSTA_ID"}
    for line in (DIR / "env.example").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        assert value or name in required, line


def test_privacy_names_hosting_from_env(monkeypatch):
    import legal_texts
    import privacy
    assert privacy.VERSION == "2" and privacy.HOST["name"] == "Amvera"     # без HOSTING — как было
    monkeypatch.setenv("HOSTING", "timeweb")
    monkeypatch.setenv("HOSTING_ORG", "ООО «Облако» (ИНН 123, Санкт-Петербург)")
    host = privacy._host()
    assert host["version"] == "3" and host["policy"] >= host["version"]   # новый получатель — согласие заново
    monkeypatch.setattr(privacy, "HOST", host)
    text = str(legal_texts.doc("privacy"))
    assert "ООО «Облако» (ИНН 123, Санкт-Петербург)" in text and "Timeweb Cloud" in text
    assert "Амвера" not in text and "Amvera" not in text
    assert "HOSTING_ORG" not in privacy.operator_missing()
    monkeypatch.setattr(privacy, "HOST", {**host, "org": host["name"]})
    assert "HOSTING_ORG" in privacy.operator_missing()                     # /status напомнит юрлицо


@pytest.mark.asyncio
async def test_s3_restore_puts_backup_into_empty_db(db, tmp_path, monkeypatch):
    import database
    from tools import s3_restore
    await database.upsert_user(5, "Никита", "partykq")
    src = sqlite3.connect(database.DATABASE_PATH)
    dst = sqlite3.connect(tmp_path / "copy.db")
    src.backup(dst)
    src.close()
    dst.close()
    raw = gzip.compress((tmp_path / "copy.db").read_bytes())
    for k, v in {"BACKUP_S3_BUCKET": "b", "BACKUP_S3_KEY_ID": "id", "BACKUP_S3_SECRET": "sec"}.items():
        monkeypatch.setenv(k, v)
    asked = []

    def handler(request):
        asked.append((request.method, request.url.path, request.headers["authorization"][:16]))
        return httpx.Response(200, content=raw)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}))

    with pytest.raises(SystemExit, match="уже есть люди"):          # живую базу не затираем
        await s3_restore.restore("daily/x.db.gz")
    assert asked == []

    new = str(tmp_path / "new" / "mirea_bot.db")
    monkeypatch.setattr(database, "DATABASE_PATH", new)
    out = await s3_restore.restore("daily/x.db.gz")
    assert asked == [("GET", "/b/daily/x.db.gz", "AWS4-HMAC-SHA256")]
    assert "людей 1" in out and os.path.exists(new) and s3_restore.people(new) == 1

    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "other.db"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(
        lambda r: httpx.Response(404))}))
    with pytest.raises(SystemExit, match="HTTP 404"):
        await s3_restore.restore("daily/x.db.gz")
