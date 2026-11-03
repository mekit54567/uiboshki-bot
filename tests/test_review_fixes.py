"""Ревью кода 04.10 (семь независимых ревьюеров) — на каждую подтверждённую
находку по СДО, базе, бэкапу, каналу и серверу свой тест."""
import asyncio
import contextlib
import gzip
import os
from datetime import date
from pathlib import Path

import httpx
import pytest

from kapibara.features.schedule import attendance
from kapibara.features.sdo import grades as sdo_grades


# ── СДО: разбор журнала и страниц заданий ───────────────────────────────────

def test_draft_is_not_submitted():
    page = sdo_grades.parse_assign_page(
        "<table><tr><th>Состояние ответа на задание</th><td>Черновик (не отправлено)</td></tr></table>")
    assert page["submitted"] is False and page["draft"] is True
    w = {"grade": None, "passed": None}
    assert sdo_grades.work_status(w, page) == "todo"                      # было «wait» — «сдано, ждёт оценки»
    sent = sdo_grades.parse_assign_page(
        "<table><tr><th>Состояние ответа на задание</th><td>Отправлено для оценивания</td></tr></table>")
    assert sent["submitted"] is True and sdo_grades.work_status(w, sent) == "wait"


def _report(rows: str) -> str:
    def item(name, grade, cls, cmid):
        return (f'<tr><th class="level3 item column-itemname"><div><span class="d-block text-uppercase small dimmed_text">'
                f'Задание</span><a class="gradeitemheader" href="https://x/mod/assign/view.php?id={cmid}">{name}</a></div></th>'
                f'<td class="level3 itemcenter column-grade {cls}">{grade}</td><td class="level3 column-range">0–5</td></tr>')
    return ('<table class="generaltable user-grade"><tbody>'
            '<tr><th class="level1 category column-itemname" colspan="3"><div>Предмет_Экзамен [I.26-27]</div></th></tr>'
            '<tr><th class="level2 category column-itemname" colspan="3"><div>Текущий контроль</div></th></tr>'
            + item("ПР 1", "Зачтено", "gradepass", 1) + item("ПР 2", "Не зачтено", "", 2) + item("ПР 3", "5,00", "gradepass", 3)
            + '</tbody></table>')


def test_scale_grades_count_as_graded():
    s = sdo_grades.summarize(sdo_grades.parse_report(_report("")), "Предмет_Экзамен")
    by = {w["name"]: w for w in s["works"]}
    assert by["ПР 1"]["graded"] and by["ПР 1"]["passed"] is True and by["ПР 1"]["grade"] is None
    assert by["ПР 2"]["graded"] and by["ПР 2"]["passed"] is False
    assert s["works_passed"] == 2 and s["works_graded"] == 3
    assert sdo_grades.work_status(by["ПР 1"], {"submitted": True}) == "ok"   # было «ждёт оценки»
    assert sdo_grades.work_status(by["ПР 2"], {}) == "low"


def test_diff_credit_has_marks():
    s = sdo_grades.summarize({"items": [], "categories": []}, "Экономика_Дифференцированный зачет [I.26-27]")
    assert s["kind"] == "exam" and [m["label"] for m in s["marks"]] == ["3", "4", "5"]
    assert sdo_grades.summarize({"items": [], "categories": []}, "Право_Зачет")["kind"] == "credit"


def test_overview_fresh_drops_course_screens(monkeypatch):
    async def no_courses(client):
        return []
    monkeypatch.setattr(sdo_grades, "this_semester_courses", no_courses)
    sdo_grades._cache.clear()
    sdo_grades._store(("detail", 5, 7), {"old": True})
    sdo_grades._store(("detail", 6, 7), {"other": True})
    sdo_grades._cache[("all", 5)] = (0, {})                                   # протух — пойдёт в СДО

    async def run():
        with contextlib.suppress(Exception):                                  # сети нет — важно, что кэш сброшен
            await sdo_grades.overview(5, "cookie", fresh=True)
    asyncio.run(run())
    assert ("detail", 5, 7) not in sdo_grades._cache and ("detail", 6, 7) in sdo_grades._cache


# ── Посещения ───────────────────────────────────────────────────────────────

def test_attendance_one_decimal_display():
    # 16 лекций по 1,25: три посещения = 3,75, СДО показывает «3,8»
    assert attendance.solve(3.8, 20, 16, 3) == [(3, 0)]
    assert attendance.solve(4.4, 20, 9, 3) == [(2, 0)]


def test_first_zero_snapshot_keeps_recent_lecture_waiting():
    lectures = [date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21)]
    out = attendance.build(0, 20, lectures, [], date(2026, 9, 16))
    st = {x["date"]: x["status"] for x in out["lectures"]}
    assert st["2026-09-14"] == "wait"                                         # было «Н» на второй день
    none = attendance.build(None, 20, lectures, [], date(2026, 9, 30))     # «-» в журнале: ещё ничего не ставили
    assert {x["status"] for x in none["lectures"]} == {"wait"}


# ── Дедлайны: удалённые не воскресают, напоминания едут со сроком ───────────

@pytest.mark.asyncio
async def test_deleted_sdo_deadline_stays_deleted(db, monkeypatch):
    from kapibara.features.sdo import parser as sdo_parser
    item = {"external_id": "sdo:6", "title": "Практика 2", "course": "Анализ данных [I.26-27]",
            "subject": "Практика 2 (Анализ данных)", "description": "", "due_date": "2026-10-20", "due_time": "23:59"}

    async def items():
        return [dict(item)]
    monkeypatch.setattr(sdo_parser, "fetch_deadline_items", items)
    monkeypatch.setattr(sdo_parser, "not_this_semester", lambda i, s: False)
    assert (await sdo_parser.sync_deadlines())["added"] == 1
    d = await db.get_deadline_by_external_id("sdo:6")
    await db.add_deadline_reminder(222, d["id"], "2026-10-19 23:59")
    await db.delete_deadline(d["id"])
    assert (await sdo_parser.sync_deadlines())["added"] == 0                 # было: вернулся без галочек
    assert await db.get_deadline_by_external_id("sdo:6") is None
    from database._conn import connect
    async with connect() as c:
        assert (await (await c.execute("SELECT COUNT(*) FROM deadline_reminders")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_moved_deadline_moves_reminders(db):
    did = await db.add_deadline("Практика", "", "2026-10-20", "23:59", 0, external_id="sdo:7")
    await db.add_deadline_reminder(222, did, "2026-10-19 23:59")              # «за день»
    await db.update_deadline_due(did, "Практика", "2026-10-12", "23:59")
    assert await db.get_user_deadline_reminders(222) == {did: ["2026-10-11 23:59"]}


@pytest.mark.asyncio
async def test_personal_deadline_of_starosta_is_personal(db, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.server as server
    from tests.conftest import STAROSTA_ID
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    c = TestClient(server.app)
    star = {"X-Telegram-Init-Data": _make_init_data(user={"id": STAROSTA_ID, "first_name": "S"})}
    r = c.post("/api/deadlines", headers=star, json={"subject": "Сходить к врачу", "due_date": "2026-10-20"})
    assert r.status_code == 200, r.text
    assert all(d["subject"] != "Сходить к врачу" for d in await db.get_active_deadlines(222))
    assert any(d["subject"] == "Сходить к врачу" for d in await db.get_active_deadlines(STAROSTA_ID))
    shared = await db.add_deadline("Общий", "", "2026-10-21", None, STAROSTA_ID)     # из бота — общий, как раньше
    assert any(d["id"] == shared for d in await db.get_active_deadlines(222))


# ── Входы в СДО: ключ и проверка ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bad_crypt_key_does_not_log_everyone_out(db, monkeypatch):
    from kapibara.features.sdo import accounts as sdo_accounts
    enc = sdo_accounts.encrypt("abcdef0123456789abcdef0123")
    await db.save_sdo_session(222, enc)
    monkeypatch.setenv("SDO_CRYPT_KEY", "my-secret-phrase")                 # не ключ Fernet
    assert sdo_accounts.decrypt(enc) == "abcdef0123456789abcdef0123"         # старый ключ работает
    assert sdo_accounts.encrypt("x") and sdo_accounts.key_source() == "bot_token"
    monkeypatch.delenv("SDO_CRYPT_KEY")

    sent = []

    class Bot:
        async def send_message(self, *a, **kw):
            sent.append(a)
    await db.save_sdo_session(333, "мусор, а не шифр")
    await sdo_accounts._check_one(await db.get_sdo_session(333), Bot())
    assert (await db.get_sdo_session(333))["status"] == "ok" and not sent   # не «вход устарел» всем


@pytest.mark.asyncio
async def test_check_does_not_expire_freshly_connected(db, monkeypatch):
    from kapibara.features.sdo import accounts as sdo_accounts
    old = sdo_accounts.encrypt("old0123456789abcdef0123456")
    await db.save_sdo_session(222, old)

    async def check(cookie):
        await db.save_sdo_session(222, sdo_accounts.encrypt("new0123456789abcdef0123456"))   # подключил новый
        return False
    monkeypatch.setattr(sdo_accounts, "check", check)
    await sdo_accounts._check_one(await db.get_sdo_session(222))
    row = await db.get_sdo_session(222)
    assert row["status"] == "ok" and sdo_accounts.decrypt(row["cookie_enc"]).startswith("new")


@pytest.mark.asyncio
async def test_download_redirect_loop_means_expired():
    from kapibara.features.sdo import files as sdo_files
    from kapibara.features.sdo.parser import SdoSessionExpired

    def loop(request):
        return httpx.Response(302, headers={"Location": str(request.url)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(loop), follow_redirects=True) as client:
        with pytest.raises(SdoSessionExpired):
            await sdo_files.download(client, sdo_files.SdoFile(course_id=1, subject="", title="x", category="",
                                                               source="sdo:1", url="https://x/pluginfile.php/1/a.pdf"))


# ── Одновременные записи ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parallel_writes_keep_both(db, monkeypatch):
    from kapibara.features.content import channel_posts
    from kapibara.features.sdo import goal as sdo_goal
    await asyncio.gather(channel_posts.mark_published("01-a", [1]), channel_posts.mark_published("02-b", [2]))
    assert set(await channel_posts.published()) == {"01-a", "02-b"}
    await asyncio.gather(sdo_goal.set_goal(7, 1, "4"), sdo_goal.set_goal(7, 2, "5"))
    assert await sdo_goal.get_goals(7) == {"1": "4", "2": "5"}

    from kapibara.features.notifications import prefs as notify_prefs
    import webapp.server as server
    from tests.test_webapp_auth import BOT_TOKEN, _make_init_data
    monkeypatch.setattr(server.deps, "BOT_TOKEN", BOT_TOKEN)
    await db.upsert_user(222, "a", "A")
    h = {"X-Telegram-Init-Data": _make_init_data()}
    real_get = db.get_user

    async def slow_get(uid):                                                  # чтение — с паузой, как под нагрузкой
        u = await real_get(uid)
        await asyncio.sleep(0.05)
        return u
    import database.users
    monkeypatch.setattr(database, "get_user", slow_get)
    monkeypatch.setattr(database.users, "get_user", slow_get)
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://t") as ac:
        await asyncio.gather(ac.post("/api/notify", headers=h, json={"prefs": {"weather": False}}),
                             ac.post("/api/notify", headers=h, json={"prefs": {"weekly": False}}))
    prefs = notify_prefs.merge((await real_get(222))["notify"])
    assert prefs["weather"] is False and prefs["weekly"] is False



@pytest.mark.asyncio
async def test_channel_double_tap_publishes_once(db, tmp_path, monkeypatch):
    from kapibara.features.content import channel_posts
    from kapibara.core import config
    from handlers import channel
    from tests.test_channel_posts import _post
    _post(tmp_path, "01-start", "<b>Как всё началось</b>")
    monkeypatch.setattr(channel_posts, "POSTS_DIR", tmp_path)
    monkeypatch.setattr(config, "CHANNEL_ID", "@ch")
    sends = []

    async def slow_send(bot, chat, post, base=""):
        sends.append(post["slug"])
        await asyncio.sleep(0.05)
        return [len(sends)]
    monkeypatch.setattr(channel_posts, "send_post", slow_send)

    class Msg:
        chat = type("C", (), {"id": 1})()

        async def answer(self, *a, **kw):
            pass

        async def edit_reply_markup(self, *a, **kw):
            pass

    class Cb:
        from_user = type("U", (), {"id": int(os.environ["STAROSTA_ID"])})()
        data = "chan:pub:01-start"
        message = Msg()
        bot = None

        async def answer(self, *a, **kw):
            pass
    await asyncio.gather(channel.channel_button(Cb()), channel.channel_button(Cb()))
    assert sends == ["01-start"]


# ── Бэкап и сервер ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restore_drops_search_index_and_limits_unpack(db, monkeypatch):
    from kapibara.ops import backup
    from kapibara.features.ai import semantic_index
    Path(semantic_index.index_path()).write_bytes(b"old index")
    data, _ = await backup.make_backup()
    tmp, info = await asyncio.to_thread(backup.inspect_backup, data)
    await backup.apply_backup(tmp)
    assert not Path(semantic_index.index_path()).exists()                   # старые куски не подклеятся к чужим id
    monkeypatch.setattr(backup, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(backup.RestoreError):
        backup.inspect_backup(gzip.compress(b"SQLite format 3\x00" + b"\x00" * 5000))
    assert await backup.keep_local_copy() == db.DATABASE_PATH + ".before-restore"


def test_chunked_body_over_limit_is_413(monkeypatch):
    import webapp.server as server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "BODY_LIMIT_DEFAULT", 1000)
    read = []

    def body():
        for _ in range(50):
            read.append(1)
            yield b"x" * 100
    r = TestClient(server.app).post("/api/notify", content=body(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413

