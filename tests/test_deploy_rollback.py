"""Автооткат на сервере (02.11, deploy/timeweb/update.sh): после перезапуска
ждём /ready с новым коммитом; не дождались — коммит в bad, прошлая удачная
сборка обратно, отметка для бота. Гоняем настоящий update.sh: вместо GitHub —
локальный репозиторий, вместо docker — заглушка, которая «отвечает» /ready."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "timeweb" / "update.sh"
pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("flock"),
                                reason="нужны sh и flock, как на сервере")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _commit(repo, msg):
    (repo / "f.txt").write_text(msg)
    subprocess.run([*GIT, "add", "f.txt"], cwd=repo, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", msg], cwd=repo, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def server(tmp_path):
    """/opt/kapibara в миниатюре: origin (ветка deploy), app (клон), data, bin/docker."""
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "deploy"], cwd=origin, check=True)
    first = _commit(origin, "Merge pull request #1 from a/b")
    root = tmp_path / "kap"
    (root / "data").mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "-b", "deploy", str(origin), str(root / "app")], check=True)
    deploy = root / "app" / "deploy" / "timeweb"
    deploy.mkdir(parents=True)
    shutil.copy(SCRIPT, deploy / "update.sh")
    (root / "deployed").write_text(first + "\n")
    # docker: exec (проверка /ready) успешен, только если коммит сборки есть в ready-ok
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f'  *" exec "*) want=$(git -C {root / "app"} rev-parse --short=7 HEAD); '
        f'grep -qx "$want" {tmp_path / "ready-ok"} 2>/dev/null ;;\n'
        '  *) exit 0 ;;\nesac\n')
    (bin_ / "docker").chmod(0o755)
    (tmp_path / "ready-ok").write_text("")

    def run(*args):
        env = {"PATH": f"{bin_}:/usr/bin:/bin", "KAP_ROOT": str(root), "READY_WAIT": "5", "HOME": str(tmp_path)}
        return subprocess.run(["sh", str(deploy / "update.sh"), *args], env=env,
                              capture_output=True, text=True)

    def ready(sha):
        with open(tmp_path / "ready-ok", "a") as f:
            f.write(sha[:7] + "\n")

    return {"origin": origin, "root": root, "run": run, "ready": ready, "first": first}


def _head(root):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root / "app", check=True,
                          capture_output=True, text=True).stdout.strip()


def test_good_build_is_marked_deployed(server):
    new = _commit(server["origin"], "Merge pull request #2 from a/b")
    server["ready"](new)
    r = server["run"]()
    assert r.returncode == 0, r.stderr
    assert (server["root"] / "deployed").read_text().strip() == new
    assert not (server["root"] / "bad").exists()


def test_bad_build_rolls_back_and_is_not_retried(server):
    server["ready"](server["first"])                     # прошлая сборка поднимается
    bad = _commit(server["origin"], "Merge pull request #3 from a/b")
    r = server["run"]()
    assert r.returncode == 1
    root = server["root"]
    assert (root / "bad").read_text().strip() == bad
    assert (root / "deployed").read_text().strip() == server["first"]    # удачной осталась прошлая
    assert _head(root) == server["first"]                                # и код — прошлый
    assert (root / "data" / "rollback.txt").read_text().split() == [bad[:7], server["first"][:7]]
    assert '"commit": "{}"'.format(server["first"][:7]) in (root / "app" / "build-info.json").read_text()
    # следующая минута таймера: тот же коммит не пробуем
    assert server["run"]().returncode == 0
    assert _head(root) == server["first"]
    # а новый мерж — пробуем
    fixed = _commit(server["origin"], "Merge pull request #4 from a/b")
    server["ready"](fixed)
    assert server["run"]().returncode == 0
    assert (root / "deployed").read_text().strip() == fixed
    assert not (root / "bad").exists()


def test_script_stays_under_shell_read_buffer():
    # sh читает файл целиком только до 8 КБ, а git reset меняет его на ходу
    assert SCRIPT.stat().st_size < 8000


async def test_bot_tells_starosta_about_rollback(db, monkeypatch, tmp_path):
    import bot
    import database
    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))

    monkeypatch.setattr(bot, "STAROSTA_ID", 42)
    (tmp_path / "rollback.txt").write_text("abc1234 def5678\n")
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    await bot.notify_rollback(FakeBot())
    assert sent and sent[0][0] == 42 and "abc1234" in sent[0][1] and "def5678" in sent[0][1]
    assert not (tmp_path / "rollback.txt").exists()
    await bot.notify_rollback(FakeBot())                 # отметки нет — молчим
    assert len(sent) == 1
