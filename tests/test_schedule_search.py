"""
Поиск расписания преподавателя/группы/аудитории. Официальный поиск МИРЭА из-за
рубежа не отвечает (в проде /teacher Морозов ~40 с висел и отвечал «не
нашёл»), поэтому свой справочник (schedule_index) собирается с зеркала
english.mirea.ru по заголовку X-WR-CALNAME каждого ical. HTTP здесь —
httpx.MockTransport, база — настоящая SQLite (фикстура db).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

import schedule_index
from tests.test_webapp_auth import _make_init_data

TZ = ZoneInfo("Europe/Moscow")

NAMES = {
    (2, 1): "Морозов А. В.", (2, 2): "Морозова Е. С.", (2, 3): "Шморозов И. И.",
    (2, 5): "Ёлкин П. П.", (1, 1): "УИБО-03-24", (1, 2): "УИБО-02-24", (3, 1): "А-18 (В-78)",
}


def _mirror(names=NAMES, fail_ids=()):
    calls = []

    def handler(request: httpx.Request):
        _, _, _, _, t, i = request.url.path.split("/")[-6:]
        key = (int(t), int(i))
        calls.append(key)
        if key in fail_ids:
            raise httpx.ConnectError("boom")
        if key not in names:
            return httpx.Response(404, text="<html>not found</html>")
        body = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:{names[key]}\r\nBEGIN:VTIMEZONE\r\n" + "X" * 3000
        return httpx.Response(200, content=body.encode())

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


@pytest.mark.asyncio
async def test_fetch_title_reads_calname_and_404_is_none(db):
    client, _ = _mirror()
    async with client:
        assert await schedule_index.fetch_title(client, 2, 1) == "Морозов А. В."
        assert await schedule_index.fetch_title(client, 2, 999) is None


@pytest.mark.asyncio
async def test_build_index_stops_after_misses_and_search_works(db, monkeypatch):
    monkeypatch.setattr(schedule_index, "STOP_AFTER_MISSES", 20)
    client, calls = _mirror()
    async with client:
        await schedule_index.build_index(client)
    assert await schedule_index.is_ready()
    assert await schedule_index.count() == len(NAMES)
    # по каждому типу — не дальше «последний найденный + серия промахов + пачка»
    assert max(i for t, i in calls if t == 2) < 5 + 20 + schedule_index.CONCURRENCY * 5

    found = await schedule_index.search("морозов", (2,))
    assert [f["title"] for f in found] == ["Морозов А. В.", "Морозова Е. С.", "Шморозов И. И."]
    assert [f["title"] for f in await schedule_index.search("елкин")] == ["Ёлкин П. П."]  # ё = е
    assert [f["id"] for f in await schedule_index.search("уибо-03", (1,))] == [1]
    assert await schedule_index.search("100%_") == []  # спецсимволы LIKE не ломают запрос


@pytest.mark.asyncio
async def test_interrupted_scan_resumes_where_it_stopped(db, monkeypatch):
    monkeypatch.setattr(schedule_index, "STOP_AFTER_MISSES", 20)
    monkeypatch.setattr(schedule_index.asyncio, "sleep", _no_sleep)
    client, _ = _mirror(fail_ids={(2, 30)})
    async with client:
        with pytest.raises(httpx.ConnectError):
            await schedule_index.build_index(client)
    assert not await schedule_index.is_ready()
    assert int(await schedule_index._get_state("next_id_1")) > 1  # группы уже пройдены

    client, calls = _mirror()
    async with client:
        await schedule_index.build_index(client)
    assert await schedule_index.is_ready()
    assert (1, 1) not in calls  # группы заново не обходились


async def _no_sleep(*_):
    return None


@pytest.mark.asyncio
async def test_search_targets_uses_index_and_reports_unavailable(db, monkeypatch):
    import mirea_schedule_api as api

    async def official_down(*_):
        raise httpx.ConnectError("schedule-of.mirea.ru не отвечает")

    monkeypatch.setattr(api, "_official_search", official_down)
    with pytest.raises(api.SearchUnavailable):  # справочника ещё нет — не «не нашёл»
        await api.search_targets("Морозов", api.TARGET_TEACHER)

    await schedule_index._save([(2, 7, "Морозов А. В.")])
    assert await api.search_targets("Морозов", api.TARGET_TEACHER) == [
        {"id": 7, "fullTitle": "Морозов А. В.", "scheduleTarget": 2}
    ]
    await schedule_index._set_state("built_at", "1")
    assert await api.search_targets("Сидоров", api.TARGET_TEACHER) == []  # собран — честное «нет»


def _teacher_ical() -> bytes:
    day = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y%m%d")
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:Блеко В. В.\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART;TZID=Europe/Moscow:{day}T124000\r\n"
        f"DTEND;TZID=Europe/Moscow:{day}T141000\r\n"
        "SUMMARY:ЛАБ Физика 1 п/г\r\nLOCATION:В-328 (В-78)\r\n"
        "DESCRIPTION:КСБО-11-26 1 п/г\\n\r\nUID:x1\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


def test_teacher_schedule_shows_groups_and_real_pair_number():
    from schedule_parser import format_target_schedule
    text = format_target_schedule(_teacher_ical(), 2)
    # 12:40 — это 3-я пара, хоть она у преподавателя в этот день и первая
    assert "3️⃣ 12:40–14:10 · Физика 1 п/г (лаб) · В-328 (В-78) · 👥 КСБО-11-26 1 п/г" in text
    assert format_target_schedule(b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n", 2) \
        == "Пар в ближайшие 14 дней нет."


@pytest.mark.asyncio
async def test_webapp_search_and_target_endpoints(db, monkeypatch):
    import mirea_schedule_api as api
    import webapp.server as server

    await schedule_index._save([(2, 100, "Блеко В. В."), (1, 4928, "УИБО-03-24")])
    await schedule_index._set_state("built_at", "1")

    async def fake_ical(target_id, target_type):
        return _teacher_ical()

    monkeypatch.setattr(api, "fetch_ical", fake_ical)
    client = TestClient(server.app)
    headers = {"X-Telegram-Init-Data": _make_init_data()}

    resp = client.get("/api/search", params={"q": "блек"}, headers=headers)
    assert resp.json() == {"items": [{"type": 2, "id": 100, "title": "Блеко В. В."}], "ready": True}
    assert client.get("/api/search", params={"q": "блек", "type": 1}, headers=headers).json()["items"] == []
    assert client.get("/api/search", params={"q": "блек"}).status_code == 401

    resp = client.get("/api/target/2/100", headers=headers)
    data = resp.json()
    assert data["title"] == "Блеко В. В."
    assert "👥 КСБО-11-26 1 п/г" in data["html"]


@pytest.mark.asyncio
async def test_graduated_groups_hidden_and_newest_first(db, monkeypatch):
    # живой тест: по «БАСО» весь верх выдачи занимали БАСО-01-12…-17
    yy = datetime.now(TZ).year % 100
    await schedule_index._save([
        (1, 1, f"БАСО-01-{yy - 14:02d}"),
        (1, 2, f"БАСО-01-{yy - 5:02d}"),
        (1, 3, f"БАСО-01-{yy:02d}"),
        (1, 4, f"БАСО-02-{yy - 1:02d}"),
        (2, 5, "Басов И. И."),
    ])
    titles = [f["title"] for f in await schedule_index.search("басо")]
    assert titles[:3] == [f"БАСО-01-{yy:02d}", f"БАСО-02-{yy - 1:02d}", f"БАСО-01-{yy - 5:02d}"]
    assert f"БАСО-01-{yy - 14:02d}" not in titles
    assert "Басов И. И." in titles


@pytest.mark.asyncio
async def test_namesakes_get_hints_and_busy_one_first(monkeypatch):
    # Прод: «/teacher Морозов» — «Морозов В. А.» ×3, «Морозов Д. В.» ×3,
    # в справочнике только инициалы, выбрать нужного невозможно.
    import mirea_schedule_api as api
    icals = {5: None, 6: _teacher_ical(), 7: b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"}

    async def fake_ical(target_id, target_type):
        return icals.get(target_id)

    monkeypatch.setattr(api, "fetch_ical", fake_ical)
    res = await api.add_hints_for_namesakes([
        {"id": 1, "fullTitle": "Морозов А. А.", "scheduleTarget": 2},
        {"id": 7, "fullTitle": "Морозов В. А.", "scheduleTarget": 2},
        {"id": 6, "fullTitle": "Морозов В. А.", "scheduleTarget": 2},
        {"id": 5, "fullTitle": "Морозов В. А.", "scheduleTarget": 2},
        {"id": 9, "fullTitle": "Моро Б. Б.", "scheduleTarget": 2},
    ])
    assert [r["id"] for r in res] == [1, 6, 7, 5, 9]      # порядок выдачи сохранён, внутри — с парами первым
    assert res[1]["hint"] == "Физика 1 п/г"
    assert res[2]["hint"] == "нет пар в ближайшие 2 недели"
    assert "hint" not in res[0] and "hint" not in res[3]  # уникальное имя / ical недоступен
