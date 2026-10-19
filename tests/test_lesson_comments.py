"""Комментарии под парой и оценка преподавателя в капибарах (Никита 19.10):
видит и пишет своя группа; мат не проходит; жалоба, «скрыть автора» и
удаление (правило Apple 1.2); оценка — только цифра, только тем, у кого
преподаватель в расписании, среднее — от SHOW_MIN оценок."""
from urllib.parse import urlencode

import pytest

import config
from tests.test_lesson_reactions import ME, MATE, STRANGER, _start, client  # noqa: F401 — фикстура

ICAL = (b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:test\r\nBEGIN:VEVENT\r\nUID:1\r\n"
        b"DTSTART:20260924T090000Z\r\nDTEND:20260924T103000Z\r\nSUMMARY:\xd0\x9b\xd0\x9a \xd0\x90\xd0\xbd\xd0\xb0\xd0\xbb\xd0\xb8\xd0\xb7\r\n"
        b"DESCRIPTION:\xd0\x9f\xd1\x80\xd0\xb5\xd0\xbf\xd0\xbe\xd0\xb4\xd0\xb0\xd0\xb2\xd0\xb0\xd1\x82\xd0\xb5\xd0\xbb\xd1\x8c: "
        b"\xd0\xa1\xd0\xb8\xd0\xb3\xd0\xb0\xd0\xbd\xd1\x8c\xd0\xba\xd0\xbe\xd0\xb2 \xd0\x90\xd0\xbb\xd0\xb5\xd0\xba\xd1\x81\xd0\xb5\xd0\xb9 "
        b"\xd0\x90\xd0\xbd\xd0\xb4\xd1\x80\xd0\xb5\xd0\xb5\xd0\xb2\xd0\xb8\xd1\x87\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
TEACHER = "Сиганьков А. А."   # в календаре — «Сиганьков Алексей Андреевич»


def _q(start, title="Анализ данных"):
    return "/api/lesson/comments?" + urlencode({"start": start, "title": title})


@pytest.mark.asyncio
async def test_group_comments_filter_and_delete(client):  # noqa: F811
    c, h = client
    s = _start()
    body = {"start": s, "title": "Анализ данных"}
    r = c.post("/api/lesson/comments", json={**body, "text": "Пару перенесли в А-17"}, headers=h(ME))
    assert r.status_code == 200 and [i["text"] for i in r.json()["items"]] == ["Пару перенесли в А-17"]
    assert c.post("/api/lesson/comments", json={**body, "text": "препод сука"}, headers=h(MATE)).status_code == 400
    assert c.post("/api/lesson/comments", json={**body, "text": "x" * 501}, headers=h(MATE)).status_code == 400
    assert c.post("/api/lesson/comments", json={**body, "text": "  "}, headers=h(MATE)).status_code == 400
    c.post("/api/lesson/comments", json={**body, "text": "спасибо!"}, headers=h(MATE))

    mate = c.get(_q(s, "анализ  ДАННЫХ"), headers=h(MATE)).json()             # та же пара, другой регистр
    assert [(i["text"], i["mine"]) for i in mate["items"]] == [("Пару перенесли в А-17", False), ("спасибо!", True)]
    assert mate["open"] and all("user_id" not in i and i["author"] for i in mate["items"])
    assert c.get(_q(s), headers=h(STRANGER)).json()["items"] == []          # другая группа — не видит

    mine = mate["items"][1]["id"]
    assert c.delete(f"/api/lesson/comments/{mine}", headers=h(ME)).status_code == 403    # чужой — нельзя
    assert c.delete(f"/api/lesson/comments/{mine}", headers=h(STRANGER)).status_code == 404
    assert c.delete(f"/api/lesson/comments/{mine}", headers=h(MATE)).status_code == 200
    assert len(c.get(_q(s), headers=h(ME)).json()["items"]) == 1

    old = _start(hours_ago=24 * 15)                                            # пара две недели назад — закрыто
    assert c.post("/api/lesson/comments", json={"start": old, "title": "Анализ данных", "text": "ок"},
                  headers=h(ME)).status_code == 400


@pytest.mark.asyncio
async def test_comment_report_and_hide_author(client, monkeypatch):  # noqa: F811
    import ugc
    c, h = client
    s = _start()
    first = c.post("/api/lesson/comments", json={"start": s, "title": "Анализ данных", "text": "где аудитория?"},
                   headers=h(MATE)).json()["id"]
    sent = []

    class Bot:
        async def send_message(self, *a, **kw):
            sent.append((a, kw))

    monkeypatch.setattr(config, "STAROSTA_ID", 1)
    rid = await ugc.report(Bot(), ME, "comment", first, "спам")
    assert sent and "Комментарий под парой" in str(sent[0]) and "где аудитория?" in str(sent[0])
    await ugc.hide_author(ME, "comment", first)
    assert c.get(_q(s), headers=h(ME)).json()["items"] == []                  # у себя скрыл
    assert len(c.get(_q(s), headers=h(MATE)).json()["items"]) == 1            # у автора — на месте
    assert await ugc.decide(rid, remove=True) == "removed"
    assert c.get(_q(s), headers=h(MATE)).json()["items"] == []                # удалён по жалобе — у всех


@pytest.mark.asyncio
async def test_teacher_rating_only_numbers_from_own_schedule(client, monkeypatch, db):  # noqa: F811
    import schedule_parser
    import teacher_rating
    c, h = client
    monkeypatch.setattr(schedule_parser, "raw_for_user", lambda uid, force=False: _raw(uid))

    async def _raw(uid):
        return ICAL if uid != STRANGER else b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"

    q = "/api/teacher/rating?" + urlencode({"name": TEACHER})
    r = c.get(q, headers=h(ME)).json()
    assert r == {"count": 0, "avg": None, "mine": None, "show_min": 3, "can_rate": True}
    assert c.post("/api/teacher/rating", json={"name": TEACHER, "score": 6}, headers=h(ME)).status_code == 400
    assert c.post("/api/teacher/rating", json={"name": TEACHER, "score": 5}, headers=h(STRANGER)).status_code == 403
    assert not c.get(q, headers=h(STRANGER)).json()["can_rate"]
    r = c.post("/api/teacher/rating", json={"name": "Сиганьков Алексей Андреевич", "score": 5}, headers=h(ME)).json()
    assert r["mine"] == 5 and r["avg"] is None and r["count"] == 1               # одна оценка — среднее скрыто
    c.post("/api/teacher/rating", json={"name": TEACHER, "score": 4}, headers=h(MATE))
    await db.upsert_user(504, "", "u504")
    await teacher_rating.put(TEACHER, 504, 3)
    r = c.get(q, headers=h(STRANGER)).json()
    assert r["count"] == 3 and r["avg"] == 4.0 and r["mine"] is None               # от трёх — видно всем
    r = c.post("/api/teacher/rating", json={"name": TEACHER, "score": 0}, headers=h(ME)).json()
    assert r["mine"] is None and r["count"] == 2 and r["avg"] is None              # убрал свою
