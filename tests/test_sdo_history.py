"""История баллов СДО: точка в день на предмет, прирост за неделю."""
from datetime import date

import pytest

from kapibara.features.sdo import history as sdo_history


@pytest.fixture
def day(monkeypatch):
    cur = {"d": date(2026, 9, 20)}
    monkeypatch.setattr(sdo_history, "today_msk", lambda: cur["d"])
    return cur


@pytest.mark.asyncio
async def test_points_and_week_delta(db, day):
    for d, s in [(date(2026, 9, 20), 4), (date(2026, 9, 25), 12), (date(2026, 9, 25), 14), (date(2026, 10, 2), 34)]:
        day["d"] = d
        await sdo_history.record(7, [{"id": 1, "score": s}, {"id": 2, "score": 50}])
    h = await sdo_history.series(7, 1)
    assert h["points"] == [["2026-09-20", 4.0], ["2026-09-25", 14.0], ["2026-10-02", 34.0]]   # за день — последняя
    assert h["week_delta"] == 20.0                                                            # 34 − 14 (неделю назад)
    assert (await sdo_history.series(8, 1))["points"] == []                                  # чужая история не видна


@pytest.mark.asyncio
async def test_first_day_no_delta_and_current_appended(db, day):
    h = await sdo_history.series(7, 1, current=10)
    assert h["points"] == [["2026-09-20", 10.0]] and h["week_delta"] is None


def test_chart_in_subject_screen():
    src = open("webapp/static/js/sdo.js", encoding="utf-8").read()
    assert "historyCard(c)" in src and "week_delta" in src
