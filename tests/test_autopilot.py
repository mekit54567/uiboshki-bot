"""Автопилот (autopilot.py, autopilot_data.py, webapp/routes/plan.py): окна
между парами, план CP-SAT (сроки, без наложений, лимит на день, баллы до
цели, правило 75 %), «что если пропущу лекцию», обучение на «сколько заняло»,
сбор входов из СДО и дедлайнов и API. Сеть не нужна — СДО и расписание
подменены."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import autopilot as ap

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=MSK)          # понедельник, утро
PREFS = dict(ap.DEFAULT_PREFS, light_weekdays=[])


def at(day: int, h: int, m: int = 0) -> datetime:
    d = NOW.date() + timedelta(days=day)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=MSK)


def task(key, minutes=60, points=0.0, due=None, course="", tk=False, kind="assign", opens=None):
    return ap.Task(key, key, course, kind, minutes, points=points, due=due, opens=opens, tk=tk)


def test_parse_ru_dt():
    assert ap.parse_ru_dt("среда, 15 октября 2026, 23:59", MSK) == datetime(2026, 10, 15, 23, 59, tzinfo=MSK)
    assert ap.parse_ru_dt("1 декабря 2026", MSK) == datetime(2026, 12, 1, 23, 59, tzinfo=MSK)   # без времени — до конца дня
    assert ap.parse_ru_dt("скоро", MSK) is None


def test_windows_cut_lessons_with_buffer():
    busy = {NOW.date(): [(at(0, 10, 40), at(0, 12, 10)), (at(0, 12, 40), at(0, 14, 10))]}
    wins = [w for w in ap.windows(busy, PREFS, NOW, days=2) if w.day == 0]
    origin = ap.origin_of(NOW.date(), MSK)
    spans = [(ap.from_slot(w.start, origin).strftime("%H:%M"), ap.from_slot(w.end, origin).strftime("%H:%M")) for w in wins]
    # 09:00–10:30 (до пары минус 10 мин), перемена 12:20–12:30 — короче 30 мин, не окно; после пар — до 23:00
    assert spans == [("09:00", "10:30"), ("14:30", "23:00")]
    # сегодня — не раньше «сейчас + 10 мин»
    late = ap.windows({}, PREFS, at(0, 20, 3), days=1)
    assert ap.from_slot(late[0].start, origin).strftime("%H:%M") == "20:15"


def _check_plan(res, tasks, prefs):
    by = {t.key: t for t in tasks}
    spans = sorted((datetime.fromisoformat(i["start"]), datetime.fromisoformat(i["end"])) for i in res["items"])
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "дела налезают друг на друга"
    for i in res["items"]:
        t = by[i["key"]]
        if t.due:
            assert datetime.fromisoformat(i["end"]) <= t.due
        if t.opens:
            assert datetime.fromisoformat(i["start"]) >= t.opens
    for day, mins in res["load"].items():
        assert mins <= prefs["max_day_min"], day


def test_solve_respects_deadlines_overlap_and_daily_cap():
    wins = ap.windows({}, PREFS, NOW, days=ap.HORIZON_DAYS)
    tasks = [task(f"t{i}", 90, points=3, due=at(2 + i % 5, 23, 59), course="c") for i in range(8)]
    tasks.append(task("later", 60, points=2, opens=at(3, 12), due=at(9, 23, 59), course="c"))
    res = ap.solve(tasks, [ap.Course("c", "Предмет", 10, 40, "3")], wins, PREFS, NOW)
    assert res["ok"] and len(res["items"]) == len(tasks)
    _check_plan(res, tasks, PREFS)
    # не всё в первые дни: запас до срока и ровная нагрузка
    assert max(res["load"].values()) <= PREFS["max_day_min"] and len(res["load"]) >= 4


def test_solve_course_short_and_tk_rule():
    wins = ap.windows({}, PREFS, NOW, days=ap.HORIZON_DAYS)
    tasks = [task("a", points=5, due=at(4, 23, 59), course="c", tk=True),
             task("gone", points=30, due=at(0, 8, 30), course="c", tk=True)]      # срок уже почти прошёл — не влезает
    c = ap.Course("c", "Анализ данных", 20, 40, "3", attendance_left=6, tk_need=2)
    res = ap.solve(tasks, [c], wins, PREFS, NOW)
    out = res["courses"][0]
    assert [i["key"] for i in res["items"]] == ["a"] and res["unplanned"][0]["key"] == "gone"
    assert out["projected"] == 31 and out["short"] == 9 and out["tk_short"] == 1 and out["status"] == "risk"
    # цель уже набрана и работ хватает — «есть»
    done = ap.solve([], [ap.Course("d", "Готово", 45, 40, "3")], wins, PREFS, NOW)
    assert done["courses"][0]["status"] == "done" and done["items"] == []


def test_light_days_and_prefs():
    prefs = dict(PREFS, light_weekdays=[0], light_max_min=60, max_day_min=120)
    wins = ap.windows({}, prefs, NOW, days=ap.HORIZON_DAYS)
    tasks = [task(f"t{i}", 60, points=2, due=at(1, 23, 59)) for i in range(3)]
    res = ap.solve(tasks, [], wins, prefs, NOW)
    assert res["load"].get(NOW.date().isoformat(), 0) <= 60            # понедельник — лёгкий
    assert len(res["items"]) == 3


def test_what_if_skip_lecture():
    wins = ap.windows({}, PREFS, NOW, days=ap.HORIZON_DAYS)
    extra = task("extra", 60, points=4, due=at(10, 23, 59), course="c")
    c = ap.Course("c", "Анализ данных", 30, 40, "3", attendance_left=10)
    # без пропуска цели хватает посещений — «лишнюю» работу можно и не делать
    res = ap.what_if_skip([extra], [c], wins, PREFS, NOW, "c", 2.5)
    assert res["ok"] and res["lost"] == 2.5
    assert res["course"]["attendance_left"] == 7.5 and res["course"]["status"] != "risk"
    # пропуск, который не добрать, — риск
    tight = ap.Course("c", "Анализ данных", 30, 40, "3", attendance_left=10)
    res = ap.what_if_skip([], [tight], wins, PREFS, NOW, "c", 2.5)
    assert res["was"]["status"] != "risk" and res["course"]["status"] == "risk" and res["course"]["short"] == 2.5


def test_multipliers_learn_from_answers():
    import autopilot_data as ad
    log = [("sdo:1", "assign", 90, 180, ""), ("sdo:2", "assign", 90, 135, ""), ("sdo:3", "quiz", 30, 60, ""),
           ("dl:1", "deadline", 60, None, "")]
    m = ad.multipliers(log)
    assert m == {"assign": 1.75}                       # медиана 2 и 1,5; у теста — один ответ, мало
    assert ad.multipliers([("x", "quiz", 30, 300, ""), ("y", "quiz", 30, 600, "")]) == {"quiz": 3.0}   # не больше ×3


def test_assign_page_time_limit_and_quiz_close():
    from sdo_grades import parse_assign_page
    html = ("<div>Разрешено попыток: 5</div><div>Ограничение по времени: 30 мин.</div>"
            "<div>Тест будет закрыт: среда, 15 октября 2026, 23:59</div><div>Проходная оценка: 3,0 из 6,0</div>")
    p = parse_assign_page(html)
    assert p["time_limit"] == 30 and p["due"] == "среда, 15 октября 2026, 23:59" and p["pass"] == 3.0
    assert parse_assign_page("<p>Ограничение по времени: 1,5 час</p>")["time_limit"] == 90


@pytest.fixture
def sdo_stub(monkeypatch):
    """СДО одного студента: предмет с двумя работами ТК (тест с лимитом
    времени и задание), посещения впереди; расписание — одна пара в день."""
    import attendance
    import schedule_parser
    import sdo_accounts
    import sdo_grades

    async def overview(user_id, cookie, fresh=False):
        return {"courses": [{"id": 7}]}

    async def detail(user_id, cookie, course_id):
        return {"id": 7, "title": "Анализ данных", "name": "Анализ данных [I.26-27]", "score": 22.0,
                "pass_share": 0.75, "marks": [{"at": 40, "label": "3"}, {"at": 60, "label": "4"}],
                "works": [
                    {"cmid": 11, "name": "Тест 2", "module": "quiz", "status": "todo", "max": 6, "time_limit": 30,
                     "due": "среда, 7 октября 2026, 23:59", "opens": "", "url": "https://sdo/mod/quiz/view.php?id=11"},
                    {"cmid": 12, "name": "ПЗ 4", "module": "assign", "status": "todo", "max": 8,
                     "due": "четверг, 15 октября 2026, 23:59", "opens": "", "url": "https://sdo/mod/assign/view.php?id=12"},
                    {"cmid": 13, "name": "ПЗ 1", "module": "assign", "status": "ok", "max": 8},
                    {"cmid": 14, "name": "ПЗ 2", "module": "assign", "status": "ok", "max": 8}]}

    async def for_course(user_id, course, manual=None):
        return {"ok": True, "can_get": 7.5, "unit": 2.5,
                "lectures": [{"date": "2026-10-08", "status": "future"}, {"date": "2026-10-01", "status": "ok"}]}

    async def raw():
        return b""

    def lessons(raw_, day):
        return [{"start_iso": datetime(day.year, day.month, day.day, 10, 40, tzinfo=MSK).isoformat(),
                 "end_iso": datetime(day.year, day.month, day.day, 12, 10, tzinfo=MSK).isoformat(), "kind": "лекция"}]

    async def cookie_for(user_id):
        return "cookie"

    monkeypatch.setattr(sdo_grades, "overview", overview)
    monkeypatch.setattr(sdo_grades, "course_detail", detail)
    monkeypatch.setattr(attendance, "for_course", for_course)
    monkeypatch.setattr(schedule_parser, "fetch_schedule_raw", raw)
    monkeypatch.setattr(schedule_parser, "lessons_for_date", lessons)
    monkeypatch.setattr(sdo_accounts, "cookie_for", cookie_for)


@pytest.mark.asyncio
async def test_gather_builds_tasks(db, sdo_stub):
    import autopilot_data as ad
    sdo_dup = await db.add_deadline("ПЗ 4 · Анализ данных", "https://sdo/mod/assign/view.php?id=12", "2026-10-15",
                                    due_time="23:59", created_by=0, external_id="sdo:900")
    sdo_other = await db.add_deadline("Эссе · Анализ данных", "https://sdo/mod/assign/view.php?id=55", "2026-10-09",
                                      due_time="18:00", created_by=0, external_id="sdo:901")
    mine = await db.add_deadline("Английский", "Выучить слова", "2026-10-06", None, 222)
    far = await db.add_deadline("Курсовая", "Сдать", "2026-12-20", None, 222)
    data = await ad.gather(222, "cookie", NOW)
    keys = {t.key: t for t in data["tasks"]}
    assert data["sdo"] == "ok" and set(keys) == {"sdo:11", "sdo:12", f"dl:{sdo_other}", f"dl:{mine}"}
    assert f"dl:{sdo_dup}" not in keys and f"dl:{far}" not in keys      # дубль работы ТК и дальше горизонта — нет
    assert keys["sdo:11"].minutes == 30 and keys["sdo:11"].kind == "quiz"   # лимит теста из СДО
    assert keys["sdo:11"].due == datetime(2026, 10, 7, 23, 59, tzinfo=MSK)
    assert keys[f"dl:{mine}"].title == "Выучить слова" and keys[f"dl:{mine}"].subject == "Английский"
    c = data["courses"][0]
    assert (c.score, c.goal, c.goal_label, c.attendance_left, c.tk_need) == (22.0, 40.0, "3", 7.5, 1)
    assert data["lectures"]["7"] == [{"date": "2026-10-08", "value": 2.5}]
    assert data["busy"][NOW.date()][0][0].hour == 10

    # сделал + сколько заняло: дело уходит, оценка учится (×2 после двух ответов)
    await ad.log_done(222, "sdo:12", "assign", 90, 180)
    await ad.log_done(222, "dl:1", "assign", 60, 120)
    await ad.set_prefs(222, {"goals": {"7": "4"}, "max_day_min": 120})
    data = await ad.gather(222, "cookie", NOW)
    keys = {t.key: t for t in data["tasks"]}
    assert "sdo:12" not in keys and data["courses"][0].goal == 60 and data["prefs"]["max_day_min"] == 120
    assert ad.multipliers(await ad._log(222)) == {"assign": 2.0}


@pytest.mark.asyncio
async def test_plan_api(db, sdo_stub, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    from webapp.routes import plan
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(plan, "_now", lambda: NOW)
    plan._cache.clear()
    mine = await db.add_deadline("Английский", "Выучить слова", "2026-10-06", None, 222)
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}

    r = c.get("/api/plan", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ok"] and p["sdo"] == "ok" and {i["key"] for i in p["items"]} == {"sdo:11", "sdo:12", f"dl:{mine}"}
    assert len(p["days"]) == 7 and p["days"][0]["cap"] == 180 and p["courses"][0]["marks"] == ["3", "4"]
    assert all(not ("10:30" < i["start"][11:16] < "12:20") for i in p["items"])   # не на паре
    assert c.get("/api/plan", headers=h).json()["updated"] == p["updated"]          # кэш

    r = c.post("/api/plan/whatif", headers=h, json={"course": "7", "date": "2026-10-08"})
    assert r.status_code == 200 and r.json()["lost"] == 2.5 and r.json()["date"] == "2026-10-08"
    assert c.post("/api/plan/whatif", headers=h, json={"course": "99"}).status_code == 404

    assert c.post("/api/plan/prefs", headers=h, json={"day_end": "25:00"}).status_code == 400
    assert c.post("/api/plan/prefs", headers=h, json={"day_start": "23:00"}).status_code == 400   # позже конца дня
    r = c.post("/api/plan/prefs", headers=h, json={"day_end": "21:00", "light_weekdays": [5, 6]})
    assert r.status_code == 200 and r.json()["prefs"]["day_end"] == "21:00"
    p = c.get("/api/plan", headers=h).json()
    assert p["prefs"]["day_end"] == "21:00" and all(i["end"][11:16] <= "21:00" for i in p["items"])

    r = c.post("/api/plan/done", headers=h, json={"key": f"dl:{mine}", "kind": "deadline", "planned": 60, "minutes": 45})
    assert r.status_code == 200
    assert await db.is_deadline_done(mine, 222)                              # галочка и в «Дедлайнах»
    assert f"dl:{mine}" not in {i["key"] for i in c.get("/api/plan", headers=h).json()["items"]}
    assert c.post("/api/plan/done", headers=h, json={"key": "rm -rf"}).status_code == 400


def test_stats_counts_plan():
    import stats
    assert stats.kind_for("GET", "/api/plan") == "plan" and stats.kind_for("POST", "/api/plan/done") == "plan_done"
    assert stats.kind_for("POST", "/api/plan/prefs") is None
    assert any(k == "plan" for k, *_ in stats.SCREENS)
