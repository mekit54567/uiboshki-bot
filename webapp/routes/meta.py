"""/api/meta — что за сервер и какие версии приложения он ещё принимает
(этап 2: API как контракт). Своё приложение спрашивает это при запуске:
его версия ниже min_client — экран «Обнови приложение» (в магазинах версии
обновляются не мгновенно, как сайт). Без входа."""

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

API_VERSION = 1
BUILD_INFO = Path(__file__).resolve().parents[2] / "build-info.json"   # пишет deploy/timeweb/update.sh
STARTED = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@lru_cache(maxsize=1)
def server_version() -> str:
    """Последняя версия из CHANGELOG.md и changelog.d/ (v5.31.0) — та, что задеплоена."""
    from tools.changelog import full_text
    try:
        text = full_text()
    except OSError:
        return ""
    found = re.findall(r"^### v(\d+\.\d+\.\d+)", text, re.M)
    return max(found, key=lambda v: tuple(int(x) for x in v.split(".")), default="")


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


def _min(platform: str) -> str:
    return os.getenv(f"APP_MIN_{platform.upper()}", "0.0.0")


@router.get("/api/meta")
async def api_meta():
    import config
    import oauth
    return {
        "api": API_VERSION,
        "server": server_version(),
        "build": build_info(),       # commit, pr, built, started — обновилось ли после мержа
        "min_client": {p: _min(p) for p in ("web", "android", "ios")},
        "login": ["telegram", *oauth.available()],   # VK/Яндекс — когда есть ключи
        # design2 — новый дизайн приложения (5.79, «Оформление»): DESIGN2=0 —
        # откат одной переменной, приложение вернётся к прежнему виду без выпуска
        "features": {"groups": True, "sessions": True, "offline": True,
                     "design2": config.design2_on()},
        # ссылки для меню «Ещё» и экрана «Вход в СДО» своего приложения (как APP_CONFIG у WebApp)
        "links": await _links(),
    }


async def _links() -> dict:
    import config
    from webapp.server import _guide_link
    import login_channel
    # news — открытый канал Капибары (LOGIN_CHANNEL) для «Капибара в других местах»
    return {"bot": f"https://t.me/{config.BOT_USERNAME}", "channel": config.CHANNEL_URL or "",
            "contact": config.CONTACT_URL or "", "sdo_guide": await _guide_link(), "news": login_channel.link()}
