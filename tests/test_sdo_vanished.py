"""Задание пропало из СДО (преподаватель удалил или скрыл) — бот убирает его
у себя: два синка подряд нет в полном календаре, у каждой группы свой счёт
(решение владельца 08.10)."""
import pytest

from kapibara.features.sdo import parser as sdo_parser
from tests.test_group_sdo import DONOR, OTHER, _events, group  # noqa: F401 — фикстура


@pytest.mark.asyncio
async def test_vanished_task_goes_after_two_syncs(group, monkeypatch):  # noqa: F811
    from kapibara.features.groups import sync as group_sync
    db = group
    shown = [_events(7, 8)]

    async def calendar(client):
        return shown[0]

    async def subjects(*a, **k):
        return ["Финансовый анализ"]

    monkeypatch.setattr(sdo_parser, "fetch_calendar_events", calendar)
    monkeypatch.setattr("kapibara.features.schedule.parser.get_group_subjects", subjects)
    await db.set_sdo_share(DONOR, True)
    home = await db.add_deadline(subject="Своё задание", description="", due_date="2099-01-01",
                                 due_time="23:59", created_by=0, external_id="sdo:999")
    assert (await group_sync.sync_group(OTHER))["added"] == 2

    shown[0] = _events(7)                                            # 8-е удалили в СДО
    assert (await group_sync.sync_group(OTHER))["gone"] == []        # раз не видно — может, сбой
    ids = {d["external_id"] for d in await db.get_sdo_deadlines()}
    assert f"sdo:{OTHER}:8" in ids
    assert (await group_sync.sync_group(OTHER))["gone"] == ["Практика 8 · Финансовый анализ"]
    ids = {d["external_id"] for d in await db.get_sdo_deadlines()}
    assert f"sdo:{OTHER}:8" not in ids and f"sdo:{OTHER}:7" in ids
    assert "sdo:999" in ids and await db.get_deadline(home)          # своя группа — не тронута
    assert not await db.is_deadline_skipped(f"sdo:{OTHER}:8")        # вернётся в СДО — вернётся и тут

    shown[0] = _events(7, 8)
    assert (await group_sync.sync_group(OTHER))["added"] == 1


@pytest.mark.asyncio
async def test_vanished_keeps_what_it_cannot_judge(db):
    keep_manual = await db.add_deadline(subject="Поправлено вручную", description="", due_date="2099-01-01",
                                        due_time="23:59", created_by=0, external_id="sdo:1")
    await db.edit_deadline(keep_manual, "Поправлено вручную", "", "2099-01-01", "23:59")
    await db.add_deadline(subject="Прошло", description="", due_date="2000-01-01", due_time="23:59",
                          created_by=0, external_id="sdo:2")
    await db.add_deadline(subject="За окном календаря", description="", due_date=sdo_parser.calendar_end()[:8] + "01",
                          due_time="23:59", created_by=0, external_id="sdo:3")
    seen = [{"external_id": "sdo:4", "calendar": True}]
    upcoming = [{"external_id": "sdo:4"}]                            # «Предстоящие» — не полный календарь
    for _ in range(3):
        assert await sdo_parser.drop_vanished(upcoming) == []
        assert await sdo_parser.drop_vanished([]) == []              # пустой ответ — скорее сбой
    assert await sdo_parser.drop_vanished(seen) == []
    gone = await sdo_parser.drop_vanished(seen)
    left = {d["external_id"] for d in await db.get_sdo_deadlines()}
    assert {"sdo:1", "sdo:2"} <= left                                # ручная правка и прошедшее — остались
    assert gone == [] and "sdo:3" in left                            # за окном календаря — не судим
