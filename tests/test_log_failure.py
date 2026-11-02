"""kapibara.core.errors.log_failure (02.11): сбой чужого сервиса — строкой,
баг у нас — с traceback (раньше оба выглядели как «СДО не отвечает»)."""
import logging

import httpx

from kapibara.core.errors import log_failure

log = logging.getLogger("test.log_failure")


def _record(caplog, e, **kw):
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="test.log_failure"):
        try:
            raise e
        except Exception as err:
            log_failure(log, "Баллы СДО", err, **kw)
    [rec] = caplog.records
    return rec


def test_network_failure_is_one_line(caplog):
    rec = _record(caplog, httpx.ConnectTimeout("timed out"))
    assert rec.getMessage() == "Баллы СДО: ConnectTimeout: timed out" and not rec.exc_info


def test_our_bug_has_traceback(caplog):
    rec = _record(caplog, KeyError("marks"))
    assert "KeyError" in rec.getMessage() and rec.exc_info


def test_expected_service_error_is_one_line(caplog):
    class GeminiError(RuntimeError):
        pass
    rec = _record(caplog, GeminiError("лимит"), expected=(GeminiError,))
    assert not rec.exc_info
