"""Рейтинг по опыту (xp.py), ники (nick_filter.py), институты (institutes.py)."""
from datetime import date, timedelta

import pytest

import institutes
import legal_texts
import nick_filter
import xp

URL = "https://online-edu.mirea.ru/mod/assign/view.php?id={i}"


@pytest.fixture(autouse=True)
def _fresh():
    xp.forget()
    yield
    xp.forget()


def _day(shift=0):
    return (date.today() + timedelta(days=shift)).isoformat()


# ── ники ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nick", ["Мандарин", "Требую", "Хачатурян", "Сукачёв", "Колеблющийся", "Лохматый",
                                  "Жидкость", "Никита К.", "nikita_03", "Кот-учёный"])
def test_nick_ok(nick):
    assert nick_filter.problem(nick) is None


@pytest.mark.parametrize("nick", ["xу1ло", "Х.У.Й", "ЧМО", "f.u.c.k", "Ebanko", "admin", "Капибара",
                                  "ссууккаа", "Староста", "a", "x" * 30, "<script>", "123"])
def test_nick_blocked(nick):
    assert nick_filter.problem(nick)


@pytest.mark.parametrize("nick", ["Капибара на паре", "Сонная капибара", "Kapibara na pare", "Студент МИРЭА",
                                  "Робот Вертер"])
def test_nick_with_service_word_ok(nick):
    """Слово «капибара» или «МИРЭА» в обычном нике — можно (робот 18.10)."""
    assert nick_filter.problem(nick) is None


@pytest.mark.parametrize("nick", ["Капибара", "капибара мирэа", "Капибара бот", "Kapibara bot", "МИРЭА",
                                  "РТУ МИРЭА", "Админ", "Поддержка", "Поддержка Капибары", "Официальная капибара",
                                  "Support", "Moderator"])
def test_nick_like_service_blocked(nick):
    """Выдаёт себя за сервис, МИРЭА или поддержку — нельзя."""
    assert nick_filter.problem(nick) == "такой ник похож на официальный — придумай другой"


def test_default_nick():
    assert nick_filter.default("Никита Курасов") == "Никита К."
    assert nick_filter.default("Егор") == "Егор"
    assert nick_filter.default("") == "Студент"


# ── институты ────────────────────────────────────────────────────────────────

def test_institute_by_prefix():
    assert institutes.of("УИБО-03-24") == "ИТУ"
    assert institutes.of("ИКБО-01-23") == "ИИТ"
    assert institutes.of("БСБО-05-22") == "ИКБ"
    assert institutes.of("Колледж 1") == ""
    rows = institutes.table(["УИБО-03-24", "УИБО-01-24", "ХББО-02-25", "что-то"])
    assert {r["prefix"]: (r["institute"], r["groups"]) for r in rows} == {"УИБО": ("ИТУ", 2), "ХББО": ("ИТХТ", 1)}


# ── опыт ─────────────────────────────────────────────────────────────────────

async def _person(db, uid, name, group_id=None):
    from database.groups import set_user_group
    await db.upsert_user(uid, f"u{uid}", name)
    if group_id is not None:
        await set_user_group(uid, group_id)


@pytest.mark.asyncio
async def test_xp_parts_only_verified(db):
    import sdo_done
    await _person(db, 1, "Анна Иванова")
    # баллы: берётся последняя точка по предмету
    await db.save_score_points(1, _day(-3), {10: 20, 11: 5})
    await db.save_score_points(1, _day(-1), {10: 30})
    # сдача через СДО за неделю до срока — SUBMIT + EARLY; галочка от руки — ничего
    a = await db.add_deadline("Практика 1", URL.format(i=1), _day(7), None, 0, external_id="sdo:1")
    b = await db.add_deadline("Практика 2", URL.format(i=2), _day(7), None, 0, external_id="sdo:2")
    assert await sdo_done.mark(1, [1]) == 1
    await db.mark_deadline_done(b, 1)
    # файлы: свои — да, из СДО — нет
    await db.add_file("Лекция 1", "Анализ", "f1", "l1.pdf", 1)
    await db.add_file("Лекция 2", "Анализ", "f2", "l2.pdf", 1, source="sdo:9")
    parts = (await xp._collect())[1]
    assert parts == {"brs": 35, "submit": xp.SUBMIT, "early": xp.EARLY, "ach": 0, "file": xp.FILE,
                     "total": 35 + xp.SUBMIT + xp.EARLY + xp.FILE}
    assert await db.is_deadline_done(a, 1)


@pytest.mark.asyncio
async def test_ach_xp_by_rank(db, monkeypatch):
    """Опыт за ачивку — по её рангу (Никита 18.10); создателю ачивки открыты
    все сразу, поэтому в опыт не идут."""
    import sys
    import types

    import config
    from database._conn import connect
    fake = types.ModuleType("achievements")
    fake.RANKS = {"dawn": ["lesson"], "noon": ["submit"], "dusk": ["month"], "midnight": ["fri13"]}
    monkeypatch.setitem(sys.modules, "achievements", fake)
    monkeypatch.setattr(config, "STAROSTA_IDS", [7])
    await _person(db, 1, "Анна")
    await _person(db, 7, "Никита")
    async with connect() as c:
        await c.execute("CREATE TABLE achievements (user_id INTEGER, ach_id TEXT, at INTEGER)")
        for uid in (1, 7):
            for a in ("lesson", "submit", "month", "fri13", "new_one"):
                await c.execute("INSERT INTO achievements VALUES (?, ?, 0)", (uid, a))
        await c.commit()
    got = await xp._collect()
    r = xp.ACH_RANK
    assert got[1]["ach"] == r["dawn"] + r["noon"] + r["dusk"] + r["midnight"] + xp.ACH
    assert r["dawn"] < r["noon"] < r["dusk"] < r["midnight"]
    assert 7 not in got or got[7]["ach"] == 0


@pytest.mark.asyncio
async def test_sdo_upgrades_manual_mark(db):
    """Отметил от руки, потом СДО подтвердило — опыт за сдачу есть."""
    import sdo_done
    await _person(db, 1, "Анна")
    did = await db.add_deadline("Практика 1", URL.format(i=5), _day(5), None, 0, external_id="sdo:5")
    await db.mark_deadline_done(did, 1)
    assert (await xp._collect()).get(1, {}).get("submit", 0) == 0
    await sdo_done.mark(1, [5])
    xp.forget()
    assert (await xp._collect())[1]["submit"] == xp.SUBMIT
    await db.mark_deadline_done(did, 1)                        # повторная галочка «via» не стирает
    assert (await xp._collect())[1]["submit"] == xp.SUBMIT


@pytest.mark.asyncio
async def test_groups_ranked_with_min_people(db):
    from database.groups import home, upsert_group
    await upsert_group(501, "УИБО-01-24")
    await upsert_group(502, "ИКБО-02-24")
    for uid, gid, pts in [(1, None, 10), (2, None, 10), (3, None, 10),          # своя: 30, трое
                          (4, 501, 50), (5, 501, 50), (6, 501, 50),           # 150, трое
                          (7, 502, 500), (8, 502, 0)]:                         # один с опытом — вне рейтинга
        await _person(db, uid, f"Имя{uid} Ф", gid)
        if pts:
            await db.save_score_points(uid, _day(-1), {1: pts})
    data = await xp.for_user(1, home())
    g = data["group"]
    assert (g["xp"], g["people"], g["need"], g["place"], g["place_inst"], g["institute"]) == (30, 3, 0, 2, 2, "ИТУ")
    assert g["institute_name"] == "Институт технологий управления"
    assert [r["name"] for r in data["institute_top"]] == ["УИБО-01-24", "УИБО-03-24"]
    assert [r["name"] for r in data["university_top"]] == ["УИБО-01-24", "УИБО-03-24"]
    assert data["university_top"][1]["mine"] is True
    other = await xp.for_user(7, 502)
    assert other["group"]["place"] is None and other["group"]["need"] == 2


@pytest.mark.asyncio
async def test_blocked_not_counted(db, monkeypatch):
    """Ждёт удаления или без согласия (privacy.blocked) — не виден в группе и
    не считается в опыте группы."""
    import privacy
    from database.groups import home

    async def blocked(uid):
        return uid == 4
    monkeypatch.setattr(privacy, "blocked", blocked)
    for uid in (1, 2, 3, 4):
        await _person(db, uid, f"Имя{uid} Ф", None)
        await db.save_score_points(uid, _day(-1), {1: 10})
    data = await xp.board()
    assert 4 not in data["people"] and set(data["people"]) == {1, 2, 3}
    g = (await xp.for_user(1, home()))["group"]
    assert (g["xp"], g["people"]) == (30, 3)


@pytest.mark.asyncio
async def test_people_only_with_consent(db):
    from database.groups import home
    for uid in (1, 2, 3):
        await _person(db, uid, f"Имя{uid} Фамилия")
        await db.save_score_points(uid, _day(-1), {1: uid * 10})
    await xp.save(2, show=True)
    await xp.save(3, nick="Тихий кот")
    data = await xp.for_user(1, home())
    assert data["people"] == [{"nick": "Имя2 Ф.", "xp": 20, "me": False, "hidden": False},
                              {"nick": "Имя1 Ф.", "xp": 10, "me": True, "hidden": True}]
    assert data["me"]["show"] is False and data["me"]["custom_nick"] is False
    assert (await xp.for_user(3, home()))["me"]["nick"] == "Тихий кот"


@pytest.mark.asyncio
async def test_nick_save_review_and_reset(db):
    await _person(db, 1, "Анна Иванова")
    with pytest.raises(ValueError):
        await xp.save(1, nick="хуйло")
    assert (await xp.save(1, nick="  Тихий   кот ", show=True)) == {"nick": "Тихий кот", "show": True,
                                                                     "locked": False, "show_all": False,
                                                                     "alias": None}
    assert [r["nick"] for r in await xp.unreviewed()] == ["Тихий кот"]
    await xp.mark_reviewed([1])
    assert await xp.unreviewed() == []
    await xp.save(1, show=False)                                # согласие без смены ника — не на проверку
    assert await xp.unreviewed() == []
    await xp.reset_nick(1)
    p = await xp.profile(1)
    assert p["nick"] is None and p["locked"] and p["show"] is False
    with pytest.raises(ValueError):
        await xp.save(1, nick="Другой")
    assert (await xp.save(1, nick=""))["nick"] is None          # вернуть имя можно всегда


@pytest.mark.asyncio
async def test_show_is_separate_consent(db):
    """Ревью 152-ФЗ: «Показывать меня группе» — отдельное согласие в consents."""
    from database.privacy import get_consents
    await _person(db, 1, "Анна")
    await xp.save(1, nick="Тихий кот")
    assert [c for c in await get_consents(1) if c["kind"] == "rating"] == []
    await xp.save(1, show=True)
    assert [(c["kind"], c["version"]) for c in await get_consents(1) if c["kind"] == "rating"] == [("rating", "1")]
    await xp.save(1, show=False)
    assert [c for c in await get_consents(1) if c["kind"] == "rating"] == []


def test_legal_texts_mention_rating():
    import legal_texts
    text = str(legal_texts.__dict__)
    assert "Показывать меня группе" in text and "из баллов СДО и сдач" in text
    assert "Показывать меня всем" in text


@pytest.mark.asyncio
async def test_history_by_weeks_and_parts(db):
    """Опыт группы по неделям — из тех же отметок по их датам; части — сумма людей."""
    from database.groups import home
    for uid in (1, 2, 3):
        await _person(db, uid, f"Имя{uid} Ф")
        await db.save_score_points(uid, _day(-20), {1: 5})
        await db.save_score_points(uid, _day(-1), {1: 10})
    data = await xp.for_user(1, home())
    hist = data["group"]["history"]
    assert len(hist) == xp.WEEKS
    assert hist[-1]["xp"] == 30 and hist[-1]["place"] == 1 and hist[-1]["place_inst"] == 1
    assert hist[0]["xp"] == 0 and hist[0]["place"] is None            # 7 недель назад опыта не было
    assert 15 in [h["xp"] for h in hist]                               # три недели назад — первые баллы
    assert [h["xp"] for h in hist] == sorted(h["xp"] for h in hist)
    assert data["group"]["parts"] == {"brs": 30, "submit": 0, "early": 0, "ach": 0, "file": 0}
    assert data["group"]["id"] == home() and data["university_top"][0]["id"] == home()


@pytest.mark.asyncio
async def test_group_view_people_by_consent(db):
    """Своя группа видит «группе» и «всем», чужая — только «всем»."""
    from database.groups import home, upsert_group
    await upsert_group(501, "УИБО-01-24")
    for uid in (1, 2, 3, 4):
        await _person(db, uid, f"Имя{uid} Ф", 501)
        await db.save_score_points(uid, _day(-1), {1: uid * 10})
    await _person(db, 9, "Гость Г")                                    # из своей группы бота
    await xp.save(2, show=True)
    await xp.save(3, show_all=True, consent=legal_texts.RATING_ALL_VERSION)
    await xp.save(4, nick="Тихий кот", show_all=True, consent=legal_texts.RATING_ALL_VERSION)
    capy = f"Капибара №{(await xp.profile(3))['alias']}"
    other = await xp.group_view(9, home(), 501)
    # чужим — только свой ник или «Капибара №…», не «Имя Ф.» (ревью 152-ФЗ)
    assert [p["nick"] for p in other["people_list"]] == ["Тихий кот", capy] and other["hidden"] == 2
    assert other["member"] is False and other["name"] == "УИБО-01-24" and len(other["history"]) == xp.WEEKS
    mine = await xp.group_view(1, 501, 501)
    assert [(p["nick"], p["hidden"]) for p in mine["people_list"]] == [
        ("Тихий кот", False), (capy, False), ("Имя2 Ф.", False), ("Имя1 Ф.", True)]
    assert mine["hidden"] == 0 and mine["member"] is True
    assert await xp.group_view(1, 501, 777) is None
    # не участник своей группы (viewer 0) не видит тех, кто разрешил только группе
    data = await xp.for_user(1, 501, member=False)
    assert [p["nick"] for p in data["people"]] == ["Тихий кот", capy, "Имя1 Ф."]


@pytest.mark.asyncio
async def test_show_all_is_own_consent(db, monkeypatch):
    """«Показывать меня всем» — только с галочкой отдельного согласия (ст. 10.1),
    его версия — в consents; новая версия текста выключает показ до нового
    согласия; номер «Капибара №…» случайный и не меняется."""
    from database.privacy import get_consents
    from database.groups import home
    await _person(db, 1, "Анна")
    with pytest.raises(ValueError, match="отдельное согласие"):
        await xp.save(1, show_all=True)
    with pytest.raises(ValueError):
        await xp.save(1, show_all=True, consent="0")
    p = await xp.save(1, show_all=True, consent=legal_texts.RATING_ALL_VERSION)
    assert p["show_all"] is True and xp.ALIAS_MIN <= p["alias"] <= xp.ALIAS_MAX
    got = {c["kind"]: c["version"] for c in await get_consents(1)}
    assert got.get("rating_all") == legal_texts.RATING_ALL_VERSION and "rating" not in got
    assert (await xp.for_user(1, home()))["me"]["public_nick"] == f"Капибара №{p['alias']}"
    ver = legal_texts.RATING_ALL_VERSION
    monkeypatch.setattr(legal_texts, "RATING_ALL_VERSION", "2")
    assert (await xp.profile(1))["show_all"] is False                  # текст поменялся — спросить заново
    monkeypatch.setattr(legal_texts, "RATING_ALL_VERSION", ver)
    await xp.save(1, show_all=False)
    assert "rating_all" not in [c["kind"] for c in await get_consents(1)]
    again = await xp.save(1, show_all=True, consent=legal_texts.RATING_ALL_VERSION)
    assert again["alias"] == p["alias"]


def test_rating_all_text():
    d = legal_texts.doc("rating_all")
    assert d["version"] == legal_texts.RATING_ALL_VERSION
    text = d["lead"] + " ".join(str(b) for sec in d["sections"] for b in sec["blocks"])
    for need in ("всем пользователям", "Капибара №", "10.1", "Показывать меня всем"):
        assert need in text
    # на листе — общая формулировка и что, где и кому; оператор — в полном тексте по ссылке
    short = d["lead_short"] + " ".join(str(b) for sec in d["sections"] if sec.get("short") for b in sec["blocks"])
    assert [sec["title"] for sec in d["sections"] if sec.get("short")] == ["Что показываем", "Где и кому"]
    assert "все пользователи" in short and "самозанят" not in short and "самозанят" not in d["lead_short"]


# ── API и бот ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_rating(db, monkeypatch):
    from fastapi.testclient import TestClient
    import ratelimit
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setattr(ratelimit, "allow", lambda *a, **k: True)
    await _person(db, 222, "Alice")
    c, h = TestClient(server.app), {"X-Telegram-Init-Data": _make_init_data()}
    r = c.get("/api/rating", headers=h)
    assert r.status_code == 200
    assert r.json()["me"]["nick"] == "Alice" and r.json()["rules"]["submit"] == xp.SUBMIT
    bad = c.put("/api/rating/me", headers=h, json={"nick": "сука"})
    assert bad.status_code == 400 and "мата" in bad.json()["detail"]
    ok = c.put("/api/rating/me", headers=h, json={"nick": "Алиса", "show": True})
    assert ok.status_code == 200 and ok.json() == {"nick": "Алиса", "show": True, "locked": False, "show_all": False,
                                                   "alias": None}
    assert c.get("/api/rating", headers=h).json()["people"][0]["nick"] == "Алиса"
    gid = c.get("/api/rating", headers=h).json()["group"]["id"]
    assert c.get(f"/api/rating/group/{gid}", headers=h).json()["people_list"][0]["nick"] == "Алиса"
    assert c.get("/api/rating/group/777", headers=h).status_code == 404
    assert c.put("/api/rating/me", headers=h, json={"show_all": True}).status_code == 400   # без галочки
    on = c.put("/api/rating/me", headers=h, json={"show_all": True, "consent": legal_texts.RATING_ALL_VERSION})
    assert on.json()["show_all"] is True
    assert c.get("/api/legal/rating_all").json()["version"] == legal_texts.RATING_ALL_VERSION


@pytest.mark.asyncio
async def test_bot_nicks_reset(db, monkeypatch):
    from handlers import rating
    await _person(db, 5, "Петя Петров")
    await xp.save(5, nick="Плохой ник")
    sent = []

    class Msg:
        from_user = type("U", (), {"id": 0})()

        async def answer(self, text, **kw):
            sent.append((text, kw.get("reply_markup")))

    monkeypatch.setattr(rating, "is_starosta", lambda uid: True)
    await rating.cmd_nicks(Msg())
    assert "Плохой ник" in sent[0][0]
    data = sent[0][1].inline_keyboard[0][0].callback_data
    assert data == "nick:reset:5" and await xp.unreviewed() == []

    answers = []

    class Cb:
        from_user = type("U", (), {"id": 0})()
        message = None

        async def answer(self, text, **kw):
            answers.append(text)

    cb = Cb()
    cb.data = data
    await rating.nick_reset(cb)
    assert answers and (await xp.profile(5))["locked"]
