"""
Проверка initData от Telegram WebApp (Mini App).

Как это работает (кратко, см. официальные доки Telegram Mini Apps):
клиентский SDK (Telegram.WebApp.initData) даёт нам query-string со всеми
полями (user, auth_date, query_id и т.д.) плюс hash — подпись HMAC-SHA256
всех остальных полей, посчитанная Telegram'ом на своей стороне секретным
ключом, который выводится из токена бота. Мы можем пересчитать тот же
HMAC на своей стороне (зная BOT_TOKEN) и сравнить — если совпало, значит
запрос реально пришёл из тг-клиента с этим ботом, а не откуда угодно.

Без этой проверки HTTP API был бы полностью открытым (любой, кто узнает
URL, мог бы дёргать эндпоинты от чужого имени) — а тут групповые данные
(дедлайны, ДЗ), так что проверка обязательна на каждый запрос, не только
на логин.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)

# initData с auth_date старше этого считается протухшим (открыли WebApp давно
# назад и не закрывали вкладку) — просим переоткрыть, чтобы Telegram выдал
# свежий initData. 24 часа с запасом: обычная сессия WebApp живёт часы, не дни.
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


class InitDataError(Exception):
    """initData отсутствует, битая, или не прошла проверку подписи/возраста."""


def _compute_hash(data_check_string: str, bot_token: str) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Возвращает распарсенные поля initData (включая user как dict), либо
    кидает InitDataError с человекочитаемой причиной."""
    if not init_data:
        raise InitDataError("initData отсутствует")
    if not bot_token:
        # Это баг конфигурации сервера, а не клиента — но пользователю всё
        # равно нельзя доверять запрос, раз проверить его нечем.
        raise InitDataError("BOT_TOKEN не настроен на сервере")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("нет hash в initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    expected_hash = _compute_hash(data_check_string, bot_token)

    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("подпись не совпала")

    auth_date = data.get("auth_date")
    if auth_date:
        age = time.time() - int(auth_date)
        if age > MAX_AUTH_AGE_SECONDS:
            raise InitDataError("initData протухла, переоткрой приложение")

    if "user" in data:
        try:
            data["user"] = json.loads(data["user"])
        except (json.JSONDecodeError, TypeError):
            raise InitDataError("не смог распарсить поле user")

    return data
