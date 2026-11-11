"""Новые баллы в СДО: сравнение с последней точкой истории, первый раз —
молча, сообщение со всеми изменившимися предметами, тумблер в уведомлениях."""
from pathlib import Path
import pytest

from kapibara.features.notifications import grade_alerts


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
    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import grades as sdo_grades
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
    from kapibara.features.notifications import prefs as notify_prefs
    assert notify_prefs.merge(None)["grades"] is True
    assert "toggleNotify('grades')" in Path("webapp/static/js/more.js").read_text(encoding="utf-8")


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
    assert grade_alerts.checked_head(done) == ("Моделирование: +5 баллов", "Практика 2 — 5 из 8")
    assert "Практика 2: <b>5 из 8</b>" in grade_alerts.checked_text(done)
    w3 = {"cmid": 13, "name": "Тест", "grade": None, "max": None, "graded": True, "passed": False}
    done = grade_alerts.checked(seen, [_course([w1, w2, w3])])
    assert grade_alerts.checked_head(done) == ("Моделирование: +5 баллов", "Практика 2: 5 из 8 · Тест: не зачтено")


@pytest.mark.asyncio
async def test_check_user_sends_checked_once(db, monkeypatch):
    from kapibara.features.sdo import grades as sdo_grades
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


@pytest.mark.asyncio
async def test_alert_after_app_opened_grades(db, monkeypatch):
    """Никита 02.11: открыл баллы в приложении (оно пишет точку истории) — пуш
    о новых баллах всё равно приходит: сравниваем с тем, что уже сообщали."""
    from kapibara.features.sdo import grades as sdo_grades
    from kapibara.features.sdo import history as sdo_history
    await db.upsert_user(1, "", "X")
    score = {"v": 30}

    async def overview(uid, cookie, fresh=False):
        return {"courses": [{"id": 7, "name": "Моделирование", "score": score["v"]}]}

    monkeypatch.setattr(sdo_grades, "overview", overview)
    sent = []

    class Bot:
        async def send_message(self, uid, text, **kw):
            sent.append(text)

    assert not await grade_alerts.check_user(Bot(), 1, "c")              # первый раз — запомнили
    score["v"] = 36
    await sdo_history.record(1, (await overview(1, "c"))["courses"])     # приложение открыло баллы
    assert await grade_alerts.check_user(Bot(), 1, "c")
    assert "30 → <b>36</b> (+6)" in sent[-1]
    assert not await grade_alerts.check_user(Bot(), 1, "c")              # второй раз — тишина


@pytest.mark.asyncio
async def test_starosta_with_shared_cookie_checked(db, monkeypatch):
    """Староста без своего входа ходит общей кукой — его баллы тоже проверяются."""
    from kapibara.core import config
    from kapibara.features.sdo import grades as sdo_grades
    monkeypatch.setattr(config, "SDO_SESSION_COOKIE", "shared")
    monkeypatch.setattr(config, "STAROSTA_IDS", [5])
    await db.upsert_user(5, "", "Никита")
    seen = []

    async def overview(uid, cookie, fresh=False):
        seen.append((uid, cookie))
        return {"courses": []}

    monkeypatch.setattr(sdo_grades, "overview", overview)

    class Bot:
        async def send_message(self, uid, text, **kw):
            pass

    await grade_alerts.check_all(Bot(), pause=0)
    assert seen == [(5, "shared")]


@pytest.mark.asyncio
async def test_grades_checked_with_own_login_check(db, monkeypatch):
    """Никита 02.11: баллы — у каждого вместе с проверкой его входа в СДО
    (своё случайное время раз в 50–59 мин), днём; ночью — нет."""
    import asyncio
    from datetime import datetime

    from kapibara.features.sdo import accounts as sdo_accounts
    from kapibara.features.sdo import grades as sdo_grades
    await db.upsert_user(7, "", "Егор")
    await db.save_sdo_session(7, sdo_accounts.encrypt("cookie0123456789abcdef0123"))
    seen = []

    async def check(cookie):
        return True

    async def overview(uid, cookie, fresh=False):
        seen.append((uid, cookie))
        return {"courses": []}

    monkeypatch.setattr(sdo_accounts, "check", check)
    monkeypatch.setattr(sdo_grades, "overview", overview)

    class Bot:
        async def send_message(self, *a, **kw):
            pass

    night = datetime(2026, 10, 1, 21, 30)      # UTC → 0:30 МСК
    await sdo_accounts._check_one(await db.get_sdo_session(7), Bot(), night)
    assert not grade_alerts._tasks and seen == []
    day = datetime(2026, 10, 1, 9, 30)         # UTC → 12:30 МСК
    await sdo_accounts._check_one(await db.get_sdo_session(7), Bot(), day)
    await asyncio.gather(*grade_alerts._tasks)
    assert seen == [(7, "cookie0123456789abcdef0123")]


def test_daytime_msk():
    from datetime import datetime
    assert grade_alerts.daytime(datetime(2026, 10, 1, 5, 0))        # 8:00 МСК
    assert not grade_alerts.daytime(datetime(2026, 10, 1, 4, 59))   # 7:59
    assert not grade_alerts.daytime(datetime(2026, 10, 1, 20, 0))   # 23:00


def test_checked_head_score_first():
    """Никита 09.11 и 11.11: в свёрнутом пуше «Проверили: Практическая работа №2 — 5 из 6»
    оценка уезжала за край, а ниже шло сырое имя курса СДО. Оценка — первой,
    имена — короткие."""
    c = {"id": 3, "name": "Архитектура предприятия_Экзамен (часть 1/1) [I.26-27]"}
    w = {"cmid": 5, "name": "Практическая работа №2", "grade": 5.0, "max": 6.0, "graded": True}
    assert grade_alerts.checked_head([(c, w)]) == ("Архитектура предприятия: +5 баллов", "Практика 2 — 5 из 6")
    w = dict(w, grade=None, max=None, passed=True)
    assert grade_alerts.checked_head([(c, dict(w, grade=7.0, max=8.0))])[0] == "Архитектура предприятия: +7 баллов"
    assert grade_alerts.checked_head([(c, dict(w, grade=1.0))])[0] == "Архитектура предприятия: +1 балл"
    w = dict(w, grade=None, max=None, passed=True)
    assert grade_alerts.checked_head([(c, w)]) == ("Архитектура предприятия: зачтено", "Проверили: Практика 2")
    assert "[I.26-27]" not in grade_alerts.checked_text([(c, w)])
