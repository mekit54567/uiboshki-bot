"""
webapp.auth.validate_init_data: реальная HMAC-подпись (та же схема, что
считает клиент Telegram WebApp), не мок. Без этой проверки любой человек,
узнавший URL, мог бы дёргать API от чужого имени.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from webapp.auth import InitDataError, validate_init_data

BOT_TOKEN = "123456:TEST-TOKEN-NOT-REAL-AAAAAAAAAAAAAAAAAAA"


def _make_init_data(bot_token=BOT_TOKEN, auth_date=None, user=None, tamper=False):
    fields = {
        "query_id": "AAEbc123",
        "user": json.dumps(user or {"id": 222, "first_name": "Alice"}, ensure_ascii=False),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        computed_hash = "0" * 64
    fields["hash"] = computed_hash
    return urlencode(fields)


def test_valid_init_data_accepted():
    init_data = _make_init_data()
    result = validate_init_data(init_data, BOT_TOKEN)
    assert result["user"]["id"] == 222


def test_tampered_hash_rejected():
    init_data = _make_init_data(tamper=True)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    init_data = _make_init_data(bot_token=BOT_TOKEN)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, "999999:SOME-OTHER-TOKEN-XXXXXXXXXXXXXXXXXXXX")


def test_expired_auth_date_rejected():
    old = int(time.time()) - 25 * 60 * 60  # старше MAX_AUTH_AGE_SECONDS (24ч)
    init_data = _make_init_data(auth_date=old)
    with pytest.raises(InitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_empty_init_data_rejected():
    with pytest.raises(InitDataError):
        validate_init_data("", BOT_TOKEN)


def test_missing_bot_token_configured_rejected():
    init_data = _make_init_data()
    with pytest.raises(InitDataError):
        validate_init_data(init_data, "")
