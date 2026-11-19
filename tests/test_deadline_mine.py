"""Ответ владельца 08.10 на вопрос 1: общий срок может изменить или убрать
каждый — но только у себя; у группы он остаётся как был, синк СДО свою
правку не трогает, «Как у всех» возвращает общий."""
import pytest

from tests.test_webapp_home import _headers_for, client  # noqa: F401 — фикстура

ANYA, BORYA = 222, 223


@pytest.mark.asyncio
async def test_edit_and_hide_only_for_me(db, client):  # noqa: F811
    c, _ = client
    for uid in (ANYA, BORYA):
        await db.upsert_user(uid, "", f"u{uid}")
    shared = await db.add_deadline("Тест 2", "", "2099-10-01", "18:00", 0, external_id="sdo:5")
    anya, borya = _headers_for(ANYA), _headers_for(BORYA)

    def mine(h):
        return {i["id"]: i for i in c.get("/api/deadlines", headers=h).json()["items"]}

    body = {"subject": "Тест 2 (перенесли)", "due_date": "2099-10-05", "due_time": "10:00", "description": "ауд. 214"}
    assert c.patch(f"/api/deadlines/{shared}", headers=anya, json=body).json()["scope"] == "me"
    a = mine(anya)[shared]
    assert (a["subject"], a["due_date"], a["due_time"], a["description"]) == \
           ("Тест 2 (перенесли)", "2099-10-05", "10:00", "ауд. 214")
    b = mine(borya)[shared]
    assert (b["subject"], b["due_date"]) == ("Тест 2", "2099-10-01")          # у Бори — как у всех
    assert "created_by" not in b                                             # чужой id не отдаём (152-ФЗ)
    soon = await db.get_deadlines_soon(days=36500, viewer_id=ANYA)
    assert next(d for d in soon if d["id"] == shared)["due_date"] == "2099-10-05"  # рассылки — по своей правке

    assert c.delete(f"/api/deadlines/{shared}", headers=borya).json()["scope"] == "me"
    assert shared not in mine(borya) and shared in mine(anya)                # убрал только у себя
    assert (await db.get_deadline_stats(BORYA))["total"] == 0

    assert c.delete(f"/api/deadlines/{shared}/mine", headers=borya).json() == {"ok": True}
    assert shared in mine(borya)                                             # «Как у всех»
    assert c.delete(f"/api/deadlines/{shared}/mine", headers=borya).json() == {"ok": False}


@pytest.mark.asyncio
async def test_cannot_touch_someone_elses_personal(db, client):  # noqa: F811
    c, _ = client
    other = await db.add_deadline("Личное Бори", "", "2099-10-01", None, BORYA, personal=True)
    body = {"subject": "x", "due_date": "2099-10-02"}
    assert c.patch(f"/api/deadlines/{other}", headers=_headers_for(ANYA), json=body).status_code == 404
    assert c.delete(f"/api/deadlines/{other}", headers=_headers_for(ANYA)).status_code == 404
