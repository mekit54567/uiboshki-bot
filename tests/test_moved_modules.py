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
    "file_categories": "kapibara.features.lectures.categories",
    "file_names": "kapibara.features.lectures.names",
    "file_request": "kapibara.features.lectures.request",
    "file_text": "kapibara.features.lectures.text",
    "lecture_day": "kapibara.features.lectures.day",
    "lecture_picker": "kapibara.features.lectures.picker",
    "lecture_summary": "kapibara.features.lectures.summary",
    "lecture_topic": "kapibara.features.lectures.topic",
    "pulse_accounts": "kapibara.features.pulse.accounts",
    "pulse_attendance": "kapibara.features.pulse.attendance",
    "pulse_check": "kapibara.features.pulse.check",
    "pulse_lab": "kapibara.features.pulse.lab",
    "pulse_probe": "kapibara.features.pulse.probe",
    "billing": "kapibara.features.billing.billing",
    "plans": "kapibara.features.billing.plans",
    "plus_grant": "kapibara.features.billing.grants",
    "plus_welcome": "kapibara.features.billing.welcome",
    "referrals": "kapibara.features.billing.referrals",
    "schedule_card": "kapibara.features.schedule.card",
    "schedule_diff": "kapibara.features.schedule.diff",
    "schedule_events": "kapibara.features.schedule.events",
    "schedule_format": "kapibara.features.schedule.format",
    "schedule_index": "kapibara.features.schedule.index",
    "schedule_parser": "kapibara.features.schedule.parser",
    "mirea_schedule_api": "kapibara.features.schedule.mirea_api",
    "attendance": "kapibara.features.schedule.attendance",
    "sdo_accounts": "kapibara.features.sdo.accounts",
    "sdo_check": "kapibara.features.sdo.check",
    "sdo_done": "kapibara.features.sdo.done",
    "sdo_files": "kapibara.features.sdo.files",
    "sdo_goal": "kapibara.features.sdo.goal",
    "sdo_grades": "kapibara.features.sdo.grades",
    "sdo_history": "kapibara.features.sdo.history",
    "sdo_net": "kapibara.features.sdo.net",
    "sdo_parser": "kapibara.features.sdo.parser",
    "sdo_submit": "kapibara.features.sdo.submit",
    "ai_bench": "kapibara.features.ai.bench",
    "ai_quota": "kapibara.features.ai.quota",
    "ai_solver": "kapibara.features.ai.solver",
    "gemini_solver": "kapibara.features.ai.gemini",
    "think": "kapibara.features.ai.think",
    "embedder": "kapibara.features.ai.embedder",
    "embed_bench": "kapibara.features.ai.embed_bench",
    "local_embed": "kapibara.features.ai.local_embed",
    "semantic_index": "kapibara.features.ai.semantic_index",
    "semantic_search": "kapibara.features.ai.semantic_search",
    "day_summary": "kapibara.features.notifications.day_summary",
    "evening_digest": "kapibara.features.notifications.evening_digest",
    "weekly_digest": "kapibara.features.notifications.weekly_digest",
    "grade_alerts": "kapibara.features.notifications.grade_alerts",
    "new_tasks": "kapibara.features.notifications.new_tasks",
    "quiz_alerts": "kapibara.features.notifications.quiz_alerts",
    "notify_prefs": "kapibara.features.notifications.prefs",
    "delivery": "kapibara.features.notifications.delivery",
    "webpush": "kapibara.features.notifications.webpush",
    "app_push": "kapibara.features.notifications.app_push",
    "push_text": "kapibara.features.notifications.push_text",
    "groups": "kapibara.features.groups.groups",
    "institutes": "kapibara.features.groups.institutes",
    "group_context": "kapibara.features.groups.context",
    "group_sync": "kapibara.features.groups.sync",
    "members": "kapibara.features.groups.members",
    "optional_subjects": "kapibara.features.groups.optional_subjects",
    "apple_signin": "kapibara.features.identity.apple",
    "oauth": "kapibara.features.identity.oauth",
    "login_channel": "kapibara.features.identity.login_channel",
    "privacy": "kapibara.features.privacy.privacy",
    "legal_texts": "kapibara.features.privacy.legal_texts",
    "offer_text": "kapibara.features.privacy.offer_text",
    "channel_posts": "kapibara.features.content.channel_posts",
    "roadmap": "kapibara.features.content.roadmap",
    "review_demo": "kapibara.features.content.review_demo",
    "config": "kapibara.core.config",
    "utils": "kapibara.core.utils",
    "translit": "kapibara.core.translit",
    "timing": "kapibara.core.timing",
    "locks": "kapibara.core.locks",
    "ratelimit": "kapibara.core.ratelimit",
    "net": "kapibara.core.net",
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


def test_nobody_holds_the_redirect_itself():
    """Если модули импортируют друг друга по кругу на верхнем уровне, кто-то мог
    бы получить сам файл-переадресацию (пустой) вместо модуля. Поднимаем всё
    приложение в чистом процессе и ищем такие ссылки."""
    code = (
        "import sys, types, bot, webapp.server\n"
        f"moved = {sorted(MOVED)!r}\n"
        "bad = [f'{n}.{k} -> {v.__name__}' for n, m in list(sys.modules.items()) if m\n"
        "       for k, v in list(vars(m).items()) if isinstance(v, types.ModuleType) and v.__name__ in moved]\n"
        "print(bad); sys.exit(1 if bad else 0)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr[-2000:]


@pytest.mark.parametrize("old,new", MOVED.items())
def test_status_area_survives_the_move(old, new):
    """Раздел ошибок в /status (health.AREAS) — по имени логгера, то есть по
    пути модуля: после переезда «ИИ» не должен стать «Прочим»."""
    import health
    if health.area_of(old) != "Прочее":                 # из «Прочего» в свой раздел — можно
        assert health.area_of(new) == health.area_of(old)


def test_data_files_found_from_project_root():
    """Файлы данных — от корня проекта (kapibara/core/paths.py), а не от файла
    модуля: после переезда Пульс по-прежнему видит pulse_lab_kit/."""
    import os

    import pulse_lab
    from kapibara.core.paths import ROOT
    assert (ROOT / "bot.py").is_file()
    assert os.path.isfile(os.path.join(pulse_lab.KIT_DIR, "hook.js"))      # kit.json — необязательный


def test_schedule_card_finds_fonts():
    import schedule_card
    assert schedule_card.FONTS.is_dir() and any(schedule_card.FONTS.iterdir())


def test_content_data_found_from_project_root():
    import channel_posts
    import review_demo
    import roadmap
    assert channel_posts.POSTS_DIR.is_dir()
    assert roadmap.PATH.is_file() and review_demo.FIXTURES.is_file()
