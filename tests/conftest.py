"""
Общий конфиг pytest для всего репозитория.

ВАЖНО: BOT_TOKEN/STAROSTA_ID/GROUP_CHAT_ID читаются config.py на уровне
модуля в момент первого импорта — поэтому они выставлены здесь, до того как
любой тестовый файл успеет сделать `import database` / `import config` /
`from handlers...`. os.environ.setdefault — чтобы не перетирать реальные
значения, если тесты вдруг запустят с уже настроенным окружением (CI).
"""
import os
import sys
import pathlib

os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("STAROSTA_ID", "111")
os.environ.setdefault("GROUP_CHAT_ID", "0")
os.environ.setdefault("DATABASE_PATH", "test_default.db")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio

STAROSTA_ID = int(os.environ["STAROSTA_ID"])


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    """Чистая временная SQLite-база на каждый тест — реальная init_db()
    со всеми таблицами и миграциями, не мок. Возвращает сам модуль database,
    чтобы тесты вызывали database.add_deadline(...) и т.д. как в проде."""
    import database
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    await database.init_db()
    return database


@pytest.fixture(autouse=True)
def _no_schedule_network(monkeypatch):
    """Кнопки предметов (/solve, /upload) строятся из расписания группы —
    в тестах без сети: иначе каждый такой тест ходил бы за ical МИРЭА."""
    import schedule_parser

    async def no_subjects(*args, **kwargs):
        return []

    monkeypatch.setattr(schedule_parser, "get_group_subjects", no_subjects)


@pytest.fixture(autouse=True)
def _no_sdo_calendar_network(monkeypatch):
    """Синк дедлайнов СДО сначала идёт в календарь по AJAX; в тестах без
    сети — как будто AJAX недоступен, и работает запасной путь (страница
    «Предстоящие», её тесты подменяют fetch_upcoming_html). Сам календарь —
    tests/test_sdo_calendar.py."""
    import sdo_parser

    async def unavailable():
        return None

    monkeypatch.setattr(sdo_parser, "fetch_calendar_deadlines", unavailable)


@pytest.fixture(autouse=True)
def _fixed_semester(monkeypatch):
    """В тестах метка «[I.26-27]» — нынешний семестр, как в живых данных
    26.09.2026, иначе с февраля 2027 они бы считались прошлым семестром и
    тесты синка СДО упали бы сами собой. Явная дата — по-прежнему своя."""
    from datetime import date
    import sdo_parser
    real = sdo_parser.current_semester_tag
    monkeypatch.setattr(sdo_parser, "current_semester_tag", lambda today=None: real(today or date(2026, 9, 26)))
    # сроки работ ТК (срок прошёл / 15 дней ждём оценку) — от той же даты
    from datetime import datetime
    import sdo_grades
    monkeypatch.setattr(sdo_grades, "_now_msk", lambda: datetime(2026, 9, 26, 12, 0))


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Счётчики ratelimit живут в памяти процесса — между тестами сбрасываем,
    иначе один тест на лимит (21 дедлайн подряд) роняет соседние с 429."""
    import mirea_schedule_api
    import ratelimit
    ratelimit.reset()
    mirea_schedule_api.reset_ical_cache()       # кэш чужих календарей — тоже в памяти процесса
    import gemini_solver
    gemini_solver._primary_rest_until = 0.0     # «основная модель отдыхает» после 429 — между тестами не тащим
    gemini_solver._missing.clear()              # и пропавшие запасные
    spare = gemini_solver.AI_SPARE_MODEL
    gemini_solver.AI_SPARE_MODEL = ""           # запасная через OpenRouter — только где тест её включил
    yield
    gemini_solver.AI_SPARE_MODEL = spare
    ratelimit.reset()
    mirea_schedule_api.reset_ical_cache()
