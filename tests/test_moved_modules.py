"""Переезд в kapibara/ (docs/adr/0001, 0003) закончен 02.11: импорты переписаны
(tools/rewrite_imports.py), переадресаций в корне нет. MOVED — где теперь
живёт каждый бывший модуль корня (справка для старых веток и документации);
тесты ниже следят, что переезд ничего не потерял: разделы /status и файлы
данных."""
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
    "file_categories": "kapibara.core.categories",
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
    "review_demo": "webapp.review_demo",
    "config": "kapibara.core.config",
    "utils": "kapibara.core.utils",
    "translit": "kapibara.core.translit",
    "timing": "kapibara.core.timing",
    "locks": "kapibara.core.locks",
    "ratelimit": "kapibara.core.ratelimit",
    "net": "kapibara.core.net",
    "health": "kapibara.ops.health",
    "backup": "kapibara.ops.backup",
    "s3_store": "kapibara.ops.s3_store",
    "net_check": "kapibara.ops.net_check",
    "stats": "kapibara.ops.stats",
    "middleware": "kapibara.bot.middleware",
    "keyboards": "kapibara.bot.keyboards",
    "long_messages": "kapibara.bot.long_messages",
    "intent_router": "kapibara.bot.intent_router",
    "scheduler": "kapibara.jobs.scheduler",
}


AREAS_BEFORE = {"lecture_summary": "ИИ", "ai_solver": "ИИ", "gemini_solver": "ИИ", "sdo_parser": "СДО",
                "sdo_grades": "СДО", "grade_alerts": "СДО", "schedule_parser": "Расписание",
                "mirea_schedule_api": "Расписание", "backup": "Бэкап"}


@pytest.mark.parametrize("old", AREAS_BEFORE)
def test_status_area_survives_the_move(old):
    """Раздел ошибок в /status (health.AREAS) — по имени логгера, то есть по
    пути модуля: после переезда «ИИ» не должен стать «Прочим»."""
    from kapibara.ops import health
    assert health.area_of(MOVED[old]) == AREAS_BEFORE[old]


def test_root_has_only_entry_point():
    """Переезд закончен (02.11): в корне из кода только точка входа."""
    assert sorted(p.name for p in ROOT.glob("*.py")) == ["bot.py"]


def test_data_files_found_from_project_root():
    """Файлы данных — от корня проекта (kapibara/core/paths.py), а не от файла
    модуля: после переезда Пульс по-прежнему видит pulse_lab_kit/."""
    import os

    from kapibara.features.pulse import lab as pulse_lab
    from kapibara.core.paths import ROOT
    assert (ROOT / "bot.py").is_file()
    assert os.path.isfile(os.path.join(pulse_lab.KIT_DIR, "hook.js"))      # kit.json — необязательный


def test_schedule_card_finds_fonts():
    from kapibara.features.schedule import card as schedule_card
    assert schedule_card.FONTS.is_dir() and any(schedule_card.FONTS.iterdir())


def test_content_data_found_from_project_root():
    from kapibara.features.content import channel_posts
    from webapp import review_demo
    from kapibara.features.content import roadmap
    assert channel_posts.POSTS_DIR.is_dir()
    assert roadmap.PATH.is_file() and review_demo.FIXTURES.is_file()


def test_stats_card_finds_fonts():
    from kapibara.ops import stats
    assert stats.FONTS.is_dir()


def test_moved_helpers_are_the_same_objects():
    """03.11: функции, которые нижние слои брали сверху (handlers, jobs, webapp,
    bot), переехали вниз; на старом месте — тот же объект, а не копия."""
    import handlers.deadlines
    import handlers.files_upload
    from kapibara.bot import intent_router
    from kapibara.features.ai import intent
    from kapibara.features.deadlines import labels
    from kapibara.features.lectures import names
    from kapibara.features.notifications import broadcast
    from kapibara.jobs import scheduler
    from kapibara.ops import build
    from webapp.routes import meta
    assert handlers.deadlines.due_label is labels.due_label
    assert handlers.files_upload.title_from_filename is names.title_from_filename
    assert intent_router.classify_intent is intent.classify_intent
    assert intent_router.SYSTEM_PROMPT is intent.SYSTEM_PROMPT
    assert scheduler.pace is broadcast.pace
    assert meta.build_info is build.build_info


def test_cycle_split_keeps_old_names_cycles_2():
    """03.11, клубок импортов: общие куски переехали в новые модули, на старом
    месте — тот же объект (снаружи ничего не поменялось)."""
    import handlers.start
    from kapibara.bot import optional
    from webapp import pages, server
    from webapp.routes import site
    assert handlers.start.ask_optional is optional.ask_optional
    assert server.STATIC_DIR is pages.STATIC_DIR and server.FLUTTER_DIR is pages.FLUTTER_DIR
    assert server._guide_link is pages.guide_link and server._digest is pages.digest
    assert site.og_meta is pages.og_meta
