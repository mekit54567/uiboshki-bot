"""ADR 0004: узкие except вместо широких. Ожидаемый сбой (сеть, битый
календарь) — как раньше: пусто или «не вышло». Баг — в лог с traceback
(aside / log_failure), а не тихо, как при прежнем `except Exception`."""
import logging

import httpx
import pytest

from kapibara.features.notifications import broadcast


@pytest.mark.asyncio
async def test_group_raws_network_failure_is_quiet_line(caplog):
    async def down():
        raise httpx.ConnectError("нет сети")

    get = await broadcast.group_raws(down)
    with caplog.at_level(logging.ERROR):
        assert await get(None) == (None, None)
    rec = [r for r in caplog.records if "Рассылка" in r.getMessage()]
    assert rec and rec[0].exc_info is None          # чужой сервис — строкой, без traceback


@pytest.mark.asyncio
async def test_group_raws_bug_logged_with_traceback(caplog):
    async def buggy():
        raise KeyError("баг у нас")

    get = await broadcast.group_raws(buggy)
    with caplog.at_level(logging.WARNING):
        assert await get(None) == (None, None)      # рассылка остальным не встаёт
    rec = [r for r in caplog.records if "Рассылка" in r.getMessage()]
    assert rec and rec[0].exc_info is not None      # баг видно в /status


@pytest.mark.asyncio
async def test_can_rate_false_when_calendar_down(monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser
    from kapibara.features.social import teacher_rating

    async def down(user_id):
        raise httpx.ReadTimeout("МИРЭА молчит")

    monkeypatch.setattr(schedule_parser, "raw_for_user", down)
    assert await teacher_rating.can_rate(1, "Иванов И. И.") is False


@pytest.mark.asyncio
async def test_can_rate_bug_is_not_hidden(monkeypatch):
    from kapibara.features.schedule import parser as schedule_parser
    from kapibara.features.social import teacher_rating

    async def buggy(user_id):
        raise KeyError("баг")

    monkeypatch.setattr(schedule_parser, "raw_for_user", buggy)
    with pytest.raises(KeyError):                   # раньше — тихое False
        await teacher_rating.can_rate(1, "Иванов И. И.")


def test_build_info_without_file(monkeypatch, tmp_path):
    from kapibara.ops import build
    monkeypatch.setattr(build, "BUILD_INFO", tmp_path / "нет.json")
    build_info = getattr(build.build_info, "__wrapped__", build.build_info)
    assert build_info()["commit"] == ""
