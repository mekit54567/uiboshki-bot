"""Границы экранов СДО (ADR 0004): одна на все запросы и одна на
необязательные шаги — человеку понятный код, баг в лог с traceback."""
import logging

import httpx
import pytest
from fastapi import HTTPException

from webapp.routes import sdo


async def _raise(e):
    raise e


@pytest.mark.asyncio
async def test_from_sdo_codes(db):
    from kapibara.features.sdo.parser import SdoSessionExpired
    for exc, code in [(LookupError(), 404), (SdoSessionExpired("кука"), 403),
                      (httpx.ConnectError("нет"), 502), (KeyError("баг"), 502)]:
        with pytest.raises(HTTPException) as e:
            await sdo._from_sdo(1, "проба", _raise(exc))
        assert e.value.status_code == code
    assert await sdo._from_sdo(1, "проба", _ok()) == {"ok": 1}


async def _ok():
    return {"ok": 1}


@pytest.mark.asyncio
async def test_aside_keeps_screen_and_shows_bug(caplog):
    with caplog.at_level(logging.WARNING, logger=sdo.logger.name):
        assert await sdo._aside("история", lambda: _raise(KeyError("score")), sdo._NO) is sdo._NO
    assert caplog.records[-1].exc_info is not None           # баг — с traceback (раньше info одной строкой)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=sdo.logger.name):
        assert await sdo._aside("история", lambda: _raise(httpx.ReadTimeout("долго"))) is None
    assert caplog.records[-1].exc_info is None               # сеть — строкой
    assert await sdo._aside("история", _ok) == {"ok": 1}
