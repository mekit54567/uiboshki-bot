"""Новые баллы в СДО: сравнение с последней точкой истории, первый раз —
молча, сообщение со всеми изменившимися предметами, тумблер в уведомлениях."""
import pytest

import grade_alerts


def test_changes_only_with_history():
    courses = [{"id": 1, "name": "Модел", "score": 39}, {"id": 2, "name": "ООП", "score": 10},
               {"id": 3, "name": "Матан", "score": 5}, {"id": 4, "name": "Без", "score": None}]
    diff = grade_alerts.changes({1: 34.0, 2: 10.0}, courses)
    assert [(c["id"], o, n) for c, o, n in diff] == [(1, 34.0, 39.0)]


def test_message_signs():
    text = grade_alerts.message([({"name": "Модел"}, 34.0, 39.0), ({"name": "А<б"}, 12.5, 10.0)])
    assert "Модел: 34 → <b>39</b> (+5)" in text
    assert "А&lt;б: 12.5 → <b>10</b> (-2.5)" in text


@pytest.mark.asyncio
async def test_check_all(db, monkeypatch):
    import sdo_accounts
    import sdo_grades
    for uid in (1, 2, 3):
        await db.upsert_user(uid, "", "X")
        await db.save_sdo_session(uid, sdo_accounts.encrypt(f"c{uid}"))
    await db.set_notify(3, {"grades": False})
    await db.save_score_points(1, "2026-09-20", {7: 30.0})
    await db.save_score_points(1, "2026-09-24", {7: 34.0})
    scores = {1: 39, 2: 50, 3: 1}

    async def overview(uid, cookie, fresh=False):
        assert fresh and cookie == f"c{uid}"
        return {"courses": [{"id": 7, "name": "Моделирование", "score": scores[uid]}]}

    monkeypatch.setattr(sdo_grades, "overview", overview)
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append((uid, text))

    await grade_alerts.check_all(Bot(), pause=0)
    assert [u for u, _ in sent] == [1]                       # 2 — первый раз, 3 — выключено
    assert "34 → <b>39</b> (+5)" in sent[0][1]
    assert await db.get_last_scores(2) == {7: 50.0}           # запомнили для следующего раза
    assert await db.get_last_scores(3) == {7: 1.0}            # тумблер выключен — сообщения нет, а точка
                                                              # истории есть: по ней считаются посещения
    sent.clear()
    await grade_alerts.check_all(Bot(), pause=0)
    assert sent == []                                         # не изменилось — тишина


def test_toggle_in_app():
    import notify_prefs
    assert notify_prefs.merge(None)["grades"] is True
    assert "toggleNotify('grades')" in open("webapp/static/js/more.js", encoding="utf-8").read()


def _course(works):
    return {"id": 7, "name": "Моделирование", "score": 39, "works": works}


def test_checked_works():
    """«Работу проверили» (Никита 25.10): новая оценка у работы — пуш с оценкой; первый раз — молча."""
    w1 = {"cmid": 11, "name": "Практика 1", "grade": 7.0, "max": 8.0, "graded": True, "passed": True}
    w2 = {"cmid": 12, "name": "Практика 2", "grade": None, "max": 8.0, "graded": False, "passed": None}
    seen = grade_alerts.graded_map([_course([w1, w2])])
    assert seen == {"7:11": "7 из 8"}
    assert grade_alerts.checked(None, [_course([w1, w2])]) == []
    w2 = dict(w2, grade=5.0, graded=True, passed=True)
    done = grade_alerts.checked(seen, [_course([w1, w2])])
    assert [w["cmid"] for _, w in done] == [12]
    assert grade_alerts.checked_head(done) == ("Проверили: Практика 2 — 5 из 8", "Моделирование")
    assert "Практика 2: <b>5 из 8</b>" in grade_alerts.checked_text(done)
    w3 = {"cmid": 13, "name": "Тест", "grade": None, "max": None, "graded": True, "passed": False}
    done = grade_alerts.checked(seen, [_course([w1, w2, w3])])
    assert grade_alerts.checked_head(done) == ("Проверили 2 работы", "Практика 2 — 5 из 8 · Тест — не зачтено")


@pytest.mark.asyncio
async def test_check_user_sends_checked_once(db, monkeypatch):
    import sdo_grades
    await db.upsert_user(1, "", "X")
    works = [{"cmid": 11, "name": "Практика 1", "grade": None, "max": 8.0, "graded": False, "passed": None}]

    async def overview(uid, cookie, fresh=False):
        return {"courses": [_course(works)]}

    monkeypatch.setattr(sdo_grades, "overview", overview)
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append(text)

    assert not await grade_alerts.check_user(Bot(), 1, "c")             # первый раз — запомнили
    works[0] = dict(works[0], grade=7.0, graded=True, passed=True)
    assert await grade_alerts.check_user(Bot(), 1, "c")
    assert "Проверили работу" in sent[-1]
    assert not await grade_alerts.check_user(Bot(), 1, "c")             # второй раз — тишина
