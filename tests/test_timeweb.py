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
    monkeypatch.setenv("HOSTING_ORG", "ООО «Облако» (ИНН 123, Санкт-Петербург)")     # старый адрес с сервера
    host = privacy._host()
    # 3 — новый получатель (19.10), 4 — комментарии, оценки и пуши приложения к магазинам (20.10)
    assert host["version"] == "4" and host["policy"] >= host["version"]
    monkeypatch.setattr(privacy, "HOST", host)
    text = str(legal_texts.doc("privacy"))
    # юрлицо и адрес — как в уведомлении в РКН, ЦОД — в Москве (22.10); HOSTING_ORG не перебивает
    assert "Санкт-Петербург" not in text and "Timeweb Cloud" in text
    assert "ОГРН 1227800052215, ИНН 7810945525" in text and "г. Иннополис, ул. Университетская, д. 7, оф. 605" in text
    assert text.count("в Москве (ЦОД IXcellerate, ул. Подольских Курсантов, д. 15Б)") == 2
    assert "Амвера" not in text and "Amvera" not in text
    consent = str(legal_texts.doc("consent"))
    for doc in (text, consent):
        assert "комментарии к парам" in doc and "RuStore" in doc
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


def test_update_writes_build_info(tmp_path):
    """update.sh после reset пишет build-info.json (коммит, PR, время) —
    его показывает /api/meta: видно, что сервер обновился после мержа."""
    import json
    update = (DIR / "update.sh").read_text()
    assert update.index('git reset -q --hard "$NEW"') < update.index("build-info.json") < update.index("up -d --build")
    lines = update.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("PR=$("))
    end = next(i for i, ln in enumerate(lines) if "> build-info.json" in ln)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "Merge pull request #261 from a/b"],
                   cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "CHANGELOG: собраны записи"],
                   cwd=tmp_path, check=True)
    subprocess.run(["sh", "-c", "\n".join(lines[start:end + 1])], cwd=tmp_path, check=True)
    info = json.loads((tmp_path / "build-info.json").read_text())
    assert info["pr"] == 261 and len(info["commit"]) == 7 and info["built"].endswith("Z")
