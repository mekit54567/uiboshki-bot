"""Какая сборка сервера работает: коммит, PR, время сборки и запуска
(/api/meta и шапка /status). Переехало из webapp/routes/meta.py (03.11):
/status (ops/health) брал это из веб-слоя, и импорт снизу вверх сцеплял
модули в клубок."""
import json
import time
from functools import lru_cache
from pathlib import Path

BUILD_INFO = Path(__file__).resolve().parents[2] / "build-info.json"   # пишет deploy/timeweb/update.sh
STARTED = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@lru_cache(maxsize=1)
def build_info() -> dict:
    """Какая сборка работает (Никита 23.10: версия теперь раз в ~10 PR, а
    видеть, что сервер обновился, нужно после каждого мержа): короткий хеш
    коммита, номер последнего смерженного PR, когда собрано и запущено."""
    info = {"commit": "", "commit_time": "", "pr": None, "built": ""}
    try:
        data = json.loads(BUILD_INFO.read_text(encoding="utf-8"))
        info.update({k: data[k] for k in info if k in data})
    except (OSError, ValueError):
        pass
    return {**info, "started": STARTED}
