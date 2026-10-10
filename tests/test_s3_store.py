"""Бэкап в российское S3 (s3_store.py, backup.send_backup): подпись AWS
Signature V4 по эталону из документации AWS, ключи копий по кругу, старосте
— только отметка, файл базы в Telegram не уходит."""
from datetime import datetime, timezone

import httpx
import pytest

import s3_store


def test_sigv4_matches_aws_example():
    # пример GET Object из документации AWS (Signature Version 4, «Example: GET Object»)
    now = datetime(2013, 5, 24, tzinfo=timezone.utc)
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    headers = {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9",
               "x-amz-content-sha256": empty, "x-amz-date": "20130524T000000Z"}
    auth = s3_store.sign("GET", "https://examplebucket.s3.amazonaws.com/test.txt", headers, empty,
                         "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", now)
    assert auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in auth


def test_backup_keys_rotate():
    assert s3_store.backup_keys(datetime(2026, 10, 5)) == ["daily/uiboshki-1-mon.db.gz"]
    assert s3_store.backup_keys(datetime(2026, 11, 1)) == ["daily/uiboshki-7-sun.db.gz",
                                                          "monthly/uiboshki-2026-11.db.gz"]


@pytest.mark.asyncio
async def test_backup_goes_to_s3_not_telegram(db, monkeypatch):
    import backup
    for k, v in {"BACKUP_S3_BUCKET": "b", "BACKUP_S3_KEY_ID": "id", "BACKUP_S3_SECRET": "sec"}.items():
        monkeypatch.setenv(k, v)
    sent = []

    def handler(request):
        sent.append((request.method, request.url.path, request.headers["authorization"][:16], len(request.content)))
        return httpx.Response(200)

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}))

    class Bot:
        docs, msgs = [], []

        async def send_document(self, *a, **kw):
            self.docs.append(a)

        async def send_message(self, chat_id, text, **kw):
            self.msgs.append(text)

    bot = Bot()
    assert await backup.send_backup(bot, 1)
    assert bot.docs == [] and "в хранилище" in bot.msgs[0]
    assert sent and sent[0][0] == "PUT" and sent[0][1].startswith("/b/daily/") and sent[0][2] == "AWS4-HMAC-SHA256"
    assert sent[0][3] > 100

    sent.clear()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(
        lambda r: httpx.Response(403))}))
    assert not await backup.send_backup(bot, 1)
    assert "не легла" in bot.msgs[-1] and bot.docs == []
