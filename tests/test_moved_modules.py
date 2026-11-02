"""Переезд в kapibara/ (docs/adr/0003-safe-moves.md): старое имя модуля — тот же
объект, что новое, поэтому импорты, подмены в тестах и состояние модулей
(кэши, замки) не раздваиваются. Переехала тема — допиши её сюда."""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MOVED = {
    "deadline_names": "kapibara.features.deadlines.names",
    "deadline_reminders": "kapibara.features.deadlines.reminders",
    "deadline_soon": "kapibara.features.deadlines.soon",
    "quiz_time": "kapibara.features.deadlines.quiz_time",
    "achievements": "kapibara.features.social.achievements",
    "group_award": "kapibara.features.social.group_award",
    "lesson_comments": "kapibara.features.social.comments",
    "lesson_reactions": "kapibara.features.social.reactions",
    "nick_filter": "kapibara.features.social.nick_filter",
    "teacher_rating": "kapibara.features.social.teacher_rating",
    "ugc": "kapibara.features.social.ugc",
    "xp": "kapibara.features.social.xp",
}


@pytest.mark.parametrize("old,new", MOVED.items())
def test_old_name_is_the_same_module(old, new):
    assert importlib.import_module(old) is importlib.import_module(new)


@pytest.mark.parametrize("old,new", MOVED.items())
def test_patch_through_old_name_reaches_new(old, new, monkeypatch):
    mod = importlib.import_module(new)
    monkeypatch.setattr(f"{old}._moved_probe", 1, raising=False)
    assert mod._moved_probe == 1


@pytest.mark.parametrize("old,new", MOVED.items())
def test_old_name_first_in_fresh_process(old, new):
    """Порядок загрузки не важен: старое имя первым в чистом процессе."""
    code = f"import {old}, {new}, sys; sys.exit(0 if sys.modules['{old}'] is {new} else 1)"
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_old_files_are_only_redirects():
    for old, new in MOVED.items():
        text = (ROOT / f"{old}.py").read_text(encoding="utf-8")
        assert f"import {new} as _m" in text and "sys.modules[__name__] = _m" in text
        assert len(text.splitlines()) <= 8, f"{old}.py — только переадресация, код живёт в {new}"
