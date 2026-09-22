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
