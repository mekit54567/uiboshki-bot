"""Одна сборка Amvera на мерж (Никита 17.10): deploy.yml ждёт сборки main по
именам — переименовал CHANGELOG или веб-сборку PWA, поправь и тут."""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _name(f):
    return yaml.safe_load((WF / f).read_text())["name"]


def test_deploy_waits_for_real_workflow_names():
    text = (WF / "deploy.yml").read_text()
    for f in ("changelog.yml", "app-web.yml"):
        assert f'.workflowName == "{_name(f)}"' in text


def test_deploy_moves_branch_once_per_merge():
    wf = yaml.safe_load((WF / "deploy.yml").read_text())
    assert wf[True]["push"]["branches"] == ["main"]          # yaml: «on» → True
    assert wf["concurrency"]["cancel-in-progress"] is True
    assert "origin/main:refs/heads/deploy" in (WF / "deploy.yml").read_text()
