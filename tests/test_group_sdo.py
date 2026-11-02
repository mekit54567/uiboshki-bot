"""Этап 1 (в): задания СДО другой группы по входу, которым поделились;
одна лекция у разных групп — один конспект; файлы — в группу загрузившего."""
import pytest
from fastapi.testclient import TestClient

from kapibara.core import config
from kapibara.features.sdo import parser as sdo_parser

HOME = config.HOME_GROUP_ID
OTHER = 5001
DONOR, MATE, STRANGER = 401, 402, 403


@pytest.fixture
async def group(db):
    from kapibara.features.sdo import accounts as sdo_accounts
    from database.groups import upsert_group
    await upsert_group(OTHER, "УИБО-01-24")
    for uid, gid in ((DONOR, OTHER), (MATE, OTHER), (STRANGER, HOME)):
        await db.upsert_user(uid, "", f"u{uid}")
        await db.set_user_group(uid, gid)
    await db.save_sdo_session(DONOR, sdo_accounts.encrypt("A" * 26))
    return db


def _events(*ids):
    import time
    return [{"id": i, "component": "mod_assign", "eventtype": "due", "name": f"Практика {i}",
             "course": {"fullname": "Финансовый анализ"}, "url": f"https://x/mod/assign/view.php?id={i}",
             "timestart": int(time.time()) + 86400 * 3} for i in ids]


@pytest.mark.asyncio
async def test_group_deadlines_come_only_with_consent(group, monkeypatch):
    from kapibara.features.groups import sync as group_sync
    db = group
    got_cookie = []

    async def calendar(client):
        got_cookie.append(client.cookies.get("MoodleSession"))
        return _events(7, 8)

    async def subjects(*a, **k):
        return ["Финансовый анализ"]

    monkeypatch.setattr(sdo_parser, "fetch_calendar_events", calendar)
    monkeypatch.setattr("kapibara.features.schedule.parser.get_group_subjects", subjects)
    assert await db.get_sharing_groups() == []                               # не согласился — синка нет
    assert (await group_sync.sync_group(OTHER))["error"]
    assert await db.set_sdo_share(DONOR, True)
    assert await db.get_sharing_groups() == [OTHER]
    res = await group_sync.sync_group(OTHER)
    assert (res["added"], res["donor"]) == (2, DONOR) and got_cookie[-1] == "A" * 26
    mate = await db.get_active_deadlines(MATE)
    assert len(mate) == 2 and all(d["group_id"] == OTHER for d in mate)
    assert mate[0]["external_id"] == f"sdo:{OTHER}:7"                         # у каждой группы своё задание
    assert await db.get_active_deadlines(STRANGER) == []                      # УИБО-03-24 их не видит
    assert (await group_sync.sync_group(OTHER))["added"] == 0                 # повтор — без дублей


@pytest.mark.asyncio
async def test_same_lecture_same_summary(db):
    a = await db.add_file("Лекция 1", "Анализ", "tg1", "l1.pdf", 1)
    b = await db.add_file("ЛК1 (копия в другом курсе)", "Анализ", "tg2", "lk1.pdf", 2, group_id=OTHER)
    c = await db.add_file("Другая лекция", "Анализ", "tg3", "l2.pdf", 1)
    await db.save_file_text(a, "Дисконтирование   денежных потоков")
    await db.save_file_text(b, "дисконтирование денежных\nпотоков")          # регистр и пробелы — неважно
    await db.save_file_text(c, "Совсем другое")
    await db.save_file_summary(a, "**Конспект**", 1)
    assert (await db.get_file_summary(b))["content"] == "**Конспект**"
    assert await db.get_file_summary(c) is None
    assert await db.get_file_ids_with_summary() == {a, b}


@pytest.mark.asyncio
async def test_uploaded_file_lands_in_uploaders_group(group):
    db = group
    from database.groups import current_group
    token = current_group.set(OTHER)
    try:
        fid = await db.add_file("Методичка", "Финансы", "tg9", "m.pdf", DONOR)
        assert [f["id"] for f in await db.get_files()] == [fid]
    finally:
        current_group.reset(token)
    assert await db.get_files() == []                                         # у своей группы его нет


@pytest.mark.asyncio
async def test_share_toggle_api(group, monkeypatch):
    from kapibara.features.groups import sync as group_sync
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    synced = []

    async def sync_group(gid):
        synced.append(gid)
        return {}

    monkeypatch.setattr(group_sync, "sync_group", sync_group)
    c = TestClient(server.app)
    h = {"X-Telegram-Init-Data": _make_init_data(user={"id": DONOR, "first_name": "D"})}
    st = c.get("/api/sdo/status", headers=h).json()
    assert st["can_share"] and not st["share"] and st["group"] == "УИБО-01-24"
    assert c.post("/api/sdo/share", json={"share": True}, headers=h).json()["share"] is True
    h2 = {"X-Telegram-Init-Data": _make_init_data(user={"id": MATE, "first_name": "M"})}
    assert c.post("/api/sdo/share", json={"share": True}, headers=h2).status_code == 400   # СДО не подключён
