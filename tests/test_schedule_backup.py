"""Зеркало расписания МИРЭА лежит → бот отдаёт последний удачный календарь
(из памяти или из базы после перезапуска) и пишет, от какого он времени."""
import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

import schedule_parser

ICS = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:test\r\n"
       b"BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Moscow:20261001T090000\r\n"
       b"DTEND;TZID=Europe/Moscow:20261001T103000\r\nSUMMARY:Lecture\r\nUID:a\r\nEND:VEVENT\r\n"
       b"END:VCALENDAR\r\n")


class FakeMirror:
    def __init__(self):
        self.mode = "ok"      # ok / down / html / cut / empty

    def client(self, *a, **kw):
        mirror = self

        class C:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *e):
                return False

            async def get(self, url):
                req = httpx.Request("GET", url)
                if mirror.mode == "down":
                    raise httpx.ConnectTimeout("timeout", request=req)
                body = {"ok": ICS, "cut": ICS[:-30],
                        "empty": b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"}.get(
                    mirror.mode, b"<html>502 Bad Gateway</html>")
                return httpx.Response(200, content=body, request=req)
        return C()


@pytest.fixture
def mirror(monkeypatch):
    m = FakeMirror()
    monkeypatch.setattr(schedule_parser.httpx, "AsyncClient", m.client)
    for name, val in (("_cache_data", None), ("_cache_time", 0.0), ("_ok_at", None), ("_stale", False),
                      ("_backup_hash", None), ("_inflight", None), ("_fail_at", None), ("_fail_exc", None)):
        monkeypatch.setattr(schedule_parser, name, val)
    return m


@pytest.mark.asyncio
async def test_down_mirror_serves_saved_copy(db, mirror):
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser.stale_label() is None and schedule_parser.stale_note() == ""

    mirror.mode = "down"                                   # в памяти есть — отдаём её
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser.stale_label() and "не отвечает" in schedule_parser.stale_note()

    schedule_parser._cache_data = None                     # «перезапуск»: память пуста — берём из базы
    mirror.mode = "html"                                   # страница ошибки с кодом 200 — тоже не календарь
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser.stale_label()

    mirror.mode = "ok"                                     # зеркало ожило — пометка пропала
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser.stale_label() is None


@pytest.mark.asyncio
async def test_down_mirror_without_copy_raises(db, mirror):
    mirror.mode = "down"
    with pytest.raises(httpx.HTTPError):
        await schedule_parser.fetch_schedule_raw(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["cut", "empty"])
async def test_cut_or_empty_calendar_keeps_backup(db, mirror, mode):
    # обрывок ical затирал запасную копию, пустой — рассылал ложные отмены
    from database import load_schedule_backup
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    mirror.mode = mode
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser.stale_label()
    assert (await load_schedule_backup())[0] == ICS


@pytest.mark.asyncio
async def test_single_flight_and_stale_while_revalidate(db, mirror, monkeypatch):
    calls = []

    async def slow_download():
        calls.append(1)
        await asyncio.sleep(0.2)
        return ICS

    monkeypatch.setattr(schedule_parser, "_download", slow_download)
    # кэша нет: 5 параллельных вызовов — одна загрузка на всех
    got = await asyncio.gather(*(schedule_parser.fetch_schedule_raw() for _ in range(5)))
    assert got == [ICS] * 5 and len(calls) == 1

    # кэш протух: старое отдаётся сразу, свежее качается в фоне один раз
    schedule_parser._cache_time -= schedule_parser.SCHEDULE_CACHE_TTL_SECONDS + 1
    t = time.monotonic()
    got = await asyncio.gather(*(schedule_parser.fetch_schedule_raw() for _ in range(5)))
    assert got == [ICS] * 5 and time.monotonic() - t < 0.1
    await schedule_parser._inflight
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_retry_counts_from_failure_not_from_request(db, mirror, monkeypatch):
    # зеркало висело 30 с: следующая попытка — через минуту после сбоя,
    # а не «минута от начала запроса», то есть почти сразу
    clock = [1000.0]
    monkeypatch.setattr(schedule_parser, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS

    async def hanging_download():
        clock[0] += 30
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(schedule_parser, "_download", hanging_download)
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    assert schedule_parser._cache_time + schedule_parser.SCHEDULE_CACHE_TTL_SECONDS - clock[0] == 60


@pytest.mark.asyncio
async def test_no_copy_failure_not_waited_again(db, mirror, monkeypatch):
    # ни кэша, ни копии: после сбоя минуту не ждём зеркало снова на каждый вызов
    calls = []

    async def failing():
        calls.append(1)
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(schedule_parser, "_download", failing)
    for _ in range(3):
        with pytest.raises(httpx.HTTPError):
            await schedule_parser.fetch_schedule_raw()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cold_start_serves_copy_without_waiting_mirror(db, mirror, monkeypatch):
    # после перезапуска первый заход ждал зеркало до 30 с (дедлайны, ДЗ, СДО по
    # 30–35 с в /status 17.10): копия из базы — сразу, свежее — в фоне
    assert await schedule_parser.fetch_schedule_raw(force=True) == ICS
    schedule_parser._cache_data = None                     # «перезапуск»
    fresh = ICS.replace(b"Lecture", b"Seminar")
    gate = asyncio.Event()

    async def slow_download():
        await gate.wait()
        return fresh

    monkeypatch.setattr(schedule_parser, "_download", slow_download)
    got = await asyncio.wait_for(schedule_parser.fetch_schedule_raw(), 1)
    assert got == ICS and schedule_parser.stale_label() is None
    gate.set()
    await schedule_parser._inflight                        # фон докачал — дальше свежее
    assert await schedule_parser.fetch_schedule_raw() == fresh
