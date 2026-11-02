"""«Итоги дня» на прошедших днях недели: сданное по МСК и прирост баллов СДО."""
import json
from datetime import date, timedelta

import pytest

from kapibara.features.notifications import day_summary
from kapibara.features.sdo import history as sdo_history
from tests.test_webapp_home import _ical, client  # noqa: F401 — фикстура клиента WebApp

D = date(2026, 9, 26)


async def _done_at(db, did: int, user_id: int, at: str):
    from database._conn import connect
    async with connect() as c:
        await c.execute("INSERT INTO deadline_done (deadline_id, user_id, done_at) VALUES (?, ?, ?)", (did, user_id, at))
        await c.commit()


@pytest.mark.asyncio
async def test_done_by_moscow_day(db):
    late = await db.add_deadline("Практика 2 · Анализ данных", "", "2026-09-27", "23:59", 0)
    early = await db.add_deadline("Лабораторная 3", "", "2026-09-27", "23:59", 0)
    other = await db.add_deadline("Тест 1", "", "2026-09-27", "23:59", 0)
    await _done_at(db, late, 7, "2026-09-25 22:30:00")    # 01:30 26.09 по Москве
    await _done_at(db, early, 7, "2026-09-26 20:59:00")   # 23:59 26.09
    await _done_at(db, other, 7, "2026-09-26 21:00:00")   # уже 27.09
    await _done_at(db, other, 8, "2026-09-26 10:00:00")   # чужое
    s = await day_summary.summary(7, D)
    assert [x["title"] for x in s["done"]] == ["Практика 2 · Анализ данных", "Лабораторная 3"]
    assert s["grades"] == [] and s["points"] == 0
    assert [x["title"] for x in (await day_summary.summary(7, D + timedelta(days=1)))["done"]] == ["Тест 1"]


@pytest.mark.asyncio
async def test_own_title_and_hidden(db):
    a = await db.add_deadline("ПР 1", "", "2026-09-27", "", 0)
    b = await db.add_deadline("ПР 2", "", "2026-09-27", "", 0)
    await db.set_deadline_mine(7, a, "Моя практика", "", "2026-09-27", "")
    await db.hide_deadline_for(7, b)
    for did in (a, b):
        await _done_at(db, did, 7, "2026-09-26 09:00:00")
    assert (await day_summary.summary(7, D))["done"] == [{"title": "Моя практика", "task": "Моя практика", "course": ""}]


@pytest.mark.asyncio
async def test_clean_names_from_raw_sdo(db, monkeypatch):
    """Никита 12.10: в сводке «Практическое задание 1 - срок сдачи (Моделирование
    бизнес-процессов_Зачет (часть 1/2) [I.26-27])» — сырые названия СДО."""
    raw = ("Практическое задание 1 - срок сдачи "
           "(Моделирование бизнес-процессов_Зачет (часть 1/2) [I.26-27])")
    a = await db.add_deadline(raw, "", "2026-09-27", "23:59", 0)
    b = await db.add_deadline("Практика 2 · Анализ данных (Экз)", "", "2026-09-27", "23:59", 0)
    for did in (a, b):
        await _done_at(db, did, 7, "2026-09-26 09:00:00")
    await db.save_score_points(7, "2026-09-25", {11: 10.0})
    await db.save_score_points(7, "2026-09-26", {11: 15.0})
    await db.set_setting(day_summary.NAMES_KEY, json.dumps(
        {"11": "Основы предпринимательской деятельности_Зачет (часть 1/1) [I.26-27]"}, ensure_ascii=False))
    s = await day_summary.summary(7, D)
    assert s["done"] == [
        {"title": "Практика 1 · Моделирование бизнес-процессов (Зач)", "task": "Практика 1",
         "course": "Моделирование бизнес-процессов"},
        {"title": "Практика 2 · Анализ данных (Экз)", "task": "Практика 2", "course": "Анализ данных"},
    ]
    assert s["grades"] == [{"name": "Основы предпринимательской деятельности", "delta": 5.0}]


@pytest.mark.asyncio
async def test_grades_delta_and_names(db, monkeypatch):
    cur = {"d": date(2026, 9, 20)}
    monkeypatch.setattr(sdo_history, "today_msk", lambda: cur["d"])
    await sdo_history.record(7, [{"id": 1, "name": "Анализ данных [II.25-26]", "title": "Анализ данных", "score": 10},
                                 {"id": 2, "name": "Архитектура", "title": "Архитектура", "score": 30}])
    cur["d"] = D
    await sdo_history.record(7, [{"id": 1, "score": 16}, {"id": 2, "score": 28}, {"id": 3, "score": 5},
                                 {"id": 4, "name": "Право", "score": 9}])
    s = await day_summary.summary(7, D)
    # курс 3 — первая точка (прироста не знаем), 4 — тоже; минус показываем честно
    assert s["grades"] == [{"name": "Анализ данных", "delta": 6.0}, {"name": "Архитектура", "delta": -2.0}]
    assert s["points"] == 4.0 and s["done"] == []
    names = json.loads(await db.get_setting(day_summary.NAMES_KEY))
    assert names == {"1": "Анализ данных", "2": "Архитектура", "4": "Право"}   # дописываются, не затираются


@pytest.mark.asyncio
async def test_small_change_unknown_name_and_empty_day(db):
    await db.save_score_points(7, "2026-09-25", {5: 10.0, 6: 3.0})
    await db.save_score_points(7, "2026-09-26", {5: 10.02, 6: 4.0})
    s = await day_summary.summary(7, D)
    assert s["grades"] == [{"name": "Предмет", "delta": 1.0}]
    assert await day_summary.summary(7, date(2026, 9, 24)) is None
    assert await day_summary.summary(8, D) is None


@pytest.mark.asyncio
async def test_api_day_summary_past_only(db, client, monkeypatch):  # noqa: F811
    from kapibara.features.schedule import parser as schedule_parser
    from kapibara.core.utils import today_msk
    today = today_msk()

    async def raw():
        return _ical(today)

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    past = today - timedelta(days=2)
    did = await db.add_deadline("Лабораторная 3", "", past.isoformat(), "", 0)
    await _done_at(db, did, 222, f"{past.isoformat()} 09:00:00")
    c, headers = client
    data = c.get("/api/day", params={"date": past.isoformat()}, headers=headers).json()
    assert data["summary"] == {"done": [{"title": "Лабораторная 3", "task": "Лабораторная 3", "course": ""}],
                               "grades": [], "points": 0}
    data = c.get("/api/day", params={"date": (past - timedelta(days=1)).isoformat()}, headers=headers).json()
    assert "summary" in data and data["summary"] is None
    data = c.get("/api/day", params={"date": (today + timedelta(days=3)).isoformat()}, headers=headers).json()
    assert "summary" not in data


@pytest.mark.asyncio
async def test_api_day_summary_failure_drops_field(db, client, monkeypatch):  # noqa: F811
    from kapibara.features.schedule import parser as schedule_parser
    from kapibara.core.utils import today_msk

    async def raw():
        return _ical(today_msk())

    async def boom(*a):
        raise RuntimeError("база занята")

    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(day_summary, "summary", boom)
    c, headers = client
    data = c.get("/api/day", params={"date": (today_msk() - timedelta(days=1)).isoformat()}, headers=headers).json()
    assert "summary" not in data and "lessons" in data
