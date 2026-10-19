"""Сдал в СДО — дедлайн у себя отмечен сам (sdo_done.py)."""
import pytest

import sdo_done

URL = "https://online-edu.mirea.ru/mod/{m}/view.php?id={i}"


def test_cmid_of_assign_and_quiz():
    assert sdo_done.cmid_of("Сдать: " + URL.format(m="assign", i=4242)) == 4242
    assert sdo_done.cmid_of(URL.format(m="quiz", i=77) + "&foo=1") == 77
    assert sdo_done.cmid_of("https://online-edu.mirea.ru/mod/forum/view.php?id=5") is None
    assert sdo_done.cmid_of(None) is None


def test_finished_only_ok_and_wait():
    course = {"works": [{"cmid": 1, "status": "ok"}, {"cmid": 2, "status": "wait"}, {"cmid": 3, "status": "low"},
                        {"cmid": 4, "status": "todo"}, {"cmid": None, "status": "ok"}]}
    assert sdo_done.finished(course) == [1, 2]


@pytest.mark.asyncio
async def test_mark_only_own_and_never_unmarks(db):
    a = await db.add_deadline("Практика 1", URL.format(m="assign", i=11), "2026-10-10", None, 0, external_id="sdo:a")
    b = await db.add_deadline("Тест 1", URL.format(m="quiz", i=12), "2026-10-11", None, 0, external_id="sdo:b")
    c = await db.add_deadline("Практика 2", URL.format(m="assign", i=13), "2026-10-12", None, 0, external_id="sdo:c")
    assert await sdo_done.mark(222, [11, 12, 999]) == 2
    assert await db.is_deadline_done(a, 222) and await db.is_deadline_done(b, 222)
    assert not await db.is_deadline_done(c, 222)
    assert not await db.is_deadline_done(a, 333)                      # у другого — своё
    assert await sdo_done.mark(222, [11]) == 0                         # уже отмечено
    assert await sdo_done.mark(222, []) == 0


@pytest.mark.asyncio
async def test_course_detail_marks_finished_works(db, monkeypatch):
    """Открыл предмет в СДО — задание «сдано, ждёт оценки» у себя в дедлайнах сданным."""
    from fastapi.testclient import TestClient
    import sdo_accounts
    import sdo_grades
    import webapp.server as server
    from tests.test_webapp_home import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    did = await db.add_deadline("Практика 1", URL.format(m="assign", i=4242), "2026-10-10", None, 0, external_id="sdo:z")

    async def detail(uid, cookie, cid, stale_ok=False):
        return {"id": cid, "name": "Анализ данных", "title": "Анализ данных", "score": 10, "categories": [],
                "works": [{"cmid": 4242, "status": "wait", "name": "Практика 1"}]}

    monkeypatch.setattr(sdo_grades, "course_detail", detail)
    await db.save_sdo_session(222, sdo_accounts.encrypt("abcdef0123456789abcdef0123"))
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    assert c.get("/api/sdo/grades/18672", headers=h).status_code == 200
    assert await db.is_deadline_done(did, 222)


def test_is_submitted_and_shared_cmid_parser():
    import sdo_submit
    assert sdo_done.is_submitted("Отправлено для оценивания") and sdo_done.is_submitted("Submitted for grading")
    assert not sdo_done.is_submitted("Черновик (не отправлено)") and not sdo_done.is_submitted("Нет ответа")
    assert not sdo_done.is_submitted(None)
    quiz = URL.format(m="quiz", i=77)
    assert sdo_submit.cmid_of(quiz) is None and sdo_submit.cmid_of(quiz, quiz=True) == 77   # сдать файлом тест нельзя
    assert sdo_submit.cmid_of(quiz + " и " + URL.format(m="assign", i=5)) == 5
