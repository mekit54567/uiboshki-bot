"""Выкладка (deploy.yml): одна сборка на мерж (Никита 17.10) и только после
зелёного CI (02.11). Ждёт сборки main по именам — переименовал CHANGELOG, веб-
сборку PWA или CI, поправь и тут."""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _text(f):
    return (WF / f).read_text(encoding="utf-8")


def _name(f):
    return yaml.safe_load(_text(f))["name"]


def test_deploy_waits_for_real_workflow_names():
    text = _text("deploy.yml")
    for f in ("changelog.yml", "app-web.yml"):
        assert f'.workflowName == \\"{_name(f)}\\"' in text


def test_deploy_moves_branch_once_per_merge():
    wf = yaml.safe_load(_text("deploy.yml"))
    assert wf["concurrency"]["cancel-in-progress"] is True
    assert "origin/main:refs/heads/deploy" in _text("deploy.yml")


def test_deploy_only_after_green_ci():
    wf = yaml.safe_load(_text("deploy.yml"))
    on = wf[True]                                            # yaml: «on» → True
    assert "push" not in on                                  # не от мержа, а от CI
    assert on["workflow_run"]["workflows"] == [_name("ci.yml")]
    assert on["workflow_run"]["branches"] == ["main"]
    cond = wf["jobs"]["deploy"]["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in cond
    assert "github.event.workflow_run.event == 'push'" in cond


def test_deploy_skips_failed_builds_and_foreign_commits():
    text = _text("deploy.yml")
    assert "--status success" in text                        # ручной запуск — последний зелёный CI
    assert ".headSha ==" in text                             # ждём сборки именно этого мержа
    assert 'select(.conclusion != "success"' in text         # упавший CHANGELOG/PWA — стоп
    assert "github-actions\\[bot\\]" in text                 # чужой коммит — не выкладываем
