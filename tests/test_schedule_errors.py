"""Ошибки расписания (ADR 0004): не загрузилось — строка человеку и строка
в лог; баг в разборе — та же строка человеку, но в лог с traceback."""
import logging
from datetime import date

import pytest

from kapibara.features.schedule import parser


@pytest.mark.asyncio
async def test_other_group_not_loaded_is_text_not_crash(monkeypatch):
    from kapibara.features.schedule import mirea_api

    async def nothing(*a, **k):
        return None
    monkeypatch.setattr(parser, "_other_group", lambda gid: bool(gid))
    monkeypatch.setattr(mirea_api, "fetch_ical", nothing)
    # раньше get_date_schedule ловил только сеть — RuntimeError чужой группы летел в инлайн
    assert (await parser.get_date_schedule(date(2026, 10, 5), group_id=777)).startswith("⚠️")
    assert (await parser.get_today_schedule(group_id=777)).startswith("⚠️")


@pytest.mark.asyncio
async def test_network_one_line_bug_with_traceback(monkeypatch, caplog):
    async def down(*a, **k):
        raise TimeoutError("зеркало молчит")
    monkeypatch.setattr(parser, "_raw", down)
    with caplog.at_level(logging.WARNING, logger=parser.logger.name):
        assert (await parser.get_week_schedule()).startswith("⚠️")
    assert caplog.records[-1].exc_info is None

    async def ok(*a, **k):
        return b"BEGIN:VCALENDAR"

    def broken(*a, **k):
        raise KeyError("time_start")
    monkeypatch.setattr(parser, "_raw", ok)
    monkeypatch.setattr(parser, "parse_events_for_date", broken)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=parser.logger.name):
        assert (await parser.get_next_lesson()).startswith("⚠️")
    assert caplog.records[-1].exc_info is not None
